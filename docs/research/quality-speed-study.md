# Study — improving translation quality and speed

> Research input for a decision, not project state. Decisions that come out of this
> go to [DECISIONS.md](../ai-context/DECISIONS.md). Baseline is the **D-022
> checkpoint** (medium/int8, beam=1, language=es, balanced 6 s/250 ms) — its exact
> values are recorded in D-022, which is the way to restore it.
> Dated 2026-07-31.

## 0. What we are actually trying to fix

From the author's real runs, the remaining defects are:

1. **Occasional wrong/garbled phrases** in otherwise good dialogue.
2. **Repetition loops** ("What? What? What?", "and / and").
3. **Sung music garbled** (VAD passes it as speech, Whisper invents lyrics).
4. **Hallucinated filler** on near-silence ("Thanks for watching!", "Bye!").
5. **Perceived lag** — subtitles trail the speech.

Point 5 is mostly **structural, not compute**: measured phrase-end → display was
~0.1–0.3 s with `dropped=0`, i.e. the GPU is not the bottleneck; the wait is having
to hear a phrase before translating it. Speed work should therefore target
*perceived* sync (shorter units) and *startup*, not raw inference throughput —
there is already ~10× real-time headroom.

## 1. Model choice

### Ruled out: `large-v3-turbo` ❌

