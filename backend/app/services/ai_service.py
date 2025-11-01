from typing import Callable, Any
import concurrent.futures
# =====================================================
# 🔹 Sync Timeout Utility for Provider Calls
# =====================================================

def _call_with_timeout(func: Callable[[], Any], timeout: float) -> Any:
    """Run a sync function with a timeout, raising TimeoutError if exceeded."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Function call timed out after {timeout} seconds")
# backend/app/services/ai_service.py

import time
import logging
import json
import threading
from typing import List, Optional, Dict, Any, Callable, Tuple
import concurrent.futures


import google.generativeai as genai

from app.config import settings
from app.prompt_templates import MAIN_SYSTEM_PROMPT  # legacy template retained for other uses
from app.services.prompt_composer import compose_prompt
from app.services.emotion_service import (
    detect_emotion,
    enrich_with_emojis,
    build_persona_directive,
    count_emojis,
)
from app.services import memory_store
from app.services.telemetry import log_interaction_event, classify_complexity
from app.services.behavior_tracker import update_behavior_from_event, get_inferred_preferences
from app.services import metrics
from app.services.redis_service import record_provider_latency, record_provider_win, fetch_adaptive_stats

logger = logging.getLogger(__name__)


def _offline_fallback(user_message: str) -> str:
    """Return a concise local reply when providers are unavailable.

    Avoids surfacing noisy outage banners; acknowledges offline mode and mirrors user intent.
    """
    snippet = (user_message or "").strip().replace("\n", " ")
    if len(snippet) > 200:
        snippet = snippet[:197] + "..."
    if not snippet:
        base = "I'm responding without external AI access right now. Let's keep it simple."
    else:
        base = (
            "I can’t reach external AI providers at the moment, so I’ll answer without using the web.\n\n"
            f"You said: {snippet}\nHere’s a concise offline response."
        )
    return base

# =====================================================
# 🔹 Post-Processing Helpers (Suggestion Enforcement)
# =====================================================
SUGGESTION_PREFIX = "➝"
def _fire_and_forget(coro):  # pragma: no cover (utility)
    """Schedule coroutine without awaiting.

    If there's an active running loop, create a task. If not, run it synchronously
    (blocks briefly) to avoid RuntimeWarning about un-awaited coroutines in test env.
    """
    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(coro)
                return
        except RuntimeError:
            pass
        # No running loop -> run synchronously
        asyncio.run(coro)
    except Exception:  # noqa: BLE001
        pass

# =====================================================
# 🔹 User Token Replacement Helper
# =====================================================
def replace_internal_user_tokens(text: str, profile: Optional[Dict[str, Any]]) -> str:
    """Replace model-emitted internal placeholders like User_<hex>.

    If profile has a name -> substitute with that exact name.
    Else substitute with a deterministic friendly alias derived from user_id hash so it stays stable.
    """
    import re as _re, hashlib as _hashlib
    pattern = _re.compile(r"User_[0-9a-fA-F]{8,40}")
    if not pattern.search(text):
        return text
    name = None
    user_id = None
    if isinstance(profile, dict):
        name = profile.get("name")
        user_id = profile.get("user_id") or profile.get("id") or profile.get("_id")
    if name:
        return pattern.sub(str(name), text)
    aliases = [
        "buddy", "friend", "rockstar", "champ", "pal", "legend", "mate", "star", "trailblazer", "ace"
    ]
    idx = 0
    if user_id:
        h = _hashlib.sha256(str(user_id).encode()).hexdigest()
        idx = int(h, 16) % len(aliases)
    alias = aliases[idx]
    # Capitalize if appears after greeting Hello/Hi etc.
    def _sub(m: _re.Match) -> str:  # noqa: ANN001
        return alias
    return pattern.sub(_sub, text)

def strip_existing_suggestions(text: str) -> str:
    """Ensure at most two suggestion lines (those starting with the arrow) are retained."""
    lines = text.splitlines()
    kept = []
    suggestion_count = 0
    for ln in lines:
        raw = ln.strip()
        if raw.startswith(SUGGESTION_PREFIX):
            if suggestion_count < 2:
                kept.append(ln)
                suggestion_count += 1
            # extra suggestions discarded silently
        else:
            kept.append(ln)
    return "\n".join(kept)

def compute_suggestions(base_text: str, user_prompt: str, profile: Optional[Dict[str, Any]]) -> List[str]:
    """Return up to two suggestion lines (each with arrow prefix) or empty list.

    Used by both append mode (non-stream) and streaming path.
    """
    from app.config import settings as _settings  # local import to avoid circular during tests
    from app.services import memory_store as _memory_store
    if not _settings.ENABLE_SUGGESTIONS:
        return []
    low_user = user_prompt.lower()
    if any(p in low_user for p in ["no suggestions", "stop suggestions", "don't give suggestions", "dont give suggestions"]):
        return []

    # If text already has suggestions, we respect them (handled in append wrapper) -> return empty so wrapper can keep existing.
    if SUGGESTION_PREFIX in base_text:
        return []

    # Determine quick vs deep answer (rough heuristic length check excluding suggestion arrows)
    plain_answer = base_text.strip()
    answer_char_len = len(plain_answer)
    answer_is_short = answer_char_len < 220  # configurable heuristic

    low = user_prompt.lower()
    raw_candidates: List[str] = []
    if any(k in low for k in ["how do i", "steps", "guide", "tutorial"]):
        if answer_is_short:
            raw_candidates += [
                "Want a detailed step-by-step checklist?",
                "Need a quick rationale for each step?",
            ]
        else:
            raw_candidates += [
                "Want a concise summary of the steps?",
                "Need a minimal checklist version?",
            ]
    elif any(k in low for k in ["what is", "explain", "define", "meaning of"]):
        if answer_is_short:
            raw_candidates += ["Want a deeper breakdown with examples?", "Should I compare it to a related concept?"]
        else:
            raw_candidates += ["Want a quick summary version?", "Need a real-world analogy?"]
    elif any(k in low for k in ["recommend", "suggest", "movie", "book", "music", "song", "playlist"]):
        raw_candidates += ["Want more options in another style?", "Should I save these preferences for later?"]
    elif any(k in low for k in ["hi", "hello", "hey"]):
        raw_candidates += ["Want a fun fact to start?", "Need help with something specific today?"]
    else:
        if answer_is_short:
            raw_candidates += ["Want me to expand this?", "Need related tips or resources?"]
        else:
            raw_candidates += ["Want a concise summary?", "Need an example to solidify it?"]

    # Derive preferred tone (profile preference) for style adaptation
    tone_pref = None
    if isinstance(profile, dict):
        prefs = profile.get("preferences") or {}
        if isinstance(prefs, dict):
            tone_pref = (prefs.get("tone") or "").lower() or None

    def _adapt_phrase(phrase: str) -> str:
        base = phrase.strip()
        if not tone_pref:
            return base
        # Formal style: replace casual stems, avoid emojis, more polite modal forms
        if tone_pref in {"formal"}:
            repl_map = {
                "want you": "would you like me",
                "want a": "would you like a",
                "want an": "would you like an",
                "want": "would you like",
                "need": "would you like",
                "should i": "shall I",
            }
            low = base.lower()
            for k, v in repl_map.items():
                if k in low:
                    # crude whole-substring replacement preserving capitalization of first letter
                    low = low.replace(k, v)
            # Reconstruct capitalization (first char upper)
            out = low[0].upper() + low[1:] if low else low
            if not out.endswith("?"):
                out += "?"
            return out
        # Playful / enthusiastic / supportive tones can allow light emoji accent
        elif tone_pref in {"playful", "enthusiastic"}:
            if not any(ch in base for ch in ["🙂", "😄", "😉", "🤗", "✨"]):
                if len(base) < 70:
                    base = base.rstrip("?")  # remove existing ? to append nicely
                    base += "? 😄"
            return base
        elif tone_pref in {"supportive", "warm"}:
            # Softer phrasing
            if base.lower().startswith("want"):
                base = "Would it help if I " + base[4:].lstrip()
            if not any(ch in base for ch in ["💛", "🤗", "🌱"]):
                if len(base) < 72:
                    base = base.rstrip("?") + "? 💛"
            return base
        elif tone_pref in {"concise"}:
            # Keep extremely short; remove fillers
            base = base.replace("Would you like", "Want").replace("Need", "Need")
            # Trim to first question mark or add one
            if len(base) > 55:
                base = base[:55].rstrip(" .,")
            if not base.endswith("?"):
                base += "?"
            return base
        return base

    # Memory-aware dedupe: filter out lines recently used
    user_id = None
    if isinstance(profile, dict):
        user_id = profile.get("user_id") or profile.get("id") or profile.get("_id")
    recent: List[str] = []
    if user_id:
        try:
            import asyncio as _asyncio
            async def _fetch():
                try:
                    return await _memory_store.get_recent_suggestions(str(user_id), limit=_settings.SUGGESTION_HISTORY_WINDOW)
                except Exception:
                    return []
            try:
                loop = _asyncio.get_running_loop()
                if loop.is_running():
                    # schedule but cannot use result in sync context
                    _fire_and_forget(_fetch())
                else:
                    recent = _asyncio.run(_fetch())
            except RuntimeError:
                recent = _asyncio.run(_fetch())
        except Exception:  # noqa: BLE001
            recent = []
    # Basic filter by exact text match (case insensitive)
    recent_lower = {r.lower() for r in recent}
    # Adapt phrases before filtering so dedupe applies to final styled text
    adapted_candidates = [_adapt_phrase(c) for c in raw_candidates]
    filtered = [c for c in adapted_candidates if c.lower() not in recent_lower]
    # If everything was filtered, fall back to original list to avoid empty set
    if not filtered:
        filtered = raw_candidates

    # Deduplicate within the candidate list
    final_candidates: List[str] = []
    seen_local = set()
    for c in filtered:
        key = c.lower()
        if key in seen_local:
            continue
        seen_local.add(key)
        final_candidates.append(c)

    suggestions: List[str] = []
    for cand in final_candidates:
        if len(suggestions) >= 2:
            break
        suggestions.append(f"{SUGGESTION_PREFIX} {cand}")

    if not suggestions:
        return []

    if user_id:
        raw_store = [s[len(SUGGESTION_PREFIX):].strip() for s in suggestions]
        try:
            from app.services import memory_store as _ms
            _fire_and_forget(_ms.push_suggestions(str(user_id), raw_store))  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            pass
    return suggestions


def append_suggestions_if_missing(base_text: str, user_prompt: str, profile: Optional[Dict[str, Any]]) -> str:
    """Wrapper for non-stream flows: append suggestions to text if missing."""
    if SUGGESTION_PREFIX in base_text:
        return strip_existing_suggestions(base_text)
    suggestions = compute_suggestions(base_text, user_prompt, profile)
    if not suggestions:
        return base_text
    return base_text.rstrip() + "\n" + "\n".join(suggestions)

# =====================================================
# 🔹 AI Client Initialization
# =====================================================
gemini_keys = [key.strip() for key in (settings.GEMINI_API_KEYS or "").split(",") if key.strip()]
current_gemini_key_index = 0

# =====================================================
# 🔹 Circuit Breaker & Provider Fallback
# =====================================================
FAILED_PROVIDERS: dict[str, float] = {}
_ADAPTIVE_LAST_REORDER: float = 0.0
_ADAPTIVE_MIN_INTERVAL = 30.0  # seconds between reorder attempts

def _derive_provider_order() -> List[str]:
    """Return current provider preference order.

    Priority: explicit env override > PRIMARY/FALLBACK envs > default static order.
    Defaults to Gemini-only for consistency with embeddings.
    """
    order_env = (settings.AI_PROVIDER_ORDER or "").strip()
    if order_env:
        items = [s.strip().lower() for s in order_env.split(",") if s.strip()]
        return [p for p in items if p in {"gemini"}]
    
    # Default to Gemini-only for consistency with embeddings and memory system
    primary = (getattr(settings, "PRIMARY_PROVIDER", None) or "gemini").lower()
    fallback = (getattr(settings, "FALLBACK_PROVIDER", None) or "gemini").lower()
    
    out: List[str] = []
    for p in (primary, fallback):
        if p in {"gemini"} and p not in out:
            out.append(p)
    
    # Ensure Gemini is always first for consistency
    if "gemini" in out:
        out.remove("gemini")
        out.insert(0, "gemini")
    
    return out or ["gemini"]

AI_PROVIDERS = _derive_provider_order()

def _is_provider_available(name: str) -> bool:
    """Check if provider is available (not in cooldown) and has keys configured."""
    import os as _os
    from app.config import settings as _s
    # In test environments, ignore cooldown to avoid cross-test bleed-through
    if _os.getenv("PYTEST_CURRENT_TEST"):
        return True
    if name == "gemini":
        return bool(gemini_keys)
    if name == "cohere":
        return False
    if name == "anthropic":
        return False
    return False

# =====================================================
# 🔹 Provider Helpers
# =====================================================
def _try_gemini(prompt: str) -> str:
    """Delegate to the centralized gemini_service to avoid duplication and ensure consistent key rotation."""
    from app.services import gemini_service as _gemini
    return _gemini.generate(prompt)

def _try_cohere(prompt: str) -> str:
    raise RuntimeError("Cohere support removed")

def _try_anthropic(prompt: str) -> str:
    raise RuntimeError("Anthropic support removed")

# =====================================================
# 🔹 Error Classification Helpers
# =====================================================
def _classify_error(exc: Exception) -> dict:
    """Classify provider exceptions for retry/alert decisions."""
    msg = str(exc) if exc else ""
    low = msg.lower()
    is_timeout = isinstance(exc, TimeoutError) or "timeout" in low
    is_rate = any(k in low for k in ["rate limit", "too many requests", "429"])
    is_server = any(k in low for k in ["500", "internal server error", "unavailable", "bad gateway", "service unavailable"])
    is_insufficient_credit = any(k in low for k in ["insufficient", "quota", "credit", "billing", "payment", "balance"]) and not is_rate
    temporary = is_timeout or is_rate or is_server
    return {
        "temporary": temporary,
        "insufficient_credit": is_insufficient_credit,
        "message": msg,
    }

# =====================================================
# 🔹 JSON Fallback Orchestrator (Minimal, Provider-Focused)
# =====================================================
async def generate_response_json(
    prompt: str,
    *,
    retries_per_provider: int = 2,
    primary_timeout_s: float | None = None,
    fallback_timeout_s: float | None = None,
) -> dict:
    """
    Generate a response with provider health checks, retry, and fallback.

    Returns JSON: {"success": bool, "output": str|None, "provider_used": str|None, "error": str|None}
    """
    primary_budget = primary_timeout_s if primary_timeout_s is not None else settings.AI_PRIMARY_TIMEOUT
    fallback_budget = fallback_timeout_s if fallback_timeout_s is not None else settings.AI_FALLBACK_TIMEOUT

    errors: list[str] = []
    chosen_provider: Optional[str] = None
    text_out: Optional[str] = None

    # Refresh ordering (respects env override and adaptive metrics)
    try:
        global AI_PROVIDERS
        AI_PROVIDERS = _derive_provider_order()
    except Exception:  # noqa: BLE001
        pass

    for idx, provider_name in enumerate(AI_PROVIDERS):
        if not _is_provider_available(provider_name):
            continue
        budget = primary_budget if idx == 0 else fallback_budget

        # Retry loop for transient errors
        attempt = 0
        while attempt <= retries_per_provider:
            try:
                start = time.time()
                candidate = await _invoke_with_timeout(provider_name, prompt, budget)
                latency_ms = int((time.time() - start) * 1000)
                try:
                    from app.services import metrics as _m
                    _m.record_hist(f"provider.latency.{provider_name}", latency_ms)
                    _fire_and_forget(record_provider_latency(provider_name, latency_ms))
                except Exception:  # noqa: BLE001
                    pass
                FAILED_PROVIDERS.pop(provider_name, None)
                chosen_provider = provider_name
                text_out = candidate
                break
            except Exception as e:  # noqa: BLE001
                classification = _classify_error(e)
                if classification.get("insufficient_credit"):
                    logger.error(f"[AI] {provider_name} insufficient credits: {classification['message']}")
                elif classification.get("temporary"):
                    logger.warning(f"[AI] {provider_name} temporary failure (attempt {attempt+1}/{retries_per_provider+1}): {classification['message']}")
                else:
                    logger.error(f"[AI] {provider_name} hard failure: {classification['message']}")

                if classification.get("temporary") and attempt < retries_per_provider:
                    # Backoff before retry
                    try:
                        import asyncio as _asyncio
                        await _asyncio.sleep(min(0.25 * (2 ** attempt), 1.0))
                    except Exception:  # noqa: BLE001
                        pass
                    attempt += 1
                    continue

                # Mark provider failed (cooldown)
                FAILED_PROVIDERS[provider_name] = time.time()
                errors.append(f"{provider_name}: {classification['message']}")
                break  # move to next provider

        if text_out is not None:
            break

    if text_out is None:
        # All providers failed: produce consolidated error msg
        joined = "; ".join(errors) if errors else "All providers failed with unknown errors"
        logger.error(f"[AI] All providers failed: {joined}")
        return {
            "success": False,
            "output": None,
            "provider_used": None,
            "error": joined,
        }

    logger.info(f"[AI] Response from {chosen_provider}: {text_out}")
    return {
        "success": True,
        "output": text_out,
        "provider_used": chosen_provider,
        "error": None,
    }

# =====================================================
# 🔹 Async Provider Wrappers (non-blocking orchestration)
# =====================================================
async def _invoke_provider(provider: str, prompt: str) -> str:
    """Invoke the underlying sync provider helper in a worker thread.

    We keep the existing sync _try_* functions for reuse in other sync utilities
    (e.g., summarization) but for the main chat path we shift to an async model
    so hedged / parallel execution does not block the event loop.
    """
    import asyncio
    if provider == "gemini":
        return await asyncio.to_thread(_try_gemini, prompt)
    if provider == "cohere":
        raise RuntimeError("Cohere support removed")
    if provider == "anthropic":
        raise RuntimeError("Anthropic support removed")
    raise RuntimeError(f"Unknown provider {provider}")


async def _invoke_with_timeout(provider: str, prompt: str, timeout_s: float) -> str:
    import asyncio
    # If timeout <= 0, wait indefinitely (no timeout wrapper)
    if timeout_s is None or float(timeout_s) <= 0:
        return await _invoke_provider(provider, prompt)
    return await asyncio.wait_for(_invoke_provider(provider, prompt), timeout=timeout_s)


def _maybe_handle_introspection(
    user_prompt: str,
    profile: Optional[Dict[str, Any]],
    neo4j_facts: Optional[str],
    user_facts_semantic: Optional[List[str]],
) -> Tuple[bool, str]:
    """Detect self-knowledge queries (name, favorites, profile summary) and answer succinctly.

    Returns (handled, response). Keeps answers short (1–2 sentences) for comfort.
    """
    if not profile:
        profile = {}
    low = user_prompt.lower().strip()

    name = profile.get("name")
    favorites = profile.get("favorites", {}) or {}
    hobbies = profile.get("hobbies", []) or []

    def fmt_list(items: List[str], limit: int = 3) -> str:
        if not items:
            return ""
        cut = items[:limit]
        if len(cut) == 1:
            return cut[0]
        if len(cut) == 2:
            return f"{cut[0]} and {cut[1]}"
        return ", ".join(cut[:-1]) + f" and {cut[-1]}"

    # Name-centric queries
    if any(p in low for p in [
        "what's my name", "whats my name", "what is my name", "do you know my name", "do u know my name", "my name?", "tell me my name"
    ]):
        if name:
            # Clean, direct answer - will be formatted by response_shaper
            return True, f"Your name is {name}."
        return True, "I don't have your name yet. You can tell me and I'll remember it."

    # Cuisine / favorite cuisine queries
    if "what cuisine do i like" in low or "my favorite cuisine" in low or "favorite cuisine" in low:
        cuisine = favorites.get("cuisine") or favorites.get("food")
        if cuisine:
            return True, f"You enjoy {cuisine} cuisine."
        return True, "You haven't told me your favorite cuisine yet."

    # General favorites query
    if any(p in low for p in [
        "what are my favorites", "what do i like", "my favorites?", "do you know my favorites"
    ]):
        if favorites:
            limited = list(favorites.items())[:3]
            fav_str = ", ".join(f"{k}={v}" for k, v in limited)
            return True, f"Your favorites I know: {fav_str}."
        return True, "I don't have any favorites stored yet."

    # Broad self-knowledge / profile summary
    if any(p in low for p in ["what do you know about me", "what do u know about me", "what do you know of me", "what can you tell me about me"]):
        if not (name or favorites or hobbies or user_facts_semantic):
            return True, "I don't have personal details yet. You can share your name or preferences and I'll remember them."
        cuisine = favorites.get("cuisine") or favorites.get("food")
        bits: List[str] = []
        if name and cuisine:
            bits.append(f"I know your name is {name} and you enjoy {cuisine} cuisine")
        elif name:
            bits.append(f"I know your name is {name}")
        elif cuisine:
            bits.append(f"You enjoy {cuisine} cuisine")
        # Add one more favorite if available (other than cuisine)
        other_fav = None
        for k, v in favorites.items():
            if k in ("cuisine", "food"):
                continue
            other_fav = (k, v)
            break
        if other_fav:
            bits.append(f"and your {other_fav[0]} is {other_fav[1]}")
        if hobbies:
            bits.append("you like " + fmt_list(hobbies, 3))
        # Join gracefully
        summary = " ".join(bits).strip()
        if not summary.endswith('.'):
            summary += '.'
        return True, summary

    return False, ""


async def get_response(
    prompt: str,
    history: Optional[List[dict]] = None,
    pinecone_context: Optional[str] = None,
    neo4j_facts: Optional[str] = None,
    state: str = "general_conversation",
    profile: Optional[Dict[str, Any]] = None,
    user_facts_semantic: Optional[List[str]] = None,
    persistent_memories: Optional[List[Dict[str, Any]]] = None,
    suppress_suggestions: bool = False,
    session_id: Optional[str] = None,
    system_override: Optional[str] = None,
) -> str:
    """Generates AI response using multiple providers with timeout + fallback (async version).

    This function was converted to async so that downstream coroutine based utilities
    (behavior updates, redis interactions, emotion trend pushes, telemetry hooks)
    can be awaited or scheduled without relying on event-loop introspection hacks.

    Timeout strategy:
      - Primary (first provider): settings.AI_PRIMARY_TIMEOUT seconds
      - Each fallback: settings.AI_FALLBACK_TIMEOUT seconds
    """

    # Offline user override: allow users to force an offline/local reply by flag or phrase.
    try:
        _low = (prompt or "").lower()
        if (system_override and str(system_override).lower() == "offline") or ("no web" in _low):
            # Minimal offline answer tailored to the prompt; skip provider calls entirely
            offline_text = (prompt or "").strip()
            if not offline_text:
                offline_text = "Acknowledged. Responding in offline mode."
            else:
                offline_text = offline_text + "\n\n(offline) I’ll answer without web access."
            try:
                if not suppress_suggestions:
                    offline_text = append_suggestions_if_missing(offline_text, prompt, profile)
            except Exception:
                pass
            return offline_text
    except Exception:
        pass

    # Introspection shortcut handling - still needs formatting
    handled, direct_resp = _maybe_handle_introspection(
        prompt, profile, neo4j_facts, user_facts_semantic
    )
    if handled:
        # Return direct response (will be formatted by response_shaper downstream)
        return direct_resp

    # Lightweight emotion detection BEFORE composing the prompt so we can append persona directive
    # Per-user preference overrides (if present)
    pref_enable_emotion = None
    pref_enable_emoji = None
    if isinstance(profile, dict):
        prefs = profile.get("preferences") or {}
        val = str(prefs.get("emotion_persona") or "").lower()
        if val in {"on", "off"}:
            pref_enable_emotion = (val == "on")
        val2 = str(prefs.get("emoji") or "").lower()
        if val2 in {"on", "off"}:
            pref_enable_emoji = (val2 == "on")

    use_emotion = (pref_enable_emotion if pref_enable_emotion is not None else settings.ENABLE_EMOTION_PERSONA)
    use_emoji = (pref_enable_emoji if pref_enable_emoji is not None else settings.ENABLE_EMOJI_ENRICHMENT)

    if use_emotion:
        emotion_result = detect_emotion(prompt)
        # Retrieve trend to evaluate escalation
        recent_emotions: List[str] = []
        # (Escalation trend retrieval handled below now that we are async.)
    else:
        class _Dummy:  # noqa: D401
            emotion = "neutral"; confidence = 0.0; tone = "neutral"; lead_emoji = ""; palette = ["🙂"]
        emotion_result = _Dummy()  # type: ignore

    # Advanced positive memory heuristic: prefer most recent positive-sounding message in history that mentions a hobby or favorite
    last_positive_memory = None
    if profile:
        try:
            favorites = (profile.get("favorites") or {}) if isinstance(profile, dict) else {}
            hobbies = (profile.get("hobbies") or []) if isinstance(profile, dict) else []
            # Scan history backwards for a line containing 'love', 'enjoy', 'like'
            if history:
                for h in reversed(history):
                    txt = (h.get("text") or h.get("content") or "").lower()
                    if any(k in txt for k in ["love", "enjoy", "like", "fun"]):
                        snippet = txt[:120]
                        last_positive_memory = snippet
                        break
            if not last_positive_memory:
                if hobbies:
                    last_positive_memory = f"You enjoy {hobbies[-1]}"
                elif favorites.get("cuisine"):
                    last_positive_memory = f"You like {favorites.get('cuisine')} cuisine"
        except Exception:  # noqa: BLE001
            pass

    # Escalation check (async)
    escalation = False
    if use_emotion and getattr(emotion_result, "emotion", "neutral") in {"sad", "angry", "anxious"}:
        try:
            # Attempt to pull recent emotions via memory_store async API if available
            if hasattr(memory_store, "redis_client"):
                key = f"user:{(profile or {}).get('user_id')}:emotions"
                try:
                    recent = await memory_store.redis_client.lrange(key, -settings.EMOTION_TREND_WINDOW, -1)  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    recent = []
                if recent:
                    streak = 0
                    for lbl in reversed(recent):
                        if lbl == getattr(emotion_result, "emotion", "neutral"):
                            streak += 1
                        else:
                            break
                    if streak >= settings.EMOTION_ESCALATION_THRESHOLD:
                        escalation = True
        except Exception:  # noqa: BLE001
            escalation = False

    tone_override = None
    if isinstance(profile, dict):
        prefs = profile.get("preferences") or {}
        tval = prefs.get("tone")
        if isinstance(tval, str) and tval.strip():
            tone_override = tval.strip()[:40]

    # ------- Inferred Preferences Caching (LRU + Redis-first) -------
    inferred_prefs: Dict[str, Any] = {}

    # Module-level LRU cache
    global _INFER_PREFS_CACHE  # type: ignore  # defined below if not yet
    try:
        _INFER_PREFS_CACHE  # type: ignore[name-defined]
    except NameError:  # noqa: BLE001
        _INFER_PREFS_CACHE = {}

    _INFER_PREFS_TTL = 120  # seconds
    def _now_ts():
        import time as _t; return int(_t.time())

    def _sync_fetch(uid: str) -> Dict[str, Any]:
        import asyncio
        async def _runner():
            try:
                return await get_inferred_preferences(uid)
            except Exception:
                return {}
        try:
            loop = asyncio.get_running_loop()
            # If already in running loop, skip (avoid nested) -> return empty (fallback)
            if loop.is_running():
                return {}
        except RuntimeError:
            pass
        try:
            return asyncio.run(_runner())
        except Exception:
            return {}

    user_id_for_infer = None
    if isinstance(profile, dict):
        user_id_for_infer = profile.get("user_id") or profile.get("id") or profile.get("_id")
    cache_source = None
    if user_id_for_infer:
        uid = str(user_id_for_infer)
        # 1. In-process LRU check
        entry = _INFER_PREFS_CACHE.get(uid)
        if entry and entry[0] > _now_ts():
            inferred_prefs = entry[1]
            cache_source = "lru"
        else:
            # 2. Redis prefetched key
            try:
                from app.services.redis_service import get_prefetched_data, set_prefetched_data  # type: ignore
                import asyncio as _asyncio
                cache_key = f"user:{uid}:inferred_prefs:v1"
                redis_data = None
                try:
                    async def _g():  # fetch helper
                        try:
                            return await get_prefetched_data(cache_key)  # type: ignore
                        except Exception:
                            return None
                    try:
                        loop2 = _asyncio.get_running_loop()
                        if loop2.is_running():
                            redis_data = await _g()
                        else:
                            redis_data = _asyncio.run(_g())
                    except RuntimeError:
                        redis_data = _asyncio.run(_g())
                except Exception:
                    redis_data = None

                if isinstance(redis_data, dict) and redis_data:
                    inferred_prefs = redis_data
                    _INFER_PREFS_CACHE[uid] = (_now_ts() + _INFER_PREFS_TTL, redis_data)
                    cache_source = "redis"
                else:
                    # Compute and then store
                    computed = _sync_fetch(uid) or {}
                    inferred_prefs = computed
                    if computed:
                        _INFER_PREFS_CACHE[uid] = (_now_ts() + _INFER_PREFS_TTL, computed)
                        cache_source = "compute"
                        try:  # best-effort async store
                            async def _s():
                                try:
                                    await set_prefetched_data(cache_key, computed, ttl_seconds=_INFER_PREFS_TTL)  # type: ignore
                                except Exception:
                                    pass
                            try:
                                loop2 = _asyncio.get_running_loop()
                                if loop2.is_running():
                                    loop2.create_task(_s())
                                else:
                                    _asyncio.run(_s())
                            except RuntimeError:
                                _asyncio.run(_s())
                        except Exception:
                            pass
            except Exception:
                inferred_prefs = _sync_fetch(uid) or {}
                if inferred_prefs and cache_source is None:
                    cache_source = "compute"

    # Instrumentation log for cache usage
    try:
        if user_id_for_infer and cache_source:
            logger.info(
                "inferred_prefs_cache | user=%s source=%s detail=%s tone=%s depth_bias=%s",
                user_id_for_infer,
                cache_source,
                inferred_prefs.get("detail_level"),
                inferred_prefs.get("tone_preference_inferred"),
                inferred_prefs.get("depth_bias"),
            )
            metrics.incr(f"inferred_prefs.source.{cache_source}")
            if "detail_level" in inferred_prefs:
                metrics.incr(f"inferred_prefs.detail.{inferred_prefs['detail_level']}")
    except Exception:  # noqa: BLE001
        pass
    persona_directive = build_persona_directive(
        emotion_result,
        last_positive_memory,
        escalation=escalation,
        tone_override=tone_override,
    ) if use_emotion else ""

    # Augment persona directive with inferred preferences - simplified, always prioritize brevity
    if inferred_prefs:
        try:
            detail_level = inferred_prefs.get("detail_level")
            tone_pref_inferred = inferred_prefs.get("tone_preference_inferred")
            add_bits = []
            # Always prioritize concise responses
            if detail_level == "concise":
                add_bits.append("Keep response very brief (1-2 sentences max).")
            elif detail_level == "deep":
                # Even for deep, keep it brief but informative
                add_bits.append("Keep response brief (2-3 sentences max).")
            else:
                # Default: always be concise
                add_bits.append("Keep response brief (1-2 sentences max).")
            if tone_pref_inferred and (tone_override or "")[:20].lower() != tone_pref_inferred.lower():
                add_bits.append(f"Prefer {tone_pref_inferred} tone briefly.")
            if add_bits:
                persona_directive = f"{persona_directive} {' '.join(add_bits)}".strip()
        except Exception:  # noqa: BLE001
            pass

    # Fire-and-forget: push emotion into trend list (only if feature enabled and non-neutral)
    if settings.ENABLE_EMOTION_PERSONA:
        try:
            if getattr(emotion_result, "emotion", "neutral") in {"sad", "angry", "anxious"}:
                user_id_for_trend = None
                if isinstance(profile, dict):
                    user_id_for_trend = profile.get("user_id") or profile.get("id") or profile.get("_id")
                if user_id_for_trend:
                    try:
                        await memory_store.push_emotion_label(str(user_id_for_trend), emotion_result.emotion)  # type: ignore[arg-type]
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

    # Real-time web search integration with content scraping (if query suggests current/recent info)
    search_context = ""
    try:
        from app.services.realtime_search import (
            smart_search_with_scraping, 
            should_use_search, 
            build_search_context
        )
        
        if should_use_search(prompt):
            logger.info(f"🔍 Real-time search with scraping triggered for query: {prompt[:50]}")
            # Use scraping-enabled search to get full article content
            search_results = await smart_search_with_scraping(
                prompt, 
                scrape_content=True,  # Enable content scraping
                use_cache=True
            )
            
            if search_results:
                # Build combined context: memory + search results with scraped content
                memory_summary = neo4j_facts or pinecone_context or ""
                search_context = await build_search_context(memory_summary, search_results)
                logger.info(f"✅ Real-time search returned {len(search_results)} results with scraped content")
            else:
                logger.warning("⚠️ Real-time search returned no results")
    except Exception as e:
        logger.debug(f"Real-time search failed (non-fatal): {e}")
        # Continue without search context - not a blocking error
    
    # Use new composer (falls back to legacy style if needed later). We piggyback persona directive
    # by appending it to the user message so providers stay stateless.
    augmented_user_prompt = f"{prompt}\n\n[Persona Guidance]\n{persona_directive}" if persona_directive else prompt
    
    # Enhance pinecone_context with search results if available
    enhanced_pinecone_context = pinecone_context
    if search_context:
        if enhanced_pinecone_context:
            enhanced_pinecone_context = f"{enhanced_pinecone_context}\n\n{search_context}"
        else:
            enhanced_pinecone_context = search_context
    
    full_prompt = compose_prompt(
        user_message=augmented_user_prompt,
        state=state,
        history=history or [],
        pinecone_context=enhanced_pinecone_context,
        neo4j_facts=neo4j_facts,
        profile=profile,
        user_facts_semantic=user_facts_semantic,
        persistent_memories=persistent_memories,
        system_override=system_override,
    )

    # Always enforce brevity: keep responses short and focused
    try:
        limit = getattr(settings, "FAST_RESPONSE_WORD_LIMIT", 60)  # Reduced from 120 to 60
        brevity_tag = (
            "[Response Guidelines] Answer directly in <={} words (1-2 sentences). "
            "Be friendly but brief. "
            "NEVER say 'Last time we discussed', 'As mentioned before', 'Previously', 'Earlier', "
            "or reference past conversations/messages. "
            "Answer ONLY the current question. Do NOT mention context or how you got the information."
        ).format(limit)
        if brevity_tag not in full_prompt:
            full_prompt = f"{brevity_tag}\n\n" + full_prompt
    except Exception:  # noqa: BLE001
        pass

    logger.debug("----- Full AI Prompt -----\n%s\n--------------------------", full_prompt)

    start_total = time.time()
    try:
        from app.services import metrics as _m
        _m.incr("chat.requests.total")
    except Exception:  # noqa: BLE001
        pass

    provider: Optional[str] = None
    result: Optional[str] = None

    # Periodically refresh adaptive provider ordering (no-op if interval not reached)
    try:
        global AI_PROVIDERS
        AI_PROVIDERS = _derive_provider_order()
    except Exception:  # noqa: BLE001
        pass

    # ---------------- Hedged Parallel Branch (async) ----------------
    if settings.AI_ENABLE_HEDGED and len(AI_PROVIDERS) > 1:
        import asyncio as _asyncio
        import asyncio  # typing alias
        start_hedge = time.time()
        done_result: Optional[Tuple[str, str]] = None
        active_tasks: dict[str, asyncio.Task] = {}

        async def _run_provider_async(p: str, budget: float) -> None:
            nonlocal done_result
            if done_result is not None:
                return
            try:
                text = await _invoke_with_timeout(p, full_prompt, budget)
                if done_result is None:
                    done_result = (p, text)
            except Exception as e:  # noqa: BLE001
                FAILED_PROVIDERS[p] = time.time()
                logger.warning(f"[AI] Hedged provider {p} failed: {e}")

        # Fire primary immediately
        primary = AI_PROVIDERS[0]
        if _is_provider_available(primary):
            active_tasks[primary] = _asyncio.create_task(_run_provider_async(primary, settings.AI_PRIMARY_TIMEOUT))

        async def _launch_hedges():
            # Conditional hedge: earliest of fixed delay or dynamic threshold
            dynamic_threshold = settings.AI_PRIMARY_TIMEOUT * 0.30
            fixed_delay = settings.AI_HEDGE_DELAY_MS / 1000.0
            wait_time = min(fixed_delay, dynamic_threshold)
            await _asyncio.sleep(wait_time)
            for p in AI_PROVIDERS[1:settings.AI_MAX_PARALLEL]:
                if done_result is not None:
                    break
                if not _is_provider_available(p):
                    continue
                active_tasks[p] = _asyncio.create_task(_run_provider_async(p, settings.AI_FALLBACK_TIMEOUT))
                try:
                    from app.services import metrics as _m
                    _m.incr("chat.hedge.launch")
                    _m.set_gauge("chat.hedge.inflight", len(active_tasks))
                except Exception:  # noqa: BLE001
                    pass

        hedge_task = _asyncio.create_task(_launch_hedges())

        while True:
            if done_result is not None:
                for t in active_tasks.values():
                    if not t.done():
                        t.cancel()
                if not hedge_task.done():
                    hedge_task.cancel()
                provider, result = done_result
                FAILED_PROVIDERS.pop(provider, None)
                try:
                    from app.services import metrics as _m
                    _m.incr("chat.hedge.enabled")
                    _m.incr(f"chat.hedge.win.provider.{provider}")
                    win_ms = int((time.time() - start_hedge) * 1000)
                    _m.record_hist("chat.hedge.win_latency_ms", win_ms)
                    _m.set_gauge("chat.hedge.inflight", 0)
                    # Persist win + latency for cross-restart adaptive ordering
                    _fire_and_forget(record_provider_win(provider))
                    _fire_and_forget(record_provider_latency(provider, win_ms))
                except Exception:  # noqa: BLE001
                    pass
                break
            if all(t.done() for t in active_tasks.values()) and hedge_task.done():
                break
            await _asyncio.sleep(0.01)

    # ---------------- Sequential Fallback Branch (async) ----------------
    if result is None:
        import asyncio as _asyncio
        for idx, p in enumerate(AI_PROVIDERS):
            if not _is_provider_available(p):
                continue
            try:
                budget = settings.AI_PRIMARY_TIMEOUT if idx == 0 else settings.AI_FALLBACK_TIMEOUT
                candidate = await _invoke_with_timeout(p, full_prompt, budget)
                FAILED_PROVIDERS.pop(p, None)
                provider, result = p, candidate
                break
            except Exception as e:  # Includes TimeoutError via asyncio.wait_for
                logger.warning(f"[AI] Provider '{p}' failed in sequential path: {e}")
                FAILED_PROVIDERS[p] = time.time()

    if result is None or provider is None:
        total_ms = int((time.time() - start_total) * 1000)
        logger.error(f"[AI] All providers failed total_latency_ms={total_ms}")
        # Provide a robust, user-friendly fallback
        return (
            "Sorry, all AI services are temporarily unavailable. "
            "Please try again in a few moments. If this persists, contact support."
        )

    # ---------------- Unified Post-processing ----------------
    try:
        result = replace_internal_user_tokens(result, profile)
    except Exception:  # noqa: BLE001
        pass
    total_ms = int((time.time() - start_total) * 1000)
    logger.info(f"[AI] Provider={provider} success total_latency_ms={total_ms}")
    try:
        from app.services import metrics as _m
        _m.record_hist(f"provider.latency.{provider}", total_ms)
        _fire_and_forget(record_provider_latency(provider, total_ms))
    except Exception:  # noqa: BLE001
        pass

    if use_emoji:
        try:
            existing = count_emojis(result)
            if existing < settings.EMOJI_MAX_TOTAL and use_emoji:
                budget = max(settings.EMOJI_MAX_AUTO_ADD - existing, 0)
                if budget > 0:
                    result = enrich_with_emojis(result, emotion_result, max_new=budget, hard_cap=settings.EMOJI_MAX_TOTAL)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            pass

    # Disabled suggestions by default - focus only on answering the user's question
    # Users can explicitly ask for suggestions if they want them
    if not suppress_suggestions:
        # Only add suggestions if user explicitly asks for them
        prompt_lower = (prompt or "").lower()
        if any(keyword in prompt_lower for keyword in ["suggest", "recommend", "options", "ideas", "what else"]):
            try:
                before = result
                result = append_suggestions_if_missing(result, prompt, profile)
                if result is not before and SUGGESTION_PREFIX in result:
                    try:
                        sug_lines = [l.strip() for l in result.splitlines() if l.strip().startswith(SUGGESTION_PREFIX)][-2:]
                        tone_pref = None
                        if isinstance(profile, dict):
                            prefs = profile.get("preferences") or {}
                            if isinstance(prefs, dict):
                                tone_pref = (prefs.get("tone") or "").lower() or None
                        logger.info(
                            "suggestions_meta | mode=inline tone=%s s1=%s s2=%s", tone_pref, sug_lines[0] if sug_lines else None, sug_lines[1] if len(sug_lines) > 1 else None
                        )
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass

    try:
        logger.info(
            "chat_response_meta | provider=%s emotion=%s conf=%.2f escalation=%s emojis_final=%d",
            provider,
            getattr(emotion_result, "emotion", "neutral"),
            getattr(emotion_result, "confidence", 0.0),
            escalation,
            count_emojis(result),
        )
    except Exception:  # noqa: BLE001
        pass

    try:
        sug_lines = [l.strip() for l in result.splitlines() if l.strip().startswith(SUGGESTION_PREFIX)][-2:]
        emotion_payload = {
            "label": getattr(emotion_result, "emotion", None),
            "confidence": getattr(emotion_result, "confidence", None),
        } if use_emotion else None
        user_id_for_log = None
        if isinstance(profile, dict):
            user_id_for_log = profile.get("user_id") or profile.get("id") or profile.get("_id")
        complexity = classify_complexity(prompt, result)
        try:
            from app.services import metrics as _m
            _m.incr("chat.responses.total")
            _m.incr(f"chat.responses.by_provider.{provider}")
            if complexity:
                _m.incr(f"complexity.{complexity}")
        except Exception:  # noqa: BLE001
            pass
        # Persona best-friend layer (post-processing) - DISABLED for direct questions
        # We skip persona responses for simple factual queries to keep responses clean
        try:
            if settings.ENABLE_PERSONA_RESPONSE:
                # Only apply persona for emotional/contextual queries, not simple facts
                prompt_lower = (prompt or "").lower()
                is_factual_query = any(keyword in prompt_lower for keyword in [
                    "what is my name", "whats my name", "what are my", "my name", 
                    "tell me my", "do you know my", "what do i like"
                ])
                
                if not is_factual_query:
                    from app.services.persona_response import generate_response as _persona_gen
                    user_id_for_log = user_id_for_log or (profile or {}).get("user_id")
                    persona_style = getattr(settings, "PERSONA_STYLE", "best_friend")
                    persona_emotion = getattr(emotion_result, "emotion", "neutral")
                    try:
                        if getattr(emotion_result, "confidence", 0.0) < settings.ADV_EMOTION_CONFIDENCE_THRESHOLD:
                            persona_emotion = "neutral"
                    except Exception:
                        pass
                    persona_result = await _persona_gen(
                        prompt,
                        emotion=persona_emotion,
                        user_id=str(user_id_for_log) if user_id_for_log else None,
                        base_ai_text=result,
                        style=persona_style,
                        confidence=getattr(emotion_result, "confidence", None),
                        second_emotion=None,
                    )
                    if persona_result:
                        result = persona_result
        except Exception:  # noqa: BLE001
            pass
        log_interaction_event(
            user_id=user_id_for_log,
            session_id=session_id,
            user_message=prompt,
            assistant_answer=result,
            emotion=emotion_payload,
            tone=getattr(emotion_result, "tone", None),
            suggestions=sug_lines,
            provider=provider,
        )
        if user_id_for_log:
            try:
                await update_behavior_from_event(
                    user_id=str(user_id_for_log),
                    complexity=complexity,
                    answer_chars=len(result),
                    tone_used=getattr(emotion_result, "tone", None),
                )
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return result


# Backward-compatibility alias used by some modules
async def generate_ai_response(prompt: str) -> str:
    return await get_response(prompt)

# =====================================================
# 🔹 Summarization Utility
# =====================================================
def summarize_text(text: str) -> str:
    summary_prompt = (
        "You are an expert at summarizing conversations. "
        "Provide a concise, third-person summary of the following transcript:\n\n"
        f"---\n{text}\n---\n\nSUMMARY:"
    )
    for idx, provider in enumerate(AI_PROVIDERS):
        if not _is_provider_available(provider):
            continue
        try:
            timeout_budget = settings.AI_PRIMARY_TIMEOUT if idx == 0 else settings.AI_FALLBACK_TIMEOUT
            def invoke() -> str:
                if provider == "gemini":
                    return _try_gemini(summary_prompt)
                if provider == "anthropic":
                    raise RuntimeError("Anthropic support removed")
                if provider == "cohere":
                    raise RuntimeError("Cohere support removed")
                raise RuntimeError("Unknown provider")
            return _call_with_timeout(invoke, timeout_budget)
        except TimeoutError as te:
            logger.warning(f"[AI] Summarization provider '{provider}' timeout: {te}")
            FAILED_PROVIDERS[provider] = time.time()
        except Exception as e:
            logger.error(f"[AI] Summarization failed with '{provider}': {e}")
            FAILED_PROVIDERS[provider] = time.time()
    return "❌ Failed to generate summary. All AI services unavailable."


def structured_distillation_summary(raw_items: list[dict], char_limit: int = 1500) -> str:
    """Generate a hierarchical distilled summary for a set of memory originals.

    raw_items: list of {title, value}
    Returns markdown-like structured summary with sections:
      - Categories (inferred heuristically: preferences, biographical, meta, other)
      - Bullet points per item (compressed)
    Falls back to simple summarization if providers unavailable.
    """
    # Preprocess into heuristic buckets
    buckets = {"preferences": [], "biographical": [], "meta": [], "other": []}
    for it in raw_items:
        title = (it.get("title") or "").lower()
        val = (it.get("value") or "").strip()
        text = f"{title} {val}".lower()
        if any(k in text for k in ["favorite", "likes", "prefers", "dislikes", "enjoys"]):
            buckets["preferences"].append(it)
        elif any(k in text for k in ["age", "birthday", "born", "live", "location", "from", "work", "job", "profession"]):
            buckets["biographical"].append(it)
        elif any(k in text for k in ["recent", "session", "conversation", "chat", "note"]):
            buckets["meta"].append(it)
        else:
            buckets["other"].append(it)

    # Build a compressed raw representation to feed to model
    def _compress(items: list[dict], limit_each: int = 140):
        out = []
        for i in items:
            t = i.get("title") or "(untitled)"
            v = (i.get("value") or "").replace("\n", " ")
            if len(v) > limit_each:
                v = v[:limit_each-3] + "..."
            out.append(f"- {t}: {v}")
        return "\n".join(out)

    raw_compiled_sections = []
    for cat, items in buckets.items():
        if not items:
            continue
        raw_compiled_sections.append(f"[{cat}]\n{_compress(items)}")
    raw_compiled = "\n\n".join(raw_compiled_sections)
    if len(raw_compiled) > 6000:
        raw_compiled = raw_compiled[:6000]  # hard safety cap

    prompt = (
        "You are an AI system creating a distilled hierarchical memory summary.\n"
        "Input items are already grouped by loose category tags in square brackets.\n"
        "Produce a concise structured summary using markdown-like headings and bullets.\n"
        "Guidelines:\n"
        "- Keep total output under " + str(char_limit) + " characters.\n"
        "- Use top-level headings for each category present.\n"
        "- Rephrase to be terse, factual, and merge duplicates.\n"
        "- Omit trivial or redundant details.\n"
        "- If a category has no meaningful items, skip it.\n"
        "- End with a short 'Core Signals:' bullet list (≤5 items) summarizing the most impactful points.\n"
        "\nINPUT:\n" + raw_compiled + "\n\nSTRUCTURED SUMMARY:\n"
    )
    for idx, provider in enumerate(AI_PROVIDERS):
        if not _is_provider_available(provider):
            continue
        try:
            timeout_budget = settings.AI_PRIMARY_TIMEOUT if idx == 0 else settings.AI_FALLBACK_TIMEOUT
            def invoke() -> str:
                if provider == "gemini":
                    return _try_gemini(prompt)
                if provider == "anthropic":
                    raise RuntimeError("Anthropic support removed")
                if provider == "cohere":
                    raise RuntimeError("Cohere support removed")
                raise RuntimeError("Unknown provider")
            out = _call_with_timeout(invoke, timeout_budget)
            if len(out) > char_limit:
                out = out[:char_limit-3] + "..."
            return out
        except TimeoutError as te:
            logger.warning(f"[AI] Distillation structured summary provider '{provider}' timeout: {te}")
            FAILED_PROVIDERS[provider] = time.time()
        except Exception as e:
            logger.error(f"[AI] Structured distillation failed with '{provider}': {e}")
            FAILED_PROVIDERS[provider] = time.time()
    # Fallback: simple summarization of concatenated text
    fallback_text = "\n".join(f"{i.get('title')}: {i.get('value')}" for i in raw_items)[:char_limit]
    return summarize_text(fallback_text)

# =====================================================
# 🔹 Fact Extraction Utility
# =====================================================
def extract_facts_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract structured facts (entities + relationships) from a conversation transcript.
    Returns a JSON dict with 'entities' and 'relationships'.
    """
    extraction_prompt = f"""
    Analyze the following transcript. Your only task is to extract entities and relationships.
    Respond with ONLY a valid JSON object. Do not include markdown, explanations, or any text
    outside of the JSON structure. If no facts are found, return {{"entities": [], "relationships": []}}.

    Transcript:
    ---
    {text}
    ---
    """
    try:
        # Build provider sequence (configurable). Default now prefers Gemini first.
        order_env = getattr(settings, "FACT_EXTRACT_PROVIDER_ORDER", None)
        if order_env:
            names = [n.strip().lower() for n in order_env.split(',') if n.strip()]
        else:
            names = ["gemini"]
        # Map names to callables (skip unknown silently)
        name_map = {
            "gemini": _try_gemini,
            # "cohere": _try_cohere,
            # "anthropic": _try_anthropic,
        }
        fact_sequence = [(n, name_map[n]) for n in names if n in name_map]
        raw_response = ""
        for idx, (name, func) in enumerate(fact_sequence):
            if not _is_provider_available(name):
                continue
            timeout_budget = settings.AI_PRIMARY_TIMEOUT if idx == 0 else settings.AI_FALLBACK_TIMEOUT
            try:
                raw_response = _call_with_timeout(lambda: func(extraction_prompt), timeout_budget)
                FAILED_PROVIDERS.pop(name, None)
                if raw_response:
                    break
            except TimeoutError as te:
                logger.warning(f"Fact extraction provider '{name}' timeout: {te}")
                FAILED_PROVIDERS[name] = time.time()
            except Exception as e:
                logger.warning(f"Fact extraction attempt failed for provider {name}: {e}")
                FAILED_PROVIDERS[name] = time.time()

        if not raw_response:
            raise RuntimeError("All fact-extraction providers failed.")

        # Attempt robust JSON parsing
        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start != -1 and end != -1:
            json_str = raw_response[start:end + 1]
            return json.loads(json_str)
        else:
            logger.warning(f"Fact extraction returned no valid JSON. Raw: {raw_response}")
            return {"entities": [], "relationships": []}

    except Exception as e:
        logger.error(f"Failed to extract facts from text: {e}")
        return {"entities": [], "relationships": []}
