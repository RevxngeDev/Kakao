"""AudioSource contract — portable core (no OS-specific imports).

Downstream of AudioSource nobody knows the audio endpoint's native format:
implementations resample and downmix to the contract below (D-003, ARCHITECTURE).
The microphone is NEVER opened (D-006) — implementations capture the system
output endpoint only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16_000  # Hz — mono float32 is the format every stage below sees.


@dataclass(frozen=True)
class AudioFrame:
    """One block of normalized audio delivered by an AudioSource."""

    pcm: np.ndarray      # 1-D float32, mono, sampled at SAMPLE_RATE
    timestamp: float     # seconds from source start, of this block's first sample

    def __post_init__(self) -> None:
        if self.pcm.ndim != 1:
            raise ValueError("AudioFrame.pcm must be 1-D (mono)")
        if self.pcm.dtype != np.float32:
            raise ValueError("AudioFrame.pcm must be float32")

    @property
    def duration(self) -> float:
        """Length of this block in seconds."""
        return len(self.pcm) / SAMPLE_RATE


FrameCallback = Callable[[AudioFrame], None]
Notify = Callable[[str], None]


class AudioSource(ABC):
    """Delivers normalized PCM and signals device changes.

    Responsible for: normalized frames + device-change / degradation signals.
    NOT responsible for: anything done with the audio afterwards.

    Implementations are OS-specific (one per platform, D-003). This interface is
    100% portable. The microphone is never opened (D-006).
    """

    #: called (from the worker thread) after the output device changes and capture resumes
    on_device_change: Notify | None = None
    #: called when capture quality degrades (e.g. Bluetooth hands-free profile)
    on_degraded: Notify | None = None

    @abstractmethod
    def start(self, on_frame: FrameCallback) -> None:
        """Begin capture. `on_frame` runs for every block, from a worker thread."""

    @abstractmethod
    def stop(self) -> None:
        """Stop capture and release the device."""
