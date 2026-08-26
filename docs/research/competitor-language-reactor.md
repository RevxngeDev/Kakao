# Competitor study — Language Reactor (languagereactor.com)

> Research input for a decision, not project state. Reviewed 2026-08-01 at the
> author's request: *"its translation is very fast and precise, I want that."*

## What it actually is

A **Chrome/desktop browser extension** (2M+ users), formerly *Learning Languages
with Netflix*. It attaches to **Netflix and YouTube inside the browser** and turns
them into a language-learning environment: bilingual subtitles, per-word dictionary
lookup with AI explanations, precise playback control (auto-pause after each
subtitle, speed, keyboard shortcuts), saved vocabulary, Anki export, an AI tutor.

Its **Pro mode adds speech recognition and machine translation** — notably, for
content where subtitle tracks are missing.

## Why it is fast and precise — the honest answer

**It does not listen to the audio.** In its core mode it reads the **subtitle track
the platform already provides**. Netflix and YouTube hand it a perfect, timed
transcript for free.

From there, all it does is translate **text → text**, which is milliseconds of work
and highly accurate, because it starts from a flawless source.

Kakao starts from raw PCM of *arbitrary* audio and must do the whole chain:
capture → segment (VAD) → **transcribe** → translate. The transcription step is the
error-prone one, and it is exactly the step Language Reactor is handed for free.

**So the comparison is not like-for-like.** Its speed and precision come from
skipping the hard part, not from doing it better. Tellingly, when there *is* no
subtitle track, it too falls back to speech recognition (Pro mode) — the same
territory Kakao lives in permanently.

## What Kakao does that Language Reactor cannot

- **Any audio on the machine**, not just Netflix/YouTube in a browser tab: video
  calls, local files, any app, any site.
- **Content with no subtitles at all** — Kakao's founding premise
  ("works regardless of whether the source has subtitles available").
- Runs **fully offline** on the user's own GPU; no account, no cloud.

Different products. Overlapping surface, different problem.

## What is worth taking

| Idea | Value | Fits Kakao? |
|---|---|---|
| **Bilingual subtitles** (source + translation) | High | ✅ — and see below |
| Show the previous line briefly | Medium | ✅ transient, not "history" |
| Per-word click-to-translate | Medium | ⚠️ conflicts with click-through |
| Playback control / auto-pause | High for them | ❌ Kakao is a passive overlay |
| Vocabulary, Anki, AI tutor | High for them | ❌ different product (learning ≠ comprehension) |

### The important one: bilingual subtitles ↔ DD-05

Language Reactor's headline feature is showing **both languages at once**. Kakao
**cannot do this today**: Whisper's `translate` task emits English only — the
Spanish is never produced, so there is nothing to show alongside.

But the **two-stage route (DD-05)** produces the native transcription as an
intermediate step. That means DD-05 would deliver *three* things at once:

1. Better translation quality (a dedicated text-MT model instead of Whisper's
   weaker secondary `translate` task).
2. **Bilingual subtitles**, essentially for free.
3. The path to **Spanish output** (the original Phase 6 / D-002 goal).

Language Reactor is also **evidence for the second half of DD-05**: text→text
translation really is fast and accurate at scale. That was the uncertain part.

### What this does NOT justify

Reading platform subtitle tracks (the thing that makes Language Reactor precise)
would require Kakao to become a **browser extension**. That is a different product
with a different architecture, not a change to adopt. Named here so it is on record
as considered and rejected, not overlooked.

## Recommendation

This study **strengthens the case for DD-05** and adds a second reason to do it
(bilingual subtitles). It does not suggest copying anything else: the rest of
Language Reactor's value lives in a product category — structured language
learning — that Kakao's non-goals explicitly exclude.

Nothing here changes the near-term plan; it informs whether Phase 7(b) is worth the
work. A measurement spike is still required before adopting (see DD-05).
