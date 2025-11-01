# backend/app/services/redis_service.py

import redis.asyncio as redis
import json
import logging
from typing import Optional, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

# =====================================================
# 🔹 Redis Client Initialization (supports Redis Cloud)
# =====================================================
redis_client = None

def get_client():
    global redis_client
    if redis_client is not None:
        return redis_client
    try:
        # Prefer REDIS_URL for Redis Cloud (e.g., rediss://:pass@host:6380/0)
        if settings.REDIS_URL:
            redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("✅ Redis client created from REDIS_URL.")
            return redis_client

        # Fallback to host/port config (enable TLS with REDIS_TLS=True for Redis Cloud)
        redis_pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            ssl=True if getattr(settings, "REDIS_TLS", False) else False,
            decode_responses=True,
        )
        redis_client = redis.Redis(connection_pool=redis_pool)
        logger.info("✅ Redis connection pool created (host/port mode).")
    except Exception as e:
        logger.error(f"❌ Failed to create Redis client: {e}")
        redis_client = None
    return redis_client

async def ping() -> bool:
    try:
        client = get_client()
        if not client:
            return False
        return bool(await client.ping())
    except Exception:
        return False

# =====================================================
# 🔹 Session State Management
# =====================================================
async def get_session_state(session_id: str) -> str:
    """
    Retrieve the current state of a conversation session.
    Returns 'initial_greeting' if no state is found or Redis is unavailable.
    """
    client = get_client()
    if not client:
        return "initial_greeting"

    state_key = f"session:state:{session_id}"
    try:
        state = await client.get(state_key)
        return state if state else "initial_greeting"
    except Exception as e:
        logger.error(f"Failed to get session state for {session_id}: {e}")
        return "initial_greeting"


async def set_session_state(session_id: str, state: str, ttl_seconds: int = 86400):
    """
    Set or update the state of a conversation session in Redis.
    """
    client = get_client()
    if not client:
        return

    state_key = f"session:state:{session_id}"
    try:
        await client.set(state_key, state, ex=ttl_seconds)
    except Exception as e:
        logger.error(f"Failed to set session state for {session_id}: {e}")


# =====================================================
# 🔹 Prefetched Data Caching
# =====================================================
async def set_prefetched_data(cache_key: str, data: Dict[str, Any], ttl_seconds: int = 900):
    """
    Store prefetched or frequently accessed data in Redis with a TTL.
    """
    client = get_client()
    if not client:
        return

    try:
        json_data = json.dumps(data)
        await client.set(cache_key, json_data, ex=ttl_seconds)
        logger.debug(f"Prefetched data cached key={cache_key} ttl={ttl_seconds}")
    except Exception as e:
        logger.error(f"Failed to set prefetched data for key {cache_key}: {e}")


async def get_prefetched_data(cache_key: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve prefetched data from Redis and decode it from JSON.
    """
    client = get_client()
    if not client:
        return None

    try:
        json_data = await client.get(cache_key)
        if json_data:
            return json.loads(json_data)
        return None
    except Exception as e:
        logger.error(f"Failed to get prefetched data for key {cache_key}: {e}")
        return None


# =====================================================
# 🔹 Utility: Delete cached data (optional helper)
# =====================================================
def delete_cache_key(cache_key: str):
    """
    Delete a specific key from Redis cache.
    """
    client = get_client()
    if not client:
        return
    try:
        client.delete(cache_key)
        logger.info(f"✅ Deleted cache key: {cache_key}")
    except Exception as e:
        logger.error(f"Failed to delete cache key {cache_key}: {e}")


# =====================================================
# 🔹 Provider Adaptive Stats (cross-restart persistence)
# =====================================================
async def record_provider_win(provider: str, ttl_seconds: int = 86400):
    """Increment win counter for a provider.

    Stored under key: provider:win:<provider>
    TTL applied so stale providers naturally age out.
    """
    client = get_client()
    if not client:
        return
    key = f"provider:win:{provider}"
    try:
        # INCR then ensure TTL (only set if new or missing)
        await client.incr(key)
        ttl = await client.ttl(key)
        if ttl == -1:  # -1 means no expiry set
            await client.expire(key, ttl_seconds)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"record_provider_win failed provider={provider}: {e}")


async def record_provider_latency(provider: str, latency_ms: int, max_samples: int = 50, ttl_seconds: int = 86400):
    """Record a latency sample for a provider.

    Uses a capped Redis list (LPUSH + LTRIM) so we keep only the most recent N samples.
    Key: provider:latencies:<provider>
    """
    client = get_client()
    if not client:
        return
    key = f"provider:latencies:{provider}"
    try:
        await client.lpush(key, int(latency_ms))
        await client.ltrim(key, 0, max_samples - 1)
        ttl = await client.ttl(key)
        if ttl == -1:
            await client.expire(key, ttl_seconds)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"record_provider_latency failed provider={provider}: {e}")


async def fetch_adaptive_stats(providers: Optional[list[str]] = None) -> Dict[str, Any]:
    """Fetch persisted adaptive stats for providers.

    Returns structure:
    {
       "wins": {provider: int},
       "avg_latency_ms": {provider: float},
       "samples": {provider: int}
    }
    Safe to call even if redis unavailable (returns empty stats).
    """
    if not providers:
        providers = ["gemini"]
    result: Dict[str, Any] = {"wins": {}, "avg_latency_ms": {}, "samples": {}}
    client = get_client()
    if not client:
        return result
    try:
        for p in providers:
            win_key = f"provider:win:{p}"
            lat_key = f"provider:latencies:{p}"
            try:
                wins_raw = await client.get(win_key)
                wins = int(wins_raw) if wins_raw is not None else 0
                lats_raw = await client.lrange(lat_key, 0, -1)
                samples = [int(v) for v in lats_raw] if lats_raw else []
                avg = float(sum(samples) / len(samples)) if samples else 0.0
                result["wins"][p] = wins
                result["avg_latency_ms"][p] = round(avg, 2)
                result["samples"][p] = len(samples)
            except Exception as inner_e:  # noqa: BLE001
                logger.debug(f"fetch_adaptive_stats inner failure provider={p}: {inner_e}")
        return result
    except Exception as e:  # noqa: BLE001
        logger.debug(f"fetch_adaptive_stats failed: {e}")
        return result


__all__ = [
    "get_session_state",
    "set_session_state",
    "set_prefetched_data",
    "get_prefetched_data",
    "delete_cache_key",
    "record_provider_win",
    "record_provider_latency",
    "fetch_adaptive_stats",
]
