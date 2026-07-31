"""Phase 0 measurement spike — THROWAWAY. Not part of the app (see ROADMAP.md).

For each model size (int8) measures: real-time factor (processing s / audio s)
sustained across repeats, peak VRAM + headroom, and prints the English
translation so quality can be judged by hand. The winning config closes DD-01
and DD-04 (record numbers in DECISIONS.md — never quote an unmeasured figure).

Whisper always encodes 30 s windows, so we feed the WHOLE clip (not 5 s slices):
a 5 s slice would be padded to 30 s and look ~6x slower than real throughput.
RTF < 1.0 means a 5 s chunk is processed in under 5 s (the gate).

Usage: uv run --group spike python scripts/spike_phase0.py <audio-file> [model]
Input: ~30-60 s of REAL, noisy audio from an actual video (not clean studio).
Never uses the microphone (D-006) — it reads a file.
"""
import os, sys, time

# Windows: CTranslate2 loads cuBLAS/cuDNN from the pip nvidia-* wheels, but they
# are not on PATH. Register their DLL dirs before importing faster-whisper.
try:
    import nvidia  # namespace package: use __path__, not __file__ (which is None)
    for _root in list(getattr(nvidia, "__path__", [])):
        for _entry in sorted(os.listdir(_root)):     # cublas, cudnn, cuda_runtime, ...
            _bin = os.path.join(_root, _entry, "bin")
            if os.path.isdir(_bin):
                os.add_dll_directory(_bin)
                os.environ["PATH"] = _bin + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

import pynvml
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

MODELS = ["tiny", "base", "small", "medium"]  # multilingual: translate needs them
COMPUTE, BEAM, REPEATS, SR = "int8", 1, 3, 16000

def used_mb(h):
    return pynvml.nvmlDeviceGetMemoryInfo(h).used / 1024 / 1024

def main(path, models):
    audio = decode_audio(path, sampling_rate=SR)
    total_s = len(audio) / SR
    pynvml.nvmlInit()
    h = pynvml.nvmlDeviceGetHandleByIndex(0)
    total_vram = pynvml.nvmlDeviceGetMemoryInfo(h).total / 1024 / 1024
    base = used_mb(h)
    print(f"audio {total_s:.1f}s | GPU {total_vram:.0f} MB total, "
          f"{base:.0f} MB in use | compute={COMPUTE} beam={BEAM} x{REPEATS}\n")
    if total_s < 20:
        print("WARNING: clip < 20s — use ~30-60s for a 'sustained' reading.\n")

    for size in models:
        model = WhisperModel(size, device="cuda", compute_type=COMPUTE)
        rtfs, peak, text = [], base, ""
        for r in range(REPEATS):
            t0 = time.perf_counter()
            segs, _ = model.transcribe(audio, task="translate", beam_size=BEAM)
            text = " ".join(s.text.strip() for s in segs)  # forces computation
            rtfs.append((time.perf_counter() - t0) / total_s)
            peak = max(peak, used_mb(h))
        sustained = rtfs[1:] or rtfs           # drop warm-up run if present
        max_rtf = max(sustained)
        gate = "PASS" if max_rtf < 1.0 else "FAIL"
        print(f"== {size} / {COMPUTE} ==")
        print(f"   RTF warmup {rtfs[0]:.2f} | sustained max {max_rtf:.2f} "
              f"-> real-time gate (<1.0): {gate}")
        print(f"   VRAM peak {peak:.0f} MB | headroom {total_vram - peak:.0f} MB")
        print(f"   translation: {text[:400]}\n")
        del model

    pynvml.nvmlShutdown()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/spike_phase0.py <audio-file> [model]")
    main(sys.argv[1], [sys.argv[2]] if len(sys.argv) > 2 else MODELS)
