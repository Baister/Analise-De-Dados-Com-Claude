# tests/test_hub_api.py
import os
import sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from unittest.mock import patch

import core.cache as _cc

SENHA_TESTE = "senha-de-teste-unitario-abc"


@pytest.fixture
def client(tmp_path):
    test_cache = _cc.CacheManager(path=str(tmp_path / "hub_test.db"))
    test_cache.save("estoque", {"itens": [1, 2], "_ts": "2026-05-07T12:00:00"})
    test_cache.save("vendas",  {"v": [9],        "_ts": "2026-05-07T11:00:00"})
    with patch("hub.server._cache", test_cache), \
         patch("hub.server.DASHBOARD_PASSWORD", SENHA_TESTE, create=True):
        import hub.server as _srv
        _srv._tokens.clear()
        yield TestClient(_srv.app)


def _token(client: TestClient) -> str:
    resp = client.post("/auth", json={"password": SENHA_TESTE})
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    return resp.json()["access_token"]


# ── Auth ──────────────────────────────────────────────────────────────

def test_auth_correct_password(client):
    resp = client.post("/auth", json={"password": SENHA_TESTE})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_auth_wrong_password(client):
    resp = client.post("/auth", json={"password": "errada"})
    assert resp.status_code == 400


# ── Endpoints protegidos — sem token devem retornar 403 ──────────────

def test_status_requires_auth(client):
    resp = client.get("/status")
    assert resp.status_code in (401, 403)


def test_dados_requires_auth(client):
    resp = client.get("/dados/estoque")
    assert resp.status_code in (401, 403)


def test_stream_requires_auth(client):
    resp = client.get("/stream")
    assert resp.status_code in (401, 403)


def test_config_requires_auth(client):
    resp = client.get("/config")
    assert resp.status_code in (401, 403)


def test_dados_cliente_requires_auth(client):
    resp = client.get("/dados/cliente")
    assert resp.status_code in (401, 403)


# ── Endpoints com token válido ────────────────────────────────────────

def test_status_with_token(client):
    tok = _token(client)
    resp = client.get("/status", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 200
    assert "bots" in resp.json()


def test_dados_with_token(client):
    tok = _token(client)
    resp = client.get("/dados/estoque", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 200
    assert resp.json()["itens"] == [1, 2]


def test_dados_missing_bot_returns_404(client):
    tok = _token(client)
    resp = client.get("/dados/crm", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 404


# ── Root ──────────────────────────────────────────────────────────────

def test_root_returns_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Novos endpoints — Task 1 ──────────────────────────────────────────

def test_stream_with_query_token(client):
    resp = client.post("/auth", json={"password": SENHA_TESTE})
    tok = resp.json()["access_token"]
    # EventSource passa token como query param.
    # Patchamos o generator para terminar após um ping, evitando hang do stream infinito.
    async def _one_shot_gen(_q):
        yield "event: ping\ndata: {}\n\n"

    with patch("hub.server._sse_generator", _one_shot_gen):
        resp2 = client.get(f"/stream?token={tok}")
    assert resp2.status_code == 200

def test_config_with_token(client):
    tok = _token(client)
    resp = client.get("/config", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "meta_faturamento_mensal" in body
    assert isinstance(body["meta_faturamento_mensal"], (int, float))

def test_dados_cliente_with_token(client):
    tok = _token(client)
    resp = client.get("/dados/cliente", headers={"Authorization": f"Bearer {tok}"})
    # Aceita 200 (dados) ou 503 (sem DB em testes unitários)
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        body = resp.json()
        assert "kpis" in body
        assert "top_clientes" in body
        assert "por_marca" in body
        assert "detalhe" in body
