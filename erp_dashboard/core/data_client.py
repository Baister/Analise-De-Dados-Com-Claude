import logging
import requests

from config.settings import HUB_URL
from core.cache import CacheManager, cache as _default_cache


class DataClient:
    def __init__(self, hub_url: str | None = None, cache: CacheManager | None = None):
        self._hub_url = (hub_url or HUB_URL).rstrip("/")
        self._cache = cache or _default_cache

    def fetch(self, bot_name: str) -> dict | None:
        url = f"{self._hub_url}/dados/{bot_name}"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return resp.json()
            logging.warning("Hub returned %s for %s", resp.status_code, bot_name)
        except requests.exceptions.RequestException as exc:
            logging.warning("Hub unreachable (%s), falling back to cache", exc)
        return self._cache.load(bot_name)


# module-level singleton for app use
data_client = DataClient()
