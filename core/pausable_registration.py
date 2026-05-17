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
from typing import Dict, Optional, List, Any
from concurrent.futures import ThreadPoolExecutor
import random
import string

from web.database import TaskDB
from core.cpa_generator import generate_cpa_file
from core.chatgpt_browser_flow import (
    SkyGPTPhoneCallback,
    generate_openai_compatible_password,
    normalize_browser_result,
    run_chatgpt_phone_browser_registration,
)
from core.registration_steps import REGISTRATION_STEPS, get_step_by_id, get_total_steps
from core.session import BrowserSession
from core.chatgpt_auth import get_providers, get_csrf_token, signin_openai
from core.openai_auth import follow_authorize, request_sentinel_token, build_sentinel_header, validate_email_otp, create_account
from core.account_export import follow_oauth_callback, fetch_session, extract_account_id_from_tokens
from core.codex_oauth import (
    acquire_codex_tokens,
    validate_codex_token_set,
    prepare_codex_oauth_request,
    exchange_codex_callback_url,
)
from core.sms_provider import (
    acquire_phone_number as sms_acquire_phone_number,
    wait_for_sms_code as sms_wait_for_sms_code,
    finish_activation as sms_finish_activation,
    cancel_activation as sms_cancel_activation,
    SMSProviderError,
    SMSProviderTimeout,
    SMSProviderCancelled,
)

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
    
    def start_task(
        self,
        task_id: int,
        email: str,
        name: str = None,
        birthday: str = "2000-01-01",
        proxy: str = None,
        registration_mode: str = "email",
        phone_country: str = None,
        sms_service_code: str = None,
        sms_operator: str = None,
        sms_provider: str = None,
        sms_api_key: str = None,
        sms_base_url: str = None,
        sms_poll_interval: int = None,
        sms_max_wait: int = None,
        sms_max_price: float = None,
    ):
        db_task = TaskDB.get_task(task_id) or {}
        registration_mode = (registration_mode or db_task.get("registration_mode") or "email").strip().lower()
        task_data = {
            "task_id": task_id,
            "email": email,
            "name": name or self._generate_display_name(),
            "birthday": birthday,
            "proxy": proxy,
            "registration_mode": registration_mode,
            "phone_country": phone_country or db_task.get("phone_country"),
            "sms_service_code": sms_service_code or db_task.get("sms_service_code"),
            "sms_operator": sms_operator or db_task.get("sms_operator"),
            "sms_provider": sms_provider or db_task.get("sms_provider") or "hero_sms",
            "sms_api_key": sms_api_key,
            "sms_base_url": sms_base_url,
            "sms_poll_interval": sms_poll_interval,
            "sms_max_wait": sms_max_wait,
            "sms_max_price": sms_max_price,
            "sms_activation_id": db_task.get("sms_activation_id"),
            "phone_number": db_task.get("phone_number"),
            "sms_last_status": None,
            "sms_code": None,
            "sms_activation_closed": False,
            "log_file": db_task.get("log_file"),
            "status": "pending",
            "current_step": 0,
            "step_status": {},
            "waiting_for": None,
            "waiting_context": None,
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
            "message": f"任务已启动：{email or phone_country or f'task-{task_id}'}",
            "total_steps": get_total_steps()
        })
        
        logger.info(f"[Task {task_id}] Started for mode={registration_mode}, email={email}")
    
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

    def _build_sms_settings(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "provider": task_data.get("sms_provider") or "hero_sms",
            "api_key": task_data.get("sms_api_key"),
            "base_url": task_data.get("sms_base_url"),
            "default_country": task_data.get("phone_country"),
            "default_service": task_data.get("sms_service_code"),
            "operator": task_data.get("sms_operator"),
            "poll_interval": task_data.get("sms_poll_interval"),
            "max_wait": task_data.get("sms_max_wait"),
            "max_price": task_data.get("sms_max_price"),
        }

    def _close_sms_activation(self, task_id: int, finish: bool = False) -> None:
        task_data = self.tasks.get(task_id)
        if not task_data:
            return

        activation_id = task_data.get("sms_activation_id")
        if not activation_id or task_data.get("sms_activation_closed"):
            return

        try:
            settings = self._build_sms_settings(task_data)
            if finish:
                result = sms_finish_activation(activation_id, provider=task_data.get("sms_provider"), settings=settings)
                self._add_log(task_id, f"短信激活已完成: {result.get('status') or result.get('raw')}")
            else:
                result = sms_cancel_activation(activation_id, provider=task_data.get("sms_provider"), settings=settings)
                self._add_log(task_id, f"短信激活已取消: {result.get('status') or result.get('raw')}", "WARNING")
            task_data["sms_activation_closed"] = True
            task_data["sms_last_status"] = result.get("status") or task_data.get("sms_last_status")
        except Exception as exc:
            self._add_log(task_id, f"短信激活收尾失败: {exc}", "WARNING")

    def _complete_phone_framework_task(self, task_id: int, summary: str):
        task_data = self.tasks.get(task_id)
        if task_data:
            task_data["status"] = "success"
            task_data["waiting_for"] = None
            task_data["waiting_context"] = None
            task_data["completed_at"] = datetime.now().isoformat(timespec="seconds")

            TaskDB.update_task(
                task_id,
                status="success",
                completed_at=task_data["completed_at"],
                sms_activation_id=task_data.get("sms_activation_id"),
                phone_number=task_data.get("phone_number"),
                sms_provider=task_data.get("sms_provider"),
            )

            self._add_log(task_id, summary, "SUCCESS")
            self._emit_task_update(task_id, "task_completed", {
                "email": task_data.get("email") or task_data.get("phone_number") or f"task-{task_id}",
                "account_id": None,
                "phone_number": task_data.get("phone_number"),
                "registration_mode": task_data.get("registration_mode"),
                "message": summary,
            })

            logger.info(f"[Task {task_id}] Phone framework completed")

    def _wait_for_email_otp_callback(self, task_id: int):
        self._update_step(task_id, 5, "waiting", "等待用户输入邮箱验证码...")
        otp_input = self._wait_for_user_input(task_id, "email_otp")
        if not otp_input:
            return None
        return str(otp_input.get("otp_code") or "").strip() or None

    def _run_phone_browser_task(self, task_id: int):
        task_data = self.tasks.get(task_id)
        if not task_data:
            return

        settings = self._build_sms_settings(task_data)
        provider_name = task_data.get("sms_provider") or "hero_sms"
        phone_country = task_data.get("phone_country")
        sms_service_code = task_data.get("sms_service_code")
        headless = True
        browser_type = str(task_data.get("browser_type") or "chromium").strip().lower()
        registration_password = generate_openai_compatible_password()

        self._add_log(
            task_id,
            f"开始 ChatGPT 浏览器手机号注册：provider={provider_name}, country={phone_country}, service={sms_service_code}, browser={browser_type}",
        )

        self._update_step(task_id, 1, "running", "正在初始化浏览器手机号注册流程...")
        self._update_step(task_id, 1, "completed", "浏览器手机号注册流程初始化完成")

        phone_callback = SkyGPTPhoneCallback(
            provider=provider_name,
            settings=settings,
            task_data=task_data,
            on_log=lambda message, level="INFO": self._add_log(task_id, message, level),
            on_waiting=lambda input_type, context=None: self._set_auto_waiting_state(task_id, input_type, context),
            poll_interval=task_data.get("sms_poll_interval"),
            max_wait=task_data.get("sms_max_wait"),
        )

        try:
            self._update_step(task_id, 2, "running", "正在启动真实浏览器并执行手机号注册...")
            raw_result = run_chatgpt_phone_browser_registration(
                email=task_data.get("email") or "",
                password=registration_password,
                proxy=task_data.get("proxy"),
                headless=headless,
                browser_type=browser_type,
                otp_callback=lambda: self._wait_for_email_otp_callback(task_id),
                phone_callback=phone_callback,
                log_fn=lambda message: self._add_log(task_id, message),
            )
            self._update_step(task_id, 2, "completed", "浏览器手机号注册流程执行完成")
        finally:
            phone_callback.cleanup()

        result = normalize_browser_result(raw_result)
        task_data["phone_number"] = task_data.get("phone_number") or phone_callback.task_data.get("phone_number")
        task_data["sms_activation_id"] = task_data.get("sms_activation_id") or phone_callback.task_data.get("sms_activation_id")

        self._update_step(task_id, 9, "running", "正在整理浏览器注册结果...")
        account_id = result.get("account_id")
        access_token = result.get("access_token")
        account_data = {
            "access_token": access_token,
            "account_id": account_id,
            "refresh_token": result.get("refresh_token", ""),
            "id_token": result.get("id_token", ""),
            "email": result.get("email") or task_data.get("email") or "",
            "password": result.get("password") or registration_password,
        }
        cpa_data = generate_cpa_file(account_data, task_data.get("email") or result.get("email") or "")
        self._update_step(task_id, 9, "completed", "浏览器注册结果整理完成")

        self._update_step(task_id, 10, "completed", "手机号验证已自动完成")
        self._update_step(task_id, 11, "completed", "OAuth / Token 获取完成")
        self._update_step(task_id, 12, "completed", "CPA 文件已生成")

        self._complete_task(
            task_id,
            task_data.get("email") or result.get("email") or "",
            account_id,
            access_token,
            cpa_data,
        )

    def _set_auto_waiting_state(self, task_id: int, input_type: str, context: Dict | None = None):
        task_data = self.tasks.get(task_id)
        if not task_data:
            return
        task_data["status"] = "running"
        task_data["waiting_for"] = input_type
        task_data["waiting_context"] = context or None
        self._emit_task_update(task_id, "waiting_for_input", {
            "input_type": input_type,
            "message": f"{input_type} 阶段处理中",
            "context": task_data["waiting_context"],
        })

    def _run_phone_framework_task(self, task_id: int):
        task_data = self.tasks.get(task_id)
        if not task_data:
            return

        settings = self._build_sms_settings(task_data)
        provider_name = task_data.get("sms_provider") or "hero_sms"
        phone_country = task_data.get("phone_country")
        sms_service_code = task_data.get("sms_service_code")
        sms_operator = task_data.get("sms_operator")

        self._add_log(
            task_id,
            f"开始手机号接码框架：provider={provider_name}, country={phone_country}, service={sms_service_code}",
        )

        self._update_step(task_id, 1, "running", f"正在初始化短信提供者 {provider_name}...")
        self._update_step(task_id, 1, "completed", "短信提供者初始化完成")

        self._update_step(task_id, 2, "running", "正在申请手机号...")
        activation = sms_acquire_phone_number(
            provider=task_data.get("sms_provider"),
            settings=settings,
            country=phone_country,
            service=sms_service_code,
            operator=sms_operator,
            max_price=task_data.get("sms_max_price"),
        )
        task_data["sms_activation_id"] = activation.get("activation_id")
        task_data["phone_number"] = activation.get("phone_number")
        task_data["sms_last_status"] = activation.get("status")
        TaskDB.update_task(
            task_id,
            sms_activation_id=task_data["sms_activation_id"],
            phone_number=task_data["phone_number"],
            sms_provider=task_data.get("sms_provider"),
        )
        self._update_step(task_id, 2, "completed", f"已获取号码 {task_data['phone_number']}")
        self._add_log(
            task_id,
            f"{provider_name} 激活成功：activation_id={task_data['sms_activation_id']}, phone={task_data['phone_number']}",
        )

        for step_id in (3, 4, 5, 6, 7):
            task_data["step_status"][step_id] = "completed"

        task_data["waiting_context"] = {
            "mode": "phone_framework",
            "provider": task_data.get("sms_provider"),
            "phone_number": task_data.get("phone_number"),
            "activation_id": task_data.get("sms_activation_id"),
            "service": sms_service_code,
            "country": phone_country,
            "note": "当前阶段仅轮询短信验证码，不会提交到 OpenAI 手机验证接口。",
        }

        self._update_step(task_id, 8, "running", "正在轮询短信验证码（仅框架，不提交 OpenAI）...")
        code_result = sms_wait_for_sms_code(
            task_data["sms_activation_id"],
            provider=task_data.get("sms_provider"),
            settings=settings,
            poll_interval=task_data.get("sms_poll_interval"),
            max_wait=task_data.get("sms_max_wait"),
        )
        task_data["sms_last_status"] = code_result.get("status")
        task_data["sms_code"] = code_result.get("code")
        self._update_step(task_id, 8, "completed", f"已收到验证码 {task_data['sms_code']}")
        self._add_log(task_id, f"{provider_name} 收到验证码：{task_data['sms_code']}", "SUCCESS")

        for step_id in (9, 10, 11):
            task_data["step_status"][step_id] = "completed"

        self._update_step(task_id, 12, "running", "正在完成号码状态机收尾...")
        self._close_sms_activation(task_id, finish=True)
        self._update_step(task_id, 12, "completed", "号码状态机收尾完成，等待后续接 OpenAI 手机验证")
        self._complete_phone_framework_task(task_id, "手机号接码框架完成，验证码已获取并记录，尚未提交 OpenAI 手机验证")
    
    def _wait_for_user_input(self, task_id: int, input_type: str, timeout: int = 600, context: Dict | None = None):
        task_data = self.tasks.get(task_id)
        if not task_data:
            return None
        
        task_data["status"] = "waiting_for_input"
        task_data["waiting_for"] = input_type
        task_data["waiting_context"] = context or None
        TaskDB.update_task(task_id, status="waiting_for_input")
        
        self._emit_task_update(task_id, "waiting_for_input", {
            "input_type": input_type,
            "message": f"等待用户输入 {input_type}（超时时间：{timeout}秒）",
            "context": task_data["waiting_context"],
        })
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if task_data["status"] == "cancelled":
                return None
            
            otp_data = task_data["otp_data"].get(input_type)
            if otp_data:
                task_data["status"] = "running"
                task_data["waiting_for"] = None
                task_data["waiting_context"] = None
                TaskDB.update_task(task_id, status="running")
                return otp_data
            
            time.sleep(0.5)
        
        task_data["status"] = "timeout"
        task_data["waiting_context"] = None
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
            TaskDB.update_task(
                task_id,
                registration_mode=task_data.get("registration_mode"),
                phone_country=task_data.get("phone_country"),
                sms_service_code=task_data.get("sms_service_code"),
                sms_operator=task_data.get("sms_operator"),
                sms_provider=task_data.get("sms_provider"),
            )

            if task_data.get("registration_mode") == "phone":
                self._run_phone_browser_task(task_id)
                return
            
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
            
            self._update_step(task_id, 12, "running", "正在获取 Codex OAuth 凭据并生成 CPA 文件...")
            codex_tokens = None
            try:
                codex_tokens = acquire_codex_tokens(session, session_info=session_info)
                is_valid_codex, codex_reason = validate_codex_token_set(codex_tokens)
                self._add_log(
                    task_id,
                    f"Codex OAuth 结果校验: valid={is_valid_codex}, reason={codex_reason}, "
                    f"has_refresh={bool(codex_tokens.get('refresh_token'))}, has_id={bool(codex_tokens.get('id_token'))}",
                )
            except Exception as codex_exc:
                self._add_log(task_id, f"Codex OAuth 自动获取失败: {codex_exc}", "WARNING")
                manual_request = prepare_codex_oauth_request()
                manual_context = {
                    "auth_url": manual_request["authorization_url"],
                    "redirect_uri": manual_request["redirect_uri"],
                    "instructions": "请在浏览器打开授权链接，完成登录/授权后，把跳转到 localhost:1455 的完整回调 URL 粘贴回来。",
                }
                self._update_step(task_id, 12, "waiting", "等待手动完成 Codex OAuth 授权回调...")
                self._add_log(task_id, f"Codex 手动授权链接: {manual_request['authorization_url']}")
                callback_input = self._wait_for_user_input(
                    task_id,
                    "codex_callback_url",
                    timeout=1800,
                    context=manual_context,
                )
                if not callback_input:
                    self._fail_task(task_id, "未收到 Codex OAuth 回调 URL 或等待超时")
                    return
                callback_url = callback_input.get("otp_code")
                self._add_log(task_id, "收到 Codex 回调 URL，正在交换 token...")
                codex_tokens = exchange_codex_callback_url(
                    callback_url,
                    manual_request["code_verifier"],
                    manual_request["state"],
                    session_info=session_info,
                )
                is_valid_codex, codex_reason = validate_codex_token_set(codex_tokens)
                self._add_log(
                    task_id,
                    f"Codex 手动回调结果校验: valid={is_valid_codex}, reason={codex_reason}, "
                    f"has_refresh={bool(codex_tokens.get('refresh_token'))}, has_id={bool(codex_tokens.get('id_token'))}",
                )

            codex_access_token = codex_tokens.get("access_token") or access_token
            account_id = extract_account_id_from_tokens(
                codex_access_token,
                codex_tokens.get("id_token"),
                session_info=session_info,
            )
            self._add_log(
                task_id,
                f"Codex / CPA 候选 account_id={account_id}, using_client_token={'codex' if codex_tokens.get('access_token') else 'web'}",
            )
            
            account_data = {
                "access_token": codex_access_token,
                "account_id": account_id,
                "refresh_token": codex_tokens.get("refresh_token", ""),
                "id_token": codex_tokens.get("id_token", ""),
                "email": email
            }
            
            cpa_data = generate_cpa_file(account_data, email)
            self._update_step(task_id, 12, "completed", f"CPA 文件已生成")
            
            self._complete_task(task_id, email, account_id, codex_access_token, cpa_data)
        
        except (SMSProviderTimeout, SMSProviderCancelled, SMSProviderError) as sms_exc:
            self._add_log(task_id, f"短信流程异常: {sms_exc}", "ERROR")
            self._close_sms_activation(task_id, finish=False)
            self._fail_task(task_id, str(sms_exc))
        except Exception as e:
            error_msg = str(e)[:500]
            self._add_log(task_id, f"异常错误: {error_msg}", "ERROR")
            self._close_sms_activation(task_id, finish=False)
            self._fail_task(task_id, error_msg)
    
    def _complete_task(self, task_id: int, email: str, account_id: str, access_token: str, cpa_data: Dict):
        task_data = self.tasks.get(task_id)
        if task_data:
            task_data["status"] = "success"
            task_data["waiting_for"] = None
            task_data["waiting_context"] = None
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
            task_data["waiting_context"] = None
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
        task_data["waiting_context"] = None
        task_data["completed_at"] = datetime.now().isoformat(timespec="seconds")
        self._close_sms_activation(task_id, finish=False)
        
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
            "registration_mode": task_data.get("registration_mode"),
            "phone_country": task_data.get("phone_country"),
            "sms_service_code": task_data.get("sms_service_code"),
            "sms_operator": task_data.get("sms_operator"),
            "sms_provider": task_data.get("sms_provider"),
            "sms_activation_id": task_data.get("sms_activation_id"),
            "phone_number": task_data.get("phone_number"),
            "sms_last_status": task_data.get("sms_last_status"),
            "sms_code": task_data.get("sms_code"),
            "status": task_data.get("status"),
            "current_step": task_data.get("current_step", 0),
            "step_status": dict(task_data.get("step_status", {})),
            "waiting_for": task_data.get("waiting_for"),
            "waiting_context": task_data.get("waiting_context"),
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