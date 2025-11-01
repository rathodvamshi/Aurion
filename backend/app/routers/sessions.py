# backend/app/routes/sessions.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from pymongo.collection import Collection
from bson import ObjectId, errors
from datetime import datetime, timedelta, timezone
import re
from typing import List, Optional, Any, Dict
import logging
import dateparser
import pytz

from app.database import get_sessions_collection, get_user_profile_collection, get_tasks_collection
from app.security import get_current_active_user
from app.services import ai_service, nlu, redis_cache
from app.services import redis_service
from app.services.response_shaper import format_structured_reply
from app.services import memory_store  # For fast redis-backed history when available
from app.services.memory_coordinator import gather_memory_context, post_message_update
import os
import asyncio
from app.celery_worker import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/sessions",
    tags=["Sessions"],
    dependencies=[Depends(get_current_active_user)]
)

# ---- Local latency budgets (seconds) ----
CONTEXT_TIMEOUT_S = float(os.getenv("CHAT_CONTEXT_TIMEOUT_S", "0.8"))
try:
    from app.config import settings as _settings
    AI_TIMEOUT_S = float(os.getenv("CHAT_AI_TIMEOUT_S", str(getattr(_settings, "AI_TIMEOUT", 2.2))))
except Exception:
    AI_TIMEOUT_S = float(os.getenv("CHAT_AI_TIMEOUT_S", "2.2"))

async def _safe_gather_context(*, user_id: str, user_key: str, session_id: str, latest_user_message: str, recent_messages: list[Any] | None) -> dict:
    """Gather memory context with a strict timeout and resilient fallback."""
    try:
        return await asyncio.wait_for(
            gather_memory_context(
                user_id=user_id,
                user_key=user_key,
                session_id=session_id,
                latest_user_message=latest_user_message,
                recent_messages=recent_messages or [],
            ),
            timeout=CONTEXT_TIMEOUT_S,
        )
    except Exception:
        try:
            logger.warning("gather_memory_context timed out/failed; using minimal context")
        except Exception:
            pass
        return {
            "history": [],
            "state": "general_conversation",
            "pinecone_context": None,
            "neo4j_facts": None,
            "profile": {},
            "user_facts_semantic": None,
            "persistent_memories": None,
        }

async def _safe_ai_response(*, prompt: str, history: list[dict] | None, state: str | None, pinecone_context: str | None, neo4j_facts: str | None, profile: dict | None, user_facts_semantic: list[str] | None, persistent_memories: list[dict] | None, session_id: str | None) -> str:
    """Call AI with a strict timeout; return a friendly fallback on timeout/failure."""
    try:
        return await asyncio.wait_for(
            ai_service.get_response(
                prompt=prompt,
                history=history,
                state=state or "general_conversation",
                pinecone_context=pinecone_context,
                neo4j_facts=neo4j_facts,
                profile=profile,
                user_facts_semantic=user_facts_semantic,
                persistent_memories=persistent_memories,
                session_id=session_id,
            ),
            timeout=AI_TIMEOUT_S,
        )
    except Exception:
        return (
            "I'm having trouble answering quickly right now. "
            "Here's a short reply; you can retry for more details."
        )

# -----------------------------
# Models
# -----------------------------

class Message(BaseModel):
    sender: str
    text: str

class ChatRequest(BaseModel):
    message: str

class TaskCreate(BaseModel):
    content: str
    due_date: str

class TaskUpdate(BaseModel):
    content: Optional[str] = None
    due_date: Optional[str] = None

# -----------------------------
# Utilities & small helpers
# -----------------------------

AUTO_CREATE_CONFIDENCE = 0.90
DUPLICATE_WINDOW_SECONDS = 60
SUCCESS_SUFFIX = " You'll get an email notification then."

def _is_valid_objectid(val: Any) -> bool:
    try:
        return isinstance(val, ObjectId) or (isinstance(val, str) and ObjectId.is_valid(val))
    except Exception:
        return False

def _as_objectid(val: Any):
    if isinstance(val, ObjectId):
        return val
    if isinstance(val, str) and ObjectId.is_valid(val):
        return ObjectId(val)
    return val

def _has_ambiguous_hour(text: str) -> bool:
    lower = (text or "").lower()
    if any(tok in lower for tok in ["am", "pm", ":", "+", "-", "gmt", "utc", "ist", "pst", "est", "cet", "cst", "edt", "pdt"]):
        return False
    m = re.search(r"\bat\s+([1-9]|1[0-2])\b", lower)
    return m is not None

