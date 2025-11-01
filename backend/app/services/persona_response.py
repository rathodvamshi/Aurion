"""Persona response layer.

Blends detected emotion + templates + optional base AI text into a warm,
friend-like reply. Keeps emoji moderation (max 1-2 inserted) and supports
multiple persona styles (currently: best_friend, neutral, professional).
"""
from __future__ import annotations

from typing import Optional, List, Dict, Tuple
import random
import yaml
import os
import time
import logging
import hashlib

from app.config import settings
from pathlib import Path
from app.memory import session_memory
from app.services import metrics

logger = logging.getLogger(__name__)

# Resolve YAML path relative to repository structure regardless of CWD
_PERSONA_YAML_PATH = str(Path(__file__).resolve().parents[2] / "config" / "persona_responses.yml")
_TEMPLATE_CACHE: Dict[str, Dict] = {}
_TEMPLATE_MTIME: float | None = None
_CACHE_TTL = 30  # seconds

_EMOJI_FALLBACK = {
    # Use canonical keys matching detection outputs (happy, sad, angry, anxious, excited, neutral)
    "happy": ["😄", "🎉", "🤗"],
    "sad": ["💙", "🤗", "💌"],
    "angry": ["😤", "💢"],
    "anxious": ["😟", "🫶"],
    "excited": ["🤩", "🚀"],
    # Extended emotions (still supported)
    "confusion": ["🤔", "💡"],
    "gratitude": ["🥹", "💖"],
    "neutral": ["🙂"],
}

_SAFE_MAX_INSERT = 2

# In-process rotation memory (fallback if not using external store). Keyed by (user_id, emotion)
_RECENT_TEMPLATE_IDS: Dict[str, List[str]] = {}
_MAX_RECENT_PER_USER = 5

def _template_id(text: str) -> str:
    # stable hash id for template rotation (first 10 hex chars)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def _load_templates(force: bool = False) -> Dict:
    global _TEMPLATE_CACHE, _TEMPLATE_MTIME
    try:
        st = os.stat(_PERSONA_YAML_PATH)
        if force or _TEMPLATE_MTIME is None or (time.time() - (_TEMPLATE_MTIME or 0) > _CACHE_TTL) or st.st_mtime != _TEMPLATE_MTIME:
            with open(_PERSONA_YAML_PATH, "r", encoding="utf-8") as f:
                _TEMPLATE_CACHE = yaml.safe_load(f) or {}
            _TEMPLATE_MTIME = st.st_mtime
    except Exception:  # noqa: BLE001
        pass
    return _TEMPLATE_CACHE


def _pick_template(emotion: str, style: str, user_id: Optional[str]) -> Optional[str]:
    data = _load_templates()
    style = style or "best_friend"
    emotion_block = data.get(emotion) or data.get("neutral") or {}
    options: List[str] = emotion_block.get(style) or []
    if not options:
        # fallback chain
        options = emotion_block.get("best_friend") or []
    if not options:
        return None
    if not user_id:
        return random.choice(options)
    rec_key = f"{user_id}:{emotion}:{style}"
    recent = _RECENT_TEMPLATE_IDS.get(rec_key, [])
    # filter out recently used (soft)
    filtered = [t for t in options if _template_id(t) not in recent]
    choice = random.choice(filtered or options)
    tid = _template_id(choice)
    updated = recent + [tid]
    if len(updated) > _MAX_RECENT_PER_USER:
        updated = updated[-_MAX_RECENT_PER_USER:]
    _RECENT_TEMPLATE_IDS[rec_key] = updated
    return choice


def _maybe_add_emoji(text: str, emotion: str) -> str:
    # Avoid adding additional emoji for intense/negative categories beyond curated template ones
    if emotion in {"angry", "toxic"}:
        return text
    # If already has emoji, do nothing. Simple heuristic.
    if any(ord(ch) > 10000 for ch in text):
        return text
    choices = _EMOJI_FALLBACK.get(emotion) or []
    if not choices:
        return text
    if random.random() < 0.70:  # 70% chance to add one
        return f"{text} {random.choice(choices)}".strip()
    return text


def _sarcasm_score(user_text: str) -> float:
    low = user_text.lower()
    score = 0.0
    # crude signals: positive emoji + negative lexicon or trailing '/s'
    positive_markers = ["😂", "😅", "😆", "lol", "lmao"]
    negative_words = ["great", "awesome", "lovely", "perfect"]
    if low.strip().endswith("/s"):
        score += 0.6
    if any(p in low for p in positive_markers) and any(f" {w}" in low or low.startswith(w) for w in negative_words):
        score += 0.5
    return min(score, 1.0)


