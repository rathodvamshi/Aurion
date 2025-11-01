# backend/app/services/news_service.py

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.services import redis_service
from app.services.http_client import get_async_client


_BASE_TOP_HEADLINES = "https://newsapi.org/v2/top-headlines"

# Reuse a single HTTP client for connection pooling/keep-alive
_HTTP_CLIENT: Optional[httpx.AsyncClient] = None
_INFLIGHT: dict[str, asyncio.Task] = {}

_CATEGORY_MAP = {
    "technology": "technology",
    "tech": "technology",
    "business": "business",
    "sports": "sports",
    "sport": "sports",
    "entertainment": "entertainment",
    "science": "science",
    "health": "health",
    "general": "general",
}


def _norm_topic(topic: Optional[str]) -> Optional[str]:
    if not topic:
        return None
    t = topic.strip().lower()
    return _CATEGORY_MAP.get(t, t)


def _norm_country(country: Optional[str]) -> Optional[str]:
    if not country:
        return None
    c = country.strip().lower()
    # accept 2-letter codes like us, in, gb, au, ca, de, fr, it, es, jp, cn, ru, br etc.
    if len(c) == 2:
        return c
    # common names
    name_map = {
        "united states": "us",
        "usa": "us",
        "us": "us",
        "india": "in",
        "indian": "in",
        "uk": "gb",
        "united kingdom": "gb",
        "england": "gb",
    }
    return name_map.get(c, None)


async def _http_get_json(url: str, params: Dict[str, Any], headers: Dict[str, str], timeout: float = 6.0, retry: bool = True) -> Dict[str, Any]:
    client = get_async_client()
    try:
        r = await client.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except (httpx.TimeoutException, httpx.ConnectError):
        if retry:
            await asyncio.sleep(0.35)
            return await _http_get_json(url, params, headers, timeout=timeout, retry=False)
        raise


async def get_news(topic: Optional[str], country: Optional[str], *, page: int = 1, page_size: int = 3, session_key: Optional[str] = None) -> Dict[str, Any]:
    """Fetch top headlines for a topic and optional country.

    Returns dict:
      {"ok": bool, "data": {"topic": str, "country": str | None, "headlines": [{"title","source"}...] } | None, "error": str | None}
    """
    api_key = settings.NEWS_API_KEY
    if not api_key:
        return {"ok": False, "data": None, "error": "news_api_unconfigured"}

    topic_n = _norm_topic(topic) or "general"
    country_n = _norm_country(country)

    cache_key = f"news:v1:{topic_n}:{country_n or 'any'}"
    try:
        cached = await redis_service.get_prefetched_data(cache_key)
    except Exception:
        cached = None
    if cached:
        return {"ok": True, "data": cached, "error": None}

    # Singleflight: coalesce concurrent identical requests by cache key
    if cache_key in _INFLIGHT:
        try:
            return await _INFLIGHT[cache_key]
        except Exception:
            pass

    params: Dict[str, Any] = {"pageSize": 5}
    if country_n:
        params["country"] = country_n
    if topic_n:
        params["category"] = topic_n

    headers = {"X-Api-Key": api_key}
    async def _compute() -> Dict[str, Any]:
        try:
            payload = await _http_get_json(_BASE_TOP_HEADLINES, params=params, headers=headers)
            if payload.get("status") != "ok":
                return {"ok": False, "data": None, "error": "api_error"}
            articles = payload.get("articles") or []
            # Basic pagination: compute slice based on page/page_size; persist last page in Redis when session_key provided
            start = max(0, (page - 1) * page_size)
            stop = start + page_size
            slice_articles = articles[start:stop]
            headlines: List[Dict[str, str]] = []
            for a in slice_articles:
                title = a.get("title") or ""
                source = (a.get("source") or {}).get("name") or ""
                if title:
                    headlines.append({"title": title.strip(), "source": source.strip()})
            data = {"topic": topic_n, "country": country_n, "headlines": headlines, "page": page}
            # Store last page for session if provided to support "show more"
            try:
                if session_key:
                    await redis_service.set_prefetched_data(f"news:last:{session_key}", {"topic": topic_n, "country": country_n, "page": page}, ttl_seconds=900)
            except Exception:
                pass
            await redis_service.set_prefetched_data(cache_key, data, ttl_seconds=300)
            return {"ok": True, "data": data, "error": None}
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if getattr(e, "response", None) else 0
            return {"ok": False, "data": None, "error": f"http_{status}"}
        except Exception:
            return {"ok": False, "data": None, "error": "unknown"}

    task = asyncio.create_task(_compute())
    _INFLIGHT[cache_key] = task
    try:
        return await task
    finally:
        _INFLIGHT.pop(cache_key, None)


__all__ = ["get_news"]
