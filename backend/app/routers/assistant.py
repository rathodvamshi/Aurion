# backend/app/routers/assistant.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.security import get_current_active_user
from app.services import redis_service
from app.services.weather_service import get_weather
from app.services.news_service import get_news
from dateutil.relativedelta import relativedelta, MO


router = APIRouter(prefix="/api/assistant", tags=["Assistant"])


class QueryBody(BaseModel):
    message: str


# Short-term session context keys in Redis
def _ctx_key(user_id: str) -> str:
    return f"assistant:ctx:{user_id}"


async def _get_ctx(user_id: str) -> Dict[str, Any]:
    try:
        ctx = await redis_service.get_prefetched_data(_ctx_key(user_id))
        return ctx or {}
    except Exception:
        return {}


async def _set_ctx(user_id: str, data: Dict[str, Any]):
    try:
        await redis_service.set_prefetched_data(_ctx_key(user_id), data, ttl_seconds=900)
    except Exception:
        pass


def _detect_intent(text: str) -> str:
    t = text.lower()
    # Weather cues
    weather_words = [
        "weather", "temperature", "rain", "snow", "forecast", "hot", "cold", "sunny", "cloudy",
    ]
    if any(w in t for w in weather_words):
        return "weather"
    # News cues
    news_words = ["news", "headlines", "updates", "breaking", "newspaper"]
    if any(w in t for w in news_words):
        return "news"
    return "general"


def _extract_city_and_date(text: str) -> tuple[Optional[str], Optional[str]]:
    # very lightweight heuristics; city remains None if not obvious
    t = text.strip()
    low = t.lower()
    date: Optional[str] = None
    if "tomorrow" in low:
        date = "tomorrow"
    elif "day after" in low or "day-after" in low:
        date = "day after tomorrow"
    elif any(w in low for w in ["today", "now", "currently"]):
        date = "today"
    # Specific time-of-day hints
    hour_hint = None
    if any(p in low for p in ["morning", "morn"]):
        hour_hint = 9
    elif any(p in low for p in ["afternoon", "noon"]):
        hour_hint = 15
    elif any(p in low for p in ["evening", "night"]):
        hour_hint = 20

    # Try pattern: in <City> / at <City> / for <City>
    import re
    m = re.search(r"\b(?:in|at|for)\s+([A-Za-z .-]{2,})$", t)
    city = m.group(1).strip() if m else None
    # Or pattern: weather in X
    if not city:
        m2 = re.search(r"weather\s+in\s+([A-Za-z .-]{2,})", low)
        if m2:
            city = t[m2.start(1): m2.end(1)].strip()
    return city, date


def _extract_topic_and_country(text: str) -> tuple[Optional[str], Optional[str]]:
    t = text.lower()
    topic = None
    for w in ["technology", "tech", "business", "sports", "entertainment", "science", "health", "general"]:
        if w in t:
            topic = w
            break
    # country 2-letter hints like US, IN, GB
    import re
    m = re.search(r"\b(us|in|gb|uk|au|ca|de|fr|it|es|jp|cn|ru|br)\b", t)
    country = m.group(1).lower() if m else None
    if country == "uk":
        country = "gb"
    # phrases like 'us news', 'indian news'
    if not country:
        if "us news" in t or "american" in t:
            country = "us"
        elif "indian" in t:
            country = "in"
    return topic, country


def _format_weather_reply(data: Dict[str, Any], when: str) -> str:
    city = data.get("city") or ""
    temp = data.get("temp_c")
    cond = data.get("condition") or ""
    hum = data.get("humidity")
    wind = data.get("wind_kmh")
    low = data.get("low_c")
    high = data.get("high_c")
    summary = f"Here’s the {('current' if when=='today' else when)} weather for {city}:"
    lines = [summary]
    if when == "today":
        lines.append(f"🌤️ {city}: {temp}°C, {cond}.")
        lines.append(f"💧 Humidity: {hum}% | 🌬️ Wind: {wind} km/h")
    else:
        lines.append(f"🌤️ {city}: {temp}°C, {cond}.")
        if high is not None and low is not None:
            lines.append(f"Tomorrow’s forecast: {high}°C high, {low}°C low.")
        if hum is not None or wind is not None:
            lines.append(f"💧 Humidity: {hum}% | 🌬️ Wind: {wind} km/h")
        if data.get("rain_chance_pct") is not None:
            lines.append(f"☔ Chance of rain: {data['rain_chance_pct']}%")
    lines.append("Would you like tomorrow’s forecast too?")
    return "\n".join(lines)


