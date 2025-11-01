# backend/app/routes/tasks.py
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from bson import ObjectId, errors
import dateparser  # retained for any legacy parsing paths
import pytz
import logging
from pymongo.errors import OperationFailure

from app.models import (
    Task,
    TaskCreate,
    TaskUpdate,
    TaskBulkUpdate,
    TaskStatus,
    TaskPriority,
)
from app.database import get_tasks_collection
from app.security import get_current_active_user
from app.utils.time_utils import parse_user_time_ist
from app.services import task_service
from app.services.realtime import realtime_bus, RTEvent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/tasks",
    tags=["Tasks"],
    dependencies=[Depends(get_current_active_user)],
)

# --------- Configuration / constants ----------
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200
DUE_SOON_DAYS_DEFAULT = 7

# --------- Utility helpers --------------------

def _str_oid(oid: Any) -> str:
    """Convert ObjectId or string id to string representation."""
    if isinstance(oid, str):
        return oid
    try:
        return str(oid)
    except Exception:
        return str(oid)

def _user_id_value(current_user: dict) -> Any:
    """Return user id in the form stored in DB (prefer existing shapes)."""
    return current_user.get("user_id") or current_user.get("userId") or current_user.get("_id")

def _make_user_match(user_id: Any) -> Dict[str, Any]:
    """
    Return a Mongo-friendly match that tolerates stored userId as either string or ObjectId.
    Use this in queries like {"$or": [{ "user_id": user_id }, { "user_id": ObjectId(user_id) }]}
    """
    clauses = []
    if user_id is not None:
        clauses.append({"user_id": user_id})
        try:
            if isinstance(user_id, str) and ObjectId.is_valid(user_id):
                clauses.append({"user_id": ObjectId(user_id)})
        except Exception:
            # non-fatal
            pass
    return {"$or": clauses} if clauses else {}

def _ensure_objectid_or_pass(val: str) -> Any:
    """Try to convert to ObjectId, otherwise return original string (tolerate string _id storage)."""
    try:
        return ObjectId(val)
    except Exception:
        return val

def _to_naive_utc_from_dt(dt_obj: datetime) -> datetime:
    """Convert any aware datetime to naive UTC for storage; or accept naive as already UTC."""
    if dt_obj is None:
        return None
    try:
        if dt_obj.tzinfo is None:
            return dt_obj
        return dt_obj.astimezone(pytz.UTC).replace(tzinfo=None)
    except Exception:
        # Defensive fallback
        return dt_obj

def _to_naive_utc_from_parsed(dt_obj: Optional[datetime]) -> Optional[datetime]:
    return _to_naive_utc_from_dt(dt_obj) if dt_obj is not None else None

# --------- Date parsing --------------------------------
def _parse_when_to_due_date(when: Optional[str], timezone: Optional[str], prefer_future: bool = True) -> Optional[datetime]:
    """IST-enforced natural language parse: ignores provided timezone and treats input as Asia/Kolkata.
    Returns naive UTC datetime for storage or None.
    """
    if not when:
        return None
    try:
        return parse_user_time_ist(when, prefer_future=prefer_future)
    except Exception as exc:
        logger.debug("IST parse error for %r: %s", when, exc)
        return None

# --------- Index helper (call on startup) ----------
def create_task_indexes(tasks_collection):
    """
    Helper to create recommended indexes.
    Call this from app startup (once).
    Indexes:
      - user_id + due_date (for due/overdue/due_soon queries)
      - user_id + status (for quick status queries)
      - text index on title + description for search
    """
    try:
        # Align names with global index definitions in app.database.ensure_indexes
        try:
            tasks_collection.create_index([("user_id", 1), ("due_date", 1)], name="user_due_date", background=True)
        except OperationFailure as of:
            # Ignore options conflict if an equivalent index already exists under another name
            if getattr(of, "code", None) != 85:
                raise
        try:
            tasks_collection.create_index([("user_id", 1), ("status", 1)], name="user_status", background=True)
        except OperationFailure as of:
            if getattr(of, "code", None) != 85:
                raise
        # create text index with weights to prioritize title
        try:
            tasks_collection.create_index([("title", "text"), ("description", "text")], name="task_text_idx", default_language="english", background=True)
        except OperationFailure as of:
            if getattr(of, "code", None) != 85:
                raise
        logger.info("Task indexes ensured.")
    except Exception as exc:
        logger.exception("Failed to create task indexes: %s", exc)

