from __future__ import annotations

import httpx
from typing import Optional

# Shared async HTTP client for connection pooling and HTTP/2
# Keep limits conservative to avoid overload; tune if needed.
_limits = httpx.Limits(max_keepalive_connections=100, max_connections=200)
_async_client: Optional[httpx.AsyncClient] = None


def get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(
            http2=True,
            limits=_limits,
            timeout=httpx.Timeout(connect=2.0, read=4.0, write=4.0),
            headers={"Connection": "keep-alive"},
        )
    return _async_client


async def close_async_client() -> None:
    global _async_client
    if _async_client is not None:
        try:
            await _async_client.aclose()
        except Exception:
            pass
        _async_client = None


__all__ = ["get_async_client", "close_async_client"]
