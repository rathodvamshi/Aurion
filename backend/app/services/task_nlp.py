from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import dateparser
import pytz
import logging

logger = logging.getLogger(__name__)


TASK_KEYWORDS = (
    "remind",
    "reminder",
    "schedule",
    "task",
    "meeting",
    "call",
    "appointment",
    "wake",
    "alarm",
    "note",
    "todo",
    "create",
    "set",
    "make",
    "add",
)

# Multilingual support
MULTILINGUAL_TASK_KEYWORDS = {
    "hindi": ["yaad", "dilana", "bata", "karna", "kal", "aaj", "subah", "shaam"],
    "spanish": ["recordar", "avisar", "cita", "reunion"],
    "french": ["rappeler", "rendez-vous", "reunion"],
    "german": ["erinnern", "termin", "treffen"],
}

# Context phrases that need clarification
CONTEXT_PHRASES = {
    "meal_times": ["after lunch", "before dinner", "after breakfast", "before lunch"],
    "relative_times": ["early", "late", "soon", "later", "tonight", "this evening"],
    "vague_periods": ["sometime", "eventually", "when possible", "when convenient"],
    "choice_words": ["or", "either", "maybe", "perhaps", "could be"],
}

# Recurring patterns
RECURRING_PATTERNS = [
    r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    r"daily|weekly|monthly",
    r"every\s+day|every\s+week|every\s+month",
    r"repeat",
]


def detect_task_intent(message: str) -> bool:
    """
    Enhanced intent detection with multilingual support and context awareness.
    Detects task creation, modification, and management intents.
    """
    if not message:
        return False
    
    low = message.lower().strip()
    
    # Check for cancellation/modification intents first
    cancel_keywords = ["cancel", "delete", "remove", "stop", "abort"]
    if any(keyword in low for keyword in cancel_keywords):
        return True
    
    # Check for listing intents
    list_keywords = ["show", "list", "display", "what", "upcoming", "tomorrow", "today"]
    if any(keyword in low for keyword in list_keywords) and any(task_word in low for task_word in ["task", "reminder", "meeting"]):
        return True
    
    # Check for verification intents
    verify_keywords = ["verify", "check", "confirm", "otp", "code"]
    if any(keyword in low for keyword in verify_keywords):
        return True
    
    # Check for reschedule intents
    reschedule_keywords = ["reschedule", "move", "change", "postpone", "delay"]
    if any(keyword in low for keyword in reschedule_keywords):
        return True
    
    # Check for English task keywords
    english_match = any(k in low for k in TASK_KEYWORDS)
    
    # Check for multilingual keywords
    multilingual_match = False
    for language, keywords in MULTILINGUAL_TASK_KEYWORDS.items():
        if any(keyword in low for keyword in keywords):
            multilingual_match = True
            break
    
    # Enhanced pattern matching for task creation
    task_patterns = [
        r"\b(?:remind|schedule|create|set|make|add)\s+(?:me\s+)?(?:to\s+)?",
        r"\b(?:wake|alarm|call|meeting|appointment)\s+(?:me\s+)?",
        r"\b(?:task|todo|note|reminder)\s+(?:for|about|to)\s+",
    ]
    
    pattern_match = any(re.search(pattern, low) for pattern in task_patterns)
    
    # Guard against false positives - search/information queries should NOT trigger reminders
    false_positive_patterns = [
        r"what\s+is\s+a\s+(?:reminder|task|meeting)",
        r"how\s+to\s+(?:create|make|set)",
        r"explain\s+(?:reminder|task|meeting)",
        r"tell\s+me\s+about\s+(?:reminder|task|meeting)",
        # Search/info queries - don't treat as reminders
        r"tell\s+me\s+about\s+(?:recent|latest|current|tech|technology|news|updates)",
        r"tell\s+me\s+about\s+(?!.*(?:remind|schedule|task|meeting|appointment|call|alarm))",
        r"what\s+(?:are|is)\s+(?:recent|latest|current|tech|technology|news|updates)",
        r"show\s+me\s+(?:recent|latest|current|tech|technology|news)",
        r"find\s+me\s+(?:information|info|about)",
    ]
    
    is_false_positive = any(re.search(pattern, low) for pattern in false_positive_patterns)
    
    # Additional check: if message contains search keywords and no explicit task keywords, it's likely a search query
    search_keywords = ["recent", "latest", "current", "tech", "technology", "news", "updates", "information"]
    has_search_keywords = any(keyword in low for keyword in search_keywords)
    explicit_task_keywords = ["remind me", "schedule", "create task", "set reminder", "appointment", "meeting", "alarm"]
    has_explicit_task = any(keyword in low for keyword in explicit_task_keywords)
    
    # If it has search keywords but no explicit task keywords, it's probably not a reminder
    if has_search_keywords and not has_explicit_task:
        is_false_positive = True
    
    return (english_match or multilingual_match or pattern_match) and not is_false_positive


