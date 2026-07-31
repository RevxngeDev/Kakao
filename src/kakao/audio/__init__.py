"""Audio capture layer — the ONLY OS-specific part of Kakao (D-003).

Exposes the portable AudioSource contract. The Windows WASAPI implementation
lives in ``kakao.audio.wasapi`` and is imported explicitly by the composition
root, so importing this package does not pull in OS-specific libraries.

Domain invariant (D-003): no module OUTSIDE this package may import a
capture/OS-specific library. Enforced by tests/test_portability.py.
"""
from kakao.audio.base import SAMPLE_RATE, AudioFrame, AudioSource

__all__ = ["AudioSource", "AudioFrame", "SAMPLE_RATE"]
