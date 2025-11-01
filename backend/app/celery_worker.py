"""
Celery Worker Tasks for Background Processing
- Fully Windows-compatible (async + eventlet)
- Integrated email & OTP sending
- Memory lifecycle, embeddings, distillation, and fact extraction
- Robust logging and error handling
"""

import os
import json
import asyncio
import logging
import time
from datetime import datetime, timedelta
from bson import ObjectId
from celery import Celery, shared_task
from app.config import settings
from app.database import db_client, get_memories_collection
from app.services import (
    ai_service,
    memory_store,
    profile_service,
    deterministic_extractor,
    pinecone_service,
)
from app.services.neo4j_service import neo4j_sync_service
from app.services.redis_service import redis_client as _redis_client
from app.services.pinecone_service import upsert_memory_embedding
from app.utils import email_utils
from app import celery_tasks as _register_tasks  # ensure task module is imported/registered
from app.utils.time_utils import format_ist
from dateutil.rrule import rrulestr
from app.logger import log_event
try:
    from app.metrics import TASK_COMPLETION_TOTAL
except Exception:
    TASK_COMPLETION_TOTAL = None

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Eventlet patching for Windows Celery worker ---
if os.environ.get("CELERY_WORKER") and os.environ.get("CELERY_USE_EVENTLET") == "1":
    try:
        import importlib
        _eventlet_spec = importlib.util.find_spec("eventlet")
        if _eventlet_spec:
            _eventlet = importlib.import_module("eventlet")
            _eventlet.monkey_patch()
    except Exception as e:
        logger.warning(f"Eventlet patching failed: {e}")


