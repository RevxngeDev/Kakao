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

# `ctypes` itself is portable, but these attributes are Windows-only. Files listed
# here are the DELIBERATE exceptions: each must guard the call with a
# `sys.platform` check, which the test below verifies. Adding a file here is a
# conscious decision to widen the OS-specific surface (D-003) — not a formality.
WIN32_ATTRS = {"windll", "WinDLL", "oledll"}
WIN32_ALLOWLIST = {
    "overlay.py",  # WS_EX_TRANSPARENT click-through; guarded by sys.platform
    "hotkey.py",   # RegisterHotKey + WM_HOTKEY; guarded by sys.platform
}


def _top_level_imports(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def _win32_ctypes_uses(path: pathlib.Path):
    """Yield `ctypes.<win32-only attr>` accesses (e.g. ctypes.windll)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in WIN32_ATTRS
            and isinstance(node.value, ast.Name)
            and node.value.id == "ctypes"
        ):
            yield f"ctypes.{node.attr}"


def _modules_outside_audio():
    for py in SRC.rglob("*.py"):
        if AUDIO not in py.parents:
            yield py


def test_no_os_specific_imports_outside_audio():
    offenders = []
    for py in _modules_outside_audio():
        for module in _top_level_imports(py):
            if module in FORBIDDEN:
                offenders.append(f"{py.relative_to(SRC)} imports {module}")
    assert not offenders, "OS-specific imports leaked outside kakao.audio: " + str(offenders)


def test_win32_ctypes_only_in_allowlisted_files():
    """`ctypes` passes the import check, so catch the Windows-only attributes too."""
    offenders = []
    for py in _modules_outside_audio():
        uses = set(_win32_ctypes_uses(py))
        if uses and py.name not in WIN32_ALLOWLIST:
            offenders.append(f"{py.relative_to(SRC)} uses {sorted(uses)}")
    assert not offenders, (
        "Windows-only ctypes usage outside kakao.audio and outside the allowlist: "
        + str(offenders)
    )


def test_the_win32_detector_actually_detects():
    """Guards against a vacuously-green test: the detector must find the one known
    Win32 usage (overlay.py's click-through). If this ever fails, the check above
    is passing because it sees nothing, not because the code is clean."""
    overlay = SRC / "overlay.py"
    assert "ctypes.windll" in set(_win32_ctypes_uses(overlay))


def test_allowlisted_win32_usage_is_platform_guarded():
    """An allowlisted file must still guard its Win32 calls with sys.platform."""
    for py in _modules_outside_audio():
        if py.name not in WIN32_ALLOWLIST or not set(_win32_ctypes_uses(py)):
            continue
        source = py.read_text(encoding="utf-8")
        assert "sys.platform" in source, (
            f"{py.relative_to(SRC)} is allowlisted for Win32 ctypes but has no "
            "sys.platform guard — it would crash on macOS/Linux."
        )