def _format_news_reply(data: Dict[str, Any]) -> str:
    topic = data.get("topic")
    country = data.get("country")
    title = f"🗞️ Latest {topic.title() if topic else 'General'} Headlines"
    if country:
        title += f" ({country.upper()})"
    lines = [title + ":"]
    headlines = data.get("headlines") or []
    if not headlines:
        return "I couldn’t find fresh headlines right now — please try again shortly."
    badges = ["1️⃣", "2️⃣", "3️⃣"]
    for i, h in enumerate(headlines[:3]):
        lines.append(f"{badges[i]} {h.get('title')} — {h.get('source')}")
    lines.append("Want me to show global headlines?")
    return "\n".join(lines)


def _normalize_natural_date(text: str) -> Optional[str]:
    """Map natural phrases to an ISO-like date or datetime string to pass to weather_service.
    Supports: next weekend, in N days, next Monday, tomorrow morning, etc.
    """
    low = text.lower()
    now = datetime.now()
    # in N days
    import re
    m = re.search(r"in\s+(\d+)\s+days?", low)
    if m:
        d = int(m.group(1))
        dt = now + timedelta(days=d)
        return dt.strftime("%Y-%m-%d")
    # next weekend -> pick Saturday
    if "next weekend" in low:
        # Move to next Saturday from now
        days_ahead = (5 - now.weekday()) % 7  # Saturday index 5
        if days_ahead == 0:
            days_ahead = 7
        saturday = now + timedelta(days=days_ahead)
        return saturday.strftime("%Y-%m-%d")
    # next <weekday>
    for idx, name in enumerate(["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]):
        if f"next {name}" in low:
            # relativedelta to next weekday
            target = now + relativedelta(weekday=getattr(__import__('dateutil.relativedelta').relativedelta, name[:2].upper())(+1))
            return target.strftime("%Y-%m-%d")
    # tomorrow morning/afternoon/evening -> set specific hours
    hour = None
    if "morning" in low:
        hour = 9
    elif "afternoon" in low or "noon" in low:
        hour = 15
    elif "evening" in low or "night" in low:
        hour = 20
    if "tomorrow" in low and hour is not None:
        dt = (now + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
        return dt.strftime("%Y-%m-%d %H:%M")
    return None


@router.post("/query")
async def assistant_query(body: QueryBody, current_user: dict = Depends(get_current_active_user)):
    text = (body.message or "").strip()
    user_id = str(current_user.get("user_id") or current_user.get("_id"))
    ctx = await _get_ctx(user_id)

    intent = _detect_intent(text)

    # Combined requests: both words appear
    low = text.lower()
    is_weather = intent == "weather"
    is_news = intent == "news"
    if ("news" in low and "weather" in low) or (is_weather and is_news):
        # Fetch weather and news in parallel for lower latency
        city, date = _extract_city_and_date(text)
        if not city:
            return {
                "message": "Fetching latest updates... please wait a moment ☁️",
                "reply": "Which city should I check the weather for?",
            }
        date_norm = _normalize_natural_date(text) or date
        topic, country = _extract_topic_and_country(text)
        import asyncio as _asyncio
        weather_task = get_weather(city, date_norm)
        news_task = get_news(topic, country, session_key=user_id)
        w, n = await _asyncio.gather(weather_task, news_task, return_exceptions=False)
        weather_part = (
            _format_weather_reply(w["data"], (date or "today").lower()) if w.get("ok") and w.get("data") else
            "I couldn’t fetch weather data right now — please check the city name or try again shortly."
        )
        news_part = (
            _format_news_reply(n["data"]) if n.get("ok") and n.get("data") else
            "I’m having trouble connecting to the news source right now. Please try again later."
        )
        ctx.update({"last_intent": "weather", "last_city": city, "last_date": date or "today"})
        ctx.update({"last_news_topic": topic or "general", "last_country": country})
        await _set_ctx(user_id, ctx)
        return {
            "message": "Fetching latest updates... please wait a moment ☁️",
            "reply": weather_part + "\n\n" + news_part,
        }

    if intent == "weather":
        city, date = _extract_city_and_date(text)
        if not city:
            return {"message": "Fetching latest updates... please wait a moment ☁️", "reply": "Which city should I check the weather for?"}
        date_kw = (date or "today").lower()
        date_norm = _normalize_natural_date(text) or date_kw
        w = await get_weather(city, date_norm)
        if not w.get("ok"):
            if w.get("error") in {"city_not_found", "missing_city"}:
                reply = "Hmm, I couldn’t find weather data for that city. Could you double-check the name?"
            else:
                reply = "I couldn’t fetch weather data right now — please check the city name or try again shortly."
        else:
            reply = _format_weather_reply(w["data"], date_kw)
        ctx.update({"last_intent": "weather", "last_city": city, "last_date": date_kw})
        await _set_ctx(user_id, ctx)
        return {"message": "Fetching latest updates... please wait a moment ☁️", "reply": reply}

    if intent == "news":
        topic, country = _extract_topic_and_country(text)
        if not topic:
            return {"message": "Fetching latest updates... please wait a moment ☁️", "reply": "Do you want general news or a specific category like tech, sports, or business?"}
        n = await get_news(topic, country, session_key=user_id)
        if not n.get("ok"):
            reply = "I’m having trouble connecting to the news source right now. Please try again later."
        else:
            reply = _format_news_reply(n["data"])
        ctx.update({"last_intent": "news", "last_news_topic": topic, "last_country": country})
        await _set_ctx(user_id, ctx)
        return {"message": "Fetching latest updates... please wait a moment ☁️", "reply": reply}

    # Context carry-over
    # e.g., "And tomorrow?" after weather
    low = text.lower()
    if "tomorrow" in low and ctx.get("last_intent") == "weather" and ctx.get("last_city"):
        city = ctx.get("last_city")
        w = await get_weather(city, "tomorrow")
        reply = (
            _format_weather_reply(w["data"], "tomorrow") if w.get("ok") and w.get("data") else
            "I couldn’t fetch weather data right now — please try again shortly."
        )
        ctx.update({"last_date": "tomorrow"})
        await _set_ctx(user_id, ctx)
        return {"message": "Fetching latest updates... please wait a moment ☁️", "reply": reply}

    if ("any updates" in low or "updates?" in low) and ctx.get("last_intent") == "news":
        topic = ctx.get("last_news_topic") or "general"
        country = ctx.get("last_country")
        n = await get_news(topic, country, session_key=user_id)
        reply = (
            _format_news_reply(n["data"]) if n.get("ok") and n.get("data") else
            "I’m having trouble connecting to the news source right now. Please try again later."
        )
        return {"message": "Fetching latest updates... please wait a moment ☁️", "reply": reply}

    # Show more: paginate news by fetching next page
    if "show more" in low and (ctx.get("last_intent") == "news" or ctx.get("last_news_topic")):
        last = await redis_service.get_prefetched_data(f"news:last:{user_id}") or {}
        topic = last.get("topic") or ctx.get("last_news_topic") or "general"
        country = last.get("country") or ctx.get("last_country")
        page = int(last.get("page") or 1) + 1
        n = await get_news(topic, country, page=page, session_key=user_id)
        if not n.get("ok"):
            return {"message": "Fetching latest updates... please wait a moment ☁️", "reply": "I’m having trouble connecting to the news source right now. Please try again later."}
        return {"message": "Fetching latest updates... please wait a moment ☁️", "reply": _format_news_reply(n["data"]) }

    # General small talk fallback (keep it simple here; the main chat router handles rich AI)
    return {
        "message": "",
        "reply": "Got it! How can I help you today? You can ask for weather or news too.",
    }
