# Code audit — 2026-07-31 (Phase 6 backlog)

> Full read of all 14 modules, the tests and the config, looking for quality,
> architectural, performance and security improvements. This is the **Phase 6
> backlog**. Findings acted on are ticked; decisions that come out of it go to
> [DECISIONS.md](../ai-context/DECISIONS.md).
>
> Overall verdict: **the code is healthy.** No memory leaks, no serious race
> conditions, no security holes. Findings 1–3 are the ones that genuinely matter;
> the rest is polish.

## 🔴 Real problems

- [x] **1. The portability test does not protect what it claims.** ✅ *Fixed
  2026-08-01:* added `WIN32_ATTRS` / `WIN32_ALLOWLIST` and three tests — one that
  rejects `ctypes.windll` outside `audio/` and the allowlist, one that requires an
  allowlisted file to carry a `sys.platform` guard, and one that asserts the
  detector actually finds the known usage (so the check can never pass vacuously).
  `tests/test_portability.py` enforces D-003 ("nothing outside `src/kakao/audio/`
  imports a Windows-specific library") via a `FORBIDDEN` list that does **not**
  include `ctypes`. `overlay.py:37` uses `ctypes.windll.user32` — pure Win32 —
  outside `audio/`, and the test stays green. It is guarded by
  `sys.platform == "win32"` so nothing breaks today, but the automated guarantee is
  weaker than the docs claim: a new Win32 call outside `audio/` would pass unnoticed.
  *Fix:* either forbid `ctypes.windll` explicitly with a documented allow-list entry
  for the overlay, or assert the guard.

- [x] **2. Settings can be corrupted and are then silently lost.** ✅ *Fixed
  2026-08-01:* writes go to a temp file then `os.replace()` (atomic on Windows and
  POSIX). A file that is already corrupt is moved to `.json.corrupt` instead of
  being discarded silently. Added `Settings.update()` for batched writes.
  `settings.py` `_write()` uses `write_text()` — not atomic. A crash mid-write
  truncates the JSON; `_read()` catches `ValueError` and returns `{}`, so **every
  setting silently resets** (overlay position, model, device, sync).
  *Fix:* write to a temp file then `os.replace()` (atomic). ~4 lines.

- [x] **3. A subtitle can appear AFTER Detener.** ✅ *Fixed 2026-08-01:*
  `Pipeline._handle` checks `self._stop.is_set()` before emitting. Covered by
  `test_no_subtitle_is_emitted_after_stop`.
  `pipeline.py` `stop()` joins with a 5 s timeout, but the ASR worker may be
  mid-inference. If it finishes after the stop, it still calls `on_subtitle` and
  paints a ghost subtitle over the video — after the UI already cleared it.
  *Fix:* check `self._stop.is_set()` before emitting.

## 🟡 Architecture

- [x] **4. The UI layer reaches into the ASR/VAD internals.** ✅ *Fixed 2026-08-01:*
  `pipeline.preload_models()` added; `ui.py` no longer imports `asr` or `vad`.
- [ ] **5. Spanish UI strings live in `config.py`** (`SYNC_LABELS`). D-007 separates
  English code from Spanish interface text; labels belong in the UI layer.
- [x] **6. Dead code.** ✅ *Fixed 2026-08-01:* `pipeline.SYNC_PRESETS` re-export
  removed. `_LanguageLock` kept — it is unreachable only while `LANGUAGE` is pinned,
  and it is the mechanism a source-language selector would rely on.

## 🟢 Performance (all minor — the pipeline has huge headroom)

- [~] **7.** `_icon()` rebuilds a QPixmap + QPainter on *every* notification.
  **Rejected 2026-08-01 (D-031):** a micro-optimization with no measurable benefit;
  recorded as known-and-declined rather than silently skipped.
- [x] **8.** `_save_geometry()` writes the whole JSON on **every arrow-key press**
  in edit mode. ✅ *Fixed 2026-08-01:* arrow nudges go through a 400 ms debounce
  timer; an explicit save (Esc, close, mouse release) cancels the pending one.
- [x] **9.** `SettingsDialog._save()` performs four separate file writes. ✅ *Fixed
  2026-08-01:* uses `Settings.update()` — one write. Covered by `test_update_writes_once`.
- [~] **10.** `VadSegmenter.feed()` `np.concatenate`s the whole retain buffer every
  frame. **Rejected 2026-08-01 (D-031):** negligible at ~10× real-time headroom;
  a ring buffer would add complexity for no measurable gain.

## 🔵 Security (low risk — local, single-user, offline)

- [ ] **11.** `_humanize()` returns `f"Error: {err}"` with the raw exception text,
  which can contain local file paths, into a user-facing notification.
- [ ] **12.** `_register_cuda_dlls()` **prepends** the NVIDIA bin dirs to the process
  `PATH`, so a name-colliding DLL would resolve from there first. It is what
  faster-whisper recommends; noted, not alarming.
- **Good, by design:** audio is never persisted, the microphone is never opened,
  there is no network I/O, no secrets, and `*.wav` is git-ignored. The real attack
  surface is minimal.

## ⚪ Minor quality

- [x] **14.** `Overlay._wrap()` empty lines. ✅ *Fixed 2026-08-01* while writing its
  test; now typed `list[str]` and covered by `test_no_empty_lines_from_trailing_or_double_spaces`.
- [ ] **15.** Quitting while `_starting` is true leaves the pipeline unstopped — the
  threads are daemons so the process exits, but the audio device stays open until then.
- [x] **16.** No tests for `_humanize()` or `Overlay._wrap()`. ✅ *Fixed 2026-08-01:*
  `tests/test_ui_helpers.py` (Qt runs offscreen for font metrics).

## Standing

Closed: 1, 2, 3, 4, 6, 8, 9, 14, 16 (D-030, D-031).
Rejected with reason: 7, 10 (micro-optimizations, no measurable gain).
Still open: **5** (Spanish UI strings in `config.py`), **11** (raw exception text
shown to the user), **15** (quit while starting leaves the pipeline unstopped).
All three are minor and would mainly matter if the app were ever distributed.