Turbo is the obvious "faster and nearly as good" candidate and it is **unusable
here**: it was fine-tuned **without translation data** and does not support the
translate task — it transcribes in the source language only. For audio→English you
must use `medium` or `large-v3`/`v2`. ([OpenAI discussion](https://github.com/openai/whisper/discussions/2363),
[faster-whisper issue #1237](https://github.com/SYSTRAN/faster-whisper/issues/1237))

### Candidate: `large-v3` / `large-v2` (measured below)

`large-v3` reports 10–20% error reduction over `large-v2` across languages and is
generally recommended for new projects, though independent testing found it can
**hallucinate more than v2 on real-world/noisy audio** — so v2 is the fallback if
v3 invents text. ([HF model card](https://huggingface.co/openai/whisper-large-v3),
[Deepgram analysis](https://deepgram.com/learn/whisper-v3-results))

The open question was purely local: **does it fit in 4 GB and hold real time on the
GTX 1650?** Measured on this machine (see §4) — never quoted from a benchmark table.

## 2. Quality levers available in the installed faster-whisper

Verified present in `WhisperModel.transcribe` (faster-whisper 1.2.1):
`initial_prompt`, `prefix`, `repetition_penalty`, `no_repeat_ngram_size`,
`hallucination_silence_threshold`, `suppress_tokens`, `temperature`, `hotwords`,
`vad_filter`.

### 2.1 Cross-chunk context — the most promising cheap win

Important subtlety: `condition_on_previous_text=True` (the default) **does nothing
for us**. It carries context between the 30 s windows *inside one* `transcribe()`
call; our chunks are ≤6 s, so every call is a single window and starts with no
history. That is very likely a cause of defect #1 — each phrase is translated with
zero knowledge of the conversation.

The fix is to pass the **previous chunk's output as `initial_prompt`**, which
replaces the "previous context window" and conditions generation on it. Only the
last ~224 tokens are consumed, so a short rolling context (1–2 previous subtitles)
is the right size. ([Whisper prompting](https://medium.com/axinc-ai/prompt-engineering-in-whisper-6bb18003562d),
[transformers #22395](https://github.com/huggingface/transformers/issues/22395))

- **Expected:** better coherence, pronouns, names and terminology across phrases.
- **Risk:** prompts can propagate an error forward, and a bad prompt can degrade a
  chunk. Mitigate by keeping the context short and resetting it after silence.
- **Cost:** none (same inference).

### 2.2 Anti-repetition — targets defect #2

`repetition_penalty` (>1.0, e.g. 1.1) and `no_repeat_ngram_size` (e.g. 3) directly
suppress the "What? What? What?" loops. Cheap, low-risk, and independent of model
size.

### 2.3 Hallucination suppression on non-speech — targets #3, #4

- `hallucination_silence_threshold` — drops text produced over silent stretches.
- `no_speech_threshold` / `log_prob_threshold` — raise the bar for accepting a
  segment as speech. Community consensus is these thresholds are unreliable in
  isolation, so they need testing on real audio, not blind tuning.
  ([whisper.cpp discussion](https://github.com/ggml-org/whisper.cpp/discussions/2286))
- **Cheapest practical fix for #4:** a small blocklist of Whisper's known
  non-speech artifacts ("Thanks for watching", "Subtitles by…", "Bye!") filtered
  before display. Crude but effective and zero-cost.
- For sung music (#3), the honest options are: raise the VAD threshold (risks
  losing quiet speech — and we already know Silero misses whispers, D-014), or
  accept it. No clean fix within this architecture.

### 2.4 beam_size — already tested, rejected

Measured on a 10-min run: `beam=5` dropped ~9 chunks vs 1 at beam=1 with no clear
quality gain (D-016). **Do not re-try on `medium`.** If a different config leaves
much more headroom, `beam=2–3` could be re-measured.

## 3. Speed levers

Compute is not the bottleneck (§0), so:

- **Perceived sync:** shorter chunks — already implemented as sync presets (D-021).
- **Startup time:** the model loads on every Start; could be loaded once and kept
  warm across Start/Stop. Real, user-visible improvement.
- **Quantization:** `int8` is correct for the GTX 1650 (no tensor cores, so fp16
  brings no benefit). Nothing to gain here.
- **Batching:** `BatchedInferencePipeline` speeds up *file* processing, not
  single-chunk live inference. Not applicable.

## 4. Measurements on the actual GTX 1650

Method: `scripts/spike_phase0.py`, the same 40 s real Spanish clip, int8, beam=1,
3 repeats, GPU idle. RTF = processing seconds per audio second (lower is better;
< 1.0 means faster than real time).

| Model | RTF (sustained) | VRAM peak | Headroom | Notes |
|---|---:|---:|---:|---|
| `medium` (baseline, D-022) | 0.10 | 1510 MB | 2586 MB | current config |
| `large-v3` | **0.16** | **2525 MB** | **1571 MB** | fits, ~6× real time |
| `large-v2` | 0.21 | 2495 MB | 1601 MB | fits, ~5× real time |

**`large-v3` fits on the GTX 1650 and holds real time comfortably.** So the "bigger
model" door is open — it was not obvious beforehand.

### But: quality on this clip did NOT improve

Same 40 s clip (a kids' science demo about a non-Newtonian fluid), translations:

- `medium`: "…we see that it is **solid**, but if we **put it in the water**, it
  becomes liquid" — semantically correct.
- `large-v3`: "…we see that it is solid, but if we **eat it, we do not jump**, it
  becomes liquid" — worse.
- `large-v2`: "**I'm going to mix it up. I'm going to mix it up.** …" — starts with a
  repetition loop, more broken overall.

**Honest reading:** this is *one* 40 s clip of poor-quality audio — weak evidence
about quality, strong evidence about RTF/VRAM. It does **not** show large-v3 is
better for this use, and it does show `medium` is a genuinely decent baseline. The
only way to know is an A/B on the author's real content.

**Caveat on headroom:** these numbers are with the **GPU idle**. In real use the same
GPU also decodes/renders the video being watched. `medium` leaves 2586 MB spare;
`large-v3` leaves 1571 MB. Both plausible, but large-v3 has materially less margin —
the same caveat recorded in D-009.

## 5. Recommendation

Ordered by (evidence × benefit) ÷ cost. The first three are free — no VRAM, no
latency, no model change — and each targets a defect actually observed in the
author's runs.

| # | Change | Targets | Cost | Risk |
|---|---|---|---|---|
| 1 | **Cross-chunk context** via rolling `initial_prompt` | #1 wrong/garbled phrases | none | prompt can propagate an error; keep it short, reset after silence |
| 2 | **`repetition_penalty` + `no_repeat_ngram_size`** | #2 repetition loops | none | very low |
| 3 | **Hallucination blocklist** ("Thanks for watching", "Bye!", …) | #4 filler on silence | none | very low; could drop a genuine short line |
| 4 | **Offer `large-v3` in the model selector** | #1, general accuracy | 1 GB more VRAM, RTF 0.10→0.16 | unproven gain; less headroom under video load |
| 5 | **Keep the model loaded across Start/Stop** | startup speed | small idle VRAM | low |

**Recommended order:** do 1–3 first (free, targeted, reversible), have the author A/B
them on real content against the D-022 baseline. Then optionally expose `large-v3` as a
*selectable* model — measured to fit — and let the author judge it on their own
material rather than deciding from one clip.

**Not recommended:** `large-v3-turbo` (no translation support — hard blocker),
`beam_size=5` on medium (measured worse, D-016), streaming partials (tried and
rejected, D-023), chasing raw inference speed (not the bottleneck).

**Out of scope / no clean fix:** sung music garbling, whispered speech (D-014).
