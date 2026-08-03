"""Single source of truth for defaults and tuning knobs.

Defaults used to be duplicated across pipeline/asr/ui/console; they live here now
so there is exactly one place to change them (project rule: one source of truth).
Values reflect the author-approved D-022 checkpoint plus the D-025 quality pass.
"""
from __future__ import annotations

# -- ASR (D-009 measured, D-016/D-017 tuned) ---------------------------------
MODEL = "medium"                  # Phase 0 winner; `small` is the fallback
MODELS = ["medium", "small"]      # offered in the settings window
COMPUTE_TYPE = "int8"             # right for a GTX 1650 (no tensor cores)
DEVICE = "cuda"
BEAM_SIZE = 1                     # beam=5 measured worse (dropped ~9x), D-016
LANGUAGE = "es"                   # pinned source language (D-017); None = auto-detect

# -- Translation quality (D-025) ---------------------------------------------
# Rolling cross-chunk context. Kept SHORT on purpose: a long prompt makes Whisper
# parrot it back when the audio is ambiguous (measured — it repeated whole phrases
# at 200 chars). Short enough to carry names/topic, too short to copy sentences.
CONTEXT_CHARS = 90
REPETITION_PENALTY = 1.15         # suppresses "What? What? What?" loops
NO_REPEAT_NGRAM_SIZE = 3

# Whisper's classic non-speech hallucinations, matched against the WHOLE output
# (never as substrings) so genuine dialogue is not filtered. Normalized: lowercase,
# no punctuation/whitespace.
JUNK_OUTPUTS = frozenset({
    "you", "thanks for watching", "thank you for watching",
    "thanks for watching this video", "please subscribe", "subscribe",
    "see you next time", "see you in the next video", "bye", "bye bye",
    "subtitles by the amaraorg community", "subtitles by the amara org community",
    "the end", "music", "applause", "outro music", "intro",
})

# -- Segmentation / sync presets (D-021) -------------------------------------
SYNC = "balanced"
SYNC_PRESETS = {
    "fast": {"max_chunk_s": 4.0, "min_silence_ms": 200},
    "balanced": {"max_chunk_s": 6.0, "min_silence_ms": 250},
    "accurate": {"max_chunk_s": 15.0, "min_silence_ms": 300},
}
SYNC_LABELS = [("Equilibrado", "balanced"), ("Más rápido", "fast"), ("Más preciso", "accurate")]

# -- Pipeline (D-005 / D-010) ------------------------------------------------
MAX_LAG_S = 3.0                   # drop chunks staler than this
QUEUE_SIZE = 8

# -- Overlay -----------------------------------------------------------------
FONT_FAMILY = "Segoe UI"
FONT_SIZE = 28
SUBTITLE_HOLD_MS = 6000
DEFAULT_GEOMETRY = [120, 680, 1200, 220]
