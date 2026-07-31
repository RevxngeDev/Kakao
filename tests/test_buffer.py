import pytest

from kakao.buffer import DropOldestQueue


def test_fifo_order():
    q: DropOldestQueue[int] = DropOldestQueue(maxsize=3)
    q.put(1)
    q.put(2)
    assert q.get() == 1
    assert q.get() == 2


def test_drops_oldest_when_full():
    q: DropOldestQueue[int] = DropOldestQueue(maxsize=2)
    q.put(1)
    q.put(2)
    q.put(3)  # 1 is dropped
    assert len(q) == 2
    assert q.dropped == 1
    assert q.get() == 2
    assert q.get() == 3


def test_get_timeout_returns_none_when_empty():
    q: DropOldestQueue[int] = DropOldestQueue(maxsize=1)
    assert q.get(timeout=0.01) is None


def test_maxsize_must_be_positive():
    with pytest.raises(ValueError):
        DropOldestQueue(maxsize=0)
