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


def test_corrupt_file_is_ignored(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert Settings(path).get("k", "d") == "d"
