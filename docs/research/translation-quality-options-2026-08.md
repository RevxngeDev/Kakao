# Research — improving translation quality and speed (Aug 2026)

> Research input for a decision, not project state. **Nothing here is measured on
> the GTX 1650.** Published benchmarks are marketing-adjacent and are quoted as
> claims, not facts. Kakao's rule stands: no latency/VRAM/quality number enters
> DECISIONS.md without a measurement on the real hardware.

## Why this search happened

The author's standing complaint is that **individual words are mistranslated**.
Four levers have already been tried and three made things worse:

| Lever | Result |
|---|---|
| `beam_size=5` | Worse — dropped ~9× more chunks (D-016) |
| Streaming partials | Worse — garbled half-phrases (D-023) |
| Two-stage (transcribe + text MT) | Worse quality, though cheaper (DD-05) |
| `large-v3` | Offered in Ajustes, **still untested by the author** (D-031) |

The DD-05 measurement produced the key structural insight: **the one-hop model
still has the audio while it translates, so it can hear through a word a text-only
translator would mangle.** Any candidate should be judged against that.

---

## Finding 1 — Free wins we are simply not using (highest value/cost)

### 1a. `hotwords` — direct fix for the proper-noun failures

faster-whisper exposes a `hotwords` parameter that **boosts specific words during
decoding**. This is a *different mechanism* from the `initial_prompt` we added in
D-025: the prompt primes context, hotwords bias the decoder itself. They can be
used together.

This targets exactly the errors seen in the author's runs — "Ecomoda" rendered as
*comfortable* / *Komoda* / *the commode*, "Calderón" → *Cateron*, "Pierson" dropped
entirely. For a user who watches one series, a short list of recurring character and
company names is realistic to maintain.

Caveat: Whisper truncates the prompt at 224 tokens, so the list must stay short.

### 1b. Confidence filtering — ❌ MEASURED AND REJECTED (2026-08-01)

**Measured before implementing; the data says do not build it.** See D-032.
Whisper's confidence does not separate good output from bad on this content: the
target hallucination scored −0.850 against a median of −0.695, and a wrong proper
noun scored −0.634 (*above* the median). Catching the hallucination requires a
threshold that discards ~26% of all subtitles, and still misses the confident
errors. `no_speech_prob` and compression ratio do not separate either.

The original reasoning is kept below for the record.



The dangerous failure the spike exposed was **an invented sentence delivered
confidently** ("our doctor thought about it…" where the audio said something else).
It is invisible today because only the English is shown.

faster-whisper returns `avg_logprob` and `no_speech_prob` **per segment**, and
supports `log_prob_threshold`, `compression_ratio_threshold` and
`no_speech_threshold` with temperature fallback. Kakao currently passes **none** of
these — it takes the defaults and never inspects the returned confidence.

Concrete option: drop or visually flag a subtitle whose `avg_logprob` is below a
tuned threshold. Showing *nothing* for one phrase is better than showing a fluent
lie — and it matches the project's existing philosophy (D-005: a wrong/late
subtitle is worse than a missing one).

**Cost of 1a + 1b: no extra VRAM, no extra latency, a handful of lines.** This is
the cheapest untried lever and it aims at the measured failures.

---

## Finding 2 — NVIDIA Canary (the potentially big one)

`nvidia/canary-1b-flash` — **883M parameters**, and per NVIDIA's model card an
inference speed of **>1000 RTFx**. It performs both ASR and translation, covering
**es→en and en→es** directly. `canary-1b-v2` extends to ~25 languages.

**Claimed** (NVIDIA / third-party summaries, not verified here): Canary outperforms
Whisper-large-v3, OWSM and SeamlessM4T on English, French, Spanish and German,
while trained on an order of magnitude less data.

Why it matters for Kakao specifically:
- It is **stronger on Spanish** than large-v3 — which is the author's source language.
- It keeps translation **inside one model with access to the audio**, so it does not
  suffer DD-05's text-MT weakness.
- **`en→es` opens Spanish output** — the original D-002 goal — without a cascade.

### Honest obstacles
- **Needs NVIDIA NeMo + torch with CUDA.** Kakao ships **torch CPU only** (for
  Silero). This is a heavy dependency change (multi-GB) and a second runtime
  alongside CTranslate2. No CTranslate2 support exists.
- **VRAM is the open question.** ~883M params ≈ 1.8 GB at fp16, plausibly ~1 GB
  int8 — but NVIDIA's docs cite **6 GB to load** `canary-1b-v2`, and there are
  reported OOMs even on machines with nominally sufficient memory. The GTX 1650 has
  **4 GB**, which has been the binding constraint since Phase 0.
- **Real-time behaviour on this hardware is unknown.** RTFx >1000 is a batched
  throughput figure on datacentre GPUs; it says little about 6-second chunks on a
  1650.
- Its translation set is narrower than Whisper's for exotic source languages.

**Verdict: the most promising candidate, and the only one worth a spike — but its
feasibility on 4 GB is genuinely uncertain, not a formality.**

---

## Finding 3 — SeamlessM4T v2 (likely too big)

Meta claims v2 improves speech-to-text translation by ~25% over Whisper-large-v3 and
translates into many languages including Spanish. But the large model is ~2.3B
parameters — against a 4 GB budget already holding Whisper. A medium variant
(~1.2B) exists. It also needs torch CUDA + transformers.

Given Canary is smaller, faster and reportedly beats SeamlessM4T on Spanish, Canary
is the better first spike. Recorded so the option is not lost.

---

## What "combining the approaches" could actually mean

The author asked about combining the recent approaches. The defensible combination
is **not** running one-hop and two-stage together (that doubles the work for a path
already measured as worse). It is:

**Keep one-hop translation (it hears the audio — DD-05) + add confidence gating and
hotwords (Finding 1) so its confident mistakes are suppressed and its proper nouns
are anchored.**

If bilingual subtitles are later wanted as a *feature*, the two-stage path already
exists and is cheap (~32 ms) — but as a feature, not a quality fix.

---

## Recommended order

1. **Hotwords + confidence gating** (Finding 1). Free, targeted at measured
   failures, reversible, no new dependencies. Do this first.
2. **Author tests `large-v3`** — already shipped in Ajustes, still untested.
3. **Spike Canary** (Finding 2) *only if* 1 and 2 are not enough, budgeting for the
   real possibility that it does not fit in 4 GB. Measure VRAM and chunk-level RTF
   before writing any integration.
4. SeamlessM4T — park it.

## Sources

- [faster-whisper (SYSTRAN)](https://github.com/SYSTRAN/faster-whisper)
- [Whisper hallucination thresholds discussion](https://github.com/openai/whisper/discussions/2420)
- [Whisper hotwords discussion](https://github.com/openai/whisper/discussions/1477)
- [nvidia/canary-1b-flash](https://huggingface.co/nvidia/canary-1b-flash)
- [nvidia/canary-1b-v2](https://huggingface.co/nvidia/canary-1b-v2)
- [NVIDIA: new standard for speech recognition and translation (NeMo Canary)](https://developer.nvidia.com/blog/new-standard-for-speech-recognition-and-translation-from-the-nvidia-nemo-canary-model)
- [Meta: Seamless Communication](https://ai.meta.com/blog/seamless-communication/)
- [SeamlessM4T paper](https://arxiv.org/pdf/2308.11596)
