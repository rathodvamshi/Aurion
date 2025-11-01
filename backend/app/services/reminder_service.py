"""Reminder service: natural language time understanding, IST normalization,
recurrence (RRULE) support, scheduling with Celery, and MongoDB storage.

Contract:
- parse_input(text) -> { task_description, time_expression }
- plan_schedule(time_expression) -> { first_run_utc_naive: datetime, pretty_ist: str, rrule_str: Optional[str] }
- create_and_schedule(user_id, description, time_expression) -> task doc with id and schedule info

Notes:
- All user-visible times are expressed in IST (Asia/Kolkata).
- All stored datetimes are naive UTC for consistency with existing code.
- Celery ETA receives timezone-aware UTC datetimes to avoid timezone ambiguity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime, timedelta, timezone

from dateutil.rrule import rrule, rrulestr, DAILY, WEEKLY, MONTHLY, MO, TU, WE, TH, FR, SA, SU
from .gemini_nlu import extract_reminder_with_gemini, gemini_available

from app.database import db_client
from app.utils.time_utils import parse_and_validate_ist, format_ist
from app.config import settings

WEEKDAY_MAP = {
    "monday": MO,
    "tuesday": TU,
    "wednesday": WE,
    "thursday": TH,
    "friday": FR,
    "saturday": SA,
    "sunday": SU,
}


@dataclass
class ParsedInput:
    task_description: str
    time_expression: str


def parse_input(text: str) -> ParsedInput:
    """Extract task_description and time_expression from free text.

    Heuristics using regex and simple phrases; spaCy is optional and not required here.
    Examples:
      "Remind me to call mom tomorrow at 8pm" -> ("call mom", "tomorrow at 8pm")
      "Every Monday at 7:30 am pay rent" -> ("pay rent", "every Monday at 7:30 am")
    """
    s = (text or "").strip()
    if not s:
        return ParsedInput(task_description="", time_expression="")

    low = s.lower()

    # Common lead phrases to strip
    lead_patterns = [
        r"^remind\s+me\s+(?:to\s+)?",
        r"^set\s+(?:a\s+)?reminder\s+(?:to\s+)?",
        r"^create\s+(?:a\s+)?reminder\s+(?:to\s+)?",
        r"^schedule\s+(?:a\s+)?(?:task|reminder)\s+(?:to\s+)?",
    ]
    for pat in lead_patterns:
        s = re.sub(pat, "", s, flags=re.IGNORECASE)

    # Try spaCy NER for DATE/TIME entity extraction first
    try:
        import spacy  # type: ignore
        try:
            nlp = spacy.load("en_core_web_sm")
        except Exception:
            nlp = spacy.blank("en")
        doc = nlp(s)
        date_like_spans: List[Tuple[int, int]] = []
        for ent in getattr(doc, "ents", []):
            if ent.label_ in {"DATE", "TIME"}:
                date_like_spans.append((ent.start_char, ent.end_char))
        if date_like_spans:
            # Merge contiguous spans
            date_like_spans.sort()
            merged: List[Tuple[int, int]] = []
            for st, en in date_like_spans:
                if not merged or st > merged[-1][1] + 1:
                    merged.append((st, en))
                else:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], en))
            # Build time expression as concatenation; description is string with these removed
            parts = [s[a:b] for (a, b) in merged]
            time_expr_spacy = " ".join(p.strip() for p in parts if p.strip())
            desc_chars = []
            last = 0
            for a, b in merged:
                if last < a:
                    desc_chars.append(s[last:a])
                last = b
            if last < len(s):
                desc_chars.append(s[last:])
            desc_spacy = (" ".join(desc_chars)).strip(",. ")
            if time_expr_spacy:
                return ParsedInput(task_description=desc_spacy, time_expression=time_expr_spacy)
    except Exception:
        pass

    # Try to split on time prepositions
    # Find last occurrence of time anchor to separate description and time
    anchors = [" at ", " in ", " on ", " by ", " after ", " every ", " daily", " weekly", " monthly"]
    idx = -1
    anchor_used = None
    for a in anchors:
        j = s.lower().rfind(a)
        if j > idx:
            idx = j
            anchor_used = a

    if idx != -1:
        desc = s[:idx].strip(",. ")
        time_expr = s[idx:].strip(",. ")
        # Remove leading preposition from time expr
        time_expr = re.sub(r"^(at|in|on|by|after|every)\s+", "", time_expr, flags=re.IGNORECASE)
        if not desc:
            # If desc empty, invert assumption: first token(s) after anchors might be description at end
            desc = s
            time_expr = ""
    else:
        # No clear split; attempt simple pattern: "<desc> tomorrow at 9pm"
        m = re.search(r"\b(today|tomorrow|tonight|next\s+\w+|in\s+\d+\s+\w+|every\b.+)$", s, re.IGNORECASE)
        if m:
            desc = s[: m.start()].strip(",. ")
            time_expr = m.group(0).strip()
        else:
            # As a fallback, if message starts with time anchor, put rest as description
            m2 = re.search(r"^(every\b.+|in\s+\d+\s+\w+|tomorrow\b.+|today\b.+)$", s, re.IGNORECASE)
            if m2:
                desc = ""
                time_expr = m2.group(0).strip()
            else:
                # No time detected; entire string as description; time will default later
                desc = s
                time_expr = ""

    return ParsedInput(task_description=desc.strip(), time_expression=time_expr.strip())


def parse_input_with_intent(text: str) -> Dict[str, str]:
    """Gemini-first parse that returns intent along with fields.

    Output keys: intent, task_description, time_expression
    Fallback: uses local parse_input and heuristic intent.
    """
    s = (text or "").strip()
    if not s:
        return {"intent": "other", "task_description": "", "time_expression": ""}
    # Gemini-first
    try:
        gem = extract_reminder_with_gemini(s)
    except Exception:
        gem = None
    if gem:
        return {
            "intent": gem.get("intent", "other"),
            "task_description": gem.get("task_description", ""),
            "time_expression": gem.get("time_expression", ""),
        }
    # Local fallback
    parsed = parse_input(s)
    intent = "reminder" if "remind me" in s.lower() else "other"
    return {"intent": intent, "task_description": parsed.task_description, "time_expression": parsed.time_expression}


def _detect_recurrence(time_expression: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """Detect recurring patterns and build an RRULE string.

    Returns (rrule_str, extras) where extras may contain parsed weekdays, etc.
    """
    if not time_expression:
        return None, {}
    t = time_expression.lower().strip()

    # Daily
    if re.search(r"\b(daily|every\s+day|everyday)\b", t):
        return "FREQ=DAILY", {}

    # Weekends / weekdays
    if re.search(r"\bweekends?\b", t):
        return "FREQ=WEEKLY;BYDAY=SA,SU", {"weekends": True}
    if re.search(r"\bweekdays?\b", t):
        return "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", {"weekdays": True}

    # Weekly specific days (single or multiple separated by commas/and)
    m_multi = re.search(r"every\s+([a-z,\s]+?)\b(?:at\b|\d|am|pm|$)", t)
    if m_multi:
        days_str = m_multi.group(1)
        tokens = re.split(r"\s*(?:,|and)\s*", days_str)
        bydays = []
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue
            abbr = tok[:3]
            wd_full = {
                "mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday",
                "fri": "friday", "sat": "saturday", "sun": "sunday",
            }
            key = wd_full.get(abbr, tok)
            if key in WEEKDAY_MAP:
                bydays.append(key[:2].upper())
        if bydays:
            return f"FREQ=WEEKLY;BYDAY={','.join(bydays)}", {"weekdays": bydays}

    m = re.search(r"every\s+((?:mon|tue|wed|thu|fri|sat|sun)(?:day)?)s?", t)
    if m:
        wd = m.group(1)
        wd_full = {
            "mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday",
            "fri": "friday", "sat": "saturday", "sun": "sunday"
        }
        key = wd_full.get(wd[:3], wd)
        if key in WEEKDAY_MAP:
            return f"FREQ=WEEKLY;BYDAY={key[:2].upper()}", {"weekday": key}

    if re.search(r"\bweekly\b", t):
        return "FREQ=WEEKLY", {}

    if re.search(r"\bmonthly\b", t):
        return "FREQ=MONTHLY", {}

    return None, {}


def plan_schedule(time_expression: str) -> Tuple[datetime, str, Optional[str]]:
    """Parse the time expression as IST, ensure future, and compute RRULE if recurring.

    If no time is provided, default to 9:00 AM IST next day.
    Returns tuple: (first_run_utc_naive, pretty_ist, rrule_str)
    """
    te = (time_expression or "").strip()

    rrule_str: Optional[str]
    rrule_str, extras = _detect_recurrence(te)

    # If time_expression missing time with only date-ish, allow default 9:00 AM IST next day
    if not te:
        te = "tomorrow 9:00 am"

    # Parse IST to UTC-naive and validate future
    try:
        due_utc_naive, pretty_ist = parse_and_validate_ist(te, min_lead_seconds=5)
    except ValueError as ve:
        # If text is date-only like "tomorrow" without time, default to 9:00 AM
        if "couldn't understand" in str(ve).lower():
            try:
                due_utc_naive, pretty_ist = parse_and_validate_ist("tomorrow 9:00 am", min_lead_seconds=5)
            except Exception:
                raise
        else:
            raise

    # If recurring and computed time already passed for today, RRULE AFTER() will handle next
    if rrule_str:
        # Build rrule from dtstart at computed time and advance to next in future if needed
        r = rrulestr(rrule_str, dtstart=due_utc_naive)
        now = datetime.utcnow().replace(tzinfo=None)
        nxt = r.after(now, inc=True)
        if nxt:
            due_utc_naive = nxt.replace(second=0, microsecond=0)
            pretty_ist = format_ist(due_utc_naive)

    return due_utc_naive.replace(second=0, microsecond=0), pretty_ist, rrule_str


def _to_aware_utc(dt_naive_utc: datetime) -> datetime:
    return dt_naive_utc.replace(tzinfo=timezone.utc)


def create_and_schedule(user_id: str, description: str, time_expression: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create a reminder task doc and schedule Celery for the first run; if recurring, store RRULE.

    Returns a dict with task_id, first_run_utc, first_run_ist, recurrence_rule.
    """
    due_utc_naive, pretty_ist, rrule_str = plan_schedule(time_expression)

    now = datetime.utcnow()
    coll = db_client.get_tasks_collection()

    doc: Dict[str, Any] = {
        "user_id": str(user_id),
        "title": (description or "Reminder").strip() or "Reminder",
        "description": (metadata or {}).get("notes") if metadata else "",
        "status": "todo",
        "priority": "medium",
        "due_date": due_utc_naive,
        "notify_channel": "email",
        "created_at": now,
        "updated_at": now,
        "time_expression": time_expression,
        "recurrence_rule": rrule_str,
        "is_recurring": bool(rrule_str),
        "next_run_at": due_utc_naive,
        "sent_count": 0,
    }

    res = coll.insert_one(doc)
    task_id = str(res.inserted_id)

    # Schedule Celery OTP task at due time (aware UTC ETA)
    try:
        from app.celery_worker import send_task_otp_task
        from app.services import profile_service
        profile = profile_service.get_profile(user_id)
        user_email = profile.get("email") or profile.get("user_email")
        if user_email:
            eta_aware = _to_aware_utc(due_utc_naive)
            # pass due_iso so worker can wait until exact time even if prewoke
            send_task_otp_task.apply_async(args=[task_id, user_email, doc["title"], None, due_utc_naive.isoformat()], eta=eta_aware)
    except Exception:
        pass

    return {
        "task_id": task_id,
        "first_run_utc": due_utc_naive,
        "first_run_ist": pretty_ist,
        "recurrence_rule": rrule_str,
        "title": doc["title"],
    }
