"""Minimal persisted settings (Phase 4 needs a persistent overlay position/size).

A tiny JSON store under the user config dir. Phase 5 expands this into the full
settings surface; for now it just holds overlay geometry and font size. Portable.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any, Optional


def _default_path() -> pathlib.Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return pathlib.Path(base) / "Kakao" / "settings.json"


class Settings:
    """Dict-like settings backed by a JSON file; writes on every `set`."""

    def __init__(self, path: Optional[os.PathLike] = None) -> None:
        self._path = pathlib.Path(path) if path is not None else _default_path()
        self._data: dict[str, Any] = self._read()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._write()

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
