"""Minimal persisted settings (Phase 4 needs a persistent overlay position/size).

A tiny JSON store under the user config dir. Phase 5 expands this into the full
settings surface; for now it just holds overlay geometry and font size. Portable.
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
from typing import Any


def _default_path() -> pathlib.Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return pathlib.Path(base) / "Kakao" / "settings.json"


class Settings:
    """Dict-like settings backed by a JSON file; writes on every `set`."""

    def __init__(self, path: os.PathLike | None = None) -> None:
        self._path = pathlib.Path(path) if path is not None else _default_path()
        self._data: dict[str, Any] = self._read()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._write()

    def update(self, values: dict[str, Any]) -> None:
        """Set several keys with a SINGLE write (a dialog saving 4 fields is 1 write)."""
        self._data.update(values)
        self._write()

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except ValueError:
            # Corrupt file: keep it aside instead of silently discarding the user's
            # settings, then start clean. Should not happen now that writes are
            # atomic, but a half-written file from an older version may still exist.
            with contextlib.suppress(OSError):
                self._path.replace(self._path.with_suffix(".json.corrupt"))
            return {}

    def _write(self) -> None:
        """Write atomically: a crash mid-write must never truncate the settings."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)  # atomic on Windows and POSIX
