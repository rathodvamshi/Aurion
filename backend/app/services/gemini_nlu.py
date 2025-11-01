"""Gemini-based NLU for intent and reminder fields with strict JSON output.

Primary output keys:
- intent: one of {reminder, play_media, smalltalk, cancel_reminder, edit_reminder, other}
- task_description: short phrase for reminder
- time_expression: natural language time string for reminder

Falls back to None if unavailable; callers should implement local fallback.
"""
from __future__ import annotations

import os
import json
from typing import Optional, Dict, Any

try:
    import google.generativeai as genai  # type: ignore
except Exception:
    genai = None


GEMINI_MODEL = os.getenv("GEMINI_MODEL", os.getenv("GOOGLE_MODEL", "gemini-1.5-flash"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def gemini_available() -> bool:
    return bool(GEMINI_API_KEY and genai is not None)


def extract_reminder_with_gemini(text: str) -> Optional[Dict[str, Any]]:
    if not gemini_available():
        return None

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        system = (
            "You are an intent and entity extractor for an assistant. "
            "Return ONLY minified JSON with keys: intent, task_description, time_expression.\n"
            "Rules:\n"
            "- intent in {\"reminder\",\"play_media\",\"smalltalk\",\"cancel_reminder\",\"edit_reminder\",\"other\"}\n"
            "- If the phrase contains 'remind me', force intent='reminder'.\n"
            "- task_description: only for reminder; a short verb phrase without time words.\n"
            "- time_expression: only for reminder; natural time string (e.g., 'in 5 minutes', 'tomorrow at 8pm', 'every Monday at 7:30 AM').\n"
            "- If not a reminder, set task_description and time_expression to \"\"."
        )

        few_shots = [
            ("In 5 minutes remind me to play", {"intent": "reminder", "task_description": "play", "time_expression": "in 5 minutes"}),
            ("Play lo-fi beats", {"intent": "play_media", "task_description": "", "time_expression": ""}),
            ("Remind me every Monday at 7:30 AM to check the report", {"intent": "reminder", "task_description": "check the report", "time_expression": "every Monday at 7:30 AM"}),
            ("Cancel my 7pm reminder", {"intent": "cancel_reminder", "task_description": "", "time_expression": ""}),
            ("Move the reminder to 6pm", {"intent": "edit_reminder", "task_description": "", "time_expression": "6pm"}),
        ]

        prompt = [
            {"role": "system", "parts": [system]},
            {"role": "user", "parts": ["Follow the format strictly."]},
        ]
        for u, y in few_shots:
            prompt.append({"role": "user", "parts": [u]})
            prompt.append({"role": "model", "parts": [json.dumps(y, separators=(",", ":"))]})
        prompt.append({"role": "user", "parts": [text]})

        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0, "response_mime_type": "application/json"},
        )
        data = json.loads(resp.text or "{}")
        if not isinstance(data, dict):
            return None
        intent = str(data.get("intent", "")).lower()
        if "remind me" in text.lower():
            intent = "reminder"
        if intent not in {"reminder", "play_media", "smalltalk", "cancel_reminder", "edit_reminder", "other"}:
            intent = "other"
        return {
            "intent": intent,
            "task_description": (data.get("task_description") or "").strip(),
            "time_expression": (data.get("time_expression") or "").strip(),
        }
    except Exception:
        return None
