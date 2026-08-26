"""The subtitle overlay (Phase 4, DD-03 = PySide6).

A borderless, transparent, always-on-top window that does NOT steal focus and, in
normal mode, is click-through (clicks reach the video behind it). Text is rendered
with a black outline + white fill so it stays legible over any background — colour
alone is not enough. Position/size persist via kakao.settings.

Normal mode: click-through overlay driven by the pipeline.
Edit mode (`--edit`): not click-through, draggable + corner-resize, saves geometry
on close — this is how position/size are adjusted.

Subtitle text arrives from the ASR worker thread; `show_subtitle` emits a Qt signal
so the actual widget update happens on the GUI thread (Qt requires that).

Click-through is Qt-native (WA_TransparentForMouseEvents) plus, on Windows, the
WS_EX_TRANSPARENT extended style so clicks pass to OTHER apps (the video). That
Win32 bit is guarded by platform — the overlay stays otherwise portable (macOS
gets its own bit later).
"""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from kakao import config
from kakao.settings import Settings


def _set_windows_click_through(hwnd: int, enable: bool = True) -> None:
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    user32 = ctypes.windll.user32
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if enable:
        ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT
    else:
        ex = (ex | WS_EX_LAYERED) & ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)


class Overlay(QWidget):
    """Transparent always-on-top subtitle window."""

    subtitle_received = Signal(str)  # marshals text from the ASR thread to the GUI thread

    def __init__(self, settings: Settings, edit: bool = False) -> None:
        super().__init__()
        self._settings = settings
        self._edit = edit
        self._standalone_edit = edit  # True only for the `--edit` launch (Esc closes)
        self._text = ""
        self._font_family = settings.get("overlay_font_family", config.FONT_FAMILY)
        self._font_size = int(settings.get("overlay_font_size", config.FONT_SIZE))
        self._drag_from = None
        self._start_geo = None
        self._resizing = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        if edit:
            self.setFocusPolicy(Qt.StrongFocus)  # needs focus for arrow-nudge / Esc
        else:
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setFocusPolicy(Qt.NoFocus)

        geo = settings.get("overlay_geometry")
        if not (isinstance(geo, (list, tuple)) and len(geo) == 4):
            geo = config.DEFAULT_GEOMETRY
        self.setGeometry(*geo)

        self.subtitle_received.connect(self._set_text)
        self._clear = QTimer(self)
        self._clear.setSingleShot(True)
        self._clear.timeout.connect(self._do_clear)

        # Holding an arrow key would otherwise rewrite settings.json on every
        # repeat; coalesce the writes into one after the movement settles.
        self._geo_save = QTimer(self)
        self._geo_save.setSingleShot(True)
        self._geo_save.setInterval(400)
        self._geo_save.timeout.connect(self._save_geometry)

    # -- pipeline entry point (thread-safe) --------------------------------
    def show_subtitle(self, text: str, lag: float = 0.0) -> None:
        self.subtitle_received.emit(text)

    def _set_text(self, text: str) -> None:
        self._text = text
        self._clear.start(config.SUBTITLE_HOLD_MS)
        self.update()

    def _do_clear(self) -> None:
        self._text = ""
        self.update()

    # -- window lifecycle --------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._edit:
            self.activateWindow()  # take focus so arrow-nudge / Esc work
            self.raise_()
        elif sys.platform == "win32":
            _set_windows_click_through(int(self.winId()))

    def closeEvent(self, event) -> None:
        self._save_geometry()
        super().closeEvent(event)

    def _save_geometry(self) -> None:
        self._geo_save.stop()  # drop any pending debounced save; this one covers it
        g = self.geometry()
        self._settings.set("overlay_geometry", [g.x(), g.y(), g.width(), g.height()])

    def set_edit(self, on: bool) -> None:
        """Toggle edit mode live (used by the tray 'edit position' action)."""
        self._edit = on
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not on)
        self.setFocusPolicy(Qt.StrongFocus if on else Qt.NoFocus)
        if sys.platform == "win32":
            _set_windows_click_through(int(self.winId()), enable=not on)
        if on:
            self.activateWindow()
            self.raise_()
        else:
            self._save_geometry()
        self.update()

    def set_font_size(self, size: int) -> None:
        self._font_size = int(size)
        self.update()

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._edit:
            painter.fillRect(self.rect(), QColor(0, 120, 215, 60))
            painter.setPen(QColor(255, 255, 255, 200))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        text = self._text or (
            "modo edición — arrastra o usa las flechas para mover · esquina para "
            "redimensionar · Esc para terminar (se guarda solo)"
            if self._edit else ""
        )
        if not text:
            return

        font = QFont(self._font_family, self._font_size, QFont.Bold)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        margin = 18
        max_w = max(1, self.width() - 2 * margin)
        lines = self._wrap(text, metrics, max_w)
        line_h = metrics.height()
        max_lines = max(1, (self.height() - 2 * margin) // line_h)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]  # keep the most recent lines; never clip the top

        path = QPainterPath()
        y = self.height() - margin - line_h * len(lines) + metrics.ascent()
        for line in lines:
            x = (self.width() - metrics.horizontalAdvance(line)) / 2
            path.addText(x, y, font, line)
            y += line_h

        painter.strokePath(path, QPen(QColor(0, 0, 0, 235), 4))
        painter.fillPath(path, QColor(255, 255, 255))

    @staticmethod
    def _wrap(text: str, metrics: QFontMetrics, max_w: int) -> list[str]:
        """Break `text` into lines that fit `max_w`. Never emits empty lines —
        one would silently eat a line of vertical space."""
        lines: list[str] = []
        for para in text.split("\n"):
            current = ""
            for word in para.split():
                trial = f"{current} {word}" if current else word
                if not current or metrics.horizontalAdvance(trial) <= max_w:
                    current = trial
                else:
                    lines.append(current)
                    current = word
            if current:
                lines.append(current)
        return lines

    # -- edit-mode move / resize -------------------------------------------
    def mousePressEvent(self, event) -> None:
        if not self._edit:
            return
        self._drag_from = event.globalPosition().toPoint()
        self._start_geo = self.geometry()
        pos = event.position().toPoint()
        self._resizing = pos.x() > self.width() - 28 and pos.y() > self.height() - 28

    def mouseMoveEvent(self, event) -> None:
        if not self._edit or self._drag_from is None:
            return
        delta = event.globalPosition().toPoint() - self._drag_from
        g = self._start_geo
        if self._resizing:
            self.setGeometry(
                g.x(), g.y(),
                max(240, g.width() + delta.x()), max(80, g.height() + delta.y()),
            )
        else:
            self.move(g.x() + delta.x(), g.y() + delta.y())

    def mouseReleaseEvent(self, event) -> None:
        self._drag_from = None
        if self._edit:
            self._save_geometry()  # persist now; don't rely on close firing (frameless, no X)

    def keyPressEvent(self, event) -> None:
        if not self._edit:
            return
        if event.key() == Qt.Key_Escape:
            if self._standalone_edit:
                self.close()      # `--edit` launch: Esc closes the app
            else:
                self.set_edit(False)  # live edit (tray): Esc returns to overlay
            return
        step = 10
        moves = {
            Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0),
            Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step),
        }
        if event.key() in moves:
            dx, dy = moves[event.key()]
            self.move(self.x() + dx, self.y() + dy)
            self._geo_save.start()  # debounced; see _geo_save
