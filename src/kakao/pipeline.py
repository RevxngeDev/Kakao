"""Live pipeline: AudioSource -> VAD -> bounded queue -> ASR thread -> subtitles.

Inference runs in its OWN thread so it never blocks capture (Phase 3). Lag — how
far a subtitle is behind live audio — is instrumented. A chunk is dropped when the
queue overflows (D-005) or when it is already staler than the latency budget
(D-010), so a temporary slowdown can never become permanent, growing lag.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from kakao.asr import AsrEngine
from kakao.audio.base import AudioSource
from kakao.buffer import DropOldestQueue
from kakao.vad import SpeechChunk, VadSegmenter

SubtitleCallback = Callable[[str, float], None]  # (english_text, lag_seconds)


class Pipeline:
    """Wires capture, segmentation, a bounded queue and threaded ASR together."""

    def __init__(
        self,
        source: AudioSource,
        on_subtitle: SubtitleCallback,
        *,
        model: str = "medium",
        language: Optional[str] = None,  # None = auto-detect+lock; "es" to pin (D-017)
        max_lag_s: float = 3.0,   # D-010 drop threshold
        queue_size: int = 8,
        asr=None,                 # injectable for tests
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._on_subtitle = on_subtitle
        self._model = model
        self._language = language
        self._max_lag = max_lag_s
        self._clock = clock
        self._queue: DropOldestQueue[SpeechChunk] = DropOldestQueue(queue_size)
        self._asr = asr
        self._segmenter: Optional[VadSegmenter] = None
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._t0 = 0.0
        self.dropped_stale = 0

    def start(self) -> None:
        if self._asr is None:
            self._asr = AsrEngine(self._model, language=self._language)  # load before capture
        self._segmenter = VadSegmenter(self._queue.put)  # loads Silero once
        self._stop.clear()
        self._t0 = self._clock()
        self._worker = threading.Thread(target=self._run, name="asr-worker", daemon=True)
        self._worker.start()
        self._source.start(self._segmenter.feed)

    def stop(self) -> None:
        self._stop.set()
        self._source.stop()
        if self._worker is not None:
            self._worker.join(timeout=5.0)
            self._worker = None

    @property
    def dropped(self) -> int:
        """Total chunks dropped (queue overflow + stale) — the health indicator."""
        return self._queue.dropped + self.dropped_stale

    @property
    def backlog(self) -> int:
        return len(self._queue)

    # -- worker ------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            chunk = self._queue.get(timeout=0.2)
            if chunk is not None:
                self._handle(chunk)

    def _handle(self, chunk: SpeechChunk) -> None:
        lag = (self._clock() - self._t0) - chunk.end
        if lag > self._max_lag:            # already stale -> drop (D-005 / D-010)
            self.dropped_stale += 1
            return
        text = self._asr.translate(chunk.pcm)
        if text:
            self._on_subtitle(text, lag)
