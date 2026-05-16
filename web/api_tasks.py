# -*- coding: utf-8 -*-
"""
Registration Task Management REST API
Handles task creation, querying, cancellation, and OTP submission
"""
import logging
import json
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, jsonify
from web.database import TaskDB
from core.pausable_registration import RegistrationManager
from core.provider_settings import get_default_sms_provider

logger = logging.getLogger(__name__)
task_bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


def _load_persisted_logs(log_file):
    if not log_file:
        return []

    path = Path(log_file)
    if not path.exists():
        return []

    logs = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            logs.append(json.loads(line))
        except json.JSONDecodeError:
            logs.append({
                "timestamp": None,
                "level": "INFO",
                "message": line,
            })
    return logs


def _merge_runtime_task(task):
    if not task:
        return task

    runtime_task = RegistrationManager.get_instance().get_task_snapshot(task["id"])
    merged = dict(task)
    persisted_logs = _load_persisted_logs(task.get("log_file"))

    if not runtime_task:
        merged["current_step"] = 0
        merged["step_status"] = {}
        merged["waiting_for"] = None
        merged["logs"] = persisted_logs
        return merged

    runtime_logs = runtime_task.get("logs", [])

    merged.update({
        "current_step": runtime_task.get("current_step", 0),
        "step_status": runtime_task.get("step_status", {}),
        "waiting_for": runtime_task.get("waiting_for"),
        "waiting_context": runtime_task.get("waiting_context"),
        "registration_mode": runtime_task.get("registration_mode", merged.get("registration_mode")),
        "phone_country": runtime_task.get("phone_country", merged.get("phone_country")),
        "sms_service_code": runtime_task.get("sms_service_code", merged.get("sms_service_code")),
        "sms_operator": runtime_task.get("sms_operator", merged.get("sms_operator")),
        "sms_provider": runtime_task.get("sms_provider", merged.get("sms_provider")),
        "sms_activation_id": runtime_task.get("sms_activation_id", merged.get("sms_activation_id")),
        "phone_number": runtime_task.get("phone_number", merged.get("phone_number")),
        "sms_last_status": runtime_task.get("sms_last_status"),
        "sms_code": runtime_task.get("sms_code"),
        "logs": runtime_logs or persisted_logs,
    })

    runtime_status = runtime_task.get("status")
    if runtime_status:
        merged["status"] = runtime_status

    if runtime_task.get("started_at"):
        merged["started_at"] = runtime_task["started_at"]

    if runtime_task.get("completed_at"):
        merged["completed_at"] = runtime_task["completed_at"]

    return merged

@task_bp.route("/create", methods=["POST"])
def create_task():
    try:
        data = request.get_json() or {}
        registration_mode = (data.get("registration_mode") or "email").strip().lower()
        email = (data.get("email") or "").strip()
        name = data.get("name")
        birthday = data.get("birthday", "2000-01-01")
        proxy = data.get("proxy")
        phone_country = data.get("phone_country")
        sms_service_code = data.get("sms_service_code")
        sms_operator = data.get("sms_operator")
        sms_provider = data.get("sms_provider") or get_default_sms_provider()
        sms_api_key = data.get("sms_api_key")
        sms_base_url = data.get("sms_base_url")
        sms_poll_interval = data.get("sms_poll_interval")
        sms_max_wait = data.get("sms_max_wait")
        sms_max_price = data.get("sms_max_price")
        
        if registration_mode not in {"email", "phone"}:
            return jsonify({"error": "registration_mode must be 'email' or 'phone'"}), 400

        if registration_mode == "email" and not email:
            return jsonify({"error": "Email is required"}), 400
        
        task = TaskDB.create_task(
            email=email,
            name=name,
            birthday=birthday,
            proxy=proxy,
            registration_mode=registration_mode,
            phone_country=phone_country,
            sms_service_code=sms_service_code,
            sms_operator=sms_operator,
            sms_provider=sms_provider,
        )
        RegistrationManager.get_instance().start_task(
            task["id"],
            email=email,
            name=name,
            birthday=birthday,
            proxy=proxy,
            registration_mode=registration_mode,
            phone_country=phone_country,
            sms_service_code=sms_service_code,
            sms_operator=sms_operator,
            sms_provider=sms_provider,
            sms_api_key=sms_api_key,
            sms_base_url=sms_base_url,
            sms_poll_interval=sms_poll_interval,
            sms_max_wait=sms_max_wait,
            sms_max_price=sms_max_price,
        )
        logger.info(f"Created task {task['id']} for mode={registration_mode}, email={email or '-'}")
        
        return jsonify({
            "success": True,
            "task": task,
            "message": "Task created successfully"
        }), 200
    except Exception as e:
        logger.error(f"Error creating task: {str(e)}")
        return jsonify({"error": str(e)}), 500

@task_bp.route("/<int:task_id>", methods=["GET"])
def get_task(task_id):
    try:
        task = TaskDB.get_task(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404

        task = _merge_runtime_task(task)
        return jsonify({"task": task}), 200
    except Exception as e:
        logger.error(f"Error getting task {task_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@task_bp.route("/list", methods=["GET"])
def list_tasks():
    try:
        status = request.args.get("status")
        tasks = TaskDB.list_tasks(status=status)
        tasks = [_merge_runtime_task(task) for task in tasks]

        if status:
            tasks = [task for task in tasks if task.get("status") == status]
        
        return jsonify({
            "tasks": tasks,
            "count": len(tasks)
        }), 200
    except Exception as e:
        logger.error(f"Error listing tasks: {str(e)}")
        return jsonify({"error": str(e)}), 500

@task_bp.route("/<int:task_id>/update", methods=["POST"])
def update_task(task_id):
    try:
        data = request.get_json()
        TaskDB.update_task(task_id, **data)
        
        task = TaskDB.get_task(task_id)
        logger.info(f"Updated task {task_id}: {data}")
        
        return jsonify({
            "success": True,
            "task": task,
            "message": "Task updated successfully"
        }), 200
    except Exception as e:
        logger.error(f"Error updating task {task_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@task_bp.route("/<int:task_id>/submit_otp", methods=["POST"])
def submit_otp(task_id):
    try:
        data = request.get_json() or {}
        otp_type = data.get("otp_type")  # "email" or "phone"
        otp_code = data.get("otp_code")
        phone_number = data.get("phone_number")  # for phone OTP
        
        if not otp_code:
            return jsonify({"error": "OTP code is required"}), 400
        
        from core.pausable_registration import RegistrationManager
        manager = RegistrationManager.get_instance()
        
        result = manager.submit_otp(task_id, otp_type, otp_code, phone_number)
        
        if not result.get("success"):
            return jsonify(result), 400

        return jsonify({
            "success": True,
            "message": f"{otp_type} OTP submitted successfully",
            "result": result
        }), 200
    except Exception as e:
        logger.error(f"Error submitting OTP for task {task_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@task_bp.route("/<int:task_id>/cancel", methods=["POST"])
def cancel_task(task_id):
    try:
        from core.pausable_registration import RegistrationManager
        manager = RegistrationManager.get_instance()
        
        result = manager.cancel_task(task_id)
        
        if result:
            TaskDB.update_task(task_id, status="cancelled", completed_at=datetime.now().isoformat(timespec="seconds"))
            logger.info(f"Cancelled task {task_id}")
            return jsonify({
                "success": True,
                "message": "Task cancelled successfully"
            }), 200
        else:
            return jsonify({"error": "Cannot cancel task"}), 400
    except Exception as e:
        logger.error(f"Error cancelling task {task_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500