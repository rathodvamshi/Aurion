from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List, Union

from bson import ObjectId

from fastapi.concurrency import run_in_threadpool

from app.database import db_client
from app.config import settings
from app.logger import log_event
from app.services.redis_service import get_client as get_redis
from app.services import profile_service
from app.utils import email_utils
from app.utils.time_utils import parse_user_time_ist, format_ist, ensure_future_ist, parse_and_validate_ist

logger = logging.getLogger(__name__)


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    try:
        return dt.replace(tzinfo=None)
    except Exception:
        return dt


def _window(due: datetime, seconds: int = 300) -> tuple[datetime, datetime]:
    return (due - timedelta(seconds=seconds), due + timedelta(seconds=seconds))


def _user_id_str(current_user: Dict[str, Any]) -> str:
    return str(current_user.get("user_id") or current_user.get("_id") or current_user.get("id"))


def _safe_object_id(val: str | ObjectId) -> Any:
    try:
        return ObjectId(val)
    except Exception:
        return val


def create_task(user, title: str, due_date_utc: datetime, description: str = None, priority: str = "normal", auto_complete: bool = True) -> str:
    """
    Create task + schedule Celery as specified in requirements.
    Returns task_id string.
    """
    from bson import ObjectId
    
    # Best-effort: try to connect, but allow in-memory fallback collections in degraded mode
    try:
        if not db_client.healthy():
            db_client.connect()
    except Exception:
        pass
    coll = db_client.get_tasks_collection()

    now = datetime.utcnow()
    user_id = _user_id_str(user)
    
    # Create task document
    task_doc = {
        "user_id": user_id,
        "email": user.get("email") or user.get("user_email"),
        "title": title,
        "description": description or "",
        "due_date": due_date_utc,
        "priority": priority,
        "status": "todo",
        "auto_complete_after_email": auto_complete,
        "created_at": now,
        "updated_at": now,
        "celery_task_id": None,
        "tags": [],
        "recurrence": "none",
        "notify_channel": "email",
        "metadata": {},
        "notification_count": 0,
        "last_notification_sent": None
    }
    
    res = coll.insert_one(task_doc)
    task_id = str(res.inserted_id)

    # Send immediate creation notification
    try:
        from app.celery_tasks import send_task_notification_email
        user_email = user.get("email") or user.get("user_email")
        if user_email:
            send_task_notification_email.delay(
                task_id=task_id,
                user_email=user_email,
                task_title=title,
                task_description=description or "",
                due_date=due_date_utc.isoformat(),
                priority=priority,
                task_type="creation",
                user_id=user_id,
            )
            log_event("task_created", user_id=user_id, task_id=task_id, email=user_email, title=title, due_utc=due_date_utc.isoformat()+"Z")
            log_event("email_notification_queued", user_id=user_id, task_id=task_id, email=user_email, kind="creation")
    except Exception as e:
        logger.warning(f"Failed to send creation notification: {e}")

    # Schedule reminder notification at due time
    try:
        from app.celery_worker import send_task_otp_task
        user_email = user.get("email") or user.get("user_email")
        if user_email:
            async_res = send_task_otp_task.apply_async(args=[task_id, user_email, title], eta=due_date_utc)
            coll.update_one({"_id": ObjectId(task_id)}, {"$set": {"celery_task_id": async_res.id}})
            log_event("reminder_scheduled", user_id=user_id, task_id=task_id, email=user_email, celery_id=async_res.id, eta=due_date_utc.isoformat()+"Z")
    except Exception as e:
        logger.warning(f"Failed to schedule reminder task: {e}")

    return task_id