def _parse_datetime_with_tz(text: str, user_tz: str):
    """
    Parse natural language datetime to a timezone-aware datetime using dateparser.
    Returns (dt (aware), parse_error: Optional[str], ambiguous: bool)
    """
    try:
        settings = {
            "TIMEZONE": user_tz or "UTC",
            "TO_TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        }
        dt = dateparser.parse(text, settings=settings)
        if not dt:
            # try searching for date substrings
            try:
                from dateparser.search import search_dates as dp_search
                matches = dp_search(text, settings=settings)
            except Exception:
                matches = None
            if matches:
                # choose first plausible future match
                now = datetime.now(pytz.timezone(user_tz or "UTC")).astimezone(pytz.UTC)
                chosen = None
                for span, val in matches:
                    try:
                        val_utc = val.astimezone(pytz.UTC)
                        if val_utc > now:
                            chosen = val
                            break
                    except Exception:
                        chosen = val
                        break
                dt = chosen or matches[0][1]
            else:
                return None, "I couldn't understand the date/time.", False
        ambiguous = _has_ambiguous_hour(text)
        return dt, None, ambiguous
    except Exception as e:
        logger.debug("parse_datetime error: %s for text=%r", e, text)
        return None, "I couldn't parse that time, please try another format.", False

def _to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    try:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        try:
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    try:
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return dt

def _normalize_channel(ch: Optional[str]) -> str:
    if not ch:
        return "email"
    c = ch.lower().strip()
    if c in ("email", "mail"):
        return "email"
    if c in ("chat", "in-app", "inapp", "message"):
        return "chat"
    if c == "both":
        return "both"
    return "email"

# Draft helpers (store simple dicts in memory_store under key session_id:reminder_draft)
async def _get_reminder_draft(session_id: str) -> Optional[dict]:
    try:
        return await memory_store.get_prefetched_context(session_id, "reminder_draft")
    except Exception:
        return None

async def _set_reminder_draft(session_id: str, draft: dict):
    try:
        await memory_store.set_prefetched_context(session_id, "reminder_draft", draft, ttl_seconds=3600)
    except Exception:
        logger.debug("Failed to set reminder draft for %s", session_id)

async def _clear_reminder_draft(session_id: str):
    try:
        await memory_store.set_prefetched_context(session_id, "reminder_draft", {}, ttl_seconds=1)
    except Exception:
        logger.debug("Failed to clear reminder draft for %s", session_id)

# -----------------------------
# Session endpoints (unchanged behaviour)
# -----------------------------

@router.post("/new", status_code=status.HTTP_201_CREATED)
async def create_empty_session(current_user: dict = Depends(get_current_active_user),
                               sessions_collection: Collection = Depends(get_sessions_collection)):
    now = datetime.utcnow()
    doc = {
        "userId": current_user["_id"],
        "title": "New Chat",
        "createdAt": now,
        "updatedAt": now,
        "lastMessageAt": None,
        "messageCount": 0,
        "lastMessage": "",
        "pinned": False,
        "saved": False,
        "messages": [],
    }
    result = sessions_collection.insert_one(doc)
    return {"id": str(result.inserted_id), "title": doc["title"], "createdAt": doc["createdAt"]}

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_session(messages: List[Message], current_user: dict = Depends(get_current_active_user),
                         sessions_collection: Collection = Depends(get_sessions_collection)):
    if not messages:
        raise HTTPException(status_code=400, detail="Cannot create an empty session.")
    first_user_msg = next((m.text for m in messages if m.sender == 'user'), "New Chat")
    title = (first_user_msg[:50] + "...") if len(first_user_msg) > 50 else first_user_msg
    now = datetime.utcnow()
    new_session = {
        "userId": current_user["_id"],
        "title": title,
        "createdAt": now,
        "updatedAt": now,
        "lastMessageAt": now,
        "messageCount": len(messages),
        "lastMessage": messages[-1].text if messages else "",
        "pinned": False,
        "saved": False,
        "messages": [
            {**m.model_dump(), "timestamp": now if i == len(messages) - 1 else now}
            for i, m in enumerate(messages)
        ],
    }
    result = sessions_collection.insert_one(new_session)
    return {"id": str(result.inserted_id), "title": title, "createdAt": new_session["createdAt"]}

@router.get("/", response_model=List[dict])
async def get_sessions(current_user: dict = Depends(get_current_active_user),
                       sessions_collection: Collection = Depends(get_sessions_collection)):
    try:
        user_id = (current_user.get("_id") or current_user.get("user_id") or current_user.get("userId"))
        if not user_id:
            return []
        query_variants = [{"userId": user_id}]
        try:
            if isinstance(user_id, str) and ObjectId.is_valid(user_id):
                query_variants.append({"userId": ObjectId(user_id)})
        except Exception:
            pass
        cursor = sessions_collection.find({"$or": query_variants}, {"messages": 0}).sort("updatedAt", -1)
        sessions: List[dict] = []
        for s in cursor:
            created_at = s.get("createdAt")
            updated_at = s.get("updatedAt", created_at)
            sessions.append({
                "id": str(s.get("_id")),
                "title": s.get("title", "New Chat"),
                "createdAt": created_at,
                "updatedAt": updated_at,
                "lastMessage": s.get("lastMessage"),
                "messageCount": s.get("messageCount", len(s.get("messages", []))),
                "pinned": bool(s.get("pinned", False)),
                "saved": bool(s.get("saved", False)),
                "lastMessageAt": s.get("lastMessageAt", updated_at),
            })
        sessions.sort(
            key=lambda x: (
                bool(x.get("pinned", False)),
                (x.get("updatedAt") or x.get("createdAt") or datetime.utcnow()),
            ),
            reverse=True,
        )
        return sessions
    except Exception as e:
        logger.exception("Error listing sessions: %s", e)
        return []

@router.get("/{session_id}")
async def get_session_messages(session_id: str,
                               page: int = Query(1, gt=0),
                               limit: int = Query(30, gt=0),
                               current_user: dict = Depends(get_current_active_user),
                               sessions_collection: Collection = Depends(get_sessions_collection)):
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID.")
    skip = (page - 1) * limit
    user_id = current_user["_id"]
    user_id_match = {"$or": [{"userId": user_id}]}
    if isinstance(user_id, str) and ObjectId.is_valid(user_id):
        user_id_match["$or"].append({"userId": ObjectId(user_id)})
    pipeline = [
        {"$match": {"_id": ObjectId(session_id), **user_id_match}},
        {"$project": {
            "title": 1,
            "createdAt": 1,
            "totalMessages": {"$size": "$messages"},
            "messages": {"$slice": ["$messages", - (skip + limit), limit]}
        }}
    ]
    result = list(sessions_collection.aggregate(pipeline))
    if not result:
        raise HTTPException(status_code=404, detail="Session not found.")
    session_data = result[0]
    session_data["_id"] = str(session_data["_id"])
    return session_data

@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str,
                         current_user: dict = Depends(get_current_active_user),
                         sessions_collection: Collection = Depends(get_sessions_collection)):
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID.")
    result = sessions_collection.delete_one({"_id": ObjectId(session_id), "userId": current_user["_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found or permission denied.")

@router.get("/{session_id}/history")
async def get_session_history(
    session_id: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    sessions_collection: Collection = Depends(get_sessions_collection),
):
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID.")
    if offset == 0 and limit <= 50:
        try:
            redis_hist = await memory_store.get_session_history(session_id, limit=limit)
            if redis_hist:
                messages_fmt = [
                    {
                        "id": str(ObjectId()),
                        "text": m.get("content", ""),
                        "sender": "user" if m.get("role") == "user" else "assistant",
                        "timestamp": datetime.utcnow(),
                        "sessionId": session_id,
                    }
                    for m in redis_hist
                ]
                return {
                    "messages": messages_fmt,
                    "total": len(messages_fmt),
                    "offset": 0,
                    "limit": limit,
                    "has_more": True,
                    "source": "redis",
                }
        except Exception:
            logger.debug("Redis fast-path failed for session %s", session_id)
    user_id = (current_user.get("_id") or current_user.get("user_id") or current_user.get("userId"))
    user_or_clauses = []
    if user_id is not None:
        user_or_clauses.append({"userId": user_id})
        try:
            if isinstance(user_id, str) and ObjectId.is_valid(user_id):
                user_or_clauses.append({"userId": ObjectId(user_id)})
        except Exception:
            pass
    user_id_match = {"$or": user_or_clauses} if user_or_clauses else {}
    match_filter = {"_id": ObjectId(session_id)}
    if user_id_match:
        match_filter.update(user_id_match)
    pipeline = [
        {"$match": match_filter},
        {"$project": {
            "messageCount": {"$size": {"$ifNull": ["$messages", []]}},
            "messages": {"$slice": [{"$ifNull": ["$messages", []]}, offset, limit]},
            "updatedAt": 1,
            "title": 1,
        }},
    ]
    docs = list(sessions_collection.aggregate(pipeline))
    if not docs:
        raise HTTPException(status_code=404, detail="Session not found or permission denied.")
    doc = docs[0]
    total = doc.get("messageCount", 0)
    raw_messages = doc.get("messages", [])
    formatted_messages = []
    for i, m in enumerate(raw_messages):
        mid = m.get("_id")
        mid_str = str(mid) if mid is not None else str(ObjectId())
        formatted_messages.append({
            "id": mid_str,
            "text": m.get("text", m.get("content", "")),
            "sender": m.get("sender", "assistant" if i % 2 else "user"),
            "timestamp": m.get("timestamp", datetime.utcnow()),
            "sessionId": session_id,
            "annotatedHtml": m.get("annotatedHtml"),
            "highlights": m.get("highlights", []),
        })
    return {
        "messages": formatted_messages,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
        "source": "mongo",
        "updatedAt": doc.get("updatedAt"),
    }

@router.put("/{session_id}/title")
async def update_session_title(
    session_id: str,
    title_data: dict,
    current_user: dict = Depends(get_current_active_user),
    sessions_collection: Collection = Depends(get_sessions_collection)
):
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID.")
    title = title_data.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty.")
    user_id = current_user["_id"]
    update_filter = {"_id": ObjectId(session_id), "$or": [{"userId": user_id}]}
    if isinstance(user_id, str) and ObjectId.is_valid(user_id):
        update_filter["$or"].append({"userId": ObjectId(user_id)})
    result = sessions_collection.update_one(
        update_filter,
        {"$set": {"title": title, "updatedAt": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found or permission denied.")
    return {"success": True, "title": title}

@router.put("/{session_id}/pin")
async def set_session_pinned(
    session_id: str,
    data: dict,
    current_user: dict = Depends(get_current_active_user),
    sessions_collection: Collection = Depends(get_sessions_collection)
):
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID.")
    pinned = bool(data.get("pinned", False))
    user_id = current_user["_id"]
    update_filter = {"_id": ObjectId(session_id), "$or": [{"userId": user_id}]}
    if isinstance(user_id, str) and ObjectId.is_valid(user_id):
        update_filter["$or"].append({"userId": ObjectId(user_id)})
    result = sessions_collection.update_one(
        update_filter,
        {"$set": {"pinned": pinned, "updatedAt": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"success": True, "pinned": pinned}

@router.put("/{session_id}/save")
async def set_session_saved(
    session_id: str,
    data: dict,
    current_user: dict = Depends(get_current_active_user),
    sessions_collection: Collection = Depends(get_sessions_collection)
):
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID.")
    saved = bool(data.get("saved", False))
    user_id = current_user["_id"]
    update_filter = {"_id": ObjectId(session_id), "$or": [{"userId": user_id}]}
    if isinstance(user_id, str) and ObjectId.is_valid(user_id):
        update_filter["$or"].append({"userId": ObjectId(user_id)})
    result = sessions_collection.update_one(
        update_filter,
        {"$set": {"saved": saved, "updatedAt": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"success": True, "saved": saved}

@router.post("/{session_id}/generate-title")
async def generate_session_title(
    session_id: str,
    current_user: dict = Depends(get_current_active_user),
    sessions_collection: Collection = Depends(get_sessions_collection)
):
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID.")
    user_id = current_user["_id"]
    session = sessions_collection.find_one({
        "_id": ObjectId(session_id),
        "$or": [
            {"userId": user_id},
            {"userId": ObjectId(user_id)} if (isinstance(user_id, str) and ObjectId.is_valid(user_id)) else {"userId": None}
        ]
    })
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or permission denied.")
    messages = session.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="Cannot generate title for empty session.")
    user_messages = [msg.get("text", "") for msg in messages if msg.get("sender") == "user"]
    if not user_messages:
        title = "Chat Session"
    else:
        first_message = user_messages[0][:50]
        if "help" in first_message.lower():
            title = f"Help: {first_message[:30]}..."
        elif "?" in first_message:
            title = f"Question: {first_message[:30]}..."
        else:
            words = re.split(r"\s+", first_message)
            short = " ".join(words[:8])
            short = short.replace("\n", " ").strip(" -_.,")
            title = short.title()
        title = title.replace("\n", " ").strip()
        if len(title) > 50:
            title = title[:47] + "..."
    update_filter = {"_id": ObjectId(session_id), "$or": [{"userId": user_id}]}
    if isinstance(user_id, str) and ObjectId.is_valid(user_id):
        update_filter["$or"].append({"userId": ObjectId(user_id)})
    sessions_collection.update_one(
        update_filter,
        {"$set": {"title": title, "updatedAt": datetime.utcnow()}}
    )
    return {"title": title}

# -----------------------------
# Chat Messaging within a Session (universal, NLU-driven)
# -----------------------------

@router.post("/{session_id}/chat")
async def send_message(session_id: str,
                       chat_req: ChatRequest,
                       current_user: dict = Depends(get_current_active_user),
                       sessions_collection: Collection = Depends(get_sessions_collection),
                       user_profiles: Collection = Depends(get_user_profile_collection),
                       tasks: Collection = Depends(get_tasks_collection)):
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID.")

    # Verify session ownership
    session = sessions_collection.find_one({"_id": ObjectId(session_id), "userId": current_user["_id"]})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or permission denied.")

    user_email = current_user.get("email") or current_user.get("sub") or ""
    user_id_str = str(current_user["_id"])

    # Load user profile (Redis cache preferred)
    user_profile_doc = await memory_store.get_cached_user_profile(user_id_str) or (user_profiles.find_one({"_id": user_id_str}) or {})
    user_tz = user_profile_doc.get("timezone") or "UTC"

    user_message_doc = {"sender": "user", "text": chat_req.message}
    now = datetime.utcnow()
    user_message_doc["timestamp"] = now

    # Auto-generate session title on first user message if appropriate
    try:
        need_title = False
        existing_title = (session.get("title") or "").strip()
        msg_count = session.get("messageCount")
        if msg_count is None:
            msg_count = len(session.get("messages", []))
        if (not existing_title) or (existing_title.lower() == "new chat") or (msg_count == 0):
            need_title = True
        if need_title:
            raw = chat_req.message.strip()
            low = raw.lower()
            if not raw:
                title = "New Chat"
            elif any(k in low for k in ("remind", "reminder", "remind me", "set reminder")):
                m = re.search(r"remind\s+me\s+(?:to|about)\s+(.+)", low)
                core = (m.group(1) if m else raw)
                core = re.sub(r"\s+in\s+\d+.*$", "", core).strip()
                title = f"Reminder: {core[:30]}".strip()
            elif raw.endswith("?"):
                title = f"Question: {raw}"[:50]
            else:
                words = re.split(r"\s+", raw)
                short = " ".join(words[:8])
                short = short.replace("\n", " ").strip(" -_.,")
                title = short.title()
            if len(title) > 50:
                title = title[:47] + "..."
            update_filter = {"_id": ObjectId(session_id), "$or": [{"userId": current_user["_id"]}]}
            if isinstance(current_user["_id"], str) and ObjectId.is_valid(current_user["_id"]):
                update_filter["$or"].append({"userId": ObjectId(current_user["_id"])})
            sessions_collection.update_one(update_filter, {"$set": {"title": title, "updatedAt": datetime.utcnow()}})
            session["title"] = title
    except Exception:
        logger.debug("Title auto-gen failed", exc_info=True)

    # Fast-path: YouTube video intent (autoplay) — reuse chat router logic when present
    try:
        lower_msg = (chat_req.message or "").lower().strip()
        vi = None
        # Hard guard: skip if it's clearly a reminder flow
        if "remind me" not in lower_msg and "reminder" not in lower_msg:
            # Import lazily to avoid circular import at module load time
            try:
                from app.routers.chat import _maybe_handle_video_intent  # type: ignore
            except Exception:
                _maybe_handle_video_intent = None  # type: ignore
            if _maybe_handle_video_intent is not None:
                vi = await _maybe_handle_video_intent(chat_req.message)
        if vi and vi.get("handled"):
            # Shape assistant reply minimally and persist both messages to session
            resp_txt = vi.get("response_text") or ""
            try:
                shaped_text = format_structured_reply(
                    user_message=chat_req.message,
                    main_text=resp_txt,
                    profile=user_profile_doc,
                    short_context={
                        "last_topic": session.get("title") if isinstance(session.get("title"), str) else None,
                    },
                )
            except Exception:
                shaped_text = resp_txt
            ai_message = {"sender": "assistant", "text": shaped_text, "timestamp": datetime.utcnow()}
            update_filter = {"_id": ObjectId(session_id), "$or": [{"userId": current_user["_id"]}]}
            if isinstance(current_user["_id"], str) and ObjectId.is_valid(current_user["_id"]):
                update_filter["$or"].append({"userId": ObjectId(current_user["_id"])})
            try:
                sessions_collection.update_one(
                    update_filter,
                    {
                        "$push": {"messages": {"$each": [user_message_doc, ai_message]}},
                        "$set": {"updatedAt": datetime.utcnow(), "lastMessageAt": datetime.utcnow(), "lastMessage": shaped_text[:200]},
                        "$inc": {"messageCount": 2},
                    },
                )
            except Exception:
                logger.exception("Failed to persist video chat messages for session %s", session_id)
            # Remember current video for session (controls may use this)
            try:
                best = vi.get("video") or {}
                if best.get("videoId"):
                    await redis_service.set_prefetched_data(f"session:video:{session_id}", best, ttl_seconds=24 * 3600)
            except Exception:
                pass
            # Post-processing hooks
            try:
                post_message_update(user_id=user_id_str, user_key=user_email, session_id=session_id, user_message=chat_req.message, ai_message=shaped_text, state=None)
            except Exception:
                logger.debug("post_message_update failed (video path)", exc_info=True)
            # Return structured response compatible with chatService normalization
            return {
                "response_text": shaped_text,
                "video": vi.get("video"),
                "video_intent": vi.get("video_intent"),
            }
    except Exception:
        # Non-fatal; fall through to normal flow
        pass

    # Check for an active reminder draft first (multi-turn slot filling)
    try:
        draft = await _get_reminder_draft(session_id)
    except Exception:
        draft = None

    if draft and isinstance(draft, dict) and draft.get("active"):
        # Handle confirmation, quick edits or cancellation in the multi-turn flow
        pending_confirmation = draft.get("pending_confirmation", False)
        title = draft.get("title")
        due_iso = draft.get("due_date")
        notes = draft.get("notes")
        repeat = draft.get("repeat")
        channel = draft.get("channel") or "email"

        lower_msg = chat_req.message.strip().lower()
        if pending_confirmation:
            # Affirmative
            if lower_msg in {"yes", "y", "yeah", "yep", "confirm", "okay", "ok", "please do", "create it"}:
                if not title or not due_iso:
                    await _clear_reminder_draft(session_id)
                    ai_response_text = "Let's start over. What should I remind you about, and when?"
                else:
                    try:
                        due_dt = datetime.fromisoformat(due_iso)
                    except Exception:
                        due_dt = None
                    if due_dt and _to_aware_utc(due_dt) and _to_aware_utc(due_dt) <= datetime.utcnow().replace(tzinfo=timezone.utc):
                        await _clear_reminder_draft(session_id)
                        ai_response_text = "That time has already passed. Please choose a future time."
                    else:
                        # Duplicate prevention
                        window_start = _to_naive_utc(due_dt - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)) if due_dt else None
                        window_end = _to_naive_utc(due_dt + timedelta(seconds=DUPLICATE_WINDOW_SECONDS)) if due_dt else None
                        query = {"user_id": user_id_str, "title": title}
                        if window_start and window_end:
                            query["due_date"] = {"$gte": window_start, "$lte": window_end}
                        dup = tasks.find_one(query)
                        if dup:
                            await _clear_reminder_draft(session_id)
                            ai_response_text = "You already have that reminder around the same time. I've not created a duplicate."
                        else:
                            task_doc = {
                                "user_id": user_id_str,
                                "title": title,
                                "description": notes,
                                "priority": "medium",
                                "due_date": _to_naive_utc(due_dt),
                                "tags": [],
                                "status": "todo",
                                "created_at": datetime.utcnow(),
                                "updated_at": datetime.utcnow(),
                                "notify_channel": _normalize_channel(channel),
                                "recurrence": repeat if repeat in {"daily", "weekly", "monthly"} else None,
                                "metadata": {"source": "chat_nlu", "draft_confirmed": True}
                            }
                            try:
                                res = tasks.insert_one(task_doc)
                                await _clear_reminder_draft(session_id)
                                pretty_time = _to_naive_utc(due_dt).strftime("%Y-%m-%d %H:%M UTC")
                                ai_response_text = f"✅ Task '{title}' has been created for {pretty_time}. {('Notes saved. ' if notes else '')}{SUCCESS_SUFFIX}"
                            except Exception:
                                logger.exception("Failed to insert task from draft")
                                await _clear_reminder_draft(session_id)
                                ai_response_text = "I couldn't save your reminder. Please try again."
            # Negative / cancel
            elif lower_msg in {"no", "n", "nope", "don't", "cancel", "stop"}:
                draft["pending_confirmation"] = False
                await _set_reminder_draft(session_id, draft)
                ai_response_text = "Okay — draft cancelled. What would you like to do instead?"
            else:
                # Try to accept a new time or tweak
                new_dt, err, ambiguous = _parse_datetime_with_tz(chat_req.message, user_tz)
                if new_dt and _to_aware_utc(new_dt) and _to_aware_utc(new_dt) > datetime.utcnow().replace(tzinfo=timezone.utc):
                    if ambiguous:
                        ai_response_text = "Do you mean AM or PM?"
                    else:
                        draft["due_date"] = new_dt.isoformat()
                        await _set_reminder_draft(session_id, draft)
                        pretty_time = _to_naive_utc(new_dt).strftime("%Y-%m-%d %H:%M UTC")
                        ai_response_text = f"Updated time to {pretty_time}. Should I create it now?"
                else:
                    ai_response_text = "Please reply with 'yes' to confirm, or give a new time (e.g., 7:30 PM)."

            # Save messages and return early (shape for consistency)
            try:
                shaped_text = format_structured_reply(
                    user_message=chat_req.message,
                    main_text=ai_response_text,
                    profile=user_profile_doc,
                    short_context={
                        "last_topic": session.get("title") if isinstance(session.get("title"), str) else None,
                    },
                )
            except Exception:
                shaped_text = ai_response_text
            ai_message = {"sender": "assistant", "text": shaped_text, "timestamp": datetime.utcnow()}
            sessions_collection.update_one(
                {"_id": ObjectId(session_id), "$or": [{"userId": current_user["_id"]}]},
                {"$push": {"messages": {"$each": [user_message_doc, ai_message]}}, "$set": {"updatedAt": datetime.utcnow(), "lastMessageAt": datetime.utcnow(), "lastMessage": shaped_text[:200]}, "$inc": {"messageCount": 2}},
            )
            post_message_update(user_id=user_id_str, user_key=user_email, session_id=session_id, user_message=chat_req.message, ai_message=shaped_text, state="task_management")
            return ai_message

    # --- NLU Processing (universal) ---
    try:
        nlu_result = await nlu.get_structured_intent(chat_req.message, user_timezone=user_tz)
    except Exception:
        logger.exception("NLU error")
        nlu_result = {"action": "general_chat", "data": None}

    action = nlu_result.get("action")

    # Map action -> skill
    if action == "create_task":
        # normalize data shape: single task or tasks list
        payload = nlu_result.get("data") or {}
        tasks_to_create = []
        if isinstance(payload, dict) and payload.get("tasks"):
            tasks_to_create = payload.get("tasks")
        elif isinstance(payload, dict):
            tasks_to_create = [payload]
        else:
            tasks_to_create = [{"title": str(payload)}]

        created = []
        clarifications = []
        for item in tasks_to_create:
            title = (item.get("title") or "").strip()
            dt_iso = item.get("datetime") or item.get("datetime_iso") or item.get("datetime_text")
            notes = item.get("notes") or None
            repeat = item.get("repeat") or None
            channel = _normalize_channel(item.get("channel"))
            conf = float(item.get("confidence") or 0.0)
            missing = item.get("missing_fields") or []

            # Try parsing datetime server-side if text or ISO present
            due_dt = None
            parse_err = None
            ambiguous = False
            if dt_iso:
                due_dt, parse_err, ambiguous = _parse_datetime_with_tz(dt_iso, user_tz)
            else:
                due_dt, parse_err, ambiguous = _parse_datetime_with_tz(chat_req.message, user_tz)

            needs_title = not title or title.lower() in {"remind me", "a reminder", "a task"}
            needs_time = due_dt is None and ("datetime" in missing or parse_err is not None)

            # Validation: past time
            if due_dt and _to_aware_utc(due_dt) and _to_aware_utc(due_dt) <= datetime.utcnow().replace(tzinfo=timezone.utc):
                clarifications.append("That time has already passed. Please choose a future time.")
                continue

            # Ambiguity -> ask AM/PM or clarify
            if ambiguous and due_dt:
                clarifications.append("Do you mean AM or PM for the time you provided?")
                continue

            if needs_title and not title:
                clarifications.append("What should I remind you about?")
                continue

            if needs_time and not due_dt:
                clarifications.append("When should I remind you? Please provide a date and time (e.g., tomorrow at 5 PM).")
                continue

            # If confidence high, auto-create
            if conf >= AUTO_CREATE_CONFIDENCE and due_dt and title:
                # duplicate check
                window_start = _to_naive_utc(due_dt - timedelta(seconds=DUPLICATE_WINDOW_SECONDS))
                window_end = _to_naive_utc(due_dt + timedelta(seconds=DUPLICATE_WINDOW_SECONDS))
                dup_query = {"user_id": user_id_str, "title": title, "due_date": {"$gte": window_start, "$lte": window_end}}
                dup = tasks.find_one(dup_query)
                if dup:
                    created.append({"status": "duplicate", "title": title, "existing_id": str(dup.get("_id"))})
                    continue
                task_doc = {
                    "user_id": user_id_str,
                    "title": title,
                    "description": notes,
                    "priority": "medium",
                    "due_date": _to_naive_utc(due_dt),
                    "tags": [],
                    "status": "todo",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "notify_channel": channel,
                    "recurrence": repeat if repeat in {"daily", "weekly", "monthly"} else None,
                    "metadata": {"source": "chat_nlu", "confidence": conf},
                }
                try:
                    res = tasks.insert_one(task_doc)
                    created.append({"status": "created", "title": title, "id": str(res.inserted_id)})
                except Exception:
                    logger.exception("Failed to insert task")
                    clarifications.append("I couldn't save one of the reminders due to a server error.")
            else:
                # request confirmation (build compact summary)
                if due_dt:
                    display_time = _to_naive_utc(due_dt).strftime("%Y-%m-%d %H:%M")
                else:
                    display_time = item.get("datetime_text") or "unspecified time"
                confirm_text = f"I'll create: '{title}' at {display_time}. Confirm? (yes/no)"
                # Save draft with pending_confirmation True
                draft = {
                    "active": True,
                    "title": title,
                    "due_date": due_dt.isoformat() if due_dt else None,
                    "notes": notes,
                    "repeat": repeat,
                    "channel": channel,
                    "pending_confirmation": True
                }
                await _set_reminder_draft(session_id, draft)
                clarifications.append(confirm_text)

        # If clarifications exist, ask them (group short)
        if clarifications:
            # Deduplicate and join up to 2 clarifications into one message
            uniq = []
            for c in clarifications:
                if c not in uniq:
                    uniq.append(c)
            ask = " ".join(uniq[:2])
            ai_response_text = ask
        else:
            # Build created summary
            if created:
                success_lines = []
                for c in created:
                    if c["status"] == "created":
                        success_lines.append(f"- {c['title']}")
                    elif c["status"] == "duplicate":
                        success_lines.append(f"- {c['title']} (duplicate)")
                ai_response_text = f"I've set the following reminders:\n" + "\n".join(success_lines) + SUCCESS_SUFFIX
            else:
                ai_response_text = "No reminders created."

    elif action == "fetch_tasks":
        # A simple fetch: support "today" keyword window
        lower_msg = chat_req.message.lower()
        start_utc = None
        end_utc = None
        if "today" in lower_msg:
            today_local = dateparser.parse("today 00:00", settings={"TIMEZONE": user_tz, "TO_TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True})
            end_local = dateparser.parse("today 23:59", settings={"TIMEZONE": user_tz, "TO_TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True})
            if today_local and end_local:
                start_utc = today_local
                end_utc = end_local
        query = {"user_id": user_id_str, "status": "todo"}
        if start_utc and end_utc:
            query["due_date"] = {"$gte": start_utc, "$lte": end_utc}
        cursor = tasks.find(query).sort("due_date", 1)
        task_list = []
        for t in cursor:
            title = t.get("title", "Untitled")
            due_dt = t.get("due_date")
            due_str = due_dt.strftime("%Y-%m-%d %H:%M") if isinstance(due_dt, datetime) else "unscheduled"
            task_list.append(f"- {title} (Due: {due_str})")
        if "today" in lower_msg:
            ai_response_text = "Your reminders for today:\n" + "\n".join(task_list) if task_list else "No reminders for today."
        else:
            ai_response_text = "Your pending tasks:\n" + "\n".join(task_list) if task_list else "No pending tasks."

    elif action in {"delete_task", "complete_task", "update_task", "task_status"}:
        # Use nlu data to perform the action; keep behavior similar to prior implementation
        data = nlu_result.get("data", {}) or {}
        selector = data.get("selector") or ("by_title" if data.get("title") else "last_created")
        query = {"user_id": user_id_str}
        if selector == "by_title" and data.get("title"):
            query["title"] = {"$regex": f"^{re.escape(data.get('title'))}$", "$options": "i"}
        task_doc = tasks.find_one(query, sort=[("created_at", -1)])
        if not task_doc:
            ai_response_text = "I couldn't find that reminder."
        else:
            if action == "delete_task":
                old_celery = task_doc.get("celery_task_id")
                if old_celery:
                    try:
                        celery_app.control.revoke(old_celery, terminate=False)
                    except Exception:
                        logger.debug("Failed to revoke celery task %s", old_celery)
                tasks.delete_one({"_id": task_doc["_id"]})
                ai_response_text = f"Deleted reminder '{task_doc.get('title')}'."
            elif action == "complete_task":
                now_ts = datetime.utcnow()
                tasks.update_one({"_id": task_doc["_id"]}, {"$set": {"status": "done", "completed_at": now_ts, "updated_at": now_ts}})
                ai_response_text = f"Marked '{task_doc.get('title')}' as done."
            elif action == "update_task":
                changes = {}
                if data.get("title"):
                    changes["title"] = data.get("title")
                if data.get("datetime"):
                    new_dt, err, ambiguous = _parse_datetime_with_tz(data["datetime"], user_tz)
                    if ambiguous:
                        ai_response_text = "Do you mean AM or PM?"
                    elif not new_dt:
                        ai_response_text = "I couldn't understand the new time."
                    else:
                        if _to_aware_utc(new_dt) <= datetime.utcnow().replace(tzinfo=timezone.utc):
                            ai_response_text = "That time has already passed. Please choose a future time."
                        else:
                            changes["due_date"] = _to_naive_utc(new_dt)
                if changes:
                    changes["updated_at"] = datetime.utcnow()
                    tasks.update_one({"_id": task_doc["_id"]}, {"$set": changes})
                    # revoke earlier celery job if any
                    old_celery = task_doc.get("celery_task_id")
                    if old_celery:
                        try:
                            celery_app.control.revoke(old_celery, terminate=False)
                        except Exception:
                            logger.debug("Failed to revoke celery task %s", old_celery)
                    ai_response_text = "Updated your reminder."
                else:
                    if not ai_response_text:
                        ai_response_text = "What should I change — the time or the description?"
            elif action == "task_status":
                status_txt = task_doc.get("status", "todo")
                due = task_doc.get("due_date")
                due_str = due.strftime("%Y-%m-%d %H:%M") if isinstance(due, datetime) else "unscheduled"
                ai_response_text = f"'{task_doc.get('title')}' is {status_txt}. Due: {due_str}."

    elif action == "save_fact":
        data = nlu_result.get("data", {}) or {}
        key, value = data.get("key"), data.get("value")
        if key and value:
            key_norm = key.lower().replace("_", " ")
            try:
                # Upsert fact in user_profiles
                user_profiles.update_one({"_id": user_id_str, "facts.key": key_norm}, {"$set": {"facts.$.value": value}})
                if user_profiles.find_one({"_id": user_id_str, "facts.key": key_norm}) is None:
                    user_profiles.update_one({"_id": user_id_str}, {"$push": {"facts": {"key": key_norm, "value": value}}, "$setOnInsert": {"_id": user_id_str}}, upsert=True)
                ai_response_text = f"Got it. I will remember that your {key_norm} is {value}."
            except Exception:
                logger.exception("Failed to save user fact")
                ai_response_text = "I couldn't save that fact — please try again."
        else:
            ai_response_text = "Could not understand the fact. Please rephrase."

    else:
        # Default: handle as general chat — gather context and ask ai_service
        memory_ctx = await _safe_gather_context(
            user_id=user_id_str,
            user_key=user_email,
            session_id=session_id,
            latest_user_message=chat_req.message,
            recent_messages=session.get("messages", [])
        )
        history_for_prompt = []
        for m in memory_ctx.get("history", [])[-20:]:
            if "content" in m:
                sender = "user" if m.get("role") == "user" else "assistant"
                history_for_prompt.append({"sender": sender, "text": m["content"]})
            elif "text" in m and "sender" in m:
                history_for_prompt.append({"sender": m["sender"], "text": m["text"]})
        if "user_id" not in user_profile_doc and current_user.get("_id"):
            user_profile_doc["user_id"] = user_id_str
        ai_response_text = await _safe_ai_response(
            prompt=chat_req.message,
            history=history_for_prompt,
            pinecone_context=memory_ctx.get("pinecone_context"),
            neo4j_facts=memory_ctx.get("neo4j_facts"),
            state=None,
            profile=user_profile_doc,
            session_id=str(session_id),
            user_facts_semantic=memory_ctx.get("user_facts_semantic"),
            persistent_memories=memory_ctx.get("persistent_memories"),
        )

    # Persist messages and post update hooks
    if not isinstance(ai_response_text, str):
        ai_response_text = str(ai_response_text or "")

    # Final shaping for consistency: greeting, hook, tone, suggestions
    try:
        shaped_text = format_structured_reply(
            user_message=chat_req.message,
            main_text=ai_response_text,
            profile=user_profile_doc,
            short_context={
                "last_topic": session.get("title") if isinstance(session.get("title"), str) else None,
            },
        )
    except Exception:
        shaped_text = ai_response_text

    ai_message = {"sender": "assistant", "text": shaped_text, "timestamp": datetime.utcnow()}

    # Atomic push: user message + assistant reply
    update_filter = {"_id": ObjectId(session_id), "$or": [{"userId": current_user["_id"]}]}
    if isinstance(current_user["_id"], str) and ObjectId.is_valid(current_user["_id"]):
        update_filter["$or"].append({"userId": ObjectId(current_user["_id"])})
    try:
        sessions_collection.update_one(
            update_filter,
            {
                "$push": {"messages": {"$each": [user_message_doc, ai_message]}},
                "$set": {"updatedAt": datetime.utcnow(), "lastMessageAt": datetime.utcnow(), "lastMessage": shaped_text[:200]},
                "$inc": {"messageCount": 2},
            },
        )
    except Exception:
        logger.exception("Failed to persist chat messages for session %s", session_id)

    # Post-processing: update short-term memory & telemetry (already async/non-blocking)
    try:
        post_message_update(user_id=user_id_str, user_key=user_email, session_id=session_id, user_message=chat_req.message, ai_message=shaped_text, state=None)
    except Exception:
        logger.debug("post_message_update failed", exc_info=True)

    return ai_message
