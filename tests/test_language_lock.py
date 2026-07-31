from kakao.asr import _LanguageLock


def test_locks_after_consistent_high_prob_detections():
    lk = _LanguageLock(min_prob=0.6, min_count=3)
    lk.update("es", 0.9)
    lk.update("es", 0.8)
    assert lk.locked is None
    lk.update("es", 0.7)
    assert lk.locked == "es"


def test_ignores_low_probability_detections():
    lk = _LanguageLock(min_prob=0.6, min_count=2)
    lk.update("zh", 0.3)   # noisy/music misfire -> ignored
    lk.update("zh", 0.4)
    assert lk.locked is None


def test_stays_locked_once_set():
    lk = _LanguageLock(min_prob=0.6, min_count=1)
    lk.update("es", 0.9)
    assert lk.locked == "es"
    lk.update("en", 0.99)  # later misfire does not override
    assert lk.locked == "es"
