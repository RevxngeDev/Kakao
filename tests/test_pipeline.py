import numpy as np

from kakao.audio.base import AudioSource
from kakao.pipeline import Pipeline
from kakao.vad import SpeechChunk


class DummySource(AudioSource):
    def start(self, on_frame):
        pass

    def stop(self):
        pass


class FakeAsr:
    def __init__(self, text="hello"):
        self.text = text
        self.calls = 0
        self.resets = 0

    def translate(self, pcm):
        self.calls += 1
        return self.text

    def reset_context(self):
        self.resets += 1


def _chunk(end):
    return SpeechChunk(pcm=np.zeros(1600, dtype=np.float32), start=max(0.0, end - 1), end=end)


def _pipeline(text, now, max_lag=3.0):
    out = []
    asr = FakeAsr(text)
    p = Pipeline(DummySource(), lambda text, lag: out.append((text, lag)),
                 asr=asr, max_lag_s=max_lag, clock=lambda: now[0])
    p._t0 = 0.0
    return p, asr, out


def test_emits_when_fresh():
    p, asr, out = _pipeline("hi", now=[10.0])
    p._handle(_chunk(end=9.0))          # lag 1.0 <= 3 -> emit
    assert out == [("hi", 1.0)]
    assert p.dropped == 0


def test_drops_when_stale():
    p, asr, out = _pipeline("hi", now=[10.0])
    p._handle(_chunk(end=5.0))          # lag 5.0 > 3 -> drop, ASR not called
    assert out == []
    assert asr.calls == 0
    assert p.dropped == 1


def test_skips_empty_translation():
    p, asr, out = _pipeline("", now=[1.0])
    p._handle(_chunk(end=1.0))          # fresh, but empty text -> no subtitle
    assert out == []
    assert asr.calls == 1


def test_no_subtitle_is_emitted_after_stop():
    """Inference can outlive stop(); it must not paint a ghost subtitle."""
    p, asr, out = _pipeline("hi", now=[10.0])
    p._stop.set()                       # user pressed Detener while a chunk was in flight
    p._handle(_chunk(end=9.0))          # fresh enough, but the pipeline is stopping
    assert out == []
    assert asr.calls == 1               # it did the work; it just did not emit


def test_resets_context_after_a_long_gap():
    p, asr, out = _pipeline("hi", now=[100.0], max_lag=1000)
    p._handle(_chunk(end=2.0))          # continuous -> no reset
    assert asr.resets == 0
    p._handle(_chunk(end=30.0))         # starts at 29.0, a ~27 s gap -> reset
    assert asr.resets == 1
