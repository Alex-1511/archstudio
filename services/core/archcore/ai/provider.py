"""Provider abstraction. Gemini is primary; others plug in behind the same interface.
The API key is read server-side from the environment and never leaves this process."""
from __future__ import annotations
import json, os, re, urllib.request
from abc import ABC, abstractmethod
from ..tools import TOOLS


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str | None = None) -> str: ...


class FakeProvider(LLMProvider):
    """Deterministic provider for tests."""
    def __init__(self, *responses: str):
        self._r = list(responses)
        self.prompts: list[str] = []

    def generate(self, prompt, system=None):
        self.prompts.append(prompt)
        return self._r.pop(0)


class GeminiProvider(LLMProvider):
    """Gemini REST client. IMPLEMENTED BUT UNTESTED: no network or API key in the build sandbox."""
    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("GEMINI_MODEL")
        self._key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.model or not self._key:
            raise RuntimeError("set GEMINI_MODEL and GEMINI_API_KEY in the server environment")

    def generate(self, prompt, system=None):
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": self._key})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        return data["candidates"][0]["content"]["parts"][0]["text"]


def _schema_text() -> str:
    from ..tools import SCHEMAS
    return "; ".join(f"{n}({', '.join(list(r) + [k + '?' for k in o])})" for n, (r, o) in SCHEMAS.items())


SYSTEM = ("You are an architectural CAD planner. Reply ONLY with a JSON array of tool calls "
          '[{"tool": name, "args": {...}}]. Tools: ' + _schema_text() + ". Units are metres. "
          'Later calls may reference earlier results as "$0.id". Never invent a dimension the user did not give; '
          'if one is missing reply [{"tool": "ask_user", "args": {"question": "..."}}].')


def plan_tool_calls(provider: LLMProvider, request: str, context: str = "") -> list[dict]:
    """Ask the model for tool calls and validate names and argument schemas. Executes nothing.
    ("$N.key" references are checked at execution time, once earlier results exist.)"""
    from ..tools import validate_args, ToolError, _REF
    prompt = (f"Project context (JSON): {context}\n\n" if context else "") + request
    text = provider.generate(prompt, system=SYSTEM).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    calls = json.loads(text)
    if not isinstance(calls, list):
        raise ValueError("planner must return a JSON array")
    for c in calls:
        if not isinstance(c, dict) or "tool" not in c or not isinstance(c.get("args", {}), dict):
            raise ValueError(f"malformed tool call: {c!r}")
        if c["tool"] == "ask_user":
            if not isinstance(c["args"].get("question"), str):
                raise ValueError("ask_user needs a question")
            continue
        if c["tool"] not in TOOLS:
            raise ValueError(f"model requested unknown tool {c['tool']!r}")
        args = c.get("args", {})
        if not any(isinstance(v, str) and _REF.match(v) for v in json.dumps(args).split('"')):
            try:
                validate_args(c["tool"], args)
            except ToolError as e:
                raise ValueError(str(e)) from e
    return calls


def converse(provider: LLMProvider, history, request: str, ask=None, permissions=frozenset({"read"}), max_rounds: int = 3) -> dict:
    """Plan -> (clarify if the model asks) -> execute atomically. Nothing runs while a question is open."""
    from ..tools import apply_batch, apply_tool_call
    for _ in range(max_rounds):
        context = json.dumps(apply_tool_call(history, "inspect_project", {}, frozenset({"read"})))
        calls = plan_tool_calls(provider, request, context)
        questions = [c["args"]["question"] for c in calls if c["tool"] == "ask_user"]
        if not questions:
            return {"status": "done", "results": apply_batch(history, calls, permissions)}
        if ask is None:
            return {"status": "needs_clarification", "question": questions[0]}
        request += f"\nUser answer to '{questions[0]}': {ask(questions[0])}"
    return {"status": "needs_clarification", "question": "too many clarification rounds"}