def _strip_quotes(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1].strip()
    return s


def _extract_title(message: str) -> Optional[str]:
    """
    Enhanced title extraction with multilingual support and better patterns.
    """
    low = (message or "").lower()
    
    # Enhanced patterns for title extraction
    patterns = [
        # English patterns
        r"remind\s+me\s+(?:to|about)\s+(.+?)(?:\s+at|\s+in|\s+on|\s+for|\s+tomorrow|\s+today|$)",
        r"schedule\s+(?:a\s+)?(?:meeting|appointment|task)\s+(?:about|for|to)\s+(.+?)(?:\s+at|\s+in|\s+on|$)",
        r"create\s+(?:a\s+)?(?:reminder|task|note)\s+(?:for|about|to)\s+(.+?)(?:\s+at|\s+in|\s+on|$)",
        r"set\s+(?:a\s+)?(?:reminder|alarm)\s+(?:for|to)\s+(.+?)(?:\s+at|\s+in|\s+on|$)",
        r"wake\s+me\s+(?:up\s+)?(?:for|to)\s+(.+?)(?:\s+at|\s+in|\s+on|$)",
        r"call\s+(?:me\s+)?(?:about|for)\s+(.+?)(?:\s+at|\s+in|\s+on|$)",
        
        # Multilingual patterns (Hindi example)
        r"yaad\s+dilana\s+(.+?)(?:\s+kal|\s+aaj|\s+subah|\s+shaam|$)",
        r"kal\s+(.+?)\s+ki\s+yaad",
        r"aaj\s+(.+?)\s+ki\s+yaad",
        
        # Generic patterns
        r"(?:remind|schedule|create|set|make|add)\s+(?:me\s+)?(?:to\s+)?(.+?)(?:\s+at|\s+in|\s+on|\s+for|$)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, low)
        if match:
            title = _strip_quotes(match.group(1)).strip()
            # Clean up common time words that might be captured
            title = re.sub(r'\s+(at|in|on|for|tomorrow|today|kal|aaj|subah|shaam)$', '', title)
            if title and len(title) > 2:  # Ensure meaningful title
                return title.capitalize()
    
    # Fallback: extract from common structures
    fallback_patterns = [
        r"remind\s+me\s+(.+)$",
        r"schedule\s+(.+)$",
        r"create\s+(.+)$",
        r"set\s+(.+)$",
    ]
    
    for pattern in fallback_patterns:
        match = re.search(pattern, low)
        if match:
            title = _strip_quotes(match.group(1)).strip()
            # Remove time-related words
            title = re.sub(r'\s+(at|in|on|for|tomorrow|today|kal|aaj|subah|shaam|8pm|9am|morning|evening|night).*$', '', title)
            if title and len(title) > 2:
                return title.capitalize()
    
    return None


def _extract_priority(message: str) -> Optional[str]:
    low = (message or "").lower()
    if "urgent" in low:
        return "urgent"
    if "high" in low:
        return "high"
    if "medium" in low:
        return "medium"
    if "low" in low:
        return "low"
    return None


def _extract_notes(message: str) -> Optional[str]:
    # Best-effort: text in quotes often represents details
    m = re.search(r'"([^"]{3,200})"', message or "")
    if m:
        return m.group(1).strip()
    return None


def parse_time(text: str, user_tz: str = "UTC") -> Optional[datetime]:
    """
    Parse time text with timezone handling as specified in requirements.
    Returns naive UTC datetime for MongoDB storage.
    """
    if not text or not text.strip():
        return None
    
    user_now = datetime.now(pytz.timezone(user_tz))
    settings = {
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": user_now,
        "TIMEZONE": user_tz,
        "RETURN_AS_TIMEZONE_AWARE": True
    }
    
    try:
        parsed = dateparser.parse(text, settings=settings)
        if not parsed:
            return None
        
        # Normalize to UTC naive
        due_utc = parsed.astimezone(pytz.UTC).replace(tzinfo=None)
        
        # ±60s tolerance: nudge near-past into +1 minute
        delta = (due_utc - datetime.utcnow()).total_seconds()
        if abs(delta) < 60 and delta < 0:
            due_utc = due_utc + timedelta(minutes=1)
        
        # round seconds for stability
        due_utc = due_utc.replace(second=0, microsecond=0)
        
        logger.info(f"[NLP_TIME] Text='{text}' → UTC={due_utc.strftime('%Y-%m-%d %H:%M UTC')}")
        return due_utc
    except Exception as e:
        logger.warning(f"[NLP_TIME] Failed to parse '{text}': {e}")
        return None


def _parse_datetime(message: str, user_timezone: Optional[str]) -> Optional[datetime]:
    """Legacy wrapper for backward compatibility."""
    return parse_time(message, user_timezone or "UTC")


def _detect_ambiguities(message: str) -> Dict[str, Any]:
    """
    Enhanced ambiguity detection covering all test cases.
    """
    low = (message or "").lower()
    
    # Check for vague time phrases
    vague_phrases = CONTEXT_PHRASES["relative_times"] + CONTEXT_PHRASES["vague_periods"]
    has_vague = any(phrase in low for phrase in vague_phrases)
    
    # Check for context phrases that need clarification
    has_meal_context = any(phrase in low for phrase in CONTEXT_PHRASES["meal_times"])
    has_choice_words = any(word in low for word in CONTEXT_PHRASES["choice_words"])
    
    # Check for recurring patterns (not yet implemented)
    has_recurring = any(re.search(pattern, low) for pattern in RECURRING_PATTERNS)
    
    # Enhanced time pattern detection
    time_patterns = [
        r"\d{1,2}:\d{2}\s*(?:am|pm)?",
        r"\d{1,2}\s*(?:am|pm)",
        r"(?:morning|afternoon|evening|night)",
        r"(?:today|tomorrow|yesterday)",
        r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        r"(?:january|february|march|april|may|june|july|august|september|october|november|december)",
        r"(?:in\s+\d+\s+(?:minute|hour|day|week|month)s?)",
        r"(?:next\s+(?:week|month|year))",
        # Multilingual time patterns
        r"(?:kal|aaj|subah|shaam|raat)",
        r"(?:mañana|tarde|noche)",  # Spanish
        r"(?:demain|matin|soir|nuit)",  # French
    ]
    
    time_matches = []
    for pattern in time_patterns:
        time_matches.extend(re.findall(pattern, low))
    
    has_multiple_times = len(time_matches) > 1
    
    # Check for conflicting time references
    has_conflicting_times = False
    if "yesterday" in low and ("today" in low or "tomorrow" in low):
        has_conflicting_times = True
    if "morning" in low and "evening" in low:
        has_conflicting_times = True
    
    # Check for incomplete time references
    has_incomplete_time = False
    incomplete_patterns = [
        r"at\s+$",  # "remind me at"
        r"in\s+$",  # "remind me in"
        r"on\s+$",  # "remind me on"
        r"for\s+$",  # "remind me for"
    ]
    has_incomplete_time = any(re.search(pattern, low) for pattern in incomplete_patterns)
    
    return {
        "has_vague": has_vague,
        "has_multiple_times": has_multiple_times,
        "has_choice": has_choice_words,
        "has_meal_context": has_meal_context,
        "has_recurring": has_recurring,
        "has_conflicting_times": has_conflicting_times,
        "has_incomplete_time": has_incomplete_time,
        "time_matches": time_matches,
        "vague_phrases_found": [phrase for phrase in vague_phrases if phrase in low],
        "context_phrases_found": [phrase for phrase in CONTEXT_PHRASES["meal_times"] if phrase in low],
    }


def _cross_validate_entities(entities: Dict[str, Any], user_timezone: Optional[str]) -> Dict[str, Any]:
    """
    Enhanced cross-validation covering all edge cases from test suite.
    """
    issues = []
    due_date = entities.get("due_date")
    
    if due_date:
        now_utc = datetime.utcnow()
        delta_secs = (due_date - now_utc).total_seconds()
        
        # Past time check (beyond 10 minutes)
        if delta_secs < -600:
            issues.append({
                "type": "past_time",
                "message": "That time has already passed. Should I schedule for tomorrow instead?",
                "delta_minutes": int(abs(delta_secs) / 60)
            })
        
        # Grace window bump (within 2 hours of past)
        elif delta_secs < 0 and delta_secs > -7200:
            try:
                entities["due_date"] = due_date + timedelta(days=1)
                issues.append({
                    "type": "auto_bump",
                    "message": f"Bumped to tomorrow since it's {int(abs(delta_secs) / 60)} minutes past.",
                    "new_time": entities["due_date"]
                })
            except Exception:
                pass
        
        # Edge case: exactly at current time (within 1 minute tolerance)
        elif abs(delta_secs) < 60:
            # Nudge forward to avoid immediate execution
            entities["due_date"] = now_utc + timedelta(minutes=1)
            issues.append({
                "type": "time_adjustment",
                "message": "Adjusted time to 1 minute from now to avoid immediate execution.",
                "new_time": entities["due_date"]
            })
    
    # Missing title check
    if not entities.get("title"):
        issues.append({
            "type": "missing_title",
            "message": "What should I remind you about?"
        })
    
    # Title too short
    elif len(entities.get("title", "")) < 3:
        issues.append({
            "type": "title_too_short",
            "message": "Please provide a more descriptive title for your reminder."
        })
    
    # Check for recurring patterns (not yet implemented)
    if entities.get("title") and any(re.search(pattern, entities["title"].lower()) for pattern in RECURRING_PATTERNS):
        issues.append({
            "type": "recurring_not_supported",
            "message": "Recurring reminders are not yet supported. Would you like to create a one-time reminder instead?"
        })
    
    return {"issues": issues, "entities": entities}


def extract_task_entities(message: str, user_timezone: Optional[str]) -> Dict[str, Any]:
    title = _extract_title(message) or None
    priority = _extract_priority(message)
    notes = _extract_notes(message)
    due_dt = _parse_datetime(message, user_timezone)
    
    entities = {
        "title": title,
        "due_date": due_dt,  # naive UTC datetime (None if missing/invalid)
        "priority": priority,
        "notes": notes,
    }
    
    # Detect ambiguities
    ambiguities = _detect_ambiguities(message)
    
    # Cross-validate for logical issues
    validation = _cross_validate_entities(entities, user_timezone)
    
    # Enhanced clarification logic covering all test cases
    needs_clarification = False
    clarification_reason = None
    
    # Priority order for clarification reasons
    if ambiguities["has_recurring"]:
        needs_clarification = True
        clarification_reason = "recurring_not_supported"
    elif ambiguities["has_conflicting_times"]:
        needs_clarification = True
        clarification_reason = "conflicting_times"
    elif ambiguities["has_incomplete_time"]:
        needs_clarification = True
        clarification_reason = "incomplete_time"
    elif ambiguities["has_meal_context"]:
        needs_clarification = True
        clarification_reason = "meal_context"
    elif not due_dt and not ambiguities["has_vague"]:
        needs_clarification = True
        clarification_reason = "missing_time"
    elif ambiguities["has_vague"]:
        needs_clarification = True
        clarification_reason = "vague_time"
    elif ambiguities["has_multiple_times"] or ambiguities["has_choice"]:
        needs_clarification = True
        clarification_reason = "ambiguous_time"
    elif validation["issues"]:
        needs_clarification = True
        clarification_reason = "validation_issues"
    
    result = {
        "entities": validation["entities"],
        "needs_clarification": needs_clarification,
        "clarification_reason": clarification_reason,
        "ambiguities": ambiguities,
        "validation_issues": validation["issues"],
        "confidence": 0.9 if not needs_clarification else 0.5,
    }
    
    # Debug logging
    try:
        logger.info(
            "[NLP_ENTITY] Title=%s, TimePhrase=%s, Confidence=%.2f, NeedsClarification=%s",
            title or "None",
            "detected" if due_dt else "missing",
            result["confidence"],
            needs_clarification
        )
        if ambiguities["time_matches"]:
            logger.info("[NLP_AMBIGUITY] TimeMatches=%s", ambiguities["time_matches"])
    except Exception:
        pass
    
    return result


def needs_followups(entities: Dict[str, Any]) -> Dict[str, bool]:
    return {
        "missing_time": entities.get("due_date") is None,
        "missing_title": not bool(entities.get("title")),
    }


