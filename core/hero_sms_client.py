# -*- coding: utf-8 -*-
"""
HeroSMS / SMS-Activate 兼容客户端。

当前实现目标：
1. 抽象 HeroSMS 基址与 API key
2. 同时兼容文本态与 JSON 态响应
3. 为后续手机号注册状态机提供稳定的底层接口
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from config.sms import get_hero_sms_settings

logger = logging.getLogger(__name__)


class HeroSMSError(RuntimeError):
    """HeroSMS 请求或业务返回异常。"""


class HeroSMSConfigError(HeroSMSError):
    """HeroSMS 配置缺失。"""


class HeroSMSClient:
    def __init__(self, settings: dict[str, Any] | None = None, timeout: int = 30):
        merged = get_hero_sms_settings(settings)
        self.provider = merged.get("provider") or "hero_sms"
        self.api_key = (merged.get("api_key") or "").strip()
        self.base_url = (merged.get("base_url") or "").strip()
        self.timeout = timeout
        self.session = requests.Session()

        if not self.api_key:
            raise HeroSMSConfigError("未配置 HERO_SMS_API_KEY，无法调用 HeroSMS")
        if not self.base_url:
            raise HeroSMSConfigError("未配置 HERO_SMS_BASE_URL，无法调用 HeroSMS")

    def _request(self, action: str, params: dict[str, Any] | None = None, prefer_json: bool = False) -> dict[str, Any]:
        query = {
            "api_key": self.api_key,
            "action": action,
        }
        for key, value in (params or {}).items():
            if value in (None, ""):
                continue
            query[key] = value

        response = self.session.get(
            self.base_url,
            params=query,
            timeout=self.timeout,
            headers={
                "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
                "User-Agent": "SkyGPT-HeroSMS-Client/1.0",
            },
        )
        response.raise_for_status()

        content_type = (response.headers.get("content-type") or "").lower()
        raw_text = response.text.strip()

        if prefer_json or raw_text.startswith("{") or raw_text.startswith("[") or "application/json" in content_type:
            try:
                data = response.json()
            except ValueError:
                try:
                    data = json.loads(raw_text)
                except ValueError:
                    logger.debug("HeroSMS JSON 解析失败，回退到文本解析: %s", raw_text)
                    return self._normalize_text_response(action, raw_text)
            return self._normalize_json_response(action, data, raw_text)

        return self._normalize_text_response(action, raw_text)

    def _normalize_json_response(self, action: str, data: Any, raw_text: str) -> dict[str, Any]:
        if isinstance(data, list):
            return {
                "action": action,
                "status": "OK",
                "success": True,
                "data": data,
                "raw": raw_text,
            }

        if not isinstance(data, dict):
            return {
                "action": action,
                "status": "UNKNOWN",
                "success": False,
                "data": data,
                "raw": raw_text,
            }

        normalized = dict(data)
        normalized.setdefault("action", action)
        normalized.setdefault("raw", raw_text)

        status = normalized.get("status")
        if not status and normalized.get("activationId"):
            status = "ACCESS_NUMBER"
        if not status and any(k in normalized for k in ("balance", "getBalance")):
            status = "ACCESS_BALANCE"

        normalized["status"] = status or "OK"
        normalized["success"] = not str(normalized["status"]).startswith(("BAD_", "ERROR", "NO_"))

        activation_id = normalized.get("activationId") or normalized.get("id")
        phone_number = normalized.get("phoneNumber") or normalized.get("phone") or normalized.get("number")
        code = normalized.get("code") or normalized.get("smsCode")

        if activation_id is not None:
            normalized["activation_id"] = str(activation_id)
        if phone_number is not None:
            normalized["phone_number"] = str(phone_number)
        if code not in (None, ""):
            normalized["code"] = str(code)

        return normalized

    def _normalize_text_response(self, action: str, raw_text: str) -> dict[str, Any]:
        normalized: dict[str, Any] = {
            "action": action,
            "raw": raw_text,
            "status": raw_text or "EMPTY_RESPONSE",
            "success": True,
        }

        if not raw_text:
            normalized["success"] = False
            return normalized

        if action == "getBalance" and raw_text.startswith("ACCESS_BALANCE"):
            _, _, balance = raw_text.partition(":")
            try:
                normalized["balance"] = float(balance)
            except ValueError:
                normalized["balance"] = balance
            return normalized

        if action in {"getNumber", "getNumberV2"} and raw_text.startswith("ACCESS_NUMBER"):
            parts = raw_text.split(":")
            if len(parts) >= 3:
                normalized["activation_id"] = parts[1]
                normalized["phone_number"] = parts[2]
            normalized["status"] = "ACCESS_NUMBER"
            return normalized

        if action in {"getStatus", "getStatusV2"}:
            if raw_text.startswith("STATUS_OK"):
                parts = raw_text.split(":", 1)
                normalized["status"] = "STATUS_OK"
                if len(parts) == 2 and parts[1]:
                    normalized["code"] = parts[1]
                return normalized
            if raw_text.startswith("STATUS_"):
                normalized["status"] = raw_text.split(":", 1)[0]
                if ":" in raw_text:
                    normalized["detail"] = raw_text.split(":", 1)[1]
                return normalized

        if action in {"setStatus", "finishActivation", "cancelActivation"}:
            normalized["status"] = raw_text
            normalized["success"] = raw_text.startswith("ACCESS_")
            return normalized

        if raw_text.startswith(("BAD_", "ERROR", "NO_")):
            normalized["success"] = False

        return normalized

    def get_balance(self) -> dict[str, Any]:
        return self._request("getBalance")

    def get_number(
        self,
        service: str,
        country: str,
        *,
        max_price: float | None = None,
        operator: str | None = None,
        phone_exception: str | None = None,
        activation_type: str | None = None,
        order_id: str | None = None,
        use_v2: bool = True,
    ) -> dict[str, Any]:
        action = "getNumberV2" if use_v2 else "getNumber"
        return self._request(
            action,
            {
                "service": service,
                "country": country,
                "maxPrice": max_price,
                "operator": operator,
                "phoneException": phone_exception,
                "activationType": activation_type,
                "orderId": order_id,
            },
            prefer_json=use_v2,
        )

    def get_status(self, activation_id: str, *, use_v2: bool = True) -> dict[str, Any]:
        action = "getStatusV2" if use_v2 else "getStatus"
        return self._request(action, {"id": activation_id}, prefer_json=use_v2)

    def set_status(self, activation_id: str, status: int) -> dict[str, Any]:
        return self._request("setStatus", {"id": activation_id, "status": status})

    def finish_activation(self, activation_id: str) -> dict[str, Any]:
        try:
            result = self._request("finishActivation", {"id": activation_id})
            if result.get("success"):
                return result
        except Exception:
            logger.debug("finishActivation 失败，回退到 setStatus=6", exc_info=True)
        return self.set_status(activation_id, 6)

    def cancel_activation(self, activation_id: str) -> dict[str, Any]:
        try:
            result = self._request("cancelActivation", {"id": activation_id})
            if result.get("success"):
                return result
        except Exception:
            logger.debug("cancelActivation 失败，回退到 setStatus=8", exc_info=True)
        return self.set_status(activation_id, 8)