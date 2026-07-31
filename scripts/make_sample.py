"""Make a ~40 s 16 kHz mono WAV sample for the Phase 0 spike (THROWAWAY).

Picks the window with the most audio activity (highest RMS) so we measure on
speech, not on a silent intro. Never modifies the source file. Never uses the
microphone (D-006) — it reads a file.

Usage: uv run --group spike python scripts/make_sample.py <video-or-audio> [out.wav] [seconds]
"""
import sys, wave
import numpy as np
from faster_whisper.audio import decode_audio

SR = 16000

def main(src, out="scripts/sample.wav", secs=40):
    secs = int(secs)
    audio = decode_audio(src, sampling_rate=SR).astype(np.float32)
    total = len(audio) / SR
    win = secs * SR
    if len(audio) <= win:
        seg, start = audio, 0
    else:
        block = SR  # 1 s energy blocks
        n = len(audio) // block
        e = np.array([np.sqrt(np.mean(audio[i*block:(i+1)*block] ** 2)) for i in range(n)])
        csum = np.concatenate([[0.0], np.cumsum(e)])
        wsum = csum[secs:] - csum[:-secs]        # energy of each 40 s window
        start = int(np.argmax(wsum))             # best window start, in seconds
        seg = audio[start*block: start*block + win]
    pcm16 = (np.clip(seg, -1, 1) * 32767).astype(np.int16)
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm16.tobytes())
    print(f"source {total:.1f}s -> sample {len(seg)/SR:.1f}s starting at {start}s -> {out}")

if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2] if len(a) > 2 else "scripts/sample.wav", a[3] if len(a) > 3 else 40)
