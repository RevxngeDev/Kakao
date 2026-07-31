"""ASR engine: audio -> translated English text in ONE hop (D-001).

Uses the Phase-0 winning configuration: faster-whisper `medium`, int8 (D-009).
Portable in principle (D-003). The only Windows-specific bit is registering the
pip CUDA DLL directories, which is guarded (`os.add_dll_directory` exists only on
Windows) and a no-op elsewhere.
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np


def _register_cuda_dlls() -> None:
    # On Windows, CTranslate2 loads cuBLAS/cuDNN/cudart from the pip nvidia-* wheels,
    # which are not on PATH. Register their bin dirs before WhisperModel is built.
    if not hasattr(os, "add_dll_directory"):
        return
    try:
        import nvidia
        for root in list(getattr(nvidia, "__path__", [])):
            for entry in sorted(os.listdir(root)):
                bin_dir = os.path.join(root, entry, "bin")
                if os.path.isdir(bin_dir):
                    os.add_dll_directory(bin_dir)
                    # PATH prepend too: CTranslate2 resolves cuBLAS's own
                    # dependencies (cudart, cublasLt) via PATH, not user dirs.
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


_register_cuda_dlls()


class _LanguageLock:
    """Auto-detect the source language ONCE, then stick with it.

    Whisper re-detects language on every chunk; on short/noisy/music chunks it
    misfires (e.g. detects Chinese on Spanish audio -> garbage). Locking to the
    first consistently-detected language stops that. Still 'auto-detect' (D-002),
    just stable rather than per-chunk.
    """

    def __init__(self, min_prob: float = 0.6, min_count: int = 3) -> None:
        self._min_prob = min_prob
        self._min_count = min_count
        self._counts: dict = {}
        self.locked: Optional[str] = None

    def update(self, language: str, probability: float) -> None:
        if self.locked is not None or probability < self._min_prob:
            return
        self._counts[language] = self._counts.get(language, 0) + 1
        if self._counts[language] >= self._min_count:
            self.locked = language


class AsrEngine:
    """Translates a mono float32 @ 16 kHz chunk to English text (one hop, D-001)."""

    def __init__(
        self,
        model: str = "medium",
        *,
        compute_type: str = "int8",
        device: str = "cuda",
        beam_size: int = 1,             # 1 keeps real time on the GTX 1650 (5 dropped ~9x more, D-016)
        language: Optional[str] = None,  # None = auto-detect + lock (D-002); e.g. "es" to pin
    ) -> None:
        from faster_whisper import WhisperModel  # lazy: keeps module import light

        self._model = WhisperModel(model, device=device, compute_type=compute_type)
        self._beam = beam_size
        self._user_language = language
        self._lock = _LanguageLock()

    def translate(self, pcm: np.ndarray) -> str:
        language = self._user_language or self._lock.locked
        segments, info = self._model.transcribe(
            pcm, task="translate", beam_size=self._beam, language=language
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        if self._user_language is None and self._lock.locked is None:
            self._lock.update(info.language, info.language_probability)
        return text