# --- Helper: Fire-and-forget coroutine ---
def _fire_and_forget(coro):
    """Run async coroutine safely from sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
    else:
        return loop.create_task(coro)


# --- Celery configuration ---
celery_app = Celery(
    "maya_tasks",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
    include=['app.celery_worker', 'app.celery_tasks'],
)
try:
    # Also ensure imports list contains tasks for older Celery versions
    celery_app.conf.imports = tuple(set((celery_app.conf.imports or ())) | {"app.celery_tasks"})
except Exception:
    pass
celery_app.conf.timezone = "UTC"

# Connect Neo4j if in worker
if os.environ.get("CELERY_WORKER"):
    try:
        neo4j_sync_service.connect()
    except Exception as e:
        logger.error(f"Neo4j sync connect failed: {e}")
    # Ensure DB connection for worker process (avoid degraded in-memory across processes)
    try:
        if not db_client.healthy():
            ok = db_client.connect()
            logger.info(f"[WorkerInit] Mongo connect attempted ok={ok}")
    except Exception as e:
        logger.warning(f"[WorkerInit] Mongo connect error: {e}")


# --- Periodic tasks setup ---
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(600.0, heartbeat.s(), name="worker_heartbeat")
    sender.add_periodic_task(15.0, drain_embedding_queue.s(), name="drain_embedding_queue_15s")
    sender.add_periodic_task(21600.0, update_memory_salience.s(), name="update_memory_salience_6h")
    sender.add_periodic_task(43200.0, lifecycle_maintenance.s(), name="memory_lifecycle_12h")
    sender.add_periodic_task(86400.0, distillation_scan.s(), name="memory_distillation_scan_24h")
    sender.add_periodic_task(60.0, reminder_sweep.s(), name="reminder_sweep_60s")
    logger.info("Periodic tasks configured successfully.")


# --- Heartbeat task ---
@celery_app.task(name="heartbeat")
def heartbeat():
    logger.info("Celery worker heartbeat - scheduler active")


# --- Audit logging ---
@celery_app.task(name="audit_log")
def audit_log(event: str, payload: dict | None = None, **kwargs):
    try:
        parts = []
        if payload:
            parts.extend(f"{k}={payload[k]}" for k in payload)
        if kwargs:
            parts.extend(f"{k}={kwargs[k]}" for k in kwargs)
        suffix = " " + " ".join(parts) if parts else ""
        logger.info(f"[Audit] {event}{suffix}")
    except Exception:
        logger.info(f"[Audit] {event}")


# --- Reminder sweep with async email sending ---
@celery_app.task(name="reminder_sweep")
def reminder_sweep(window_seconds: int = 60):
    try:
        db = db_client
        if not db.healthy():
            try:
                db.connect()
            except Exception:
                pass
        if not db.healthy():
            logger.info("[Reminders] Skip sweep - DB unhealthy")
            return

        tasks = db.get_tasks_collection()
        notifications = db.get_notifications_collection()
        profiles = db.get_user_profile_collection()
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)

        query = {
            "due_date": {"$gte": window_start, "$lte": now},
            "status": {"$in": ["todo", "pending"]},
        }

        scanned = 0
        dispatched = 0
        emailed = 0
        skipped_recent = 0
        for t in tasks.find(query).limit(200):
            try:
                scanned += 1
                user_id = t.get("user_id")
                title = t.get("title", "Reminder")
                notes = t.get("description")
                channel = t.get("notify_channel") or "email"
                last_sent = t.get("last_sent_at")
                if last_sent and isinstance(last_sent, str):
                    try:
                        last_sent = datetime.fromisoformat(last_sent)
                    except Exception:
                        last_sent = None
                if last_sent and (now - last_sent).total_seconds() < window_seconds:
                    skipped_recent += 1
                    continue

                # Create notification in DB
                notif = {
                    "_id": str(ObjectId()),
                    "user_id": str(user_id),
                    "title": "Reminder",
                    "message": f"It's time: {title}",
                    "type": "info",
                    "action_url": None,
                    "read": False,
                    "created_at": now,
                }
                try:
                    notifications.insert_one(notif)
                except Exception:
                    pass

                # Send email asynchronously
                if channel in ("email", "both"):
                    try:
                        profile = profiles.find_one({"user_id": str(user_id)}) or {}
                        to_email = profile.get("email") or profile.get("user_email") or t.get("email")
                        if to_email:
                            due_dt = t.get("due_date")
                            pretty_time = str(due_dt)
                            pretty_time = format_ist(due_dt)

                            subject = f"Reminder: {title}"
                            body = (
                                "Hi there,\n\n"
                                f"This is a friendly reminder for your scheduled task:\n\n"
                                f"Title: {title}\n"
                                f"Time: {pretty_time}\n"
                                f"Details: {notes or 'No additional details provided.'}\n\n"
                                "Stay productive,\nYour Personal AI Assistant"
                            )
                            html_body = f"""
                            <html>
                              <body>
                                <p>Hi there,</p>
                                <p>This is a friendly reminder for your scheduled task:</p>
                                <p><strong>Title:</strong> {title}<br>
                                   <strong>Time:</strong> {pretty_time}<br>
                                   <strong>Details:</strong> {notes or 'No additional details provided.'}</p>
                                <p>Stay productive,<br>Your Personal AI Assistant</p>
                              </body>
                            </html>
                            """
                            # Async send email via Celery
                            send_email_task.delay(to_email, subject, body, html_body)
                            emailed += 1
                            log_event("sweep_email_queued", user_id=str(user_id), task_id=str(t.get("_id")), email=to_email, title=title)
                    except Exception:
                        pass

                # Update task sent info
                tasks.update_one({"_id": t.get("_id")}, {"$set": {"last_sent_at": now}, "$inc": {"sent_count": 1}})
                dispatched += 1
            except Exception:
                continue
        if scanned:
            logger.info(f"[Reminders] Sweep complete scanned={scanned} dispatched={dispatched} emailed={emailed} skipped_recent={skipped_recent} window={window_seconds}s")
        else:
            logger.info("[Reminders] Sweep complete - no due tasks found")
    except Exception as e:
        logger.exception(f"Reminder sweep failed: {e}")


# --- Celery Email Tasks ---
@shared_task(name="send_email_task", autoretry_for=(email_utils.EmailSendError,), retry_kwargs={"max_retries":3, "countdown":10})
def send_email_task(recipient: str, subject: str, body: str, html: str = None):
    import uuid, time
    trace_id = str(uuid.uuid4())[:8]
    start = time.time()
    logger.info(f"[EmailTask] trace={trace_id} dispatch recipient={recipient} subject='{subject}'")
    try:
        email_utils.send_email(recipient, subject, body, html)
        dur = int((time.time() - start) * 1000)
        logger.info(f"[EmailTask] trace={trace_id} success ms={dur}")
    except Exception as e:
        dur = int((time.time() - start) * 1000)
        logger.warning(f"[EmailTask] trace={trace_id} failure ms={dur} error={e}")
        raise


@shared_task(name="send_otp_email_task", autoretry_for=(email_utils.EmailSendError,), retry_kwargs={"max_retries":3, "countdown":5})
def send_otp_email_task(to_email: str, otp_code: str):
    email_utils.send_otp_email(to_email, otp_code)


# --- Task Reminder OTP ---
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_task_otp_task(self, task_id: str, user_email: str, title: str, otp: str = None, due_iso: str = None):
    """
    Complete Celery job: send_task_otp_task with logging + OTP + auto-complete as specified.
    """
    import random
    from app.utils.email_utils import send_html_email
    from app.database import db_client
    from app.services.redis_service import get_client as get_redis_client
    
    # 1) defensive fetch task
    coll = db_client.get_tasks_collection()
    task = coll.find_one({"_id": ObjectId(task_id)})
    if not task:
        logger.error(f"[OTP_ERROR] Task not found {task_id}")
        return

    # Check if task already deleted or status not TODO
    if task.get("status") in ("done", "cancelled"):
        logger.info(f"[OTP_SKIP] Task {task_id} status {task['status']} - skipping email.")
        return

    # 2) generate OTP if not provided
    otp_val = otp or f"{random.randint(100000, 999999):06d}"

    # 3) store OTP in Redis for 600s
    redis_key = f"otp:task:{task_id}"
    try:
        redis_client = get_redis_client()
        if redis_client:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.run_until_complete(redis_client.setex(redis_key, 600, otp_val))
            except RuntimeError:
                # No running loop, create new one
                asyncio.run(redis_client.setex(redis_key, 600, otp_val))
    except Exception as e:
        logger.error(f"[OTP_ERROR] Redis SETEX failed for {redis_key}: {e}")
        # still try to send email (optional), but log failure

    # If scheduled as pre-wake, wait until actual due time
    try:
        due_target = None
        if due_iso:
            try:
                from datetime import datetime as _dt
                due_target = _dt.fromisoformat(due_iso.replace("Z",""))
            except Exception:
                due_target = None
        else:
            due_target = task.get("due_date") if isinstance(task.get("due_date"), datetime) else None
        if due_target:
            now = datetime.utcnow()
            remaining = (due_target - now).total_seconds()
            if remaining > 0:
                # sleep in small chunks to allow graceful shutdowns
                sl = min(remaining, 120)
                while remaining > 0:
                    time.sleep(min(1.0, remaining))
                    remaining -= 1.0
    except Exception:
        pass

    # 4) prepare email using template
    subject = f"Reminder: {title} (OTP inside)"
    from app.templates.email_templates import render_template
    html_body = render_template("task_otp_email.html", title=title, otp=otp_val, user_email=user_email)
    text_body = f"Your OTP for '{title}' is {otp_val}. Valid 10 minutes."

    # 5) send email
    try:
        ist_str = format_ist(datetime.utcnow())
        log_event("otp_sending", user_id=str(task.get("user_id")), task_id=str(task_id), email=user_email, otp_key=redis_key, time_utc=datetime.utcnow().isoformat(), time_ist=ist_str)
        send_html_email(to=[user_email], subject=subject, html=html_body, text=text_body)
        log_event("otp_dispatched", user_id=str(task.get("user_id")), task_id=str(task_id), email=user_email, redis_ttl="600s")
    except Exception as exc:
        logger.exception(f"[OTP_ERROR] sending email for task {task_id}: {exc}")
        raise self.retry(exc=exc)  # will retry with backoff

    # 6) Recurrence handling or auto-complete for one-time tasks
    try:
        recurrence_rule = task.get("recurrence_rule") or task.get("rrule")
        is_recurring = bool(task.get("is_recurring")) or bool(recurrence_rule)
    except Exception:
        recurrence_rule = None
        is_recurring = False

    if is_recurring and recurrence_rule:
        # Compute next run based on RRULE after now
        try:
            now_utc = datetime.utcnow().replace(tzinfo=None)
            # Determine reference dtstart: use task.due_date or parsed due_iso
            dtstart = None
            if due_target:
                dtstart = due_target.replace(tzinfo=None)
            else:
                due_field = task.get("due_date") if isinstance(task.get("due_date"), datetime) else None
                if due_field:
                    dtstart = due_field.replace(tzinfo=None)
            if not dtstart:
                dtstart = now_utc

            r = rrulestr(str(recurrence_rule), dtstart=dtstart)
            nxt = r.after(now_utc, inc=False)
            if nxt is None:
                # No further runs; mark as done
                coll.update_one({"_id": ObjectId(task_id)}, {"$set": {"status": "done", "completed_at": datetime.utcnow(), "updated_at": datetime.utcnow()}})
                log_event("recurring_finished", user_id=str(task.get("user_id")), task_id=str(task_id))
            else:
                # Update next_run and due_date and reschedule celery
                coll.update_one(
                    {"_id": ObjectId(task_id)},
                    {"$set": {"due_date": nxt.replace(second=0, microsecond=0), "next_run_at": nxt.replace(second=0, microsecond=0), "updated_at": datetime.utcnow()}},
                )
                # schedule next occurrence
                from app.celery_worker import send_task_otp_task as _send_task_otp_task
                eta = nxt.replace(tzinfo=None)
                _send_task_otp_task.apply_async(args=[task_id, user_email, title, None, nxt.isoformat()], eta=eta)
                log_event("recurring_rescheduled", user_id=str(task.get("user_id")), task_id=str(task_id), next_iso=nxt.isoformat())
        except Exception as exc:
            logger.exception(f"[RECURRING] failed to compute next occurrence for {task_id}: {exc}")
            # fallback: mark as done
            coll.update_one({"_id": ObjectId(task_id)}, {"$set": {"status": "done", "completed_at": datetime.utcnow(), "updated_at": datetime.utcnow()}})
    else:
        # One-time: auto-complete (respect flag) and delete
        if task.get("auto_complete_after_email", True):
            coll.update_one(
                {"_id": ObjectId(task_id)},
                {"$set": {"status": "done", "completed_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
            )
            # Update user profile embedded task if present
            try:
                prof_col = db_client.get_user_profile_collection()
                if prof_col and task.get("user_id"):
                    prof_col.update_one(
                        {"_id": str(task.get("user_id"))},
                        {"$set": {"tasks.$[t].status": "completed", "tasks.$[t].completed_at": datetime.utcnow()}},
                        array_filters=[{"t.task_id": str(task_id)}],
                        upsert=True,
                    )
            except Exception:
                pass

            # Activity log: task_completed
            try:
                act = db_client.get_activity_logs_collection()
                if act:
                    act.insert_one({
                        "type": "task_completed",
                        "task_id": str(task_id),
                        "user_id": str(task.get("user_id")),
                        "timestamp": datetime.utcnow(),
                    })
            except Exception:
                pass

            log_event("task_auto_complete", user_id=str(task.get("user_id")), task_id=str(task_id), email=user_email)

        # Remove one-time task
        try:
            coll.delete_one({"_id": ObjectId(task_id)})
        except Exception:
            pass

    # done


# --- Memory Salience Update ---
@celery_app.task(name="update_memory_salience")
def update_memory_salience():
    if not _redis_client:
        return
    try:
        mem_coll = get_memories_collection()
        cursor = 0
        counts = {}
        pattern = "user:*:memory_freq:*"
        while True:
            cursor, keys = _redis_client.scan(cursor=cursor, match=pattern, count=500)
            for k in keys:
                try:
                    val = int(_redis_client.get(k) or 0)
                    if val <= 0:
                        continue
                    parts = k.split(":")
                    if len(parts) >= 4:
                        uid = parts[1]
                        mid = parts[-1]
                        counts.setdefault(uid, {})[mid] = val
                except Exception:
                    continue
            if cursor == 0:
                break

        import math
        for uid, mem_map in counts.items():
            if not mem_map:
                continue
            max_freq = max(mem_map.values()) or 1
            bulk_ops = []
            for mid, freq in mem_map.items():
                norm = math.log(1 + freq) / math.log(1 + max_freq)
                salience = 0.8 + norm * 0.45
                try:
                    bulk_ops.append({
                        "filter": {"_id": ObjectId(mid), "user_id": uid},
                        "update": {"$set": {"salience_score": round(salience, 4), "updated_at": datetime.utcnow().isoformat()}},
                    })
                except Exception:
                    continue
            for op in bulk_ops:
                try:
                    mem_coll.update_one(op["filter"], op["update"])
                except Exception:
                    pass

        # Clear frequency counters in Redis
        for uid, mem_map in counts.items():
            for mid in mem_map:
                try:
                    _redis_client.delete(f"user:{uid}:memory_freq:{mid}")
                except Exception:
                    pass

        logger.info(f"Salience update complete for {sum(len(m) for m in counts.values())} memories across {len(counts)} users")
    except Exception as e:
        logger.exception(f"Salience update failed: {e}")


# --- Lifecycle Maintenance ---
@celery_app.task(name="memory_lifecycle_maintenance")
def lifecycle_maintenance():
    try:
        mem_coll = get_memories_collection()
        now = datetime.utcnow()
        iso_now = now.isoformat()
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        sixty_days_ago = (now - timedelta(days=60)).isoformat()
        undo_expiry = (now + timedelta(days=30)).isoformat()

        # Aging stage
        aging_candidates = mem_coll.find({
            "lifecycle_state": "active",
            "$or": [
                {"last_accessed_at": {"$lt": thirty_days_ago}},
                {"salience_score": {"$lt": 0.9}},
            ],
            "user_flags.pinned": {"$ne": True},
        }).limit(500)

        moved_aging = 0
        for doc in aging_candidates:
            try:
                mem_coll.update_one({"_id": doc["_id"]}, {"$set": {"lifecycle_state": "aging", "updated_at": iso_now, "aging_at": iso_now}})
                moved_aging += 1
            except Exception:
                continue

        # Archival stage
        aging_to_archive = mem_coll.find({
            "lifecycle_state": "aging",
            "last_accessed_at": {"$lt": sixty_days_ago},
            "salience_score": {"$lt": 0.95},
        }).limit(500)

        archived = 0
        for doc in aging_to_archive:
            try:
                mem_coll.update_one({"_id": doc["_id"]}, {"$set": {"lifecycle_state": "archived", "archived_at": iso_now, "undo_expiry_at": undo_expiry, "updated_at": iso_now}})
                archived += 1
            except Exception:
                continue

        if moved_aging or archived:
            logger.info(f"Lifecycle maintenance: moved {moved_aging} -> aging, archived {archived}")
    except Exception as e:
        logger.exception(f"Lifecycle maintenance failed: {e}")


# --- Distillation Scan ---
@celery_app.task(name="distillation_scan")
def distillation_scan(batch_limit_per_user: int = 30, max_users: int = 200):
    try:
        mem_coll = get_memories_collection()
        pipeline = [
            {"$match": {
                "lifecycle_state": {"$in": ["aging", "archived"]},
                "salience_score": {"$lte": 0.93},
                "type": {"$ne": "distilled"},
                "lineage.distilled_id": {"$exists": False},
            }},
            {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": max_users},
        ]
        user_groups = list(mem_coll.aggregate(pipeline))
        created_total = 0

        from app.services import memory_service as ms
        global_cap = getattr(settings, "DISTILLATION_SCAN_GLOBAL_CAP", 25)
        per_user_cap = getattr(settings, "DISTILLATION_SCAN_PER_USER_CAP", 2)
        group_size = getattr(settings, "DISTILLATION_GROUP_SIZE", 8)

        if global_cap <= 0 or per_user_cap <= 0:
            logger.info("Distillation scan skipped (caps disabled)")
            return

        for ug in user_groups:
            if created_total >= global_cap:
                break
            uid = ug.get("_id")
            if not uid:
                continue
            remaining_for_user = per_user_cap
            cands = asyncio.run(ms.get_distillation_candidates(uid, limit=batch_limit_per_user))
            if not cands:
                continue
            start = 0
            while start < len(cands) and remaining_for_user > 0 and created_total < global_cap:
                chunk = cands[start:start+group_size]
                start += group_size
                ids = [c.get("_id") for c in chunk if c.get("_id")]
                if not ids:
                    continue
                result = asyncio.run(ms.run_distillation_batch(uid, ids))
                if result.get("created"):
                    created_total += 1
                    remaining_for_user -= 1

        if created_total:
            logger.info(f"Distillation scan created {created_total} distilled memories (global cap {global_cap})")
    except Exception as e:
        logger.exception(f"Distillation scan failed: {e}")


# --- Re-embed Outdated Memories ---
@celery_app.task(name="reembed_outdated_memories")
def reembed_outdated_memories(batch_size: int = 300):
    try:
        target_version = settings.EMBEDDING_MODEL_VERSION
        coll = get_memories_collection()
        outdated = coll.find({"model_version": {"$ne": target_version}}, projection=["_id", "title", "value", "lifecycle_state", "user_id"], limit=batch_size)
        count = 0
        for doc in outdated:
            try:
                text = f"{doc.get('title')}: {doc.get('value','')}"
                upsert_memory_embedding(str(doc["_id"]), doc.get("user_id"), text, doc.get("lifecycle_state", "active"))
                coll.update_one({"_id": doc["_id"]}, {"$set": {"model_version": target_version, "updated_at": datetime.utcnow().isoformat()}})
                count += 1
            except Exception:
                continue
        if count:
            logger.info(f"Re-embedded {count} outdated memories -> version {target_version}")
    except Exception as e:
        logger.exception(f"Re-embed task failed: {e}")


# --- Fire-and-forget Embedding Queue ---
@celery_app.task(name="drain_embedding_queue")
def drain_embedding_queue(max_items: int = 40):
    async def _inner():
        try:
            batch = await memory_store.dequeue_embedding_batch(max_items=max_items)
            if batch:
                store_embeddings_batch.delay(batch)
        except Exception:
            logger.exception("Failed draining embedding queue")
    _fire_and_forget(_inner())


@celery_app.task(name="store_embeddings_batch")
def store_embeddings_batch(batch: list[dict]):
    try:
        pinecone_service.initialize_pinecone()
        pinecone_service.bulk_upsert(batch)
    except Exception:
        logger.exception("Failed batch embedding upsert")


# --- Extract & Store Facts ---
@celery_app.task(
    name="extract_and_store_facts",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True
)
def extract_and_store_facts_task(user_message: str, assistant_message: str, user_id: str):
    try:
        transcript = f"Human: {user_message}\nAssistant: {assistant_message}"
        neo4j_sync_service.connect()
        det = deterministic_extractor.extract(user_message, assistant_message)

        if det.get("profile_update"):
            try:
                profile_service.merge_update(user_id, **det["profile_update"])
            except Exception:
                logger.exception("Profile merge_update failed")

        # Preferences
        for pref in det.get("preferences", []) or []:
            if pref.get("type") == "hobby" and pref.get("value"):
                try:
                    neo4j_sync_service.upsert_user_preference_sync(user_id, pref["value"], "HOBBY")
                except Exception:
                    logger.debug("Failed preference upserts")

        # Friend locations
        for fl in det.get("friend_locations", []) or []:
            friend = fl.get("friend")
            city = fl.get("city")
            if friend and city:
                try:
                    neo4j_sync_service.upsert_friend_location_sync(user_id, friend, city)
                except Exception:
                    logger.debug("Failed friend location upserts")

        # Semantic facts enqueue
        semantic_facts = det.get("semantic_facts", []) or []
        if semantic_facts:
            try:
                ts = datetime.utcnow().isoformat()
                for fact in semantic_facts:
                    payload = {"user_id": user_id, "session_id": "", "text": fact, "role": "fact", "timestamp": ts, "kind": "user_fact"}
                    _fire_and_forget(memory_store.enqueue_embedding_job(payload))
            except Exception:
                logger.exception("Failed to enqueue semantic facts")

        # AI service extraction
        facts_data = ai_service.extract_facts_from_text(transcript)
        entities, relationships = [], []
        parsed = None
        if facts_data:
            if isinstance(facts_data, str):
                try:
                    parsed = json.loads(facts_data)
                except json.JSONDecodeError:
                    logger.error("AI returned invalid JSON for facts")
            elif isinstance(facts_data, dict):
                parsed = facts_data
            if parsed:
                entities = parsed.get("entities", []) if isinstance(parsed.get("entities"), list) else []
                relationships = parsed.get("relationships", []) if isinstance(parsed.get("relationships"), list) else []

        valid_entities = [e for e in entities if isinstance(e, dict) and e.get("name")]
        user_node_name = f"User_{user_id}"
        valid_entities.append({"name": user_node_name, "label": "User", "id": user_id})
        person_entity = next((e for e in valid_entities if e.get("label") == "PERSON"), None)
        if person_entity:
            relationships.append({"source": user_node_name, "target": person_entity["name"], "type": "IS_NAMED"})
            try:
                neo4j_sync_service.run_query(f"MERGE (u:User {{id: '{user_id}'}})")
            except Exception:
                logger.debug("Failed to merge user node in Neo4j")
    except Exception as e:
        logger.exception(f"Fact extraction task failed: {e}")


# --- Suggestions for future improvements ---
# 1. Consider batch processing emails for high volume to reduce SMTP connections.
# 2. Use async email library like aiosmtplib if more concurrency is needed.
# 3. Monitor Celery task queue lengths to dynamically scale workers.
# 4. Add detailed metrics/logs for memory embeddings and distillation tasks.
# 5. Add proper type hints for all task arguments for better code clarity.
