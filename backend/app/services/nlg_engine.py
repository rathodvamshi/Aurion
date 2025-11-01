# backend/app/services/nlg_engine.py

"""
NLG Layer (Step 4)

Consumes structured nlg_input from the LLM Brain, generates user-facing text
using Gemini 2.5 Flash TextCompletion, and returns a structured dict.

Key properties:
- Async and non-blocking relative to background memory updates
- Provider selection via llm_brain API pool (with fallback)
- Lightweight personalization from Redis context and nlg_input memories
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List
import logging
import json
import httpx

from app.services.llm_brain import select_gemini_api, use_api
from app.services import redis_service
from app.config import settings

logger = logging.getLogger(__name__)


def _model_name() -> str:
    # Prefer configured model; mapping to 2.5 Flash handled outside
    return getattr(settings, "GOOGLE_MODEL", None) or "gemini-1.5-flash"


def _endpoint_for_model(model: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _headers() -> Dict[str, str]:
    # We'll pass key via query param (standard), but keep content-type
    return {"Content-Type": "application/json"}


def _api_key() -> str:
    keys = [k.strip() for k in (getattr(settings, "GEMINI_API_KEYS", None) or "").split(",") if k.strip()]
    if keys:
        return keys[0]
    return (getattr(settings, "GEMINI_API_KEY", None) or "").strip()


async def _fetch_personalization(user_id: str, session_id: str) -> Dict[str, Any]:
    """Lightweight best-effort personalization from Redis (non-fatal)."""
    out: Dict[str, Any] = {"recent_context": None, "session_summary": None}
    try:
        client = redis_service.get_client()
        if not client:
            return out
        try:
            # last ~6 messages compact
            msgs_key = f"sess:{session_id}:msgs"
            items = await client.lrange(msgs_key, -6, -1)
            if items:
                out["recent_context"] = "\n".join(items)
        except Exception:
            pass
        try:
            sum_key = f"sess:{session_id}:summary"
            out["session_summary"] = await client.get(sum_key)
        except Exception:
            pass
    except Exception:
        pass
    return out


def _build_prompt(nlg_input: Dict[str, Any], personalization: Dict[str, Any]) -> str:
    intent = nlg_input.get("intent")
    entities = nlg_input.get("entities") or {}
    memories: List[Dict[str, Any]] = nlg_input.get("gathered_memory") or []
    actions = (nlg_input.get("plan") or {}).get("actions") or []

    # Compose a compact, robust prompt
    sys = (
        "You are a helpful, concise assistant. Use the plan and context to craft a friendly, clear reply. "
        "NEVER reference past conversations, previous messages, or say 'Last time we discussed'. "
        "Answer ONLY the current question directly. Do NOT mention context or history."
    )
    ctx_parts: List[str] = []
    if personalization.get("session_summary"):
        ctx_parts.append(f"Session summary: {personalization['session_summary']}")
    if personalization.get("recent_context"):
        ctx_parts.append(f"Recent context (compact):\n{personalization['recent_context']}")
    # Include a couple of memory snippets for tone/personalization
    for m in (memories[:2] if isinstance(memories, list) else []):
        snippet = (m or {}).get("snippet")
        src = (m or {}).get("source")
        if snippet:
            ctx_parts.append(f"Memory[{src}]: {snippet}")

    ctx = "\n".join(ctx_parts)
    ent_str = json.dumps(entities, ensure_ascii=False)
    plan_str = json.dumps(actions, ensure_ascii=False)

    user_goal = f"Intent: {intent or 'unknown'}\nEntities: {ent_str}\nPlanned actions: {plan_str}"

    prompt = (
        f"System: {sys}\n\nContext:\n{ctx}\n\nTask:\n"
        f"Given the user intent/entities and the proposed plan, reply naturally and helpfully."
        f" Keep it concise, avoid markdown unless helpful, and be specific."
        f"\n\nInputs:\n{user_goal}\n\nAnswer:"
    )
    return prompt


async def _call_gemini_text(prompt: str, provider_id: str) -> Optional[str]:
    model = _model_name()
    url = _endpoint_for_model(model)
    key = _api_key()
    params = {"key": key} if key else {}
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 600},
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            import time as _t
            _t0 = _t.time()
            resp = await client.post(url, headers=_headers(), params=params, json=body)
            resp.raise_for_status()
            data = resp.json()
            txt = None
            try:
                candidates = data.get("candidates") or []
                if candidates:
                    parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
                    if parts and isinstance(parts[0], dict):
                        txt = parts[0].get("text")
            except Exception:
                txt = None
            try:
                from app.services import metrics as _m
                from app.services.telemetry import log_provider_usage
                lat_ms = int((_t.time() - _t0) * 1000)
                _m.record_hist("provider.latency.gemini", lat_ms)
                await log_provider_usage("gemini", "nlg", lat_ms, True)
            except Exception:
                pass
            return txt
    except Exception as e:
        logger.debug("Gemini text call failed via %s: %s", provider_id, e)
        try:
            from app.services.telemetry import log_provider_usage
            await log_provider_usage("gemini", "nlg", 0, False)
        except Exception:
            pass
        return None


def _count_tokens_rough(text: str) -> int:
    # Rough approximation when tokenization utilities are not available
    if not text:
        return 0
    return max(1, len(text) // 4)


async def generate_response(nlg_input: dict, user_id: str, session_id: str) -> dict:
    """
    Generates a natural language response using structured data from LLM Brain.
    Returns { "response_text": str, "tokens_used": int, "provider": str }
    """
    # Personalization (best-effort; non-fatal)
    personalization = await _fetch_personalization(user_id, session_id)
    prompt = _build_prompt(nlg_input, personalization)

    # Provider selection with fallback
    provider = select_gemini_api("TextCompletion")
    if not provider:
        return {
            "response_text": "Sorry, I couldn’t process that request right now. Please try again later.",
            "tokens_used": _count_tokens_rough(prompt),
            "provider": None,
        }

    # First attempt
    use_api(provider)
    text = await _call_gemini_text(prompt, provider)
    if text:
        return {
            "response_text": text.strip(),
            "tokens_used": _count_tokens_rough(prompt + (text or "")),
            "provider": provider,
        }

    # Fallback to another active text provider, if available
    alt = select_gemini_api("TextCompletion")
    if alt and alt != provider:
        use_api(alt)
        text2 = await _call_gemini_text(prompt, alt)
        if text2:
            return {
                "response_text": text2.strip(),
                "tokens_used": _count_tokens_rough(prompt + (text2 or "")),
                "provider": alt,
            }

    # Safe fallback
    return {
        "response_text": "Sorry, I couldn’t process that request right now. Please try again later.",
        "tokens_used": _count_tokens_rough(prompt),
        "provider": None,
    }


