# -*- coding: utf-8 -*-
"""
短信 provider 持久化设置解析。

职责：
1. 在环境变量默认值之上叠加数据库保存的 provider 设置
2. 再叠加本次任务/请求传入的 overrides
3. 提供默认 provider 与设置列表给 Web UI 使用
"""
from __future__ import annotations

from typing import Any

from config.sms import SMS_PROVIDER, get_sms_provider_settings

SUPPORTED_SMS_PROVIDERS = ("hero_sms", "sms_activate", "api_cc")


def _pick_override(overrides: dict[str, Any], key: str) -> Any:
    value = overrides.get(key)
    return value if value not in (None, "") else None


def get_default_sms_provider() -> str:
    try:
        from web.database import SMSProviderSettingsDB

        provider = SMSProviderSettingsDB.get_default_provider()
        if provider:
            return provider
    except Exception:
        pass
    return SMS_PROVIDER or "hero_sms"


def resolve_sms_provider_settings(provider: str | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    provider_name = str(overrides.get("provider") or provider or get_default_sms_provider()).strip().lower() or "hero_sms"
    merged = get_sms_provider_settings(provider_name, {})

    try:
        from web.database import SMSProviderSettingsDB

        saved = SMSProviderSettingsDB.get_provider_setting(provider_name)
        if saved:
            saved_config = dict(saved.get("config") or {})
            merged.update({k: v for k, v in saved_config.items() if v not in (None, "")})
    except Exception:
        saved = None

    for key in (
        "provider",
        "api_key",
        "base_url",
        "default_country",
        "default_service",
        "operator",
        "poll_interval",
        "max_wait",
        "max_price",
        "auto_select_best_country",
        "best_country_min_stock",
        "best_country_max_price",
    ):
        value = _pick_override(overrides, key)
        if value is not None:
            merged[key] = value

    merged["provider"] = provider_name
    return merged


def list_sms_provider_settings() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    default_provider = get_default_sms_provider()
    for provider in SUPPORTED_SMS_PROVIDERS:
        settings = resolve_sms_provider_settings(provider)
        try:
            from web.database import SMSProviderSettingsDB

            saved = SMSProviderSettingsDB.get_provider_setting(provider)
        except Exception:
            saved = None

        items.append(
            {
                "provider": provider,
                "display_name": (saved or {}).get("display_name") or provider,
                "enabled": bool((saved or {}).get("enabled", True)),
                "is_default": provider == default_provider,
                "config": settings,
            }
        )
    return items