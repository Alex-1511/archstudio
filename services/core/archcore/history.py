"""Undo/redo, named versions and version diff. Every mutation goes through History.apply,
so a failed command can never leave the project half-modified."""
from __future__ import annotations
import copy
from typing import Callable, Any
from .bim import Project


class History:
    def __init__(self, project: Project, revision: int = 0):
        self.project = project
        self.revision = revision  # increments on every apply/undo/redo; used for optimistic concurrency
        self._undo: list[tuple[str, dict]] = []
        self._redo: list[tuple[str, dict]] = []
        self.versions: dict[str, dict] = {}
        self.log: list[str] = []

    def _restore(self, snap: dict) -> None:
        self.project.restore(copy.deepcopy(snap))  # in place: object identity is preserved

    def apply(self, label: str, fn: Callable[[Project], Any]) -> Any:
        before = self.project.to_dict()
        try:
            result = fn(self.project)
            self.project.validate()  # catches invalid values set by direct attribute mutation
        except Exception:
            self._restore(before)  # atomic: roll back partial changes
            raise
        self._undo.append((label, before))
        self._redo.clear()
        self.log.append(label)
        self.revision += 1
        return result

    def undo(self) -> str | None:
        if not self._undo:
            return None
        label, snap = self._undo.pop()
        self._redo.append((label, self.project.to_dict()))
        self._restore(snap)
        self.revision += 1
        return label

    def redo(self) -> str | None:
        if not self._redo:
            return None
        label, snap = self._redo.pop()
        self._undo.append((label, self.project.to_dict()))
        self._restore(snap)
        self.revision += 1
        return label

    def save_version(self, name: str) -> None:
        if name in self.versions:
            raise ValueError(f"version {name!r} exists; versions are immutable")
        self.versions[name] = copy.deepcopy(self.project.to_dict())

    def diff(self, a: str, b: str) -> dict:
        """Data diff between two saved versions, by element id."""
        out = {}
        for key in ("levels", "walls", "rooms"):
            ea = {e["id"]: e for e in self.versions[a][key]}
            eb = {e["id"]: e for e in self.versions[b][key]}
            out[key] = {
                "added": sorted(set(eb) - set(ea)),
                "removed": sorted(set(ea) - set(eb)),
                "changed": sorted(i for i in set(ea) & set(eb) if ea[i] != eb[i]),
            }
        return out
