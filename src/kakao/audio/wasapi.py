"""WASAPI loopback AudioSource — the ONLY OS-specific implementation (D-003).

Captures the system OUTPUT endpoint via WASAPI loopback (never the microphone,
D-006), downmixes to mono and requests SAMPLE_RATE so WASAPI shared-mode converts
the rate, so callers only ever see the normalized AudioFrame contract. Follows
default-device changes (e.g. plugging in headphones) by reopening the stream, and
flags Bluetooth hands-free degradation.

DD-02: the WASAPI binding is `soundcard` (see DECISIONS.md D-011).
"""
from __future__ import annotations

import threading

import numpy as np
import soundcard  # OS/capture-specific — must never be imported outside audio/

from kakao.audio.base import SAMPLE_RATE, AudioFrame, AudioSource, FrameCallback

_BLOCK = SAMPLE_RATE // 10  # 100 ms blocks
_DEGRADED_HINTS = ("hands-free", "hands free", "hfp", "headset")


class WasapiLoopbackSource(AudioSource):
    """System-audio capture via `soundcard` WASAPI loopback."""

    def __init__(self, block_frames: int = _BLOCK) -> None:
        self._block = block_frames
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._t = 0.0  # seconds of audio delivered so far (frame timestamps)
        self._reported_degraded: set[str] = set()

    # -- lifecycle ---------------------------------------------------------
    def start(self, on_frame: FrameCallback) -> None:
        if self._thread is not None:
            raise RuntimeError("AudioSource already started")
        self._stop.clear()
        self._t = 0.0
        self._thread = threading.Thread(
            target=self._run, args=(on_frame,), name="wasapi-loopback", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # -- worker ------------------------------------------------------------
    def _run(self, on_frame: FrameCallback) -> None:
        while not self._stop.is_set():
            speaker = soundcard.default_speaker()
            loopback = soundcard.get_microphone(speaker.id, include_loopback=True)
            self._check_degraded(speaker.name)
            device_id = speaker.id
            try:
                with loopback.recorder(samplerate=SAMPLE_RATE) as rec:
                    while not self._stop.is_set():
                        if soundcard.default_speaker().id != device_id:
                            break  # default device changed -> reopen on the new one
                        block = rec.record(numframes=self._block)
                        mono = self._to_mono(block)
                        frame = AudioFrame(pcm=mono, timestamp=self._t)
                        self._t += frame.duration
                        on_frame(frame)
            except Exception as exc:  # device vanished mid-stream, format error, ...
                if self._stop.is_set():
                    break
                self._notify("on_degraded", f"capture error, retrying: {exc}")
                self._stop.wait(0.2)
                continue
            if not self._stop.is_set():
                self._notify("on_device_change", soundcard.default_speaker().name)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _to_mono(block: np.ndarray) -> np.ndarray:
        """Downmix to mono inside the capture layer (format hidden downstream)."""
        if block.ndim == 2:
            block = block.mean(axis=1)
        return np.ascontiguousarray(block, dtype=np.float32)

    def _check_degraded(self, name: str) -> None:
        low = name.lower()
        if any(h in low for h in _DEGRADED_HINTS) and name not in self._reported_degraded:
            self._reported_degraded.add(name)
            self._notify("on_degraded", f"Bluetooth hands-free / degraded output: {name}")

    def _notify(self, attr: str, msg: str) -> None:
        cb = getattr(self, attr)
        if cb is not None:
            cb(msg)
