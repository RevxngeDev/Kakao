"""Phase 5 control UI: a system-tray icon plus a settings window (D-020).

Tray for day-to-day use (Start/Stop, Edit position, Quit); the settings window
opens only to change device/model/font. Errors surface as tray notifications in
plain Spanish (user-facing text is Spanish, D-007). Callbacks that arrive from
worker threads are marshalled to the GUI thread via Qt signals.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QMenu,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
)

from kakao import config
from kakao.audio.wasapi import WasapiLoopbackSource, list_output_devices
from kakao.hotkey import GlobalHotkey
from kakao.overlay import Overlay
from kakao.pipeline import Pipeline, preload_models
from kakao.settings import Settings


def _humanize(err: str) -> str:
    low = err.lower()
    if any(k in low for k in ("out of memory", "cuda", "cublas", "cudnn", "cudart")):
        return "El modelo no cabe en la GPU o falló CUDA. Prueba el modelo 'small' en Ajustes."
    if any(k in low for k in ("device", "speaker", "loopback", "wasapi")):
        return "Problema con el dispositivo de audio. Revisa la salida de sonido."
    return f"Error: {err}"


ICON_IDLE = "#3aa0ff"
ICON_RUNNING = "#33cc66"
ICON_ERROR = "#e05555"


def _icon(color: str = ICON_IDLE) -> QIcon:
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
        self._model.addItems(config.MODELS)
        self._model.setCurrentText(settings.get("model", config.MODEL))
        self._model.setToolTip(
            "small: el más rápido y ligero, menor calidad.\n"
            "medium: el equilibrio recomendado (por defecto).\n"
            "large-v3: usa ~1 GB más de VRAM y no siempre traduce mejor —\n"
            "pruébalo con tu contenido antes de dejarlo."
        )
        form.addRow("Modelo:", self._model)

        self._sync = QComboBox()
        for label, key in config.SYNC_LABELS:
            self._sync.addItem(label, key)
        sync_idx = self._sync.findData(settings.get("sync", config.SYNC))
        self._sync.setCurrentIndex(sync_idx if sync_idx >= 0 else 0)
        form.addRow("Sincronización:", self._sync)

        self._font = QSpinBox()
        self._font.setRange(12, 72)
        self._font.setValue(int(settings.get("overlay_font_size", config.FONT_SIZE)))
        form.addRow("Tamaño de letra:", self._font)

        save = QPushButton("Guardar")
        save.clicked.connect(self._save)
        form.addRow(save)

    def _save(self) -> None:
        self._settings.update({          # one write, not four
            "device_id": self._device.currentData(),
            "model": self._model.currentText(),
            "sync": self._sync.currentData(),
            "overlay_font_size": self._font.value(),
        })
        self.accept()


class TrayController(QObject):
    """Owns the overlay, the tray icon and the pipeline lifecycle."""

    _error_sig = Signal(str)
    _degraded_sig = Signal(str)
    _notify_sig = Signal(str)        # notification raised from a worker thread
    _started_sig = Signal(object)    # the started Pipeline, or None if it failed

    def __init__(self, app, settings: Settings, preload: bool = True) -> None:
        super().__init__()
        self._app = app
        self._settings = settings
        self._pipeline = None
        self._last_dropped = 0
        self._starting = False
        self._preloaded = threading.Event()

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

        self._hotkey = self._install_hotkey()
        hint = f" Atajo: {config.HOTKEY_LABEL}." if self._hotkey else ""
        self._notify(f"Listo. Clic derecho en el icono para iniciar.{hint}")

        self._error_sig.connect(self._show_error)
        self._degraded_sig.connect(lambda m: self._notify(m, title="Kakao — audio"))
        self._notify_sig.connect(self._notify)
        self._started_sig.connect(self._on_started)
        self._health = QTimer(self)
        self._health.timeout.connect(self._check_health)
        self._health.start(5000)

        if preload:
            # Load the model NOW, in the background: measured ~10 s the first time
            # (import faster_whisper 4.9 s + weights 5.3 s). Doing it while the user
            # sets up their video makes the first Iniciar instant (D-027).
            threading.Thread(target=self._preload, name="model-preload", daemon=True).start()
        else:
            self._preloaded.set()

    def _install_hotkey(self) -> GlobalHotkey | None:
        """Register the system-wide start/stop shortcut, if it is available."""
        if not config.HOTKEY_ENABLED:
            return None
        hotkey = GlobalHotkey(
            self.toggle,
            modifiers=config.HOTKEY_MODIFIERS,
            virtual_key=config.HOTKEY_VIRTUAL_KEY,
        )
        if hotkey.register(self._app, self._overlay.winId()):
            return hotkey
        # Another app owns the combination, or the platform has no implementation.
        # Say so rather than losing the shortcut silently.
        self._notify(
            f"No se pudo registrar el atajo {config.HOTKEY_LABEL} "
            "(otra aplicación lo está usando). Usa el menú del icono."
        )
        return None

    def _preload(self) -> None:
        try:
            self._notify_sig.emit("Preparando el modelo…")
            preload_models(self._settings.get("model", config.MODEL))
            self._notify_sig.emit("Listo para traducir.")
        except Exception as exc:  # surfaced, but the app stays usable
            self._error_sig.emit(str(exc))
        finally:
            self._preloaded.set()

    def _notify(
        self, msg: str, *, title: str = "Kakao", color: str = ICON_IDLE, ms: int = 4000
    ) -> None:
        self._tray.showMessage(title, msg, _icon(color), ms)

    # -- tray actions ------------------------------------------------------
    def toggle(self) -> None:
        if self._starting:
            return
        if self._pipeline is not None:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        """Start translating. Runs off the GUI thread so the UI never freezes."""
        if self._starting or self._pipeline is not None:
            return
        self._starting = True
        self._act_toggle.setEnabled(False)
        self._act_toggle.setText("Iniciando…")
        if not self._preloaded.is_set():
            self._notify("Terminando de preparar el modelo…", ms=3000)
        threading.Thread(target=self._start_worker, name="pipeline-start", daemon=True).start()

    def _start_worker(self) -> None:
        try:
            preset = config.SYNC_PRESETS.get(
                self._settings.get("sync", config.SYNC), config.SYNC_PRESETS[config.SYNC]
            )
            source = WasapiLoopbackSource(device_id=self._settings.get("device_id"))
            source.on_degraded = self._degraded_sig.emit
            pipeline = Pipeline(
                source, self._overlay.show_subtitle,
                model=self._settings.get("model", config.MODEL),
                on_error=self._error_sig.emit, **preset,
            )
            pipeline.start()  # blocks on the model load if the preload is still running
            self._started_sig.emit(pipeline)
        except Exception as exc:
            self._started_sig.emit(None)
            self._error_sig.emit(_humanize(str(exc)))

    def _on_started(self, pipeline) -> None:
        """Back on the GUI thread: adopt the pipeline and update the tray."""
        self._starting = False
        self._act_toggle.setEnabled(True)
        if pipeline is None:
            self._act_toggle.setText("Iniciar")
            return
        self._pipeline = pipeline
        self._last_dropped = 0
        self._act_toggle.setText("Detener")
        self._tray.setIcon(_icon(ICON_RUNNING))
        self._notify(f"Traduciendo (modelo {self._settings.get('model', config.MODEL)}).", ms=3000)

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None
        self._overlay.show_subtitle("")
        self._act_toggle.setText("Iniciar")
        self._tray.setIcon(_icon(ICON_IDLE))

    def edit_position(self) -> None:
        self._overlay.set_edit(True)
        self._notify("Arrastra o usa las flechas; Esc para terminar.", ms=3000)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self._settings)
        if dialog.exec():
            font = int(self._settings.get("overlay_font_size", config.FONT_SIZE))
            self._overlay.set_font_size(font)
            if self._pipeline is not None:
                self._notify("Detén e inicia para aplicar el modelo/dispositivo.")

    def quit(self) -> None:
        if self._hotkey is not None:
            self._hotkey.unregister(self._app)
        self.stop()
        self._app.quit()

    # -- notifications (marshalled to the GUI thread by the signals) -------
    def _show_error(self, msg: str) -> None:
        self._notify(_humanize(msg), title="Kakao — error", color=ICON_ERROR, ms=6000)

    def _check_health(self) -> None:
        if self._pipeline is None:
            return
        dropped = self._pipeline.dropped
        if dropped - self._last_dropped >= 3:
            self._notify("Va con retraso; se descartan subtítulos.")
        self._last_dropped = dropped
