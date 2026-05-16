# -*- coding: utf-8 -*-
"""
短信平台配置。

当前目标：
1. 支持多 provider 的统一配置入口
2. 保持 HeroSMS 现有兼容性
3. 为 SMS-Activate / api.cc 等 provider 预留扩展位
4. 继续避免把临时 API key 写死到仓库
"""

from __future__ import annotations

import os
from typing import Any


def _env_str(name: str, default: str = "") -> str:
    return (os.environ.get(name, default) or "").strip()


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float | None = None) -> float | None:
    raw = _env_str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


SMS_PROVIDER = _env_str("SMS_PROVIDER", "hero_sms") or "hero_sms"

SMS_PROVIDER_COMPATIBILITY = {
    "hero_sms": "sms_activate_compatible",
    "sms_activate": "sms_activate_compatible",
    "api_cc": "custom",
}

HERO_SMS_API_KEY = _env_str("HERO_SMS_API_KEY")
HERO_SMS_BASE_URL = _env_str(
    "HERO_SMS_BASE_URL",
    "https://dashboard.herosms.com/stubs/handler_api.php",
)
HERO_SMS_DEFAULT_COUNTRY = _env_str("HERO_SMS_DEFAULT_COUNTRY", "0")
HERO_SMS_DEFAULT_SERVICE = _env_str("HERO_SMS_DEFAULT_SERVICE")
HERO_SMS_POLL_INTERVAL = _env_int("HERO_SMS_POLL_INTERVAL", 5)
HERO_SMS_MAX_WAIT = _env_int("HERO_SMS_MAX_WAIT", 180)
HERO_SMS_OPERATOR = _env_str("HERO_SMS_OPERATOR")
HERO_SMS_MAX_PRICE = _env_float("HERO_SMS_MAX_PRICE")

SMS_ACTIVATE_API_KEY = _env_str("SMS_ACTIVATE_API_KEY")
SMS_ACTIVATE_BASE_URL = _env_str(
    "SMS_ACTIVATE_BASE_URL",
    "https://api.sms-activate.ae/stubs/handler_api.php",
)
SMS_ACTIVATE_DEFAULT_COUNTRY = _env_str("SMS_ACTIVATE_DEFAULT_COUNTRY", "0")
SMS_ACTIVATE_DEFAULT_SERVICE = _env_str("SMS_ACTIVATE_DEFAULT_SERVICE")
SMS_ACTIVATE_POLL_INTERVAL = _env_int("SMS_ACTIVATE_POLL_INTERVAL", 5)
SMS_ACTIVATE_MAX_WAIT = _env_int("SMS_ACTIVATE_MAX_WAIT", 180)
SMS_ACTIVATE_OPERATOR = _env_str("SMS_ACTIVATE_OPERATOR")
SMS_ACTIVATE_MAX_PRICE = _env_float("SMS_ACTIVATE_MAX_PRICE")

API_CC_API_KEY = _env_str("API_CC_API_KEY")
API_CC_BASE_URL = _env_str("API_CC_BASE_URL", "https://api.cc")
API_CC_DEFAULT_COUNTRY = _env_str("API_CC_DEFAULT_COUNTRY")
API_CC_DEFAULT_SERVICE = _env_str("API_CC_DEFAULT_SERVICE")
API_CC_POLL_INTERVAL = _env_int("API_CC_POLL_INTERVAL", 5)
API_CC_MAX_WAIT = _env_int("API_CC_MAX_WAIT", 180)
API_CC_OPERATOR = _env_str("API_CC_OPERATOR")
API_CC_MAX_PRICE = _env_float("API_CC_MAX_PRICE")


def _normalize_provider_name(provider: str | None) -> str:
    return (provider or SMS_PROVIDER or "hero_sms").strip().lower()


