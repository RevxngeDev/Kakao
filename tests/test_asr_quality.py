"""Tests for the D-025 quality pass: hallucination filter + rolling context."""
import numpy as np
import pytest

from kakao.asr import AsrEngine, is_junk


@pytest.mark.parametrize("text", [
    "Thanks for watching!", "thanks for watching", "You", "you.", "Bye!",
    "Subscribe", "See you next time.", "♪♪♪", "   ", "",
])
def test_junk_outputs_are_detected(text):
    assert is_junk(text)


@pytest.mark.parametrize("text", [
    "Thank you for the money you lent me.",   # contains junk words, but is real dialogue
    "You know what happened to us, right?",
    "Bye, I'll call you tomorrow.",
    "The lawyer is crazy.",
])
def test_real_dialogue_is_kept(text):
    assert not is_junk(text)


class _StubModel:
    """Records the prompt it was called with and returns queued texts."""

    def __init__(self, texts):
        self._texts = list(texts)
        self.prompts = []

    def transcribe(self, pcm, **kw):
        self.prompts.append(kw.get("initial_prompt"))
        text = self._texts.pop(0)
        segment = type("S", (), {"text": text})()
        info = type("I", (), {"language": "es", "language_probability": 0.99})()
        return [segment], info


def _engine(monkeypatch, texts):
    monkeypatch.setattr("kakao.asr.load_model", lambda *a, **k: _StubModel(texts))
    engine = AsrEngine(language="es")
    return engine, engine._model


def test_context_is_carried_into_the_next_call(monkeypatch):
    engine, model = _engine(monkeypatch, ["Hello Betty.", "She is at Ecomoda."])
    engine.translate(np.zeros(16000, dtype=np.float32))
    engine.translate(np.zeros(16000, dtype=np.float32))

    assert model.prompts[0] is None                 # nothing to condition on yet
    assert model.prompts[1] == "Hello Betty."       # previous output becomes the prompt


def test_junk_output_does_not_pollute_the_context(monkeypatch):
    engine, model = _engine(monkeypatch, ["Thanks for watching!", "Real line."])
    assert engine.translate(np.zeros(16000, dtype=np.float32)) == ""
    engine.translate(np.zeros(16000, dtype=np.float32))
    assert model.prompts[1] is None                 # junk was not remembered


def test_reset_context_clears_it(monkeypatch):
    engine, model = _engine(monkeypatch, ["First.", "Second."])
    engine.translate(np.zeros(16000, dtype=np.float32))
    engine.reset_context()
    engine.translate(np.zeros(16000, dtype=np.float32))
    assert model.prompts[1] is None


def test_context_is_bounded(monkeypatch):
    from kakao import config
    engine, model = _engine(monkeypatch, ["x" * 500, "next"])
    engine.translate(np.zeros(16000, dtype=np.float32))
    engine.translate(np.zeros(16000, dtype=np.float32))
    assert len(model.prompts[1]) <= config.CONTEXT_CHARS


def test_model_is_cached_and_evicted_on_change(monkeypatch):
    """Warm cache makes restarts instant; only ONE model is held (4 GB VRAM)."""
    import kakao.asr as asr_module

    built = []

    class _FakeWhisper:
        def __init__(self, name, device=None, compute_type=None):
            built.append(name)

    monkeypatch.setattr(asr_module, "_cached_key", None, raising=False)
    monkeypatch.setattr(asr_module, "_cached_model", None, raising=False)
    monkeypatch.setitem(
        __import__("sys").modules, "faster_whisper",
        type("M", (), {"WhisperModel": _FakeWhisper}),
    )

    first = asr_module.load_model("medium", "cuda", "int8")
    again = asr_module.load_model("medium", "cuda", "int8")
    assert again is first and built == ["medium"]      # reused, not reloaded

    other = asr_module.load_model("small", "cuda", "int8")
    assert other is not first and built == ["medium", "small"]  # evicted + reloaded


def test_repeated_output_is_suppressed(monkeypatch):
    """Prompting makes Whisper parrot the context back; don't show it twice."""
    engine, _ = _engine(monkeypatch, ["We are going to mix.", "we are going to mix!", "New line."])
    pcm = np.zeros(16000, dtype=np.float32)
    assert engine.translate(pcm) == "We are going to mix."
    assert engine.translate(pcm) == ""          # same line again -> suppressed
    assert engine.translate(pcm) == "New line."  # different line still passes
