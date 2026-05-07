import os, sys, json, tempfile, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.cache import CacheManager

@pytest.fixture
def cache(tmp_path):
    return CacheManager(path=str(tmp_path / "test.db"))

def test_save_and_load_roundtrip(cache):
    data = {"col_a": [1, 2, 3], "col_b": ["x", "y", "z"], "_ts": "2026-05-07T12:00:00"}
    cache.save("estoque", data)
    result = cache.load("estoque")
    assert result["col_a"] == [1, 2, 3]
    assert result["col_b"] == ["x", "y", "z"]
    assert result["_ts"] == "2026-05-07T12:00:00"

def test_load_missing_key_returns_none(cache):
    assert cache.load("nao_existe") is None

def test_overwrite_updates_value(cache):
    cache.save("vendas", {"x": [1]})
    cache.save("vendas", {"x": [9, 8]})
    assert cache.load("vendas")["x"] == [9, 8]

def test_status_lists_all_saved_names(cache):
    cache.save("dashboard", {"a": [1]})
    cache.save("crm", {"b": [2]})
    st = cache.status()
    assert "dashboard" in st
    assert "crm" in st

def test_status_includes_timestamp(cache):
    cache.save("financeiro", {"v": [5], "_ts": "2026-05-07T10:00:00"})
    st = cache.status()
    assert st["financeiro"]["ts"] == "2026-05-07T10:00:00"
