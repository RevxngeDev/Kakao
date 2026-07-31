"""Phase 2 verification helper (THROWAWAY): run the VAD segmenter over a WAV and
show the chunk boundaries, so you can review — one by one — that no boundary
splits a word (the Phase 2 gate).

Feed it a 16 kHz mono WAV. To make one from a real (noisy) video:
    uv run --group spike python scripts/make_sample.py "video.mp4" scripts/long.wav 600

Then:
    uv run python scripts/segment_probe.py scripts/long.wav --dump

`--dump` writes each chunk to scripts/chunks/chunkNNN.wav so you can listen to the
edges. Never opens the microphone (D-006).
"""
import pathlib
import sys
import wave

import numpy as np

from kakao.audio.base import SAMPLE_RATE, AudioFrame
from kakao.vad import VadSegmenter

_BLOCK = SAMPLE_RATE // 10  # 100 ms, mimics the live AudioSource block size


def _read_wav(path):
    with wave.open(path, "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        raw = raw.reshape(-1, ch).mean(axis=1)
    if sr != SAMPLE_RATE:
        print(f"WARNING: {path} is {sr} Hz, expected {SAMPLE_RATE}. Re-make it at 16 kHz.")
    return raw


def _write_wav(path, pcm):
    pcm16 = (np.clip(pcm, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm16.tobytes())


def main(path, dump=False):
    audio = _read_wav(path)
    chunks = []
    seg = VadSegmenter(chunks.append)
    for i in range(0, len(audio), _BLOCK):
        seg.feed(AudioFrame(pcm=audio[i : i + _BLOCK].copy(), timestamp=i / SAMPLE_RATE))
    seg.flush()

    print(f"\n{path}: {len(audio) / SAMPLE_RATE:.1f}s -> {len(chunks)} chunks\n")
    print(f"{'#':>3} {'start':>8} {'end':>8} {'dur':>6}  overlap/gap vs prev")
    prev_end = None
    for i, c in enumerate(chunks):
        rel = "" if prev_end is None else (
            f"overlap {prev_end - c.start:+.2f}s" if c.start <= prev_end
            else f"GAP {c.start - prev_end:.2f}s"
        )
        print(f"{i:>3} {c.start:>8.2f} {c.end:>8.2f} {c.duration:>6.2f}  {rel}")
        prev_end = c.end

    if dump:
        out = pathlib.Path("scripts/chunks")
        out.mkdir(parents=True, exist_ok=True)
        for i, c in enumerate(chunks):
            _write_wav(out / f"chunk{i:03d}.wav", c.pcm)
        print(f"\nwrote {len(chunks)} chunk WAVs to {out}/ — listen to the edges.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "scripts/sample.wav", dump="--dump" in sys.argv)
