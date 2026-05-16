# -*- coding: utf-8 -*-
"""半自动 ChatGPT 注册执行器。

复用 any-auto-register 的浏览器注册能力：
- 手机号 + 短信验证码：自动
- 邮箱地址 + 邮箱验证码：人工
- 最终输出 SkyGPT 现有 CPA 文件
"""

from __future__ import annotations

import random
import string
import sys
import importlib.util
from pathlib import Path
from typing import Callable


def _ensure_any_auto_register_importable() -> None:
    repo = Path(__file__).resolve().parents[2] / "any-auto-register"
    if not repo.exists():
        raise RuntimeError("未找到 any-auto-register 仓库目录，无法启用半自动手机号注册")
    repo_str = str(repo)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)


def generate_password(length: int = 16) -> str:
    specials = ",._!@#"
    pool = string.ascii_letters + string.digits + specials
    required = [
        random.choice(string.ascii_lowercase),
        random.choice(string.ascii_uppercase),
        random.choice(string.digits),
        random.choice(specials),
    ]
    required.extend(random.choice(pool) for _ in range(max(length, 12) - len(required)))
    random.shuffle(required)
    return "".join(required)


def build_phone_callback(sms_provider: str, sms_config: dict, log_fn: Callable[[str], None]):
    repo = Path(__file__).resolve().parents[2] / "any-auto-register"
    base_sms_path = repo / "core" / "base_sms.py"
    if not base_sms_path.exists():
        raise RuntimeError("未找到 any-auto-register/core/base_sms.py")

    spec = importlib.util.spec_from_file_location("any_auto_register_base_sms", base_sms_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 any-auto-register 的 base_sms 模块")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    create_phone_callbacks = getattr(module, "create_phone_callbacks", None)
    if not callable(create_phone_callbacks):
        raise RuntimeError("any-auto-register base_sms 中缺少 create_phone_callbacks")

    provider_key = str(sms_provider or sms_config.get("sms_provider") or "herosms").strip()
    config = dict(sms_config or {})
    service = str(config.get("sms_service") or "dr").strip() or "dr"
    country = str(config.get("sms_country") or "52").strip()
    return create_phone_callbacks(
        provider_key,
        config,
        service=service,
        country=country,
        log_fn=log_fn,
    )


def run_semi_auto_chatgpt_registration(
    *,
    email: str,
    otp_callback: Callable[[], str],
    sms_provider: str,
    sms_config: dict,
    proxy: str | None,
    headless: bool,
    log_fn: Callable[[str], None],
) -> dict:
    _ensure_any_auto_register_importable()
    from platforms.chatgpt.browser_register import ChatGPTBrowserRegister  # type: ignore

    password = generate_password()
    phone_callback, cleanup = build_phone_callback(sms_provider, sms_config, log_fn)
    try:
        worker = ChatGPTBrowserRegister(
            headless=headless,
            proxy=proxy,
            otp_callback=otp_callback,
            phone_callback=phone_callback,
            log_fn=log_fn,
        )
        result = worker.run(email=email, password=password)
        if not isinstance(result, dict) or not result.get("access_token") or not result.get("account_id"):
            raise RuntimeError(f"浏览器注册未返回完整 token: {result}")
        result.setdefault("email", email)
        result.setdefault("password", password)
        return result
    finally:
        try:
            cleanup()
        except Exception:
            pass