"""ASR engine: audio -> translated English text in ONE hop (D-001).

Uses the Phase-0 winning configuration (D-009) with the D-025 quality pass:
rolling cross-chunk context, repetition suppression and a hallucination filter.
Defaults live in `kakao.config`.

Portable in principle (D-003): the only Windows-specific bit is registering the
pip CUDA DLL directories, guarded by platform and a no-op elsewhere.
"""
from __future__ import annotations

import os
import re
import threading

import numpy as np

from kakao import config


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

# Single-entry model cache: keeps the loaded model across Start/Stop so restarting
# is instant (D-025). Only ONE model is held — with 4 GB VRAM, caching two would
# not fit, so requesting a different one evicts the previous.
_cache_lock = threading.Lock()
_cached_key = None
_cached_model = None


def load_model(name: str, device: str, compute_type: str):
    """Return a WhisperModel, reusing the cached one when the config matches."""
    global _cached_key, _cached_model
    from faster_whisper import WhisperModel  # lazy: keeps module import light

    key = (name, device, compute_type)
    with _cache_lock:
        if key != _cached_key:
            _cached_model = None  # free the old one before allocating the new
            _cached_model = WhisperModel(name, device=device, compute_type=compute_type)
            _cached_key = key
        return _cached_model


_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize(text: str) -> str:
    return " ".join(_PUNCT.sub("", text).lower().split())


def is_junk(text: str) -> bool:
    """True if the WHOLE output is a known Whisper non-speech hallucination.

    Matched against the full string only (never as a substring), so genuine
    dialogue that merely contains these words is kept.
    """
    normalized = _normalize(text)
    return not normalized or normalized in config.JUNK_OUTPUTS


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
        self.locked: str | None = None

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
        model: str = config.MODEL,
        *,
        compute_type: str = config.COMPUTE_TYPE,
        device: str = config.DEVICE,
        beam_size: int = config.BEAM_SIZE,
        language: str | None = config.LANGUAGE,
        use_context: bool = True,
    ) -> None:
        self._model = load_model(model, device, compute_type)
        self._beam = beam_size
        self._user_language = language
        self._lock = _LanguageLock()
        self._use_context = use_context
        self._context = ""
        self._last_normalized = ""

    def reset_context(self) -> None:
        """Forget the rolling context (call on a scene/silence break)."""
        self._context = ""
        self._last_normalized = ""

    def translate(self, pcm: np.ndarray) -> str:
        language = self._user_language or self._lock.locked
        segments, info = self._model.transcribe(
            pcm,
            task="translate",
            beam_size=self._beam,
            language=language,
            # Cross-chunk context: our chunks are one 30 s window each, so
            # condition_on_previous_text does nothing — the previous output must be
            # passed explicitly as the prompt (D-025).
            initial_prompt=self._context or None,
            repetition_penalty=config.REPETITION_PENALTY,
            no_repeat_ngram_size=config.NO_REPEAT_NGRAM_SIZE,
        )
        text = " ".join(s.text.strip() for s in segments).strip()

        if self._user_language is None and self._lock.locked is None:
            self._lock.update(info.language, info.language_probability)

        if is_junk(text):
            return ""

        # Prompting makes Whisper parrot the context back when the audio is
        # ambiguous (measured). Suppress an output that just repeats the previous
        # subtitle instead of showing the same line twice.
        normalized = _normalize(text)
        if normalized == self._last_normalized:
            return ""
        self._last_normalized = normalized

        if self._use_context:
            self._context = f"{self._context} {text}".strip()[-config.CONTEXT_CHARS:]
        return text
