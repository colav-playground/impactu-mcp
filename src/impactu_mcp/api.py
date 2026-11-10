"""Small async client for the ImpactU API, with a cache and a limit on concurrent requests."""
import asyncio
import os
import time
from urllib.parse import quote

import httpx

API_BASE = os.environ.get("IMPACTU_API_BASE", "https://api.dev.impactu.colav.co").rstrip("/")
TIMEOUT = float(os.environ.get("IMPACTU_TIMEOUT", "90"))
CACHE_TTL = float(os.environ.get("IMPACTU_CACHE_TTL", "600"))
CACHE_SIZE = int(os.environ.get("IMPACTU_CACHE_SIZE", "2000"))
MAX_CONCURRENCY = int(os.environ.get("IMPACTU_MAX_CONCURRENCY", "8"))
USER_AGENT = "impactu-mcp/0.1 (+https://mcp.impactu.colav.co)"


class ApiError(Exception):
    """An error to show to the model: a bad parameter, an unknown id, or the API being down."""


def seg(value: str) -> str:
    """Quote one path segment."""
    return quote(str(value).strip(), safe="")


class ImpactUClient:
    def __init__(self, base: str = API_BASE):
        self.base = base
        self._client: httpx.AsyncClient | None = None
        self._sem = asyncio.Semaphore(MAX_CONCURRENCY)
        self._cache: dict[str, tuple[float, object]] = {}

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
            )
        return self._client

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, path: str, params: dict | None = None):
        params = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
        key = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL:
            return hit[1]
        async with self._sem:
            try:
                r = await self._http().get(path, params=params)
            except httpx.TimeoutException:
                raise ApiError("The ImpactU API did not answer in time. Try a smaller page or fewer filters.")
            except httpx.HTTPError as e:
                raise ApiError(f"Could not reach the ImpactU API: {type(e).__name__}")
        if r.status_code == 404:
            raise ApiError("Not found in ImpactU (unknown id or route).")
        is_json = r.headers.get("content-type", "").startswith("application/json")
        if r.status_code >= 400:
            msg = r.json().get("error") if is_json and isinstance(r.json(), dict) else r.text[:200]
            raise ApiError(f"ImpactU API error {r.status_code}: {msg}")
        if not is_json:
            raise ApiError(f"Unexpected response from the ImpactU API ({r.headers.get('content-type')}).")
        data = r.json()
        if len(self._cache) >= CACHE_SIZE:
            for k in list(self._cache)[: CACHE_SIZE // 4]:
                del self._cache[k]
        self._cache[key] = (time.monotonic(), data)
        return data
