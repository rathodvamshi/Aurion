"""Emotion & Tone Detection + Emoji Enrichment Service.

Lightweight heuristic module (no external heavy models) that:
 1. Detects coarse emotion from a user message (sad, happy, angry, anxious, excited, neutral).
 2. Builds a response tone directive (supportive, upbeat, calm, neutral) for downstream prompt composition.
 3. Provides an "emoji palette" that can be applied to the final assistant text.
 4. Enriches generated assistant reply with context-appropriate emojis while avoiding overuse.

Guidelines:
 - Emojis added only if not already present for that semantic slot.
 - Max 4 injected emojis (excluding those already in model output) to keep output natural.
 - Avoid duplicating the same emoji more than twice.
 - Preserve markdown / code blocks (not expected often in casual chat, but guarded).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional
import re


PRIMARY_EMOTION_KEYWORDS: Dict[str, List[str]] = {
    "sad": ["sad", "down", "unhappy", "depressed", "blue", "gloomy", "upset", "low"],
    "happy": ["happy", "glad", "great", "awesome", "fantastic", "wonderful", "good mood"],
    "angry": ["angry", "mad", "furious", "irritated", "annoyed", "pissed"],
    "anxious": ["anxious", "worried", "nervous", "stressed", "overwhelmed", "scared", "afraid"],
    "excited": ["excited", "pumped", "thrilled", "ecstatic", "can't wait", "so excited"],
}

# Emoji signal lists (kept small & explicit to avoid noisy inference). Each emoji contributes to the related emotion score.
EMOTION_EMOJIS: Dict[str, List[str]] = {
    "sad": ["😢", "😞", "😔", "😭", "☹️", "😟"],
    "happy": ["😄", "😀", "😊", "🙂", "😃", "😁", "😸"],
    "angry": ["😠", "😡", "😤", "🔥"],  # include 🔥 sometimes used in hype but we bias to excited via keyword; context may adjust later
    "anxious": ["😰", "😥", "😨", "😬", "😟"],
    "excited": ["🤩", "🎉", "🚀", "🙌", "🔥", "✨"],
}

# Mapping emotion -> (tone directive, default leading emoji, palette list)
EMOTION_STYLE_MAP = {
    "sad": {
        "tone": "supportive",
        "lead": "😔",
        "palette": ["😔", "💛", "🤗", "🌱", "💬"],
    },
    "happy": {
        "tone": "playful",
        "lead": "😄",
        "palette": ["😄", "😊", "🎉", "🌟", "🙌"],
    },
    "angry": {
        "tone": "calm",
        "lead": "😤",
        "palette": ["😤", "😌", "🧘", "🤝", "💬"],
    },
    "anxious": {
        "tone": "reassuring",
        "lead": "😟",
        "palette": ["😟", "💛", "🫶", "🧘", "🌤️"],
    },
    "excited": {
        "tone": "enthusiastic",
        "lead": "🤩",
        "palette": ["🤩", "🚀", "🎉", "🔥", "🙌"],
    },
    "neutral": {
        "tone": "neutral",
        "lead": "🙂",
        "palette": ["🙂", "💬", "🤖"],
    },
}

NEUTRAL = "neutral"


@dataclass
class EmotionResult:
    emotion: str
    confidence: float
    tone: str
    lead_emoji: str
    palette: List[str]


def detect_emotion(text: str) -> EmotionResult:
    """Very lightweight keyword heuristic.

    If multiple emotions match, pick the highest keyword density.
    Returns neutral with low confidence if nothing meaningful found.
    """
    lower = text.lower()
    scores: Dict[str, int] = {}
    for emotion, kws in PRIMARY_EMOTION_KEYWORDS.items():
        count = sum(1 for kw in kws if kw in lower)
        if count:
            scores[emotion] = count
    # Emoji-based augmentation
    if any(ch in text for ch in ("😢", "😞", "😔", "😭", "☹️", "😟", "😄", "😀", "😊", "🙂", "😃", "😁", "😸", "😠", "😡", "😤", "🔥", "😰", "😥", "😨", "😬", "🤩", "🎉", "🚀", "🙌", "✨")):
        for emotion, emjs in EMOTION_EMOJIS.items():
            ecount = sum(text.count(e) for e in emjs)
            if ecount:
                # Give emojis slightly higher weight (1.2x) so a lone emoji still registers above weak keyword noise
                scores[emotion] = scores.get(emotion, 0) + int(ecount * 1.2 + 0.5)
    if not scores:
        style = EMOTION_STYLE_MAP[NEUTRAL]
        return EmotionResult(NEUTRAL, 0.15, style["tone"], style["lead"], style["palette"])
    # select max; break ties by predefined priority order
    ordered = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    top_emotion, top_score = ordered[0]
    style = EMOTION_STYLE_MAP.get(top_emotion, EMOTION_STYLE_MAP[NEUTRAL])
    # crude confidence scaling: min 0.55 up to 0.95 based on count
    confidence = min(0.5 + 0.15 * top_score, 0.95)
    return EmotionResult(top_emotion, confidence, style["tone"], style["lead"], style["palette"])


EMOJI_SENTENCE_POSITIONS = ["start", "mid", "end"]


def count_emojis(text: str) -> int:
    return len(re.findall(r"[\U0001F300-\U0001FAFF]", text))


def enrich_with_emojis(original: str, emotion: EmotionResult, max_new: int = 4, hard_cap: Optional[int] = None) -> str:
    """Inject context-appropriate emojis into the assistant's reply.

    Strategy:
      - Skip code/pre-formatted blocks entirely (simple regex for backticks).
      - Ensure at least one leading emoji if emotion != neutral and none already at start.
      - Attempt to add at most one emoji per major sentence chunk until budget exhausted.
      - Avoid stacking emojis (>=2) directly adjacent.
    """
    if not original.strip():
        return original

    # Protect code blocks (very simple heuristic)
    if "```" in original:
        return original

    text = original
    inserted = 0
    lead_present = bool(re.match(r"^[\W_]*[\U0001F300-\U0001FAFF]", text))  # crude emoji at start
    if emotion.emotion != NEUTRAL and not lead_present:
        text = f"{emotion.lead_emoji} {text}"; inserted += 1

    if hard_cap is not None and count_emojis(text) >= hard_cap:
        return text
    if inserted >= max_new:
        return text

    # Split into sentences (simple)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) == 1:
        sentences = [text]

    palette_cycle = [e for e in emotion.palette if e != emotion.lead_emoji] or emotion.palette
    used_counts: Dict[str, int] = {p: text.count(p) for p in palette_cycle}

    def pick_emoji() -> Optional[str]:
        # prefer least used
        sorted_palette = sorted(palette_cycle, key=lambda p: used_counts.get(p, 0))
        for c in sorted_palette:
            if used_counts.get(c, 0) < 2:  # avoid more than twice
                used_counts[c] = used_counts.get(c, 0) + 1
                return c
        return None

    enhanced_sentences: List[str] = []
    for idx, s in enumerate(sentences):
        if hard_cap is not None and count_emojis(text) + inserted >= hard_cap:
            enhanced_sentences.append(s)
            continue
        if inserted >= max_new:
            enhanced_sentences.append(s)
            continue
        clean = s.strip()
        if not clean:
            enhanced_sentences.append(s)
            continue
        # Skip if sentence already ends with emoji
        if re.search(r"[\U0001F300-\U0001FAFF]$", clean):
            enhanced_sentences.append(s)
            continue
        # Choose position: end favored
        emoji = pick_emoji()
        if not emoji:
            enhanced_sentences.append(s)
            continue
        # Avoid adding if sentence extremely short and already early emoji used
        if len(clean) < 12 and idx > 0:
            enhanced_sentences.append(s)
            continue
        enhanced_sentences.append(f"{clean} {emoji}")
        inserted += 1
    # Rebuild (preserve original spacing by using single space join)
    rebuilt = " ".join(enhanced_sentences)
    return rebuilt


def build_persona_directive(
    emotion: EmotionResult,
    last_positive_memory: Optional[str],
    escalation: bool = False,
    tone_override: Optional[str] = None,
) -> str:
    """Build a concise persona directive focused on current response only."""
    parts = [
        f"Adopt a {emotion.tone} tone.",
        "Keep response SHORT (1-3 sentences), friendly, and direct.",
        "Focus ONLY on answering the user's current question.",
    ]
    if tone_override:
        parts.append(f"User prefers {tone_override} tone.")
    if escalation and emotion.emotion in {"sad", "anxious", "angry"}:
        parts.append("Be empathetic but brief - do not add multiple follow-up questions.")
    # Removed last_positive_memory reference to avoid mentioning old conversations
    return " ".join(parts)


__all__ = [
    "EmotionResult",
    "detect_emotion",
    "enrich_with_emojis",
    "build_persona_directive",
    "count_emojis",
]
