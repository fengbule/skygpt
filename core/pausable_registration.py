# -*- coding: utf-8 -*-
"""
Pausable Registration Module with Step Tracking
Supports real-time progress visualization and user input waiting
"""
import logging
import threading
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List
from concurrent.futures import ThreadPoolExecutor
import random
import string

from web.database import TaskDB
from core.cpa_generator import generate_cpa_file
from core.registration_steps import REGISTRATION_STEPS, get_step_by_id, get_total_steps
from core.session import BrowserSession
from core.chatgpt_auth import get_providers, get_csrf_token, signin_openai
from core.openai_auth import follow_authorize, request_sentinel_token, build_sentinel_header, validate_email_otp, create_account
from core.account_export import follow_oauth_callback, fetch_session

logger = logging.getLogger(__name__)

class PausableRegistration:
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self):
        self.tasks: Dict[int, Dict] = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.socketio = None
        self.task_logs: Dict[int, List[str]] = {}
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def set_socketio(self, socketio):
        self.socketio = socketio
    
    def start_task(self, task_id: int, email: str, name: str = None, birthday: str = "2000-01-01", proxy: str = None):
        db_task = TaskDB.get_task(task_id) or {}
        task_data = {
            "task_id": task_id,
            "email": email,
            "name": name or self._generate_display_name(),
            "birthday": birthday,
            "proxy": proxy,
            "log_file": db_task.get("log_file"),
            "status": "pending",
            "current_step": 0,
            "step_status": {},
            "waiting_for": None,
            "otp_data": {},
            "logs": [],
            "started_at": None,
            "completed_at": None,
            "session": None
        }
        
        for step in REGISTRATION_STEPS:
            task_data["step_status"][step["id"]] = "pending"
        
        self.tasks[task_id] = task_data
        self.task_logs[task_id] = []
        
        self.executor.submit(self._run_registration_task, task_id)
        
        self._emit_task_update(task_id, "task_started", {
            "message": f"任务已启动：{email}",
            "total_steps": get_total_steps()
        })
        
        logger.info(f"[Task {task_id}] Started for {email}")
    
    def _generate_display_name(self):
        first = random.choice(string.ascii_uppercase) + "".join(random.choices(string.ascii_lowercase, k=random.randint(3, 6)))
        last = random.choice(string.ascii_uppercase) + "".join(random.choices(string.ascii_lowercase, k=random.randint(3, 6)))
        return f"{first} {last}"
    
    def _add_log(self, task_id: int, message: str, level: str = "INFO"):
        task_data = self.tasks.get(task_id)
        if task_data:
            log_entry = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "level": level,
                "message": message
            }
            task_data["logs"].append(log_entry)
            
            if task_id in self.task_logs:
                self.task_logs[task_id].append(f"[{level}] {message}")

            log_file = task_data.get("log_file")
            if log_file:
                try:
                    log_path = Path(log_file)
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with log_path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                except Exception:
                    logger.debug(f"[Task {task_id}] 写入日志文件失败", exc_info=True)
            
            self._emit_task_update(task_id, "log_update", {"log": log_entry})
    
    def _update_step(self, task_id: int, step_id: int, status: str, message: str = None):
        task_data = self.tasks.get(task_id)
        if task_data:
            task_data["step_status"][step_id] = status
            task_data["current_step"] = step_id
            
            step_info = get_step_by_id(step_id)
            step_name = step_info["name"] if step_info else f"Step {step_id}"
            
            log_message = f"[步骤 {step_id}/{get_total_steps()}] {step_name}: {status}"
            if message:
                log_message += f" - {message}"
            
            self._add_log(task_id, log_message)
            
            self._emit_task_update(task_id, "step_update", {
                "step_id": step_id,
                "step_name": step_name,
                "status": status,
                "progress": step_id / get_total_steps() * 100,
                "message": message
            })
    
    def _emit_task_update(self, task_id: int, event_type: str, data: Dict):
        if self.socketio:
            self.socketio.emit(event_type, {
                "task_id": task_id,
                **data,
                "timestamp": datetime.now().isoformat(timespec="seconds")
            })
    
    def _wait_for_user_input(self, task_id: int, input_type: str, timeout: int = 600):
        task_data = self.tasks.get(task_id)
        if not task_data:
            return None
        
        task_data["status"] = "waiting_for_input"
        task_data["waiting_for"] = input_type
        TaskDB.update_task(task_id, status="waiting_for_input")
        
        self._emit_task_update(task_id, "waiting_for_input", {
            "input_type": input_type,
            "message": f"等待用户输入 {input_type}（超时时间：{timeout}秒）"
        })
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if task_data["status"] == "cancelled":
                return None
            
            otp_data = task_data["otp_data"].get(input_type)
            if otp_data:
                task_data["status"] = "running"
                task_data["waiting_for"] = None
                TaskDB.update_task(task_id, status="running")
                return otp_data
            
            time.sleep(0.5)
        
        task_data["status"] = "timeout"
        self._add_log(task_id, f"等待 {input_type} 超时", "ERROR")
        return None
    
    def _run_registration_task(self, task_id: int):
        task_data = self.tasks.get(task_id)
        if not task_data:
            return
        
        try:
            TaskDB.update_task(task_id, status="running", started_at=datetime.now().isoformat(timespec="seconds"))
            task_data["status"] = "running"
            task_data["started_at"] = datetime.now().isoformat(timespec="seconds")
            
            email = task_data["email"]
            name = task_data["name"]
            birthday = task_data["birthday"]
            proxy = task_data["proxy"]
            
            self._add_log(task_id, f"开始注册流程：邮箱={email}, 名称={name}")
            
            session = BrowserSession(proxy=proxy)
            task_data["session"] = session
            
            self._update_step(task_id, 1, "running", "正在获取认证提供商...")
            providers = get_providers(session)
            self._update_step(task_id, 1, "completed", "获取成功")
            time.sleep(0.5)
            
            self._update_step(task_id, 2, "running", "正在获取 CSRF Token...")
            csrf_token = get_csrf_token(session)
            self._update_step(task_id, 2, "completed", "获取成功")
            time.sleep(0.5)
            
            self._update_step(task_id, 3, "running", "正在发起 OAuth signin...")
            authorize_url = signin_openai(session, csrf_token, email)
            self._update_step(task_id, 3, "completed", "发起成功")
            time.sleep(0.5)
            
            self._update_step(task_id, 4, "running", "正在跟随 authorize URL...")
            follow_authorize(session, authorize_url)
            self._update_step(task_id, 4, "completed", "建立 cookies 成功")
            time.sleep(2)
            
            self._update_step(task_id, 5, "waiting", "等待用户输入邮箱验证码...")
            otp_input = self._wait_for_user_input(task_id, "email_otp")
            
            if not otp_input:
                self._fail_task(task_id, "未收到邮箱验证码或超时")
                return
            
            otp_code = otp_input.get("otp_code")
            
            self._update_step(task_id, 6, "running", "正在获取 Sentinel Token...")
            sentinel_resp = request_sentinel_token(session, "authorize_continue")
            sentinel_header, _ = build_sentinel_header(session, sentinel_resp, "authorize_continue")
            self._update_step(task_id, 6, "completed", "获取成功")
            time.sleep(0.3)
            
            self._update_step(task_id, 7, "running", "正在提交邮箱验证码...")
            validate_result = validate_email_otp(session, otp_code, sentinel_header)
            self._update_step(task_id, 7, "completed", "验证成功")
            time.sleep(0.5)
            
            self._update_step(task_id, 9, "running", "正在获取 OAuth Sentinel Token...")
            sentinel_resp_oauth = request_sentinel_token(session, "oauth_create_account")
            sentinel_header_oauth, so_header_oauth = build_sentinel_header(session, sentinel_resp_oauth, "oauth_create_account")
            self._update_step(task_id, 9, "completed", "获取成功")
            time.sleep(0.3)
            
            self._update_step(task_id, 10, "running", "正在创建账号...")
            create_result = create_account(session, name, birthday, sentinel_header_oauth, so_header_oauth)
            self._update_step(task_id, 10, "completed", "账号创建成功")
            time.sleep(1)
            
            continue_url = create_result.get("continue_url")
            if not continue_url:
                self._fail_task(task_id, "缺少 continue_url")
                return
            
            self._update_step(task_id, 11, "running", "正在完成 OAuth 回调...")
            follow_oauth_callback(session, continue_url)
            time.sleep(1)
            session_info = fetch_session(session)
            access_token = session_info.get("accessToken")
            
            if not access_token:
                self._fail_task(task_id, "未获取到 accessToken")
                return
            
            self._update_step(task_id, 11, "completed", f"获取 Token 成功")
            
            self._update_step(task_id, 12, "running", "正在生成 CPA 文件...")
            account_id = session_info.get("user", {}).get("id", "")
            
            account_data = {
                "access_token": access_token,
                "account_id": account_id,
                "email": email
            }
            
            cpa_data = generate_cpa_file(account_data, email)
            self._update_step(task_id, 12, "completed", f"CPA 文件已生成")
            
            self._complete_task(task_id, email, account_id, access_token, cpa_data)
        
        except Exception as e:
            error_msg = str(e)[:500]
            self._add_log(task_id, f"异常错误: {error_msg}", "ERROR")
            self._fail_task(task_id, error_msg)
    
    def _complete_task(self, task_id: int, email: str, account_id: str, access_token: str, cpa_data: Dict):
        task_data = self.tasks.get(task_id)
        if task_data:
            task_data["status"] = "success"
            task_data["waiting_for"] = None
            task_data["completed_at"] = datetime.now().isoformat(timespec="seconds")
            
            TaskDB.update_task(
                task_id,
                status="success",
                account_id=account_id,
                access_token=access_token,
                completed_at=datetime.now().isoformat(timespec="seconds")
            )
            
            from web.database import AccountDB
            AccountDB.save_account(email, {
                "account_id": account_id,
                "access_token": access_token,
                "refresh_token": cpa_data.get("refresh_token", ""),
                "id_token": cpa_data.get("id_token", ""),
                "cpa_file": cpa_data.get("cpa_file", ""),
                "expired": cpa_data.get("expired", "")
            })
            
            self._add_log(task_id, f"注册成功！账号 ID: {account_id}", "SUCCESS")
            
            self._emit_task_update(task_id, "task_completed", {
                "email": email,
                "account_id": account_id,
                "cpa_file": cpa_data.get("cpa_file"),
                "message": "注册流程完成"
            })
            
            logger.info(f"[Task {task_id}] Completed successfully")
    
    def _fail_task(self, task_id: int, error: str):
        task_data = self.tasks.get(task_id)
        if task_data:
            task_data["status"] = "failed"
            task_data["waiting_for"] = None
            task_data["completed_at"] = datetime.now().isoformat(timespec="seconds")
            
            TaskDB.update_task(task_id, status="failed", error=error, completed_at=datetime.now().isoformat(timespec="seconds"))
            
            self._emit_task_update(task_id, "task_failed", {
                "error": error,
                "message": "注册失败"
            })
            
            logger.error(f"[Task {task_id}] Failed: {error}")
    
    def submit_otp(self, task_id: int, otp_type: str, otp_code: str, phone_number: str = None) -> Dict:
        task_data = self.tasks.get(task_id)
        if not task_data:
            return {"success": False, "error": "任务不存在"}
        
        if task_data["status"] != "waiting_for_input":
            return {"success": False, "error": "任务当前不需要输入"}
        
        if task_data["waiting_for"] != otp_type:
            return {"success": False, "error": f"任务等待的是 {task_data['waiting_for']}，而不是 {otp_type}"}
        
        task_data["otp_data"][otp_type] = {
            "otp_code": otp_code,
            "phone_number": phone_number
        }
        
        self._add_log(task_id, f"用户提交了 {otp_type}: {otp_code}")
        
        return {"success": True, "message": f"{otp_type} 已提交"}
    
    def cancel_task(self, task_id: int) -> bool:
        task_data = self.tasks.get(task_id)
        if not task_data:
            return False
        
        if task_data["status"] in ["success", "failed", "cancelled"]:
            return False
        
        task_data["status"] = "cancelled"
        task_data["completed_at"] = datetime.now().isoformat(timespec="seconds")
        
        TaskDB.update_task(task_id, status="cancelled", completed_at=datetime.now().isoformat(timespec="seconds"))
        
        self._add_log(task_id, "用户取消了任务", "WARNING")
        
        self._emit_task_update(task_id, "task_cancelled", {
            "message": "任务已取消"
        })
        
        logger.info(f"[Task {task_id}] Cancelled by user")
        
        return True
    
    def get_task_status(self, task_id: int) -> Optional[Dict]:
        return self.get_task_snapshot(task_id)

    def get_task_snapshot(self, task_id: int) -> Optional[Dict]:
        task_data = self.tasks.get(task_id)
        if not task_data:
            return None

        return {
            "task_id": task_data["task_id"],
            "email": task_data.get("email"),
            "name": task_data.get("name"),
            "birthday": task_data.get("birthday"),
            "proxy": task_data.get("proxy"),
            "status": task_data.get("status"),
            "current_step": task_data.get("current_step", 0),
            "step_status": dict(task_data.get("step_status", {})),
            "waiting_for": task_data.get("waiting_for"),
            "started_at": task_data.get("started_at"),
            "completed_at": task_data.get("completed_at"),
            "logs": list(task_data.get("logs", [])),
        }

    def list_task_snapshots(self) -> Dict[int, Dict]:
        return {
            task_id: self.get_task_snapshot(task_id)
            for task_id in self.tasks.keys()
        }
    
    def get_task_logs(self, task_id: int) -> List[str]:
        return self.task_logs.get(task_id, [])

class RegistrationManager:
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = PausableRegistration()
        return cls._instance