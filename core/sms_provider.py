# -*- coding: utf-8 -*-
"""
短信平台调度层。

当前实现：
1. provider 注册表
2. HeroSMS / SMS-Activate 兼容 provider
3. api.cc 独立 provider 预留骨架
4. 统一的 acquire / wait / finish / cancel 接口
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from config.sms import get_sms_provider_settings
from core.hero_sms_client import HeroSMSClient

logger = logging.getLogger(__name__)


class SMSProviderError(RuntimeError):
    pass


class SMSProviderTimeout(SMSProviderError):
    pass


class SMSProviderCancelled(SMSProviderError):
    pass


@dataclass
class SMSActivation:
    activation_id: str
    phone_number: str
    provider: str
    status: str
    country: str
    service: str
    operator: str | None = None
    activation_cost: Any = None
    country_code: str | None = None
    can_get_another_sms: bool | None = None
    activation_time: str | None = None
    raw: Any = None


@dataclass
class SMSCodeResult:
    activation_id: str
    provider: str
    status: str
    code: str | None = None
    raw: Any = None


class SMSActivateCompatibleProvider:
    provider_name = "sms_activate_compatible"

    def __init__(self, settings: dict[str, Any] | None = None, provider_name: str = "hero_sms"):
        self.provider_name = provider_name
        self.settings = get_sms_provider_settings(provider_name, settings)
        self.client = HeroSMSClient(self.settings)

    def get_balance(self) -> dict[str, Any]:
        return self.client.get_balance()

    def acquire_phone_number(
        self,
        *,
        country: str | None = None,
        service: str | None = None,
        operator: str | None = None,
        max_price: float | None = None,
        phone_exception: str | None = None,
        activation_type: str | None = None,
        order_id: str | None = None,
    ) -> SMSActivation:
        country = str(country or self.settings.get("default_country") or "0")
        service = (service or self.settings.get("default_service") or "").strip()
        operator = operator or self.settings.get("operator") or None
        max_price = self.settings.get("max_price") if max_price is None else max_price

        if not service:
            raise SMSProviderError("未配置短信服务代码 sms_service_code / default_service")

        data = self.client.get_number(
            service=service,
            country=country,
            max_price=max_price,
            operator=operator,
            phone_exception=phone_exception,
            activation_type=activation_type,
            order_id=order_id,
            use_v2=True,
        )
        if not data.get("activation_id") or not data.get("phone_number"):
            raise SMSProviderError(f"获取号码失败: {data.get('raw') or data.get('status')}")

        activation = SMSActivation(
            activation_id=str(data["activation_id"]),
            phone_number=str(data["phone_number"]),
            provider=self.provider_name,
            status=str(data.get("status") or "ACCESS_NUMBER"),
            country=country,
            service=service,
            operator=operator,
            activation_cost=data.get("activationCost") or data.get("activation_cost"),
            country_code=data.get("countryCode") or data.get("country_code"),
            can_get_another_sms=data.get("canGetAnotherSms"),
            activation_time=data.get("activationTime"),
            raw=data,
        )

        try:
            self.client.set_status(activation.activation_id, 1)
        except Exception:
            logger.debug("setStatus=1 失败，继续轮询", exc_info=True)

        return activation

    def wait_for_sms_code(
        self,
        activation_id: str,
        *,
        poll_interval: int | None = None,
        max_wait: int | None = None,
    ) -> SMSCodeResult:
        poll_interval = int(poll_interval or self.settings.get("poll_interval") or 5)
        max_wait = int(max_wait or self.settings.get("max_wait") or 180)

        deadline = time.time() + max_wait
        last_status = None

        while time.time() < deadline:
            data = self.client.get_status(str(activation_id), use_v2=True)
            status = str(data.get("status") or "UNKNOWN")
            code = data.get("code")
            last_status = status

            if status == "STATUS_OK" and code:
                return SMSCodeResult(
                    activation_id=str(activation_id),
                    provider=self.provider_name,
                    status=status,
                    code=str(code),
                    raw=data,
                )

            if status in {"STATUS_CANCEL", "ACCESS_CANCEL"}:
                raise SMSProviderCancelled(f"激活已取消: {data.get('raw') or status}")

            if status in {"STATUS_WAIT_CODE", "STATUS_WAIT_RETRY", "STATUS_WAIT_RESEND", "ACCESS_READY", "ACCESS_ACTIVATION"}:
                time.sleep(poll_interval)
                continue

            if code:
                return SMSCodeResult(
                    activation_id=str(activation_id),
                    provider=self.provider_name,
                    status=status,
                    code=str(code),
                    raw=data,
                )

            time.sleep(poll_interval)

        raise SMSProviderTimeout(f"等待短信验证码超时，最后状态={last_status or 'UNKNOWN'}")

    def finish_activation(self, activation_id: str) -> dict[str, Any]:
        return self.client.finish_activation(str(activation_id))

    def cancel_activation(self, activation_id: str) -> dict[str, Any]:
        return self.client.cancel_activation(str(activation_id))


class HeroSMSProvider(SMSActivateCompatibleProvider):
    provider_name = "hero_sms"

    def __init__(self, settings: dict[str, Any] | None = None):
        super().__init__(settings=settings, provider_name=self.provider_name)


class SMSActivateProvider(SMSActivateCompatibleProvider):
    provider_name = "sms_activate"

    def __init__(self, settings: dict[str, Any] | None = None):
        super().__init__(settings=settings, provider_name=self.provider_name)


class ApiCCProvider:
    provider_name = "api_cc"

    def __init__(self, settings: dict[str, Any] | None = None):
        self.settings = get_sms_provider_settings(self.provider_name, settings)

    def get_balance(self) -> dict[str, Any]:
        raise SMSProviderError("api.cc provider 已预留，但当前仍缺少稳定 API 文档/样本，暂未实现")

    def acquire_phone_number(self, **kwargs) -> SMSActivation:
        raise SMSProviderError("api.cc provider 已预留，但当前仍缺少稳定 API 文档/样本，暂未实现")

    def wait_for_sms_code(self, activation_id: str, **kwargs) -> SMSCodeResult:
        raise SMSProviderError("api.cc provider 已预留，但当前仍缺少稳定 API 文档/样本，暂未实现")

    def finish_activation(self, activation_id: str) -> dict[str, Any]:
        raise SMSProviderError("api.cc provider 已预留，但当前仍缺少稳定 API 文档/样本，暂未实现")

    def cancel_activation(self, activation_id: str) -> dict[str, Any]:
        raise SMSProviderError("api.cc provider 已预留，但当前仍缺少稳定 API 文档/样本，暂未实现")


SMS_PROVIDER_REGISTRY = {
    "hero_sms": HeroSMSProvider,
    "sms_activate": SMSActivateProvider,
    "api_cc": ApiCCProvider,
}


def get_sms_provider(provider: str | None = None, settings: dict[str, Any] | None = None):
    provider_name = (provider or (settings or {}).get("provider") or "").strip().lower()
    if not provider_name:
        provider_name = get_sms_provider_settings(provider, settings).get("provider") or "hero_sms"
    provider_cls = SMS_PROVIDER_REGISTRY.get(provider_name)
    if not provider_cls:
        raise SMSProviderError(f"暂不支持短信平台: {provider_name}")
    return provider_cls(settings=settings)


def get_balance(provider: str | None = None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_sms_provider(provider, settings).get_balance()


def acquire_phone_number(provider: str | None = None, settings: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    activation = get_sms_provider(provider, settings).acquire_phone_number(**kwargs)
    return asdict(activation)


def wait_for_sms_code(
    activation_id: str,
    provider: str | None = None,
    settings: dict[str, Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    result = get_sms_provider(provider, settings).wait_for_sms_code(activation_id, **kwargs)
    return asdict(result)


def finish_activation(activation_id: str, provider: str | None = None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_sms_provider(provider, settings).finish_activation(activation_id)


def cancel_activation(activation_id: str, provider: str | None = None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_sms_provider(provider, settings).cancel_activation(activation_id)