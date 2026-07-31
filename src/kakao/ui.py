"""Phase 5 control UI: a system-tray icon plus a settings window (D-020).

Tray for day-to-day use (Start/Stop, Edit position, Quit); the settings window
opens only to change device/model/font. Errors surface as tray notifications in
plain Spanish (user-facing text is Spanish, D-007). Callbacks that arrive from
worker threads are marshalled to the GUI thread via Qt signals.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QMenu, QPushButton, QSpinBox, QSystemTrayIcon,
)

from kakao.audio.wasapi import WasapiLoopbackSource, list_output_devices
from kakao.overlay import Overlay
from kakao.pipeline import SYNC_PRESETS, Pipeline
from kakao.settings import Settings

_MODELS = ["medium", "small"]  # D-009: chosen + fallback
_SYNC = [("Equilibrado", "balanced"), ("Más rápido", "fast"), ("Más preciso", "accurate")]


def _humanize(err: str) -> str:
    low = err.lower()
    if any(k in low for k in ("out of memory", "cuda", "cublas", "cudnn", "cudart")):
        return "El modelo no cabe en la GPU o falló CUDA. Prueba el modelo 'small' en Ajustes."
    if any(k in low for k in ("device", "speaker", "loopback", "wasapi")):
        return "Problema con el dispositivo de audio. Revisa la salida de sonido."
    return f"Error: {err}"


def _icon(color: str = "#3aa0ff") -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(QColor("#0a0a0a"))
    painter.drawEllipse(8, 8, 48, 48)
    painter.end()
    return QIcon(pix)


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kakao — Ajustes")
        self._settings = settings
        form = QFormLayout(self)

        self._device = QComboBox()
        for label, dev_id in list_output_devices():
            self._device.addItem(label, dev_id)
        idx = self._device.findData(settings.get("device_id"))
        self._device.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("Dispositivo de salida:", self._device)

        self._model = QComboBox()
        self._model.addItems(_MODELS)
        self._model.setCurrentText(settings.get("model", "medium"))
        form.addRow("Modelo:", self._model)

        self._sync = QComboBox()
        for label, key in _SYNC:
            self._sync.addItem(label, key)
        sync_idx = self._sync.findData(settings.get("sync", "balanced"))
        self._sync.setCurrentIndex(sync_idx if sync_idx >= 0 else 0)
        form.addRow("Sincronización:", self._sync)

        self._font = QSpinBox()
        self._font.setRange(12, 72)
        self._font.setValue(int(settings.get("overlay_font_size", 28)))
        form.addRow("Tamaño de letra:", self._font)

        save = QPushButton("Guardar")
        save.clicked.connect(self._save)
        form.addRow(save)

    def _save(self) -> None:
        self._settings.set("device_id", self._device.currentData())
        self._settings.set("model", self._model.currentText())
        self._settings.set("sync", self._sync.currentData())
        self._settings.set("overlay_font_size", self._font.value())
        self.accept()


class TrayController(QObject):
    """Owns the overlay, the tray icon and the pipeline lifecycle."""

    _error_sig = Signal(str)
    _degraded_sig = Signal(str)

    def __init__(self, app, settings: Settings) -> None:
        super().__init__()
        self._app = app
        self._settings = settings
        self._pipeline = None
        self._last_dropped = 0

        self._overlay = Overlay(settings, edit=False)
        self._overlay.show()

        self._tray = QSystemTrayIcon(_icon(), self)
        self._tray.setToolTip("Kakao")
        menu = QMenu()
        self._act_toggle = QAction("Iniciar", self)
        self._act_toggle.triggered.connect(self.toggle)
        act_edit = QAction("Editar posición", self)
        act_edit.triggered.connect(self.edit_position)
        act_settings = QAction("Ajustes…", self)
        act_settings.triggered.connect(self.open_settings)
        act_quit = QAction("Salir", self)
        act_quit.triggered.connect(self.quit)
        for act in (self._act_toggle, act_edit, act_settings):
            menu.addAction(act)
        menu.addSeparator()
        menu.addAction(act_quit)
        self._tray.setContextMenu(menu)
        self._tray.show()
        self._tray.showMessage("Kakao", "Listo. Clic derecho en el icono para iniciar.", _icon(), 4000)

        self._error_sig.connect(self._show_error)
        self._degraded_sig.connect(lambda m: self._tray.showMessage("Kakao — audio", m, _icon(), 4000))
        self._health = QTimer(self)
        self._health.timeout.connect(self._check_health)
        self._health.start(5000)

    # -- tray actions ------------------------------------------------------
    def toggle(self) -> None:
        self.stop() if self._pipeline is not None else self.start()

    def start(self) -> None:
        try:
            model = self._settings.get("model", "medium")
            preset = SYNC_PRESETS.get(self._settings.get("sync", "balanced"), SYNC_PRESETS["balanced"])
            source = WasapiLoopbackSource(device_id=self._settings.get("device_id"))
            source.on_degraded = self._degraded_sig.emit
            self._pipeline = Pipeline(
                source, self._overlay.show_subtitle, model=model, language="es",
                on_error=self._error_sig.emit, **preset,
            )
            self._pipeline.start()
            self._last_dropped = 0
            self._act_toggle.setText("Detener")
            self._tray.setIcon(_icon("#33cc66"))
            self._tray.showMessage("Kakao", f"Traduciendo (modelo {model}).", _icon(), 3000)
        except Exception as exc:
            self._pipeline = None
            self._show_error(_humanize(str(exc)))

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None
        self._overlay.show_subtitle("")
        self._act_toggle.setText("Iniciar")
        self._tray.setIcon(_icon("#3aa0ff"))

    def edit_position(self) -> None:
        self._overlay.set_edit(True)
        self._tray.showMessage("Kakao", "Arrastra o usa las flechas; Esc para terminar.", _icon(), 3000)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self._settings)
        if dialog.exec():
            self._overlay.set_font_size(int(self._settings.get("overlay_font_size", 28)))
            if self._pipeline is not None:
                self._tray.showMessage(
                    "Kakao", "Detén e inicia para aplicar el modelo/dispositivo.", _icon(), 4000
                )

    def quit(self) -> None:
        self.stop()
        self._app.quit()

    # -- notifications (marshalled to the GUI thread by the signals) -------
    def _show_error(self, msg: str) -> None:
        self._tray.showMessage("Kakao — error", _humanize(msg), _icon("#e05555"), 6000)

    def _check_health(self) -> None:
        if self._pipeline is None:
            return
        dropped = self._pipeline.dropped
        if dropped - self._last_dropped >= 3:
            self._tray.showMessage("Kakao", "Va con retraso; se descartan subtítulos.", _icon(), 4000)
        self._last_dropped = dropped
