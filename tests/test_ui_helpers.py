"""Tests for the pure helpers behind the UI (audit #16).

These need a QApplication for font metrics, so the suite runs Qt offscreen.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontMetrics  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kakao.overlay import Overlay  # noqa: E402
from kakao.ui import _humanize  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def metrics(qt_app):
    return QFontMetrics(QFont("Segoe UI", 28))


# -- _humanize: technical errors must reach the user in plain Spanish ---------

@pytest.mark.parametrize("raw", [
    "CUDA failed with error out of memory",
    "Library cublas64_12.dll is not found or cannot be loaded",
    "cudnn error",
])
def test_gpu_errors_suggest_a_smaller_model(raw):
    message = _humanize(raw)
    assert "GPU" in message or "CUDA" in message
    assert "small" in message  # tells the user what to actually do


@pytest.mark.parametrize("raw", [
    "device disconnected",
    "no loopback speaker found",
])
def test_audio_errors_point_at_the_output_device(raw):
    assert "dispositivo de audio" in _humanize(raw).lower()


def test_unknown_errors_are_passed_through():
    assert "algo raro" in _humanize("algo raro")


# -- Overlay._wrap ------------------------------------------------------------

def test_short_text_stays_on_one_line(metrics):
    assert Overlay._wrap("hola mundo", metrics, 10_000) == ["hola mundo"]


def test_long_text_is_split(metrics):
    lines = Overlay._wrap("palabra " * 40, metrics, 400)
    assert len(lines) > 1
    assert all(metrics.horizontalAdvance(line) <= 400 for line in lines)


def test_no_empty_lines_from_trailing_or_double_spaces(metrics):
    """An empty line would silently consume a line of vertical space (audit #14)."""
    for text in ("hola  mundo ", " hola", "hola\n\nmundo", "hola \n mundo "):
        assert all(line.strip() for line in Overlay._wrap(text, metrics, 10_000))


def test_words_are_never_lost(metrics):
    text = "the lawyer filed a preventive embargo against the company today"
    assert " ".join(Overlay._wrap(text, metrics, 300)).split() == text.split()