async def generate_response(
    user_text: str,
    *,
    emotion: Optional[str] = None,
    user_id: Optional[str] = None,
    base_ai_text: Optional[str] = None,
    style: Optional[str] = None,
    confidence: Optional[float] = None,
    second_emotion: Optional[Tuple[str, float]] = None,
) -> str:
    """Compose persona reply.

    Args:
      user_text: raw user input
      emotion: canonical emotion label (joy, sadness, ...)
      user_id: for context memory
      base_ai_text: optional already-generated model reply to blend
      style: persona style override
    """
    if not settings.ENABLE_PERSONA_RESPONSE:
        return base_ai_text or ""

    style = style or settings.PERSONA_STYLE
    original_emotion = (emotion or "neutral").lower()
    emotion_norm = original_emotion
    fallback_reason = None

    # Confidence gate (low confidence -> neutral)
    if confidence is not None and confidence < settings.ADV_EMOTION_CONFIDENCE_THRESHOLD:
        fallback_reason = fallback_reason or "low_confidence"
        emotion_norm = "neutral"

    # Sarcasm dampening
    if _sarcasm_score(user_text) >= 0.6 and emotion_norm in {"happy", "excited", "joy"}:
        fallback_reason = fallback_reason or "sarcasm"
        emotion_norm = "neutral"

    # 1. Retrieve recent context (may be used later for personalization hook)
    context_pairs = []
    try:
        if user_id:
            context_pairs = await session_memory.get_context(user_id)
    except Exception:  # noqa: BLE001
        context_pairs = []

    # 2. Recent emotion streak (escalation detection)
    escalation = False
    try:
        if user_id and original_emotion in {"sad", "angry", "anxious", "sadness"}:
            emos = await session_memory.get_recent_emotions(user_id, limit=10)  # type: ignore[attr-defined]
            streak = 0
            for lbl in reversed(emos):
                if not lbl:
                    break
                if lbl.startswith(original_emotion[:3]):  # sad vs sadness
                    streak += 1
                else:
                    break
            if streak >= 3:
                escalation = True
    except Exception:
        escalation = False

    # 3. Pick a template
    chosen = _pick_template(emotion_norm, style, user_id) or ""

    # Multi-emotion blend (if second provided and close probability)
    if second_emotion and chosen:
        sec_label, sec_conf = second_emotion
        if sec_label and sec_conf and confidence is not None:
            margin = confidence - sec_conf if sec_conf is not None else 1.0
            if 0.0 < margin <= 0.12 and sec_conf >= 0.30 and sec_label != emotion_norm:
                # Blend by appending an acknowledging clause if not already long
                if len(chosen) < 140:
                    chosen = f"{chosen.split('!')[0].rstrip('.')} but I can feel a bit of {sec_label} there too — that’s totally okay."  # simple blend

    # 4. Optionally blend with base AI text - prioritize base AI text for direct answers
    final: str
    if base_ai_text:
        # Always prefer base AI text - it answers the question directly
        # Only use template as prefix for emotional support if needed
        if emotion_norm in {"sadness", "angry", "sad", "anxious"} and len(chosen) < 50:
            # Add brief emotional support prefix only for negative emotions
            final = f"{chosen} {base_ai_text}".strip()
        else:
            # For neutral/positive emotions, use base AI text directly
            final = base_ai_text
    elif chosen:
        final = chosen
    else:
        final = "(I'm here)"

    # Escalation softening: keep it short and sweet
    if escalation and len(final) < 150 and emotion_norm in {"sad", "angry", "anxious"}:
        final = f"{final} I'm here for you."

    # 5. Minimal emoji enrichment (max 1 inserted by us, keep it subtle)
    if len(final) < 200:  # Only add emoji for shorter responses
        final = _maybe_add_emoji(final, emotion_norm)

    # 6. Persist to memory buffer (fire-and-forget)
    try:
        if user_id and base_ai_text is not None:
            # we store the user input and final (persona) output
            await session_memory.add_to_context(user_id, user_text, final, emotion_norm)
    except Exception:  # noqa: BLE001
        pass

    # 7. Metrics & telemetry
    try:
        h = hashlib.sha256(user_text.encode("utf-8")).hexdigest()[:10]
        if fallback_reason:
            try:
                metrics.incr(f"persona.fallback.neutral.{fallback_reason}")
            except Exception:
                pass
        try:
            metrics.incr(f"persona.template.select.{emotion_norm}")
        except Exception:
            pass
        if escalation:
            try:
                metrics.incr(f"persona.escalation.{emotion_norm}")
            except Exception:
                pass
        logger.debug(
            f"[persona] emotion={emotion_norm} orig={original_emotion} fallback={fallback_reason} escalate={escalation} style={style} text_hash={h} len_ctx={len(context_pairs)}"
        )
    except Exception:  # noqa: BLE001
        pass

    return final
