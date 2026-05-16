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

from core.provider_settings import resolve_sms_provider_settings

logger = logging.getLogger(__name__)


class HeroSMSError(RuntimeError):
    """HeroSMS 请求或业务返回异常。"""


class HeroSMSConfigError(HeroSMSError):
    """HeroSMS 配置缺失。"""


class HeroSMSClient:
    def __init__(self, settings: dict[str, Any] | None = None, timeout: int = 30):
        merged = resolve_sms_provider_settings((settings or {}).get("provider"), settings)
        self.provider = merged.get("provider") or "hero_sms"
        self.api_key = (merged.get("api_key") or "").strip()
        self.base_url = (merged.get("base_url") or "").strip()
        self.timeout = timeout
        self.session = requests.Session()
        self.provider_label = self.provider or "sms_provider"

        if not self.api_key:
            raise HeroSMSConfigError(f"未配置 {self.provider_label} 的 API key，无法调用短信平台")
        if not self.base_url:
            raise HeroSMSConfigError(f"未配置 {self.provider_label} 的 base_url，无法调用短信平台")

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

    @staticmethod
    def _extract_payload(normalized: dict[str, Any]) -> Any:
        data = normalized.get("data")
        if isinstance(data, (list, dict)):
            return data

        meta_keys = {"action", "raw", "status", "success", "activation_id", "phone_number", "code", "detail"}
        payload = {k: v for k, v in normalized.items() if k not in meta_keys}
        return payload

    @staticmethod
    def _coerce_rows(payload: Any, *, key_name: str = "id", name_key: str = "name") -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]

        if not isinstance(payload, dict):
            return []

        rows: list[dict[str, Any]] = []
        for key, value in payload.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault(key_name, str(row.get(key_name) or key))
                row.setdefault(name_key, row.get("eng") or row.get("name") or row.get("title") or str(key))
                rows.append(row)
            elif isinstance(value, str):
                rows.append({key_name: str(key), name_key: value})
        return rows

    @staticmethod
    def _parse_top_countries_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            rows = [dict(row) for row in payload if isinstance(row, dict)]
        elif isinstance(payload, dict):
            rows = []
            for key, value in payload.items():
                if isinstance(value, dict):
                    row = dict(value)
                    row.setdefault("country", str(row.get("country") or row.get("id") or key))
                    rows.append(row)
        else:
            rows = []

        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            country = str(row.get("country") or row.get("id") or "").strip()
            if not country:
                continue
            price = row.get("price")
            count = row.get("count") or row.get("qty") or row.get("available")
            try:
                price = float(price) if price not in (None, "") else None
            except (TypeError, ValueError):
                price = None
            try:
                count = int(count) if count not in (None, "") else 0
            except (TypeError, ValueError):
                count = 0

            normalized_rows.append(
                {
                    "country": country,
                    "name": row.get("name") or row.get("eng") or row.get("title") or country,
                    "price": price,
                    "count": count,
                    "raw": row,
                }
            )

        normalized_rows.sort(key=lambda item: (item.get("price") if item.get("price") is not None else 999999, -(item.get("count") or 0)))
        return normalized_rows

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

    def get_countries(self) -> list[dict[str, Any]]:
        data = self._request("getCountries", prefer_json=True)
        return self._coerce_rows(self._extract_payload(data), key_name="id", name_key="name")

    def get_services(self, *, country: str | None = None, lang: str = "cn") -> list[dict[str, Any]]:
        params: dict[str, Any] = {"lang": lang}
        if country not in (None, ""):
            params["country"] = country
        data = self._request("getServicesList", params=params, prefer_json=True)
        return self._coerce_rows(self._extract_payload(data), key_name="code", name_key="name")

    def get_prices(self, *, service: str | None = None, country: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if service not in (None, ""):
            params["service"] = service
        if country not in (None, ""):
            params["country"] = country
        data = self._request("getPrices", params=params, prefer_json=True)
        payload = self._extract_payload(data)
        return payload if isinstance(payload, dict) else {}

    def get_top_countries(self, *, service: str | None = None) -> list[dict[str, Any]]:
        for action in ("getTopCountriesByServiceRank", "getTopCountriesByService"):
            try:
                data = self._request(action, params={"service": service} if service else None, prefer_json=True)
                rows = self._parse_top_countries_rows(self._extract_payload(data))
                if rows:
                    return rows
            except Exception:
                logger.debug("%s 查询失败，继续尝试下一个接口", action, exc_info=True)

        prices = self.get_prices(service=service)
        rows: list[dict[str, Any]] = []
        for country_id, services in prices.items():
            if not isinstance(services, dict):
                continue
            svc_data = services.get(service) if service else next((v for v in services.values() if isinstance(v, dict)), None)
            if not isinstance(svc_data, dict):
                continue

            price = svc_data.get("cost") or svc_data.get("price")
            count = svc_data.get("count") or svc_data.get("qty") or svc_data.get("available")
            try:
                price = float(price) if price not in (None, "") else None
            except (TypeError, ValueError):
                price = None
            try:
                count = int(count) if count not in (None, "") else 0
            except (TypeError, ValueError):
                count = 0
            if price is None and count <= 0:
                continue
            rows.append({"country": str(country_id), "name": str(country_id), "price": price, "count": count, "raw": svc_data})

        rows.sort(key=lambda item: (item.get("price") if item.get("price") is not None else 999999, -(item.get("count") or 0)))
        return rows

    def get_best_country(self, *, service: str | None = None, min_stock: int = 20, max_price: float = 0) -> dict[str, Any] | None:
        rows = self.get_top_countries(service=service)
        if not rows:
            return None

        for row in rows:
            price = row.get("price") or 0
            count = row.get("count") or 0
            if count < min_stock:
                continue
            if max_price > 0 and price > max_price:
                continue
            return row

        for row in rows:
            price = row.get("price") or 0
            count = row.get("count") or 0
            if count <= 0:
                continue
            if max_price > 0 and price > max_price:
                continue
            return row

        return None

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