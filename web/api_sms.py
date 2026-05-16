# -*- coding: utf-8 -*-
"""
SMS Capability REST API
融合参考仓库中的接码查询策略，提供多 provider 的余额、国家、服务、价格与优选国家查询。
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from core.hero_sms_client import HeroSMSConfigError
from core.sms_provider import (
    SMSProviderError,
    get_balance,
    get_best_country,
    get_countries,
    get_prices,
    get_services,
    get_top_countries,
)

logger = logging.getLogger(__name__)
sms_bp = Blueprint("sms", __name__, url_prefix="/api/sms")


def _request_json() -> dict:
    return request.get_json(silent=True) or {}


def _build_sms_settings(payload: dict) -> dict:
    return {
        "provider": payload.get("provider"),
        "api_key": payload.get("api_key"),
        "base_url": payload.get("base_url"),
        "default_country": payload.get("default_country") or payload.get("country"),
        "default_service": payload.get("default_service") or payload.get("service"),
        "operator": payload.get("operator"),
        "poll_interval": payload.get("poll_interval"),
        "max_wait": payload.get("max_wait"),
        "max_price": payload.get("max_price"),
    }


def _response(data, **extra):
    return jsonify({"success": True, "data": data, **extra}), 200


def _handle_sms_error(exc: Exception):
    logger.error("SMS API error: %s", exc)
    status_code = 400 if isinstance(exc, (SMSProviderError, HeroSMSConfigError, ValueError)) else 500
    return jsonify({"success": False, "error": str(exc)}), status_code


@sms_bp.route("/providers/<provider>/balance", methods=["POST"])
def provider_balance(provider: str):
    payload = _request_json()
    try:
        settings = _build_sms_settings(payload)
        return _response(get_balance(provider=provider, settings=settings), provider=provider)
    except Exception as exc:
        return _handle_sms_error(exc)


@sms_bp.route("/providers/<provider>/countries", methods=["GET", "POST"])
def provider_countries(provider: str):
    payload = _request_json()
    try:
        settings = _build_sms_settings(payload)
        return _response(get_countries(provider=provider, settings=settings), provider=provider)
    except Exception as exc:
        return _handle_sms_error(exc)


@sms_bp.route("/providers/<provider>/services", methods=["GET", "POST"])
def provider_services(provider: str):
    payload = _request_json()
    country = payload.get("country") or request.args.get("country")
    lang = payload.get("lang") or request.args.get("lang") or "cn"
    try:
        settings = _build_sms_settings(payload)
        data = get_services(provider=provider, settings=settings, country=country, lang=lang)
        return _response(data, provider=provider, country=country, lang=lang)
    except Exception as exc:
        return _handle_sms_error(exc)


@sms_bp.route("/providers/<provider>/prices", methods=["POST"])
def provider_prices(provider: str):
    payload = _request_json()
    service = payload.get("service")
    country = payload.get("country")
    try:
        settings = _build_sms_settings(payload)
        data = get_prices(provider=provider, settings=settings, service=service, country=country)
        return _response(data, provider=provider, service=service, country=country)
    except Exception as exc:
        return _handle_sms_error(exc)


@sms_bp.route("/providers/<provider>/top-countries", methods=["POST"])
def provider_top_countries(provider: str):
    payload = _request_json()
    service = payload.get("service")
    try:
        settings = _build_sms_settings(payload)
        data = get_top_countries(provider=provider, settings=settings, service=service)
        return _response(data, provider=provider, service=service)
    except Exception as exc:
        return _handle_sms_error(exc)


@sms_bp.route("/providers/<provider>/best-country", methods=["POST"])
def provider_best_country(provider: str):
    payload = _request_json()
    service = payload.get("service")
    min_stock = payload.get("min_stock", 20)
    max_price = payload.get("max_price", 0)
    try:
        settings = _build_sms_settings(payload)
        data = get_best_country(
            provider=provider,
            settings=settings,
            service=service,
            min_stock=int(min_stock or 0),
            max_price=float(max_price or 0),
        )
        return _response(data, provider=provider, service=service, min_stock=min_stock, max_price=max_price)
    except Exception as exc:
        return _handle_sms_error(exc)