def create_task_legacy(current_user: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Legacy create_task function for backward compatibility.
    """
    try:
        if not db_client.healthy():
            db_client.connect()
    except Exception:
        pass
    coll = db_client.get_tasks_collection()

    now = datetime.utcnow()
    user_id = _user_id_str(current_user)
    title = (payload.get("title") or "").strip()
    due = _naive(payload.get("due_date"))
    if due is None:
        raise ValueError("due_date required")
    if due <= now and not payload.get("allow_past", False):
        raise ValueError("due_date must be in the future")

    # Duplicate within ±5 minutes
    ws, we = _window(due, 300)
    existing = coll.find_one({
        "user_id": user_id,
        "title": title,
        "due_date": {"$gte": ws, "$lte": we},
    })
    if existing:
        raise ValueError("duplicate_task_window")

    doc = {
        "_id": str(ObjectId()),
        "user_id": user_id,
        "title": title,
        "description": (payload.get("description") or "").strip(),
        "status": payload.get("status") or "todo",
        "priority": payload.get("priority") or "medium",
        "due_date": due,
        "tags": payload.get("tags") or [],
        "recurrence": payload.get("recurrence") or "none",
        "notify_channel": payload.get("notify_channel") or "email",
        "auto_complete_after_email": payload.get("auto_complete_after_email", True),
        "created_at": now,
        "updated_at": now,
        "celery_task_id": None,
        "metadata": {},
    }
    coll.insert_one(doc)

    # Schedule OTP email at exact due time
    try:
        from app.celery_worker import send_task_otp_task
        user_email = current_user.get("email") or current_user.get("user_email")
        if user_email:
            res = send_task_otp_task.apply_async(args=[str(doc["_id"]), user_email, title], eta=due)
            try:
                coll.update_one({"_id": doc["_id"]}, {"$set": {"celery_task_id": res.id}})
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed to schedule OTP task: {e}")

    return doc


def reschedule_task(current_user: Dict[str, Any], task_id: str, new_due_date: datetime) -> Dict[str, Any]:
    coll = db_client.get_tasks_collection()
    user_id = _user_id_str(current_user)
    doc = coll.find_one({"_id": _safe_object_id(task_id), "user_id": user_id})
    if not doc:
        raise ValueError("not_found")
    old_celery = doc.get("celery_task_id")
    # Best-effort revoke if we had a celery id
    if old_celery:
        try:
            from app.celery_app import celery_app
            celery_app.control.revoke(old_celery, terminate=False)
        except Exception:
            pass
    now = datetime.utcnow()
    coll.update_one({"_id": doc["_id"]}, {"$set": {"due_date": _naive(new_due_date), "updated_at": now}})
    # Re-schedule
    try:
        from app.celery_worker import send_task_otp_task
        user_email = current_user.get("email") or current_user.get("user_email")
        if user_email:
            res = send_task_otp_task.apply_async(args=[user_id, user_email, str(doc["_id"]), doc.get("title") or "Reminder"], eta=_naive(new_due_date))
            coll.update_one({"_id": doc["_id"]}, {"$set": {"celery_task_id": res.id}})
    except Exception:
        pass
    return coll.find_one({"_id": doc["_id"]}) or {}


def delete_task(current_user: Dict[str, Any], task_id: str) -> bool:
    coll = db_client.get_tasks_collection()
    user_id = _user_id_str(current_user)
    doc = coll.find_one({"_id": _safe_object_id(task_id), "user_id": user_id})
    if not doc:
        return False
    if doc.get("celery_task_id"):
        try:
            from app.celery_app import celery_app
            celery_app.control.revoke(doc["celery_task_id"], terminate=False)
        except Exception:
            pass
    res = coll.delete_one({"_id": doc["_id"]})
    return bool(getattr(res, "deleted_count", 0))


async def verify_otp_async(current_user: Dict[str, Any], task_id: str, otp: str) -> Dict[str, Any]:
    client = get_redis()
    if not client:
        raise RuntimeError("redis_unavailable")
    key = f"otp:task:{task_id}"
    try:
        val = await client.get(key)
    except Exception:
        val = None

    if not val:
        return {"verified": False, "reason": "otp_expired_or_missing"}
    if str(val).strip() != str(otp).strip():
        return {"verified": False, "reason": "otp_mismatch"}

    try:
        await client.delete(key)
    except Exception:
        pass

    # Mark task metadata
    coll = db_client.get_tasks_collection()
    coll.update_one({"_id": _safe_object_id(task_id), "user_id": _user_id_str(current_user)}, {"$set": {"metadata.otp_verified": True, "updated_at": datetime.utcnow()}})
    return {"verified": True}


def verify_otp(current_user: Dict[str, Any], task_id: str, otp: str) -> Dict[str, Any]:
    """Sync wrapper for OTP verification. Uses asyncio.run only if no loop is active."""
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        # If we're in an event loop, run via create_task and wait
        fut = asyncio.run_coroutine_threadsafe(
            verify_otp_async(current_user, task_id, otp), loop
        )
        return fut.result()
    except RuntimeError:
        # No running loop
        import asyncio as _asyncio
        return _asyncio.run(verify_otp_async(current_user, task_id, otp))


def list_upcoming_summary(current_user: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    coll = db_client.get_tasks_collection()
    user_id = _user_id_str(current_user)
    now = datetime.utcnow()
    cur = coll.find({"user_id": user_id, "due_date": {"$gte": now}, "status": {"$in": ["todo", "in_progress"]}}).sort("due_date", 1).limit(int(limit))
    out: List[Dict[str, Any]] = []
    for d in cur:
        dd = dict(d)
        try:
            dd["_id"] = str(dd.get("_id"))
        except Exception:
            pass
        out.append(dd)
    return out


# -------------------------------
# New: IST-aware async task creation API
# -------------------------------
async def create_user_task(
    user_id: str,
    title: str,
    task_time: Optional[Union[str, datetime]] = None,
    payload: Optional[Dict[str, Any]] = None,
    user_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a user task with IST-aware time parsing and schedule Celery ETA.

    - Accepts task_time as either datetime (assumed UTC-naive or aware) or natural language string.
    - Ensures due time is in the future (bumps to now+60s if needed).
    - Inserts into global tasks collection and schedules OTP email via Celery at ETA.
    - Records recent task reference in user profile.
    - Emits a lightweight activity_logs document for observability.

    Returns a dict with task_id, due_utc (datetime), due_ist (str), and title.
    """
    # 1) Resolve due_utc from task_time
    due_utc: Optional[datetime] = None
    if isinstance(task_time, datetime):
        # Normalize to UTC-naive
        if task_time.tzinfo is not None:
            try:
                due_utc = task_time.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                due_utc = task_time.replace(tzinfo=None)
        else:
            due_utc = task_time
    elif isinstance(task_time, str):
        try:
            # Enforce IST parsing + min lead with friendly errors
            due_utc, _pretty = parse_and_validate_ist(task_time, min_lead_seconds=5)
        except ValueError as ve:
            raise ValueError(str(ve))
        except Exception:
            due_utc = None

    # Validate future (IST policy). Reject if past.
    now = datetime.utcnow().replace(tzinfo=None)
    if not due_utc or not ensure_future_ist(due_utc):
        raise ValueError("Scheduled time must be in the future (IST).")

    # Round seconds for stability
    due_utc = due_utc.replace(second=0, microsecond=0)

    # 2) Lookup user email if not provided
    try:
        if not user_email:
            prof = profile_service.get_profile(user_id)
            user_email = prof.get("email") or prof.get("user_email")
    except Exception:
        user_email = None

    # 3) Create task using existing sync helper in threadpool
    def _create() -> str:
        return create_task(
            user={"user_id": user_id, "email": user_email} if user_email else {"user_id": user_id},
            title=title,
            due_date_utc=due_utc,
            description=(payload or {}).get("description") if payload else None,
            priority=(payload or {}).get("priority", "normal") if payload else "normal",
            auto_complete=True,
        )

    task_id: str = await run_in_threadpool(_create)

    # 4) Best-effort profile update (recent task reference)
    try:
        profile_service.record_task_created(user_id, task_id=task_id, title=title, due_date=due_utc)
    except Exception:
        logger.debug("record_task_created failed", exc_info=True)

    # 5) Activity log for observability
    try:
        act = db_client.get_activity_logs_collection()
        if act is not None:
            doc = {
                "type": "task_created",
                "user_id": str(user_id),
                "task_id": str(task_id),
                "title": title,
                "due_utc": due_utc,
                "due_ist": format_ist(due_utc),
                "source": (payload or {}).get("source") or "llm_brain",
                "timestamp": datetime.utcnow(),
            }
            await run_in_threadpool(act.insert_one, doc)
    except Exception:
        logger.debug("activity_log task_created failed", exc_info=True)

    # 6) Schedule pre-wake Celery job 2 minutes before due (bounded to now+5s minimum)
    try:
        from app.celery_worker import send_task_otp_task
        prewake_seconds = int(getattr(settings, "PREWAKE_BUFFER_SECONDS", 120) or 120)
        eta = due_utc - timedelta(seconds=prewake_seconds)
        min_eta = now + timedelta(seconds=5)
        if eta < min_eta:
            eta = min_eta
        send_task_otp_task.apply_async(args=[task_id, user_email or "", title, None, due_utc.isoformat()], eta=eta)
        log_event("reminder_prewake", user_id=user_id, task_id=task_id, email=user_email or "", eta=eta.isoformat(), run_at=due_utc.isoformat())

        # activity log
        try:
            act = db_client.get_activity_logs_collection()
            if act:
                act.insert_one({
                    "type": "task_scheduled",
                    "task_id": task_id,
                    "user_id": str(user_id),
                    "title": title,
                    "eta": eta,
                    "run_at": due_utc,
                    "timestamp": datetime.utcnow(),
                })
        except Exception:
            logger.debug("activity_log task_scheduled failed", exc_info=True)
    except Exception:
        logger.debug("prewake scheduling failed", exc_info=True)

    return {"task_id": task_id, "due_utc": due_utc, "due_ist": format_ist(due_utc), "title": title}


