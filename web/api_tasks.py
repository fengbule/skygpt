# -*- coding: utf-8 -*-
"""
Registration Task Management REST API
Handles task creation, querying, cancellation, and OTP submission
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from web.database import TaskDB

logger = logging.getLogger(__name__)
task_bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")

@task_bp.route("/create", methods=["POST"])
def create_task():
    try:
        data = request.get_json()
        email = data.get("email")
        name = data.get("name")
        birthday = data.get("birthday", "2000-01-01")
        proxy = data.get("proxy")
        
        if not email:
            return jsonify({"error": "Email is required"}), 400
        
        task = TaskDB.create_task(email=email, name=name, birthday=birthday, proxy=proxy)
        logger.info(f"Created task {task['id']} for email {email}")
        
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
        
        return jsonify({"task": task}), 200
    except Exception as e:
        logger.error(f"Error getting task {task_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@task_bp.route("/list", methods=["GET"])
def list_tasks():
    try:
        status = request.args.get("status")
        tasks = TaskDB.list_tasks(status=status)
        
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
        data = request.get_json()
        otp_type = data.get("otp_type")  # "email" or "phone"
        otp_code = data.get("otp_code")
        phone_number = data.get("phone_number")  # for phone OTP
        
        if not otp_code:
            return jsonify({"error": "OTP code is required"}), 400
        
        from core.pausable_registration import RegistrationManager
        manager = RegistrationManager.get_instance()
        
        result = manager.submit_otp(task_id, otp_type, otp_code, phone_number)
        
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