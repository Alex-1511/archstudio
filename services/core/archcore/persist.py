"""Atomic project files with two distinct integrity levels, plus strict import.

* checksum (always): SHA-256 of the project data. Detects accidental corruption and truncation ONLY.
  Anyone who edits the file can recompute it, so it is NOT tamper protection.
* hmac (optional, key=...): HMAC-SHA256 over the whole payload. Detects deliberate modification by
  anyone who does not hold the key. Key management is the caller's responsibility; cloud projects
  should additionally enforce integrity server-side.
* Import is hostile-input safe: size cap, NaN/Infinity literals rejected at parse time, exact
  structure required, and every model invariant re-checked (a correct checksum does not make
  invalid geometry valid)."""
from __future__ import annotations
import hashlib, hmac, json, os, tempfile
from .bim import Project

MAX_BYTES = 64 * 1024 * 1024


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _checksum(project_dict: dict) -> str:
    return hashlib.sha256(_canon(project_dict)).hexdigest()


def _mac(key: bytes, schema: int, project_dict: dict) -> str:
    return hmac.new(key, _canon({"schema_version": schema, "project": project_dict}), hashlib.sha256).hexdigest()


def _reject_constant(name: str):
    raise ValueError(f"non-finite JSON literal {name} is not allowed")


def save_project(project: Project, path: str, key: bytes | None = None) -> None:
    project.validate()  # never persist an invalid model
    d = project.to_dict()
    payload = {"schema_version": Project.SCHEMA, "checksum": _checksum(d), "project": d}
    if key is not None:
        payload["hmac"] = _mac(key, Project.SCHEMA, d)
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=1, allow_nan=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)  # atomic on POSIX and Windows
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_project(path: str, key: bytes | None = None, max_bytes: int = MAX_BYTES) -> Project:
    if os.path.getsize(path) > max_bytes:
        raise ValueError(f"project file exceeds {max_bytes} bytes")
    with open(path) as f:
        payload = json.load(f, parse_constant=_reject_constant)  # JSONDecodeError is a ValueError
    if not isinstance(payload, dict) or "project" not in payload or not isinstance(payload["project"], dict):
        raise ValueError("not an ArchStudio project file")
    if payload.get("schema_version") != Project.SCHEMA:
        raise ValueError(f"unsupported schema version {payload.get('schema_version')}")
    if payload.get("checksum") != _checksum(payload["project"]):
        raise ValueError("project file failed checksum verification (corrupt or modified)")
    if key is not None:
        mac = payload.get("hmac")
        if not isinstance(mac, str) or not hmac.compare_digest(mac, _mac(key, payload["schema_version"], payload["project"])):
            raise ValueError("project file failed signature verification (missing, wrong key, or tampered)")
    return Project.from_dict(payload["project"])
