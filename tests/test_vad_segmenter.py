import numpy as np
import pytest

from kakao.audio.base import SAMPLE_RATE, AudioFrame
from kakao.vad import VadSegmenter

W = 512  # VAD window


class FakeVad:
    """Deterministic VAD: returns a pre-set event per call index."""

    def __init__(self, events_by_index):
        self._events = events_by_index
        self._i = 0

    def __call__(self, window):
        event = self._events.get(self._i)
        self._i += 1
        return event


def _feed_windows(seg: VadSegmenter, n_windows: int):
    seg.feed(AudioFrame(pcm=np.zeros(n_windows * W, dtype=np.float32), timestamp=0.0))


def test_emits_one_chunk_with_overlap():
    chunks = []
    seg = VadSegmenter(
        chunks.append, overlap_ms=32, min_chunk_s=0.0, max_chunk_s=100,
        vad=FakeVad({2: {"start": 2 * W}, 6: {"end": 6 * W}}),
    )
    _feed_windows(seg, 8)

    assert len(chunks) == 1
    # speech [1024, 3072] padded by one 512 overlap on each side -> [512, 3584]
    assert len(chunks[0].pcm) == 3072
    assert chunks[0].start == pytest.approx(512 / SAMPLE_RATE)
    assert chunks[0].end == pytest.approx(3584 / SAMPLE_RATE)


def test_drops_subminimum_fragment():
    chunks = []
    seg = VadSegmenter(
        chunks.append, overlap_ms=32, min_chunk_s=0.2,  # 3200 samples
        vad=FakeVad({2: {"start": 2 * W}, 3: {"end": 3 * W}}),
    )
    _feed_windows(seg, 6)
    assert chunks == []  # span is only ~1536 samples -> dropped as noise blip


def test_forced_cut_on_long_speech_keeps_overlap_and_coverage():
    chunks = []
    seg = VadSegmenter(
        chunks.append, overlap_ms=32, min_chunk_s=0.0, max_chunk_s=0.16,  # max 2560
        vad=FakeVad({0: {"start": 0}}),  # speech starts and never ends
    )
    _feed_windows(seg, 12)
    seg.flush()

    assert len(chunks) >= 2  # long speech was force-cut into several chunks
    # consecutive chunks overlap (no audio lost between them at the cuts)
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt.start <= prev.end
    # coverage from the very start to the end of what was fed
    assert chunks[0].start == pytest.approx(0.0)
    assert chunks[-1].end == pytest.approx(12 * W / SAMPLE_RATE)
