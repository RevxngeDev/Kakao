"""Phase 3 console runner: print live English subtitles for system audio.

Run: uv run python -m kakao.console [minutes]
It plays nothing itself — start a video yourself. Prints each subtitle with its
lag, and a periodic health line (backlog + dropped). Never opens the microphone
(D-006). Ctrl+C stops.
"""
from __future__ import annotations

import sys
import time

from kakao import config
from kakao.audio.wasapi import WasapiLoopbackSource
from kakao.pipeline import Pipeline


def main(minutes: float = 10.0) -> None:
    source = WasapiLoopbackSource()
    source.on_device_change = lambda d: print(f"[device change] {d}")
    source.on_degraded = lambda d: print(f"[degraded] {d}")

    def on_subtitle(text: str, lag: float) -> None:
        print(f"[{lag:4.1f}s] {text}")

    pipeline = Pipeline(source, on_subtitle)  # defaults come from kakao.config
    print(f"loading model ({config.MODEL}/{config.COMPUTE_TYPE}, source={config.LANGUAGE}) "
          "and starting capture... play a video now.")
    pipeline.start()
    try:
        end = time.time() + minutes * 60
        while time.time() < end:
            time.sleep(10)
            print(f"  -- health: backlog={pipeline.backlog} dropped={pipeline.dropped}")
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        print(f"stopped. total dropped={pipeline.dropped}")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 10.0)
