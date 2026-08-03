"""Voice-activity segmentation (D-004).

Cuts the audio stream on silence into complete units of speech, with overlap so a
word at a boundary is never split, and with min/max duration bounds so a silence
that never arrives cannot block output indefinitely. Portable (no OS-specific
imports). Uses Silero VAD (D-013), driven as a streaming iterator over fixed
16 kHz windows.

The VAD backend is injectable so the segmentation logic is unit-testable without
loading the model: pass any `vad` callable mapping a 512-sample window to
`None | {"start": int} | {"end": int}` (absolute sample indices).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from kakao.audio.base import SAMPLE_RATE, AudioFrame

WINDOW = 512  # Silero VAD window at 16 kHz (samples)

VadEvent = dict | None
Vad = Callable[[np.ndarray], VadEvent]


@dataclass(frozen=True)
class SpeechChunk:
    """A complete unit of speech to translate."""

    pcm: np.ndarray  # float32 mono @ SAMPLE_RATE
    start: float     # seconds from stream start
    end: float       # seconds from stream start

    @property
    def duration(self) -> float:
        return len(self.pcm) / SAMPLE_RATE


ChunkCallback = Callable[[SpeechChunk], None]


_silero_model = None  # cached across pipeline restarts so Start is fast (D-025)


def _load_silero():
    global _silero_model
    if _silero_model is None:
        from silero_vad import load_silero_vad
        _silero_model = load_silero_vad()
    return _silero_model


def _default_vad(threshold: float, min_silence_ms: int, speech_pad_ms: int) -> Vad:
    import torch
    from silero_vad import VADIterator  # lazy: avoids torch on import

    it = VADIterator(
        _load_silero(),
        threshold=threshold,
        sampling_rate=SAMPLE_RATE,
        min_silence_duration_ms=min_silence_ms,
        speech_pad_ms=speech_pad_ms,
    )

    def call(window: np.ndarray) -> VadEvent:
        return it(torch.from_numpy(window))

    return call


class VadSegmenter:
    """Turns a stream of AudioFrames into overlapping SpeechChunks."""

    def __init__(
        self,
        on_chunk: ChunkCallback,
        *,
        threshold: float = 0.5,
        min_silence_ms: int = 300,
        speech_pad_ms: int = 100,
        overlap_ms: int = 200,
        max_chunk_s: float = 15.0,
        min_chunk_s: float = 0.2,
        vad: Vad | None = None,
    ) -> None:
        self._on_chunk = on_chunk
        self._overlap = int(overlap_ms / 1000 * SAMPLE_RATE)
        self._max = int(max_chunk_s * SAMPLE_RATE)
        self._min = int(min_chunk_s * SAMPLE_RATE)
        self._vad = vad or _default_vad(threshold, min_silence_ms, speech_pad_ms)

        self._accum = np.zeros(0, dtype=np.float32)   # pending samples (< WINDOW after draining)
        self._retain = np.zeros(0, dtype=np.float32)  # retained raw audio for extraction
        self._base = 0                                # absolute index of _retain[0]
        self._pos = 0                                 # absolute samples fed to the VAD
        self._active_start: int | None = None      # start of the in-progress speech

    def feed(self, frame: AudioFrame) -> None:
        """Feed one AudioFrame; emits chunks via the callback as they complete."""
        self._retain = np.concatenate([self._retain, frame.pcm])
        self._accum = np.concatenate([self._accum, frame.pcm])
        while len(self._accum) >= WINDOW:
            window = self._accum[:WINDOW]
            self._accum = self._accum[WINDOW:]
            self._process_window(window)
            self._pos += WINDOW
        self._trim()

    def flush(self) -> None:
        """Emit any trailing in-progress speech (call once when the stream ends)."""
        if self._active_start is not None:
            self._emit(self._active_start, self._pos + len(self._accum))
            self._active_start = None

    # -- internals ---------------------------------------------------------
    def _process_window(self, window: np.ndarray) -> None:
        event = self._vad(window)
        if event and "start" in event:
            self._active_start = int(event["start"])
        elif event and "end" in event and self._active_start is not None:
            self._emit(self._active_start, int(event["end"]))
            self._active_start = None

        # Force a cut if speech runs past max_chunk without a silence (D-004).
        active = self._active_start
        if active is not None and (self._pos + WINDOW - active) >= self._max:
            cut = self._pos + WINDOW
            self._emit(active, cut)
            self._active_start = cut - self._overlap  # carry overlap into the next chunk

    def _emit(self, start: int, end: int) -> None:
        a = max(self._base, start - self._overlap)
        b = min(self._base + len(self._retain), end + self._overlap)
        if b - a < self._min:  # drop sub-minimum fragments (noise blips)
            return
        pcm = self._retain[a - self._base : b - self._base].copy()
        self._on_chunk(SpeechChunk(pcm=pcm, start=a / SAMPLE_RATE, end=b / SAMPLE_RATE))

    def _trim(self) -> None:
        anchor = self._active_start if self._active_start is not None else self._pos
        keep_from = max(self._base, anchor - self._overlap - WINDOW)
        keep_from = min(keep_from, self._base + len(self._retain))
        drop = keep_from - self._base
        if drop > 0:
            self._retain = self._retain[drop:]
            self._base += drop
