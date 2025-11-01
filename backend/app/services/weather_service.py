# backend/app/services/weather_service.py

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
from dateutil import parser as dtparser

from app.config import settings
from app.services import redis_service
from app.services.http_client import get_async_client


_BASE_CURRENT = "https://api.openweathermap.org/data/2.5/weather"
_BASE_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"  # 3-hourly

# Reuse a single HTTP client for connection pooling/keep-alive (cuts ~50-150ms TCP/TLS per call)
_HTTP_CLIENT: Optional[httpx.AsyncClient] = None
_INFLIGHT: dict[str, asyncio.Task] = {}


def _norm_date_keyword(date: Optional[str]) -> str:
    if not date:
        return "today"
    d = date.strip().lower()
    if d in {"today", "now", "current"}:
        return "today"
    if d in {"tomorrow", "tmrw"}:
        return "tomorrow"
    if d in {"day after tomorrow", "day-after-tomorrow", "dat"}:
        return "day_after"
    return d


async def _http_get_json(url: str, params: Dict[str, Any], timeout: float = 6.0, retry: bool = True) -> Dict[str, Any]:
    client = get_async_client()
    try:
        r = await client.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except (httpx.TimeoutException, httpx.ConnectError):
        if retry:
            await asyncio.sleep(0.35)
            return await _http_get_json(url, params, timeout=timeout, retry=False)
        raise


def _select_forecast_bucket(forecast: Dict[str, Any], target_dt: datetime, prefer_hour: Optional[int] = None) -> Optional[Dict[str, Any]]:
    # OpenWeather 5-day forecast in 3h buckets; pick the closest bucket to desired time (default noon)
    lst = forecast.get("list") or []
    if not lst:
        return None
    hour = 12 if prefer_hour is None else int(prefer_hour)
    target_time = target_dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    best = None
    best_delta = None
    for entry in lst:
        ts = entry.get("dt")
        if ts is None:
            continue
        dt = datetime.fromtimestamp(ts)
        # only consider same date as target
        if dt.date() != target_time.date():
            continue
        delta = abs((dt - target_time).total_seconds())
        if best is None or delta < best_delta:  # type: ignore[arg-type]
            best = entry
            best_delta = delta
    return best


def _format_current(payload: Dict[str, Any]) -> Dict[str, Any]:
    main = payload.get("main") or {}
    weather = (payload.get("weather") or [{}])[0]
    wind = payload.get("wind") or {}
    name = payload.get("name")
    return {
        "city": name,
        "temp_c": round((main.get("temp") or 0) - 273.15, 1),
        "condition": (weather.get("description") or "").title(),
        "humidity": main.get("humidity"),
        "wind_kmh": round((wind.get("speed") or 0) * 3.6, 1),
    }


def _format_bucket(city: str, bucket: Dict[str, Any]) -> Dict[str, Any]:
    main = bucket.get("main") or {}
    weather = (bucket.get("weather") or [{}])[0]
    wind = bucket.get("wind") or {}
    temp_c = round((main.get("temp") or 0) - 273.15, 1)
    temp_min_c = round((main.get("temp_min") or 0) - 273.15, 1)
    temp_max_c = round((main.get("temp_max") or 0) - 273.15, 1)
    rain_prob = (bucket.get("pop") or 0) * 100
    return {
        "city": city,
        "temp_c": temp_c,
        "low_c": temp_min_c,
        "high_c": temp_max_c,
        "condition": (weather.get("description") or "").title(),
        "humidity": main.get("humidity"),
        "wind_kmh": round((wind.get("speed") or 0) * 3.6, 1),
        "rain_chance_pct": int(rain_prob),
    }


async def get_weather(city: str, date: Optional[str] = None) -> Dict[str, Any]:
    """Fetch current or near-term forecast for a given city.

    Returns dict:
      {"ok": bool, "data": {...} | None, "error": str | None}
    """
    api_key = settings.WEATHER_API_KEY
    if not api_key:
        return {"ok": False, "data": None, "error": "weather_api_unconfigured"}

    if not city:
        return {"ok": False, "data": None, "error": "missing_city"}
    city = city.strip()
    key = f"weather:v1:{city}:{_norm_date_keyword(date)}"

    # quick cache
    try:
        cached = await redis_service.get_prefetched_data(key)
    except Exception:
        cached = None
    if cached:
        return {"ok": True, "data": cached, "error": None}

    # Singleflight: coalesce concurrent identical requests by cache key
    if key in _INFLIGHT:
        try:
            return await _INFLIGHT[key]
        except Exception:
            # If waiting task failed, fall through to fresh attempt
            pass

    async def _compute() -> Dict[str, Any]:
        try:
            when = _norm_date_keyword(date)
            if when == "today":
                payload = await _http_get_json(_BASE_CURRENT, {"q": city, "appid": api_key})
                data = _format_current(payload)
                await redis_service.set_prefetched_data(key, data, ttl_seconds=600)
                return {"ok": True, "data": data, "error": None}

            # Tomorrow / Day after -> use 5-day forecast buckets
            if when in ("tomorrow", "day_after"):
                offset_days = 1 if when == "tomorrow" else 2
                target_dt = datetime.now().replace(tzinfo=None) + timedelta(days=offset_days)
                forecast = await _http_get_json(_BASE_FORECAST, {"q": city, "appid": api_key})
                city_name = (forecast.get("city") or {}).get("name") or city
                bucket = _select_forecast_bucket(forecast, target_dt)
                if not bucket:
                    return {"ok": False, "data": None, "error": "no_forecast"}
                data = _format_bucket(city_name, bucket)
                await redis_service.set_prefetched_data(key, data, ttl_seconds=600)
                return {"ok": True, "data": data, "error": None}

            # Otherwise attempt to parse explicit ISO date/datetime
            try:
                target_dt = dtparser.parse(when)
            except Exception:
                target_dt = None
            if target_dt is None:
                # Unknown keyword; fallback to current as safe default
                payload = await _http_get_json(_BASE_CURRENT, {"q": city, "appid": api_key})
                data = _format_current(payload)
                await redis_service.set_prefetched_data(key, data, ttl_seconds=600)
                return {"ok": True, "data": data, "error": None}
            # Determine hour hint if provided (from datetime); else None -> noon
            prefer_hour = target_dt.hour if isinstance(target_dt, datetime) else None
            forecast = await _http_get_json(_BASE_FORECAST, {"q": city, "appid": api_key})
            city_name = (forecast.get("city") or {}).get("name") or city
            bucket = _select_forecast_bucket(forecast, target_dt, prefer_hour=prefer_hour)
            if not bucket:
                return {"ok": False, "data": None, "error": "no_forecast"}
            data = _format_bucket(city_name, bucket)
            await redis_service.set_prefetched_data(key, data, ttl_seconds=600)
            return {"ok": True, "data": data, "error": None}
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if getattr(e, "response", None) else 0
            if status == 404:
                return {"ok": False, "data": None, "error": "city_not_found"}
            return {"ok": False, "data": None, "error": f"http_{status}"}
        except Exception:
            return {"ok": False, "data": None, "error": "unknown"}

    task = asyncio.create_task(_compute())
    _INFLIGHT[key] = task
    try:
        return await task
    finally:
        _INFLIGHT.pop(key, None)


__all__ = ["get_weather"]
