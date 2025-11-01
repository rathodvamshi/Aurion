from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Optional, Dict, Any
from datetime import datetime

from app.security import get_current_active_user
from app.database import get_tasks_collection
from app.services.reminder_service import parse_input, parse_input_with_intent, create_and_schedule

router = APIRouter(prefix="/api/reminders", tags=["Reminders"], dependencies=[Depends(get_current_active_user)])


@router.post("/parse")
async def parse_reminder_text(payload: Dict[str, Any] = Body(...)):
	"""Return intent, task_description and time_expression extracted from free text."""
	text = str(payload.get("text") or "").strip()
	parsed = parse_input_with_intent(text)
	return parsed


@router.post("/")
async def create_reminder(
	payload: Dict[str, Any] = Body(...),
	current_user: dict = Depends(get_current_active_user),
):
	"""Create and schedule a reminder from natural language text or explicit fields.

	Body:
	  - text: free text like "Remind me to call mom tomorrow at 8pm"
	  - description: optional explicit description
	  - time_expression: optional explicit time expression
	"""
	text = str(payload.get("text") or "").strip()
	description = (payload.get("description") or "").strip()
	time_expression = (payload.get("time_expression") or "").strip()

	if not description or not time_expression:
		parsed = parse_input_with_intent(text)
		description = description or parsed.get("task_description")
		time_expression = time_expression or parsed.get("time_expression")

	if not time_expression:
		# default policy: next day 9am IST
		time_expression = "tomorrow 9:00 am"

	if not description:
		raise HTTPException(status_code=400, detail="Please specify what to remind you about.")

	res = create_and_schedule(str(current_user.get("user_id") or current_user.get("_id")), description, time_expression)
	return res


@router.get("/")
async def list_reminders(
	limit: int = Query(50, ge=1, le=200),
	current_user: dict = Depends(get_current_active_user),
	tasks = Depends(get_tasks_collection),
):
	user_id = str(current_user.get("user_id") or current_user.get("_id"))
	now = datetime.utcnow()
	cur = tasks.find({"user_id": user_id, "status": {"$in": ["todo", "pending", "in_progress"]}}).sort("due_date", 1).limit(limit)
	out = []
	for d in cur:
		d["_id"] = str(d.get("_id"))
		out.append(d)
	return out


@router.get("/{task_id}")
async def get_reminder(task_id: str, current_user: dict = Depends(get_current_active_user), tasks = Depends(get_tasks_collection)):
	user_id = str(current_user.get("user_id") or current_user.get("_id"))
	doc = tasks.find_one({"_id": task_id, "user_id": user_id}) or tasks.find_one({"_id": task_id})
	if not doc:
		raise HTTPException(status_code=404, detail="Reminder not found")
	doc["_id"] = str(doc.get("_id"))
	return doc


@router.patch("/{task_id}/cancel")
async def cancel_reminder(task_id: str, current_user: dict = Depends(get_current_active_user), tasks = Depends(get_tasks_collection)):
	user_id = str(current_user.get("user_id") or current_user.get("_id"))
	doc = tasks.find_one({"_id": task_id, "user_id": user_id})
	if not doc:
		raise HTTPException(status_code=404, detail="Reminder not found")
	celery_id = doc.get("celery_task_id")
	if celery_id:
		try:
			from app.celery_app import celery_app
			celery_app.control.revoke(celery_id, terminate=False)
		except Exception:
			pass
	tasks.update_one({"_id": doc["_id"]}, {"$set": {"status": "cancelled", "updated_at": datetime.utcnow()}})
	return {"ok": True, "task_id": task_id, "status": "cancelled"}

