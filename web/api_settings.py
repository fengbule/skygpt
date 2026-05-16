# -*- coding: utf-8 -*-
"""
Settings REST API
提供短信 provider 的持久化设置、默认值读取与连接测试。
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from core.provider_settings import SUPPORTED_SMS_PROVIDERS, get_default_sms_provider, list_sms_provider_settings, resolve_sms_provider_settings
from core.sms_provider import SMSProviderError, get_balance
from web.database import SMSProviderSettingsDB

logger = logging.getLogger(__name__)
settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")


def _sms_setting_response(provider: str):
    saved = SMSProviderSettingsDB.get_provider_setting(provider)
    config = resolve_sms_provider_settings(provider)
    if saved and saved.get("config"):
        config["api_key"] = saved["config"].get("api_key", config.get("api_key", ""))
    return {
        "provider": provider,
        "display_name": (saved or {}).get("display_name") or provider,
        "enabled": bool((saved or {}).get("enabled", True)),
        "is_default": provider == get_default_sms_provider(),
        "config": config,
    }


@settings_bp.route("/sms", methods=["GET"])
def list_sms_settings():
    return jsonify({
        "success": True,
        "default_provider": get_default_sms_provider(),
        "providers": list_sms_provider_settings(),
        "supported_providers": list(SUPPORTED_SMS_PROVIDERS),
    }), 200


@settings_bp.route("/sms/default", methods=["GET"])
def get_sms_default_setting():
    provider = get_default_sms_provider()
    return jsonify({"success": True, "item": _sms_setting_response(provider)}), 200


@settings_bp.route("/sms/<provider>", methods=["GET"])
def get_sms_provider_setting(provider: str):
    provider = (provider or "").strip().lower()
    if provider not in SUPPORTED_SMS_PROVIDERS:
        return jsonify({"success": False, "error": f"不支持的短信 provider: {provider}"}), 400
    return jsonify({"success": True, "item": _sms_setting_response(provider)}), 200


@settings_bp.route("/sms/<provider>", methods=["PUT"])
def save_sms_provider_setting(provider: str):
    provider = (provider or "").strip().lower()
    if provider not in SUPPORTED_SMS_PROVIDERS:
        return jsonify({"success": False, "error": f"不支持的短信 provider: {provider}"}), 400

    payload = request.get_json(silent=True) or {}
    config = dict(payload.get("config") or {})
    item = SMSProviderSettingsDB.save_provider_setting(
        provider,
        display_name=payload.get("display_name") or provider,
        enabled=bool(payload.get("enabled", True)),
        is_default=bool(payload.get("is_default", False)),
        config=config,
    )
    return jsonify({"success": True, "item": _sms_setting_response(provider), "saved": item}), 200


@settings_bp.route("/sms/<provider>/test", methods=["POST"])
def test_sms_provider_setting(provider: str):
    provider = (provider or "").strip().lower()
    if provider not in SUPPORTED_SMS_PROVIDERS:
        return jsonify({"success": False, "error": f"不支持的短信 provider: {provider}"}), 400

    payload = request.get_json(silent=True) or {}
    overrides = dict(payload.get("config") or {})
    overrides["provider"] = provider
    try:
        settings = resolve_sms_provider_settings(provider, overrides)
        result = get_balance(provider=provider, settings=settings)
        return jsonify({"success": True, "provider": provider, "result": result}), 200
    except (SMSProviderError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("测试短信 provider 失败: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500