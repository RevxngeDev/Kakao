import numpy as np
import pytest

from kakao.audio import SAMPLE_RATE, AudioFrame


def test_sample_rate_is_16k():
    assert SAMPLE_RATE == 16_000


def test_frame_accepts_mono_float32():
    frame = AudioFrame(pcm=np.zeros(1600, dtype=np.float32), timestamp=0.0)
    assert frame.duration == pytest.approx(0.1)


def test_frame_rejects_stereo():
    with pytest.raises(ValueError):
        AudioFrame(pcm=np.zeros((1600, 2), dtype=np.float32), timestamp=0.0)


def test_frame_rejects_non_float32():
    with pytest.raises(ValueError):
        AudioFrame(pcm=np.zeros(1600, dtype=np.float64), timestamp=0.0)
