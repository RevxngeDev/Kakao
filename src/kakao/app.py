"""Kakao app entry point.

  uv run python -m kakao.app            # the app: tray icon + overlay (Phase 5)
  uv run python -m kakao.app --edit      # just place/size the overlay, close to save
  uv run python -m kakao.app --smoke     # construct UI briefly, then quit (test)

Never opens the microphone (D-006). Source language pinned to Spanish (D-017).
Start/stop, device and model are controlled from the tray icon and its settings
window.
"""
from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from kakao.overlay import Overlay
from kakao.settings import Settings


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    edit = "--edit" in argv
    smoke = "--smoke" in argv

    app = QApplication(sys.argv)

    # Qt's event loop swallows SIGINT; route Ctrl+C to a clean quit and keep a
    # heartbeat alive so Python can run the handler between event-loop iterations.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    heartbeat = QTimer()
    heartbeat.start(200)
    heartbeat.timeout.connect(lambda: None)

    settings = Settings()

    if edit:  # standalone positioning tool
        overlay = Overlay(settings, edit=True)
        overlay.show()
        return app.exec()

    # Tray app: closing dialogs/windows must not quit — only the tray "Salir" does.
    app.setQuitOnLastWindowClosed(False)
    from kakao.ui import TrayController

    controller = TrayController(app, settings)  # noqa: F841 (kept alive by reference)
    if smoke:
        QTimer.singleShot(1500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
