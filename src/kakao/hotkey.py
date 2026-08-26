"""System-wide hotkey for Iniciar/Detener.

Qt shortcuts only fire when the application has focus, and Kakao deliberately never
takes focus (the overlay is click-through, the tray has no window). So the hotkey
must be registered with the OS itself.

On Windows that is `RegisterHotKey` plus a native event filter that watches for
WM_HOTKEY. This is a **deliberate second exception** to D-003 ("only kakao.audio is
OS-specific"): the Win32 calls live here, guarded by `sys.platform`, and the file is
listed in `tests/test_portability.py`'s WIN32_ALLOWLIST. Every other platform gets a
no-op until a native implementation exists, so nothing crashes.
"""
from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable

if sys.platform == "win32":
    from ctypes import wintypes  # NOT pulled in by `import ctypes` alone

from PySide6.QtCore import QAbstractNativeEventFilter

# Win32 modifier flags (winuser.h)
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000  # don't repeat while the keys are held down
_WM_HOTKEY = 0x0312
_HOTKEY_ID = 1


class GlobalHotkey(QAbstractNativeEventFilter):
    """Registers one system-wide hotkey and calls `on_pressed` when it fires.

    `register()` returns False when the combination is unavailable (another app
    already owns it) or the platform is unsupported — callers should tell the user
    rather than silently losing the shortcut.
    """

    def __init__(
        self,
        on_pressed: Callable[[], None],
        *,
        modifiers: int,
        virtual_key: int,
    ) -> None:
        super().__init__()
        self._on_pressed = on_pressed
        self._modifiers = modifiers | MOD_NOREPEAT
        self._vk = virtual_key
        self._hwnd = 0
        self._registered = False

    @property
    def registered(self) -> bool:
        return self._registered

    def register(self, app, hwnd: int) -> bool:
        """Register the hotkey against `hwnd` and start filtering native events."""
        if sys.platform != "win32":
            return False
        self._hwnd = int(hwnd)
        ok = bool(
            ctypes.windll.user32.RegisterHotKey(
                self._hwnd, _HOTKEY_ID, self._modifiers, self._vk
            )
        )
        if ok:
            app.installNativeEventFilter(self)
            self._registered = True
        return ok

    def unregister(self, app) -> None:
        if not self._registered:
            return
        app.removeNativeEventFilter(self)
        ctypes.windll.user32.UnregisterHotKey(self._hwnd, _HOTKEY_ID)
        self._registered = False

    # -- QAbstractNativeEventFilter ---------------------------------------
    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt signature)
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                self._on_pressed()
                return True, 0
        return False, 0
