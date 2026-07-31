"""Kakao app entry point (Phase 4): live subtitles on a transparent overlay.

  uv run python -m kakao.app           # normal: click-through overlay + live pipeline
  uv run python -m kakao.app --edit     # position/resize the overlay, close to save
  uv run python -m kakao.app --smoke    # construct + render briefly, then quit (test)

Never opens the microphone (D-006). Source language pinned to Spanish (D-017).
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

    # The normal overlay is click-through and has no close button, so Ctrl+C in the
    # terminal is the way to stop it. Qt's event loop otherwise swallows SIGINT, so
    # route it to app.quit() and keep a heartbeat timer alive so Python can run the
    # handler (the interpreter only processes signals between bytecode, not while
    # blocked in the C++ event loop).
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    heartbeat = QTimer()
    heartbeat.start(200)
    heartbeat.timeout.connect(lambda: None)

    settings = Settings()
    overlay = Overlay(settings, edit=edit)
    overlay.show()

    if smoke:
        overlay.show_subtitle("Kakao overlay — español → English", 0.0)
        QTimer.singleShot(1000, app.quit)
        return app.exec()

    pipeline = None
    if not edit:
        # imported here so --edit / --smoke don't spin up the ASR/audio stack
        from kakao.audio.wasapi import WasapiLoopbackSource
        from kakao.pipeline import Pipeline

        source = WasapiLoopbackSource()
        pipeline = Pipeline(source, overlay.show_subtitle, model="medium", language="es")
        pipeline.start()

    try:
        return app.exec()
    finally:
        if pipeline is not None:
            pipeline.stop()


if __name__ == "__main__":
    raise SystemExit(main())
