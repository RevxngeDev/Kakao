"""Enforces D-003: no module OUTSIDE src/kakao/audio/ imports a capture/OS-specific
library. This is the automated guarantee that only the audio layer is OS-bound.
"""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "kakao"
AUDIO = SRC / "audio"

# Capture / Windows-specific libraries that must stay inside kakao.audio.
FORBIDDEN = {
    "soundcard",
    "soxr",
    "comtypes",
    "pycaw",
    "winreg",
    "pyaudiowpatch",
    "sounddevice",
}


def _top_level_imports(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_no_os_specific_imports_outside_audio():
    offenders = []
    for py in SRC.rglob("*.py"):
        if AUDIO in py.parents:
            continue
        for module in _top_level_imports(py):
            if module in FORBIDDEN:
                offenders.append(f"{py.relative_to(SRC)} imports {module}")
    assert not offenders, "OS-specific imports leaked outside kakao.audio: " + str(offenders)
