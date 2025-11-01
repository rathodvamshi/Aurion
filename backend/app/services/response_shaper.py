"""Response Shaper: consistent, friendly, structured replies in ChatGPT-style.

This module centralizes the final shaping of assistant responses so they:
- Greet the user with name and a light personal touch (tone-aware)
- Use Markdown formatting for structure
- Present the main answer/message in short paragraphs (1-2 lines max)
- Add suggestions below a horizontal rule with arrows
- Limit emojis (1-2 max per message)

Minimal external deps: relies on emotion_service for tone and palette and ai_service for
computing lightweight suggestions. Safe to call for any text reply.
"""
from __future__ import annotations

from typing import Optional, Dict, Any, List
import re

from app.services.emotion_service import detect_emotion, enrich_with_emojis
from app.services.ai_service import append_suggestions_if_missing, SUGGESTION_PREFIX


def _first_name(profile: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(profile, dict):
        return None
    name = profile.get("name") or profile.get("displayName") or profile.get("first_name")
    if not name:
        return None
    # Trim to first token
    return str(name).split()[0]


def _get_emoji_for_emotion(emotion_label: str) -> str:
    """Get a single appropriate emoji based on emotion (1-2 max per message)."""
    emoji_map = {
        "happy": "😊",
        "excited": "😄",
        "sad": "💛",
        "angry": "💬",
        "anxious": "💛",
        "neutral": "💬",
    }
    return emoji_map.get(emotion_label, "😊")


def _format_markdown_text(text: str) -> str:
    """Format text with Markdown: break long paragraphs, add emphasis where appropriate."""
    if not text:
        return text
    
    # Split into sentences for better paragraph breaking
    sentences = re.split(r'([.!?]\s+)', text)
    formatted_parts = []
    current_paragraph = []
    
    for i, sentence in enumerate(sentences):
        if sentence.strip():
            current_paragraph.append(sentence)
            # Break into new paragraph after 1-2 sentences
            if len(current_paragraph) >= 2:
                formatted_parts.append("".join(current_paragraph).strip())
                current_paragraph = []
    
    if current_paragraph:
        formatted_parts.append("".join(current_paragraph).strip())
    
    # Join with double newlines for spacing (Markdown paragraphs)
    return "\n\n".join(formatted_parts)


def _clean_response_text(text: str, name: Optional[str] = None) -> str:
    """Aggressively remove ALL unwanted phrases and clean up the response text."""
    if not text:
        return text
    
    # Remove ALL references to past conversations - be EXTREMELY aggressive
    unwanted_patterns = [
        # Past conversation references
        r'Last time we discussed[^.]*',
        r'last time we discussed[^.]*',
        r'As mentioned before[^.]*',
        r'as mentioned before[^.]*',
        r'As we discussed[^.]*',
        r'as we discussed[^.]*',
        r'Previously[^.]*',
        r'previously[^.]*',
        r'Earlier[^.]*',
        r'earlier[^.]*',
        r'Before[^.]*',
        r'before[^.]*',
        r'In our last conversation[^.]*',
        r'in our last conversation[^.]*',
        r'We talked about[^.]*',
        r'we talked about[^.]*',
        r'Last message[^.]*',
        r'last message[^.]*',
        r'Previous message[^.]*',
        r'previous message[^.]*',
        r'Earlier message[^.]*',
        r'earlier message[^.]*',
        r'The message above[^.]*',
        r'the message above[^.]*',
        # Follow-up questions
        r'How are you feeling right now\?',
        r'How are you doing\?',
        r'Just checking in[^.]*',
        r'just checking in[^.]*',
        r'want to talk about anything\?',
        r'Want to talk about anything\?',
        # Greetings
        r'Hey there!',
        r'Hey there\?',
        r'Hey there\.',
    ]
    
    cleaned = text
    for pattern in unwanted_patterns:
        # Remove with surrounding context (before and after)
        cleaned = re.sub(pattern + r'.*?', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r'.*?' + pattern, '', cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Remove persona response prefixes (e.g., "Just checking in 💛 want to talk about anything? 💬")
    persona_patterns = [
        r'Just checking in[^\n]*?want to talk',
        r'just checking in[^\n]*?want to talk',
        r'Just checking in[^\n]*?\?',
        r'just checking in[^\n]*?\?',
    ]
    for pattern in persona_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Remove name duplication patterns (e.g., "Rathod, your name is Rathod" -> "Your name is Rathod")
    if name:
        # Remove patterns like "Name, your name is Name" or "Name, your name is Name."
        pattern = rf'{re.escape(name)},\s*your name is {re.escape(name)}[\.]?'
        cleaned = re.sub(pattern, f'Your name is {name}.', cleaned, flags=re.IGNORECASE)
        # Remove "Name, ..." at the start (standalone name prefix)
        cleaned = re.sub(rf'^{re.escape(name)},\s*', '', cleaned, flags=re.IGNORECASE)
        # Also handle "Name. Your name is Name"
        pattern2 = rf'{re.escape(name)}\.\s*Your name is {re.escape(name)}[\.]?'
        cleaned = re.sub(pattern2, f'Your name is {name}.', cleaned, flags=re.IGNORECASE)
    
    # Remove any leading conversational fluff before the actual answer
    # Look for patterns like "💬 [answer] 💬" and extract just the answer
    # Pattern: emoji(s) space text emoji(s) -> extract just text
    emoji_wrapped_pattern = r'^[\U0001F300-\U0001F9FF\s]*([^\U0001F300-\U0001F9FF]+?)[\U0001F300-\U0001F9FF\s]*$'
    match = re.match(emoji_wrapped_pattern, cleaned.strip())
    if match:
        cleaned = match.group(1).strip()
    
    # Remove excessive emoji clusters (more than 2 in a row)
    cleaned = re.sub(r'([\U0001F300-\U0001F9FF]\s*){3,}', '', cleaned)
    
    # Remove standalone emojis at the start or end
    cleaned = re.sub(r'^[\U0001F300-\U0001F9FF]+\s+', '', cleaned)
    cleaned = re.sub(r'\s+[\U0001F300-\U0001F9FF]+$', '', cleaned)
    
    # Clean up multiple spaces and newlines
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'\n+', ' ', cleaned)
    
    # Remove leading/trailing punctuation issues
    cleaned = cleaned.strip('.,!? ')
    
    return cleaned.strip()


def _extract_suggestions(text: str) -> tuple[str, list[str]]:
    """Extract suggestions from text (lines starting with SUGGESTION_PREFIX)."""
    lines = text.splitlines()
    main_lines = []
    suggestions = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(SUGGESTION_PREFIX):
            # Remove prefix and clean up
            suggestion = stripped[len(SUGGESTION_PREFIX):].strip()
            if suggestion:
                suggestions.append(suggestion)
        else:
            main_lines.append(line)
    
    main_text = "\n".join(main_lines).strip()
    return main_text, suggestions


def format_structured_reply(
    *,
    user_message: str,
    main_text: str,
    profile: Optional[Dict[str, Any]] = None,
    short_context: Optional[Dict[str, Any]] = None,
    add_emojis: bool = True,
) -> str:
    """Compose a ChatGPT-style structured, friendly reply with Markdown formatting.

    Structure: Greeting → Core → Horizontal Rule → Suggestions (with arrows)
    
    Inputs:
    - user_message: latest user text (for emotion and suggestions)
    - main_text: the core answer already computed upstream (NLU/skills/LLM)
    - profile: optional user profile dict with name/preferences
    - short_context: optional dict with recent topic or hooks
    - add_emojis: toggle emoji enrichment (limited to 1-2 max)

    Output: final text to send to the client in ChatGPT-style Markdown format.
    """
    user_text = (user_message or "").strip()
    core = (main_text or "").strip()
    
    # Extract name for personalization - always use profile name
    name = _first_name(profile)
    
    # Clean up the core text first - remove unwanted phrases and excessive emojis
    core = _clean_response_text(core, name)
    
    if not core:
        core = "I'm here and ready to help. What would you like to do?"

    # Emotion + tone
    emo = detect_emotion(user_text)
    
    # Extract suggestions from main_text if present
    core_text, existing_suggestions = _extract_suggestions(core)
    
    # NO GREETING - user wants only the answer and suggestions
    # Remove ALL greetings from core_text to ensure clean output
    greeting = ""
    if name:
        # Aggressively remove any greetings
        core_text = re.sub(rf'^Hey {re.escape(name)}[!.]?\s*', '', core_text, flags=re.IGNORECASE)
        core_text = re.sub(rf'Hey {re.escape(name)}[!.]?\s*', '', core_text, flags=re.IGNORECASE)
    core_text = re.sub(rf'^Hey there[!.]?\s*', '', core_text, flags=re.IGNORECASE)
    core_text = re.sub(rf'Hey there[!.]?\s*', '', core_text, flags=re.IGNORECASE)
    core_text = re.sub(rf'^Hey[!.]?\s*', '', core_text, flags=re.IGNORECASE)
    core_text = core_text.strip()
    
    # Format core text with Markdown (short paragraphs)
    formatted_core = _format_markdown_text(core_text)
    
    # Add suggestions if missing or use existing ones
    suggestions = existing_suggestions
    if not suggestions:
        # Try to compute new suggestions
        text_with_suggestions = append_suggestions_if_missing(formatted_core, user_text, profile)
        new_core, new_suggestions = _extract_suggestions(text_with_suggestions)
        if new_suggestions:
            suggestions = new_suggestions
            formatted_core = _format_markdown_text(new_core)
    
    # Build final message: Core → Horizontal Rule → Suggestions (NO GREETING)
    parts = []
    
    # Add core message directly (no greeting)
    parts.append(formatted_core)
    
    # Add horizontal rule and suggestions if present
    if suggestions:
        parts.append("")  # Empty line before separator
        parts.append("---")  # Horizontal rule
        parts.append("")  # Empty line after separator
        # Add suggestions with arrow prefix
        for sug in suggestions[:2]:  # Max 2 suggestions
            parts.append(f"➝ {sug}")
    
    # Join all parts
    final = "\n".join(parts).strip()
    
    # Final cleanup: ensure no excessive emojis (max 2 total)
    if add_emojis:
        # Count existing emojis
        emoji_count = len(re.findall(r'[\U0001F300-\U0001F9FF]', final))
        if emoji_count < 2:
            # Only enrich if we have less than 2 emojis
            final = enrich_with_emojis(final, emo, max_new=1, hard_cap=2)
    
    # Final pass: remove any remaining unwanted phrases that might have slipped through
    final = _clean_response_text(final, name)
    
    # Additional cleanup: catch any remaining temporal references
    temporal_patterns = [
        r'last\s+time',
        r'previous\s+(?:conversation|message|discussion)',
        r'earlier\s+(?:conversation|message|discussion)',
        r'in\s+our\s+(?:last|previous)\s+',
        r'we\s+(?:talked|discussed|mentioned)\s+',
    ]
    for pattern in temporal_patterns:
        final = re.sub(pattern, '', final, flags=re.IGNORECASE)
    
    # Remove any sentence that starts with temporal words followed by "we" or "you"
    sentence_pattern = r'(?:^|\.\s+)(?:Last|Previous|Earlier|Before)[^.]*(?:we|you)[^.]*\.'
    final = re.sub(sentence_pattern, '', final, flags=re.IGNORECASE | re.MULTILINE)
    
    # Ensure proper formatting: remove multiple consecutive newlines and spaces
    final = re.sub(r'\n{3,}', '\n\n', final)
    final = re.sub(r' +', ' ', final)
    
    return final.strip()


__all__ = ["format_structured_reply"]
