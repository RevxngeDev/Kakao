"""Phase 1 verification helper (THROWAWAY): record system audio to a WAV.

Run it, then perform the GATE test: start playback, PLUG IN HEADPHONES halfway
through, stop. The WAV must contain the whole audio with no cuts and no silent
gaps. Never opens the microphone (D-006).

Shows a live level meter so you can confirm audio is actually being captured, and
always writes the WAV — even if you stop early with Ctrl+C.

Usage: uv run python scripts/dump_wav.py [out.wav] [seconds]
"""
import sys
import time
import wave

import numpy as np

from kakao.audio.base import SAMPLE_RATE
from kakao.audio.wasapi import WasapiLoopbackSource


def main(out="scripts/capture.wav", seconds=20):
    frames: list[np.ndarray] = []
    src = WasapiLoopbackSource()
    src.on_device_change = lambda d: print(f"\n[device change] now capturing: {d}")
    src.on_degraded = lambda d: print(f"\n[degraded] {d}")
    src.start(lambda f: frames.append(f.pcm))

    print(f"recording ~{seconds}s to {out}")
    print("  -> play some audio, PLUG IN HEADPHONES halfway. Ctrl+C stops early.")
    t0 = time.time()
    try:
        while time.time() - t0 < seconds:
            time.sleep(0.5)
            elapsed = time.time() - t0
            peak = float(np.max(np.abs(frames[-1]))) if frames else 0.0
            bar = "#" * min(30, int(peak * 30))
            print(f"\r  {elapsed:4.1f}s  blocks={len(frames):4d}  level|{bar:<30}|",
                  end="", flush=True)
    except KeyboardInterrupt:
        print("\n  interrupted - saving what was captured so far...")
    finally:
        src.stop()
        pcm = np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)
        pcm16 = (np.clip(pcm, -1, 1) * 32767).astype(np.int16)
        with wave.open(out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm16.tobytes())
        secs = len(pcm) / SAMPLE_RATE
        loud = float(np.max(np.abs(pcm))) if len(pcm) else 0.0
        print(f"\nwrote {secs:.1f}s ({len(frames)} blocks) -> {out}  (peak level {loud:.2f})")
        if loud < 1e-4:
            print("  WARNING: captured audio is silent - was anything playing on the "
                  "DEFAULT output device while recording?")


if __name__ == "__main__":
    a = sys.argv
    main(a[1] if len(a) > 1 else "scripts/capture.wav", int(a[2]) if len(a) > 2 else 20)
