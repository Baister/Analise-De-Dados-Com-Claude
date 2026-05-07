import os, sys, json, pytest
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.data_client import DataClient
from core.cache import CacheManager

@pytest.fixture
def dc(tmp_path):
    c = CacheManager(path=str(tmp_path / "dc_test.db"))
    return DataClient(hub_url="http://hub:8765", cache=c)

def test_fetch_returns_hub_data_when_reachable(dc):
    payload = {"itens": [1, 2], "_ts": "2026-05-07T12:00:00"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    with patch("core.data_client.requests.get", return_value=mock_resp) as m:
        result = dc.fetch("estoque")
    assert result == payload
    m.assert_called_once_with("http://hub:8765/dados/estoque", timeout=5)

def test_fetch_falls_back_to_cache_on_connection_error(dc):
    dc._cache.save("estoque", {"itens": [9], "_ts": "2026-05-07T10:00:00"})
    import requests as req
    with patch("core.data_client.requests.get", side_effect=req.exceptions.ConnectionError):
        result = dc.fetch("estoque")
    assert result["itens"] == [9]

def test_fetch_falls_back_to_cache_on_non_200(dc):
    dc._cache.save("vendas", {"v": [7]})
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch("core.data_client.requests.get", return_value=mock_resp):
        result = dc.fetch("vendas")
    assert result["v"] == [7]

def test_fetch_returns_none_when_hub_down_and_no_cache(dc):
    import requests as req
    with patch("core.data_client.requests.get", side_effect=req.exceptions.ConnectionError):
        result = dc.fetch("crm")
    assert result is None
