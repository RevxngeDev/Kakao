from kakao.settings import Settings


def test_roundtrip_persists_across_instances(tmp_path):
    path = tmp_path / "s.json"
    s = Settings(path)
    assert s.get("x", 5) == 5           # default when missing
    s.set("x", 42)
    assert Settings(path).get("x") == 42  # persisted to disk


def test_missing_file_returns_defaults(tmp_path):
    s = Settings(tmp_path / "nope.json")
    assert s.get("k") is None
    assert s.get("k", "d") == "d"


def test_corrupt_file_is_set_aside_not_silently_dropped(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")

    assert Settings(path).get("k", "d") == "d"          # falls back to defaults
    assert path.with_suffix(".json.corrupt").exists()   # but the bad file is kept
    assert not path.exists()


def test_update_writes_once(tmp_path, monkeypatch):
    """A dialog saving four fields must not hit the disk four times."""
    path = tmp_path / "s.json"
    settings = Settings(path)
    writes = []
    original = Settings._write
    monkeypatch.setattr(
        Settings, "_write", lambda self: (writes.append(1), original(self))[1]
    )

    settings.update({"a": 1, "b": 2, "c": 3, "d": 4})

    assert len(writes) == 1
    assert Settings(path).get("c") == 3


def test_write_leaves_no_temp_file_behind(tmp_path):
    path = tmp_path / "s.json"
    Settings(path).set("x", 1)
    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()