def _provider_defaults(provider: str) -> dict[str, Any]:
    provider = _normalize_provider_name(provider)
    if provider == "hero_sms":
        return {
            "api_key": HERO_SMS_API_KEY,
            "base_url": HERO_SMS_BASE_URL,
            "default_country": HERO_SMS_DEFAULT_COUNTRY,
            "default_service": HERO_SMS_DEFAULT_SERVICE,
            "poll_interval": HERO_SMS_POLL_INTERVAL,
            "max_wait": HERO_SMS_MAX_WAIT,
            "operator": HERO_SMS_OPERATOR,
            "max_price": HERO_SMS_MAX_PRICE,
        }
    if provider == "sms_activate":
        return {
            "api_key": SMS_ACTIVATE_API_KEY,
            "base_url": SMS_ACTIVATE_BASE_URL,
            "default_country": SMS_ACTIVATE_DEFAULT_COUNTRY,
            "default_service": SMS_ACTIVATE_DEFAULT_SERVICE,
            "poll_interval": SMS_ACTIVATE_POLL_INTERVAL,
            "max_wait": SMS_ACTIVATE_MAX_WAIT,
            "operator": SMS_ACTIVATE_OPERATOR,
            "max_price": SMS_ACTIVATE_MAX_PRICE,
        }
    if provider == "api_cc":
        return {
            "api_key": API_CC_API_KEY,
            "base_url": API_CC_BASE_URL,
            "default_country": API_CC_DEFAULT_COUNTRY,
            "default_service": API_CC_DEFAULT_SERVICE,
            "poll_interval": API_CC_POLL_INTERVAL,
            "max_wait": API_CC_MAX_WAIT,
            "operator": API_CC_OPERATOR,
            "max_price": API_CC_MAX_PRICE,
        }
    return {
        "api_key": "",
        "base_url": "",
        "default_country": "",
        "default_service": "",
        "poll_interval": 5,
        "max_wait": 180,
        "operator": "",
        "max_price": None,
    }


def get_hero_sms_settings(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    运行时读取 HeroSMS 配置。

    - 优先使用调用方 overrides（便于单任务切换 API key / 参数）
    - 其次读取当前环境变量
    - 最后回退到模块级默认值
    """
    return get_sms_provider_settings("hero_sms", overrides)


def get_sms_activate_settings(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_sms_provider_settings("sms_activate", overrides)


def get_api_cc_settings(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_sms_provider_settings("api_cc", overrides)


def get_sms_provider_settings(provider: str | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    provider_name = _normalize_provider_name(overrides.get("provider") or provider)
    defaults = _provider_defaults(provider_name)

    def _pick(key: str, fallback: Any) -> Any:
        value = overrides.get(key)
        if value not in (None, ""):
            return value
        return fallback

    poll_interval = _pick("poll_interval", defaults.get("poll_interval"))
    max_wait = _pick("max_wait", defaults.get("max_wait"))
    max_price = _pick("max_price", defaults.get("max_price"))

    try:
        poll_interval = int(poll_interval)
    except (TypeError, ValueError):
        poll_interval = defaults.get("poll_interval") or 5

    try:
        max_wait = int(max_wait)
    except (TypeError, ValueError):
        max_wait = defaults.get("max_wait") or 180

    if max_price in ("", None):
        max_price = None
    else:
        try:
            max_price = float(max_price)
        except (TypeError, ValueError):
            max_price = defaults.get("max_price")

    return {
        "provider": provider_name,
        "compatibility": SMS_PROVIDER_COMPATIBILITY.get(provider_name, "custom"),
        "api_key": _pick("api_key", defaults.get("api_key") or ""),
        "base_url": _pick("base_url", defaults.get("base_url") or ""),
        "default_country": _pick("default_country", defaults.get("default_country") or ""),
        "default_service": _pick("default_service", defaults.get("default_service") or ""),
        "operator": _pick("operator", defaults.get("operator") or ""),
        "poll_interval": poll_interval,
        "max_wait": max_wait,
        "max_price": max_price,
    }