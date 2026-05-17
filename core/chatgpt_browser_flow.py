from __future__ import annotations

import importlib.util
import importlib.machinery
import json
import logging
import re
import secrets
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from core.sms_provider import (
    acquire_phone_number,
    cancel_activation,
    finish_activation,
    wait_for_sms_code,
)

logger = logging.getLogger(__name__)

_LOAD_LOCK = threading.Lock()
_BROWSER_REGISTER_CLS = None
_PLAYWRIGHT_RUNTIME_HINTS = (
    "Executable doesn't exist at",
    "chromium_headless_shell",
    "chrome-headless-shell",
    "ms-playwright",
    "download new browsers",
    "playwright install",
)


def generate_openai_compatible_password(length: int = 16) -> str:
    specials = ",._!@#"
    minimum_length = 12
    size = max(int(length or minimum_length), minimum_length)
    required = [
        secrets.choice("abcdefghijklmnopqrstuvwxyz"),
        secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        secrets.choice("0123456789"),
        secrets.choice(specials),
    ]
    pool = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" + specials
    required.extend(secrets.choice(pool) for _ in range(size - len(required)))
    secrets.SystemRandom().shuffle(required)
    return "".join(required)


def _load_module(module_name: str, file_path: Path):
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing

    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块 {module_name}: {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _rewrite_playwright_runtime_error(exc: Exception) -> Exception:
    message = str(exc or "")
    if not any(hint in message for hint in _PLAYWRIGHT_RUNTIME_HINTS):
        return exc

    missing_path = ""
    match = re.search(r"Executable doesn't exist at\s+([^\r\n]+)", message)
    if match:
        missing_path = match.group(1).strip()

    detail = (
        "Playwright 浏览器运行时缺失：当前缺的不是系统 Chrome，也不是 Python，"
        "而是 Playwright 自己管理的 Chromium headless shell 可执行文件。"
    )
    if missing_path:
        detail += f" 缺失路径: {missing_path}。"
    detail += " 请先执行 `python -m playwright install chromium`，再重试浏览器流程。"
    return RuntimeError(detail)


def get_chatgpt_browser_register_class():
    global _BROWSER_REGISTER_CLS
    if _BROWSER_REGISTER_CLS is not None:
        return _BROWSER_REGISTER_CLS

    with _LOAD_LOCK:
        if _BROWSER_REGISTER_CLS is not None:
            return _BROWSER_REGISTER_CLS

        repo_root = Path(__file__).resolve().parent.parent
        chatgpt_dir = repo_root / "any-auto-register" / "platforms" / "chatgpt"
        if not chatgpt_dir.exists():
            raise RuntimeError(f"未找到 any-auto-register ChatGPT 实现目录: {chatgpt_dir}")

        package_name = "aar_chatgpt"
        package = sys.modules.get(package_name)
        if package is None:
            package = importlib.util.module_from_spec(
                importlib.machinery.ModuleSpec(package_name, loader=None, is_package=True)
            )
            package.__path__ = [str(chatgpt_dir)]
            sys.modules[package_name] = package

        _load_module(f"{package_name}.constants", chatgpt_dir / "constants.py")
        _load_module(f"{package_name}.oauth", chatgpt_dir / "oauth.py")
        _BROWSER_REGISTER_CLS = _load_module(
            f"{package_name}.browser_register",
            chatgpt_dir / "browser_register.py",
        ).ChatGPTBrowserRegister
        return _BROWSER_REGISTER_CLS


class SkyGPTPhoneCallback:
    def __init__(
        self,
        *,
        provider: str,
        settings: dict[str, Any],
        task_data: dict[str, Any],
        on_log: Callable[[str, str], None],
        on_waiting: Callable[[str, dict[str, Any] | None], None],
        poll_interval: int | None = None,
        max_wait: int | None = None,
    ):
        self.provider = provider
        self.settings = dict(settings or {})
        self.task_data = task_data
        self.on_log = on_log
        self.on_waiting = on_waiting
        self.poll_interval = poll_interval
        self.max_wait = max_wait

        self.phase = "need_number"
        self.activation: dict[str, Any] | None = None
        self.completed = False
        self.resend_callback: Callable[[], None] | None = None

    def __call__(self):
        if self.phase == "need_number":
            activation = acquire_phone_number(
                provider=self.provider,
                settings=self.settings,
                country=self.task_data.get("phone_country"),
                service=self.task_data.get("sms_service_code"),
                operator=self.task_data.get("sms_operator"),
                max_price=self.task_data.get("sms_max_price"),
            )
            self.activation = activation
            self.task_data["sms_activation_id"] = activation.get("activation_id")
            self.task_data["phone_number"] = activation.get("phone_number")
            self.task_data["sms_last_status"] = activation.get("status")
            self.phase = "need_code"
            self.on_log(
                f"浏览器手机号流程已获取号码: {activation.get('phone_number')} (activation_id={activation.get('activation_id')})",
                "INFO",
            )
            return activation.get("phone_number")

        if self.phase == "need_code":
            if not self.activation or not self.activation.get("activation_id"):
                raise RuntimeError("短信激活不存在，无法等待验证码")

            self.on_waiting(
                "sms_otp_auto",
                {
                    "mode": "phone_browser",
                    "provider": self.provider,
                    "phone_number": self.task_data.get("phone_number"),
                    "activation_id": self.task_data.get("sms_activation_id"),
                    "note": "正在自动轮询短信验证码并提交到 OpenAI 手机验证页面。",
                },
            )
            result = wait_for_sms_code(
                str(self.activation["activation_id"]),
                provider=self.provider,
                settings=self.settings,
                poll_interval=self.poll_interval,
                max_wait=self.max_wait,
            )
            self.task_data["sms_last_status"] = result.get("status")
            self.task_data["sms_code"] = result.get("code")
            self.phase = "code_received"
            self.on_log(f"浏览器手机号流程收到短信验证码: {result.get('code')}", "SUCCESS")
            return result.get("code")

        return self.task_data.get("sms_code")

    def set_resend_callback(self, callback: Callable[[], None] | None = None) -> None:
        self.resend_callback = callback

    def mark_send_failed(self, reason: str = "") -> None:
        self.on_log(f"OpenAI 手机号发送失败: {reason}", "WARNING")

    def mark_send_succeeded(self) -> None:
        self.on_log("OpenAI 已接受手机号并发送短信", "INFO")

    def mark_code_failed(self, reason: str = "") -> None:
        self.phase = "need_code"
        self.on_log(f"短信验证码未通过，等待下一条验证码: {reason}", "WARNING")

    def report_success(self) -> None:
        self.completed = True
        self.on_log("手机号短信验证通过", "SUCCESS")

    def cleanup(self) -> None:
        activation_id = str((self.activation or {}).get("activation_id") or "")
        if not activation_id:
            return
        try:
            if self.completed:
                finish_activation(activation_id, provider=self.provider, settings=self.settings)
            else:
                cancel_activation(activation_id, provider=self.provider, settings=self.settings)
        except Exception as exc:
            logger.warning("短信激活清理失败: %s", exc)


def run_chatgpt_phone_browser_registration(
    *,
    email: str,
    password: str,
    proxy: str | None,
    headless: bool,
    browser_type: str = "camoufox",
    otp_callback: Callable[[], str | None],
    phone_callback: SkyGPTPhoneCallback,
    log_fn: Callable[[str], None],
) -> dict[str, Any]:
    try:
        browser_register_cls = get_chatgpt_browser_register_class()
        worker = browser_register_cls(
            headless=headless,
            proxy=proxy,
            browser_type=browser_type,
            otp_callback=otp_callback,
            phone_callback=phone_callback,
            log_fn=log_fn,
        )
        return worker.run(email=email, password=password)
    except Exception as exc:
        rewritten = _rewrite_playwright_runtime_error(exc)
        if rewritten is not exc:
            log_fn(str(rewritten))
            raise rewritten from exc
        raise


def normalize_browser_result(result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result or {})
    access_token = str(payload.get("access_token") or "")
    if not access_token:
        raise RuntimeError(f"浏览器注册结果缺少 access_token: {json.dumps(payload, ensure_ascii=False)[:500]}")
    return {
        "email": str(payload.get("email") or ""),
        "password": str(payload.get("password") or ""),
        "account_id": str(payload.get("account_id") or ""),
        "access_token": access_token,
        "refresh_token": str(payload.get("refresh_token") or ""),
        "id_token": str(payload.get("id_token") or ""),
        "session_token": str(payload.get("session_token") or ""),
        "workspace_id": str(payload.get("workspace_id") or ""),
        "cookies": str(payload.get("cookies") or ""),
        "profile": payload.get("profile") or {},
    }