# --------- Response normalization --------------------
def _to_task_response(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize DB document to a JSON-serializable dict that matches Task model shape.
    Keeps backward compatibility: converts _id to string and ensures default fields exist.
    """
    out = dict(doc)
    if "_id" in out:
        out["_id"] = _str_oid(out["_id"])
    out.setdefault("status", TaskStatus.TODO)
    out.setdefault("priority", TaskPriority.MEDIUM)
    out.setdefault("tags", out.get("tags") or [])
    return out

# ===========================
# CRUD & endpoints
# ===========================

@router.get("/")
async def list_tasks(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    due_soon: Optional[bool] = Query(False),
    overdue: Optional[bool] = Query(False),
    search: Optional[str] = Query(None, description="Full-text search on title & description"),
    sort_by: Optional[str] = Query("updated_at", description="Sort field: updated_at | due_date | created_at"),
    sort_dir: Optional[int] = Query(-1, ge=-1, le=1, description="Sort direction: 1 asc, -1 desc"),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    """
    List tasks for the user with flexible filtering, search, sorting and pagination.
    Implements defensive handling of user_id shapes and optimized queries for due_soon/overdue.
    """
    user_id = _user_id_value(current_user)
    if not user_id:
        return []

    # Ensure indexes exist if necessary (non-blocking; safe to call multiple times)
    try:
        create_task_indexes(tasks)
    except Exception:
        logger.debug("Index creation attempted (may have been created before).")

    query: Dict[str, Any] = {"user_id": user_id}

    if status:
        query["status"] = status
    if priority:
        query["priority"] = priority
    if tag:
        # match membership in array or exact
        query["tags"] = tag

    now = datetime.utcnow()
    # overdue overrides due_soon
    if overdue:
        query["due_date"] = {"$lt": now}
        # exclude completed/cancelled when counting overdue unless explicit
        query.setdefault("status", {"$nin": ["done", "cancelled"]})
    elif due_soon:
        window_end = now + timedelta(days=DUE_SOON_DAYS_DEFAULT)
        query["due_date"] = {"$gte": now, "$lte": window_end}

    # Search: prefer text index when available
    cursor = None
    try:
        if search:
            # Use Mongo's $text search if index present; fallback to regex on title/description
            try:
                cursor = tasks.find({**query, "$text": {"$search": search}}, {"score": {"$meta": "textScore"}})
                # sort by score desc then requested sort
                cursor = cursor.sort([("score", {"$meta": "textScore"})])
            except Exception:
                # fallback regex
                regex = {"$regex": search, "$options": "i"}
                cursor = tasks.find({**query, "$or": [{"title": regex}, {"description": regex}]})
        else:
            cursor = tasks.find(query)
    except Exception as exc:
        logger.exception("Task listing query failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to query tasks")

    # Sorting and pagination
    if cursor is not None:
        sort_field = sort_by if sort_by in {"updated_at", "due_date", "created_at"} else "updated_at"
        sort_direction = int(sort_dir) if sort_dir in (-1, 1) else -1
        cursor = cursor.sort(sort_field, sort_direction).skip(offset).limit(limit)

    items: List[Dict[str, Any]] = []
    try:
        for d in cursor:
            # normalize id and fields
            items.append(_to_task_response(d))
    except Exception as exc:
        logger.exception("Error iterating tasks cursor: %s", exc)
        raise HTTPException(status_code=500, detail="Error reading tasks")

    return items

# alias to avoid strict slash issues
@router.get("")
async def list_tasks_alias(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    due_soon: Optional[bool] = Query(False),
    overdue: Optional[bool] = Query(False),
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("updated_at"),
    sort_dir: Optional[int] = Query(-1),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    return await list_tasks(status, priority, tag, due_soon, overdue, search, sort_by, sort_dir, limit, offset, current_user, tasks)  # type: ignore[arg-type]


@router.post("/", response_model=Task)
async def create_task(
    task_in: TaskCreate,
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    """
    Create a new task with comprehensive notification system.
    Accepts either due_date explicitly (ISO string / datetime) or a natural language 'when' with timezone.
    Stores due_date as naive UTC datetime in Mongo.
    Disallows creating tasks in the past by default to avoid accidental scheduling; set allow_past True in request if needed.
    """
    user_id = _user_id_value(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user context")

    # Resolve due date: priority order: explicit due_date field -> when + timezone
    due_date = None
    if getattr(task_in, "due_date", None):
        # if pydantic parsed it to a datetime, use as provided; if string, try parse
        if isinstance(task_in.due_date, datetime):
            due_date = task_in.due_date
        else:
            try:
                # Try iso format parse using dateparser fallback
                parsed = _parse_when_to_due_date(str(task_in.due_date), task_in.timezone or None, prefer_future=True)
                due_date = parsed
            except Exception:
                due_date = None
    elif getattr(task_in, "when", None):
        due_date = _parse_when_to_due_date(task_in.when, task_in.timezone or None, prefer_future=True)

    # If due_date present, ensure not in past unless allow_past True
    if due_date and not getattr(task_in, "allow_past", False):
        now = datetime.utcnow()
        if due_date <= now:
            raise HTTPException(status_code=400, detail="due_date must be in the future")

    # Use enhanced task flow service for comprehensive task creation
    try:
        from app.services.task_flow_service import create_task_with_full_flow
        
        # Prepare user data for task flow service
        user_data = {
            "user_id": user_id,
            "email": current_user.get("email") or current_user.get("user_email"),
            "name": current_user.get("name") or current_user.get("username")
        }
        
        # Create task with full flow (notifications, memory storage, etc.)
        flow_result = await create_task_with_full_flow(
            user=user_data,
            title=task_in.title.strip(),
            due_date_utc=due_date or (datetime.utcnow() + timedelta(hours=1)),
            description=(task_in.description or "").strip(),
            priority=task_in.priority or TaskPriority.MEDIUM,
            tags=task_in.tags or []
        )
        
        if not flow_result["success"]:
            logger.error(f"Task flow creation failed: {flow_result.get('errors', [])}")
            # Fall back to basic task creation
            return await _create_basic_task(task_in, current_user, tasks)
        
        # Get the created task from database
        task_id = flow_result["task_id"]
        created = tasks.find_one({"_id": ObjectId(task_id)})
        if not created:
            raise HTTPException(status_code=500, detail="Task created but could not be read back")
        
        # Convert _id for pydantic model
        created["_id"] = str(created["_id"])
        
        # Log successful creation with flow details
        logger.info(f"Task created with full flow: {task_id}, notifications: {flow_result.get('notifications', {})}")
        
        # Emit realtime event
        try:
            await realtime_bus.emit(RTEvent(type="task.created", user_id=str(user_id), payload=_to_task_response(created)))
        except Exception:
            pass
        return Task(**created)
        
    except Exception as exc:
        logger.exception("Enhanced task creation failed, falling back to basic: %s", exc)
        # Fall back to basic task creation
        return await _create_basic_task(task_in, current_user, tasks)


async def _create_basic_task(task_in: TaskCreate, current_user: dict, tasks) -> Task:
    """Fallback basic task creation without enhanced flow."""
    user_id = _user_id_value(current_user)
    
    # Resolve due date
    due_date = None
    if getattr(task_in, "due_date", None):
        if isinstance(task_in.due_date, datetime):
            due_date = task_in.due_date
        else:
            try:
                parsed = _parse_when_to_due_date(str(task_in.due_date), task_in.timezone or None, prefer_future=True)
                due_date = parsed
            except Exception:
                due_date = None
    elif getattr(task_in, "when", None):
        due_date = _parse_when_to_due_date(task_in.when, task_in.timezone or None, prefer_future=True)

    # Build document with safe defaults
    now = datetime.utcnow()
    doc = {
        "user_id": user_id,
        "title": task_in.title.strip(),
        "description": (task_in.description or "").strip(),
        "status": task_in.status or TaskStatus.TODO,
        "priority": task_in.priority or TaskPriority.MEDIUM,
        "due_date": _to_naive_utc_from_parsed(due_date),
        "tags": task_in.tags or [],
        "recurrence": task_in.recurrence,
        "created_at": now,
        "updated_at": now,
    }

    try:
        res = tasks.insert_one(doc)
    except Exception as exc:
        logger.exception("Failed to insert task: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create task")

    created = tasks.find_one({"_id": res.inserted_id})
    if not created:
        raise HTTPException(status_code=500, detail="Task created but could not be read back")

    # Convert _id for pydantic model
    created["_id"] = str(created["_id"])
    # Emit realtime event
    try:
        await realtime_bus.emit(RTEvent(type="task.created", user_id=str(user_id), payload=_to_task_response(created)))
    except Exception:
        pass
    return Task(**created)


@router.post("")
async def create_task_alias(
    task_in: TaskCreate,
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    return await create_task(task_in, current_user, tasks)  # type: ignore[arg-type]


# ----------------------------
# OTP Verification & Reschedule & Summary
# ----------------------------

@router.post("/{task_id}/verify-otp")
async def verify_task_otp(
    task_id: str,
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_active_user),
):
    """
    Verify OTP for a task (optional audit endpoint).
    Since auto-complete is triggered, OTP verification is optional.
    """
    otp = str(payload.get("otp") or "").strip()
    if not otp:
        raise HTTPException(status_code=400, detail="OTP required")
    
    try:
        result = await task_service.verify_otp_async(current_user, task_id, otp)
        
        if result.get("verified"):
            return {"status": "success", "message": "OTP verified successfully"}
        else:
            reason = result.get("reason", "unknown")
            if reason == "otp_expired_or_missing":
                raise HTTPException(status_code=410, detail="OTP expired or not found")
            else:
                raise HTTPException(status_code=400, detail="Invalid OTP")
                
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"OTP verification failed for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{task_id}/reschedule")
async def reschedule_task_endpoint(
    task_id: str,
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_active_user),
):
    new_due = payload.get("due_date") or payload.get("when")
    if not new_due:
        raise HTTPException(status_code=400, detail="due_date or when required")
    # Parse if string
    if isinstance(new_due, str):
        parsed = _parse_when_to_due_date(new_due, payload.get("timezone") or None, prefer_future=True)
        if not parsed:
            raise HTTPException(status_code=400, detail="invalid due_date")
        new_due = parsed
    try:
        doc = task_service.reschedule_task(current_user, task_id, new_due)
        if not doc:
            raise HTTPException(status_code=404, detail="Task not found")
        return _to_task_response(doc)
    except ValueError as e:
        if str(e) == "not_found":
            raise HTTPException(status_code=404, detail="Task not found")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to reschedule task")


@router.get("/summary")
async def tasks_summary(
    limit: int = Query(5, ge=1, le=20),
    current_user: dict = Depends(get_current_active_user),
):
    try:
        items = task_service.list_upcoming_summary(current_user, limit=limit)
        return [
            {
                "_id": i.get("_id"),
                "title": i.get("title"),
                "due_date": i.get("due_date"),
                "priority": i.get("priority"),
                "status": i.get("status"),
            }
            for i in items
        ]
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get summary")


@router.get("/{task_id}", response_model=Task)
async def get_task(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    user_id = _user_id_value(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user context")

    # try ObjectId then fallback to string id toleration
    query = {"user_id": user_id}
    try:
        oid = ObjectId(task_id)
        query["_id"] = oid
    except Exception:
        query["_id"] = task_id

    doc = tasks.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    doc["_id"] = str(doc["_id"])
    return Task(**doc)


@router.put("/{task_id}")
async def update_task(
    task_id: str,
    updates: TaskUpdate,
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    """
    Partial update of a task. If due_date provided as string (natural language), attempt to parse
    using the optional timezone included in the request body (updates.timezone).
    """
    user_id = _user_id_value(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user context")

    data = updates.model_dump(exclude_unset=True)
    if "due_date" in data and isinstance(data["due_date"], str):
        parsed = _parse_when_to_due_date(data["due_date"], data.get("timezone"))
        if parsed:
            data["due_date"] = parsed
        else:
            # try to allow ISO string
            try:
                iso_dt = dateparser.parse(data["due_date"], settings={"RETURN_AS_TIMEZONE_AWARE": True})
                if iso_dt:
                    data["due_date"] = iso_dt.astimezone(pytz.UTC).replace(tzinfo=None)
                else:
                    data.pop("due_date", None)
            except Exception:
                data.pop("due_date", None)

    # if due_date present, ensure not in the past unless explicitly allowed
    if "due_date" in data and data["due_date"] is not None and not data.get("allow_past", False):
        if isinstance(data["due_date"], datetime) and data["due_date"] <= datetime.utcnow():
            raise HTTPException(status_code=400, detail="due_date must be in the future")

    data["updated_at"] = datetime.utcnow()
    try:
        oid = ObjectId(task_id)
        res = tasks.update_one({"_id": oid, "user_id": user_id}, {"$set": data})
    except Exception:
        # fallback to string _id
        res = tasks.update_one({"_id": task_id, "user_id": user_id}, {"$set": data})

    if getattr(res, "matched_count", 0) == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    # Emit update event (best-effort)
    try:
        payload = {"id": task_id, **{k: v for k, v in data.items() if k != "allow_past"}}
        await realtime_bus.emit(RTEvent(type="task.updated", user_id=str(user_id), payload=payload))
    except Exception:
        pass
    return {"success": True}


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    user_id = _user_id_value(current_user)
    try:
        oid = ObjectId(task_id)
        res = tasks.delete_one({"_id": oid, "user_id": user_id})
    except Exception:
        res = tasks.delete_one({"_id": task_id, "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    # Emit delete event
    try:
        await realtime_bus.emit(RTEvent(type="task.deleted", user_id=str(user_id), payload={"id": task_id}))
    except Exception:
        pass
    return {"success": True}


@router.post("/bulk")
async def bulk_update(
    payload: TaskBulkUpdate,
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    user_id = _user_id_value(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user context")

    ids: List[Any] = []
    for tid in payload.task_ids:
        try:
            ids.append(ObjectId(tid))
        except Exception:
            ids.append(tid)

    q = {"_id": {"$in": ids}, "user_id": user_id}

    # Perform operation and return per-id info where helpful
    if payload.operation == "delete":
        res = tasks.delete_many(q)
        # Emit a compact bulk-delete event
        try:
            await realtime_bus.emit(RTEvent(type="task.bulk_deleted", user_id=str(user_id), payload={"ids": payload.task_ids}))
        except Exception:
            pass
        return {"success": True, "deleted": res.deleted_count}
    elif payload.operation == "complete":
        now = datetime.utcnow()
        res = tasks.update_many(q, {"$set": {"status": TaskStatus.DONE, "completed_at": now, "updated_at": now}})
        try:
            await realtime_bus.emit(RTEvent(type="task.bulk_updated", user_id=str(user_id), payload={"status": TaskStatus.DONE, "ids": payload.task_ids}))
        except Exception:
            pass
        return {"success": True, "updated": res.modified_count}
    elif payload.operation == "update_status" and payload.status:
        res = tasks.update_many(q, {"$set": {"status": payload.status, "updated_at": datetime.utcnow()}})
        try:
            await realtime_bus.emit(RTEvent(type="task.bulk_updated", user_id=str(user_id), payload={"status": payload.status, "ids": payload.task_ids}))
        except Exception:
            pass
        return {"success": True, "updated": res.modified_count}
    elif payload.operation == "update_priority" and payload.priority:
        res = tasks.update_many(q, {"$set": {"priority": payload.priority, "updated_at": datetime.utcnow()}})
        try:
            await realtime_bus.emit(RTEvent(type="task.bulk_updated", user_id=str(user_id), payload={"priority": payload.priority, "ids": payload.task_ids}))
        except Exception:
            pass
        return {"success": True, "updated": res.modified_count}
    else:
        raise HTTPException(status_code=400, detail="Invalid bulk operation")

# ----------------------------
# STATS & TAGS (improved)
# ----------------------------
@router.get("/stats/summary")
async def task_stats_summary(
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    user_id = _user_id_value(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user context")

    try:
        total = tasks.count_documents({"user_id": user_id})
        now = datetime.utcnow()
        overdue = tasks.count_documents({"user_id": user_id, "due_date": {"$lt": now}, "status": {"$nin": ["done", "cancelled"]}})
        def _count(q):
            return tasks.count_documents({"user_id": user_id, **q})
        return {
            "total": total,
            "todo": _count({"status": "todo"}),
            "in_progress": _count({"status": "in_progress"}),
            "done": _count({"status": "done"}),
            "cancelled": _count({"status": "cancelled"}),
            "overdue": overdue,
        }
    except Exception as exc:
        logger.exception("Failed to compute stats: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to compute stats")

@router.get("/stats/priority")
async def task_priority_stats(
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    user_id = _user_id_value(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user context")
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$priority", "count": {"$sum": 1}}},
    ]
    agg = list(tasks.aggregate(pipeline))
    base = {"low": 0, "medium": 0, "high": 0, "urgent": 0}
    for row in agg:
        key = (row.get("_id") or "").lower()
        if key in base:
            base[key] = row.get("count", 0)
    return base

@router.get("/tags")
async def user_tags(
    current_user: dict = Depends(get_current_active_user),
    tasks = Depends(get_tasks_collection),
):
    user_id = _user_id_value(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user context")
    try:
        tags = tasks.distinct("tags", {"user_id": user_id})
        uniq = set()
        for t in tags:
            if isinstance(t, list):
                for s in t:
                    if isinstance(s, str):
                        uniq.add(s)
            elif isinstance(t, str):
                uniq.add(t)
        return sorted(uniq)
    except Exception as exc:
        logger.exception("Failed to fetch tags: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch tags")
