"""Minimal JSON-Schema subset validator (type incl. unions, enum, required, properties,
additionalProperties:false, items, minItems/maxItems, $ref to #/$defs). Stdlib only."""
import json, os

_CONTRACT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "contracts", "api.v1.schema.json")
DEFS = json.load(open(_CONTRACT))["$defs"]
_T = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(v, t):
    if t == "number": return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "integer": return isinstance(v, int) and not isinstance(v, bool)
    return isinstance(v, _T[t])


def check(value, schema, path="$"):
    """Returns a list of violation strings (empty = valid)."""
    if "$ref" in schema:
        return check(value, DEFS[schema["$ref"].split("/")[-1]], path)
    errs = []
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: {value!r} not in {schema['enum']}"]
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is(value, t) for t in types):
            return [f"{path}: expected {types}, got {type(value).__name__}"]
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value: errs.append(f"{path}: missing {k!r}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errs += [f"{path}: unexpected key {k!r}" for k in value if k not in props]
        for k, sub in props.items():
            if k in value: errs += check(value[k], sub, f"{path}.{k}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0): errs.append(f"{path}: too few items")
        if len(value) > schema.get("maxItems", 10**9): errs.append(f"{path}: too many items")
        if "items" in schema:
            for i, x in enumerate(value): errs += check(x, schema["items"], f"{path}[{i}]")
    return errs
