import os, sys, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from unittest.mock import patch

import core.cache as _cc

@pytest.fixture
def client(tmp_path):
    test_cache = _cc.CacheManager(path=str(tmp_path / "hub_test.db"))
    test_cache.save("estoque", {"itens": [1, 2], "_ts": "2026-05-07T12:00:00"})
    test_cache.save("vendas",  {"v": [9],        "_ts": "2026-05-07T11:00:00"})
    with patch("hub.server._cache", test_cache):
        from hub.server import app
        yield TestClient(app)

def test_status_returns_200(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "bots" in body
    assert "estoque" in body["bots"]

def test_dados_returns_cached_data(client):
    resp = client.get("/dados/estoque")
    assert resp.status_code == 200
    body = resp.json()
    assert body["itens"] == [1, 2]

def test_dados_missing_bot_returns_404(client):
    resp = client.get("/dados/crm")
    assert resp.status_code == 404

def test_dados_all_bots(client):
    for name in ("estoque", "vendas"):
        resp = client.get(f"/dados/{name}")
        assert resp.status_code == 200
