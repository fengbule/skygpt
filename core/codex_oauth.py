# -*- coding: utf-8 -*-
"""
Codex / WHAM OAuth 导出模块。

目标：在已经完成 ChatGPT 注册并建立浏览器登录态后，
使用 Codex CLI 对应的 OAuth client_id + PKCE 流程，额外换取
可用于 Codex / CLIProxyAPI 的 access_token / refresh_token / id_token。
"""
import base64
import hashlib
import json
import logging
import re
import secrets
from urllib.parse import urlencode, urljoin, urlparse, parse_qs

from core.session import BrowserSession
from config import CODEX_CLIENT_ID, CODEX_SCOPE, CODEX_REDIRECT_URI

logger = logging.getLogger(__name__)

CODEX_AUTH_URL = "https://auth.openai.com/oauth/authorize"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_ORIGINATOR = "codex_cli_rs"
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    return _b64url_no_pad(hashlib.sha256(verifier.encode("ascii")).digest())


def _random_state() -> str:
    return secrets.token_hex(16)


def _decode_jwt_payload(token: str) -> dict:
    if not token or token.count(".") < 2:
        return {}
    payload = token.split(".")[1]
    payload += "=" * ((4 - len(payload) % 4) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except Exception:
        return {}


def _extract_uuid_like(value: str | None) -> str:
    if not value:
        return ""
    match = _UUID_RE.search(str(value))
    return match.group(0) if match else ""


def _token_client_id(token: str) -> str:
    payload = _decode_jwt_payload(token)
    return str(payload.get("client_id") or "")


def _token_summary(token: str) -> dict:
    payload = _decode_jwt_payload(token)
    auth = payload.get("https://api.openai.com/auth") or {}
    return {
        "client_id": payload.get("client_id"),
        "scp": payload.get("scp"),
        "sub": payload.get("sub"),
        "chatgpt_account_id": auth.get("chatgpt_account_id"),
        "chatgpt_account_user_id": auth.get("chatgpt_account_user_id"),
        "organizations": auth.get("organizations"),
    }


def _extract_workspace_id(session: BrowserSession) -> str | None:
    """
    从 auth.openai.com 登录态 cookie 中尽量提取 workspace id。
    某些 Codex consent 流程需要先选择 workspace 才会继续签发 code。
    """
    cookie_candidates = [
        session.session.cookies.get("oai-client-auth-session"),
        session.session.cookies.get("oai-client-auth_session"),
    ]
    for cookie_value in cookie_candidates:
        if not cookie_value:
            continue
        parts = cookie_value.split(".")
        for idx in (1, 0):
            if idx >= len(parts):
                continue
            try:
                payload = parts[idx]
                payload += "=" * ((4 - len(payload) % 4) % 4)
                data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
            except Exception:
                continue
            workspaces = data.get("workspaces")
            if isinstance(workspaces, list) and workspaces:
                ws = workspaces[0]
                if isinstance(ws, dict) and ws.get("id"):
                    return ws["id"]
            if isinstance(workspaces, dict) and workspaces.get("id"):
                return workspaces["id"]
    return None


def _extract_account_id(access_token: str, id_token: str, session_info: dict | None = None) -> str:
    """
    优先提取 Codex 文件期望的账号 ID。
    经验上 `session_info.account.id` 更接近 Codex 侧需要的 uuid，
    再回退到 token claims 中的 chatgpt_account_id。
    """
    for token in (id_token, access_token):
        payload = _decode_jwt_payload(token)
        auth = payload.get("https://api.openai.com/auth") or {}
        account_id = _extract_uuid_like(auth.get("chatgpt_account_id"))
        if account_id:
            return account_id
        account_id = _extract_uuid_like(auth.get("chatgpt_account_user_id"))
        if account_id:
            return account_id

    if session_info:
        account = session_info.get("account") or {}
        account_id = _extract_uuid_like(account.get("id"))
        if account_id:
            return account_id

    return ""


def validate_codex_token_set(token_data: dict) -> tuple[bool, str]:
    access_token = (token_data.get("access_token") or "").strip()
    refresh_token = (token_data.get("refresh_token") or "").strip()
    id_token = (token_data.get("id_token") or "").strip()

    if not access_token:
        return False, "missing access_token"

    client_id = _token_client_id(access_token)
    if client_id != CODEX_CLIENT_ID:
        return False, f"unexpected access_token client_id: {client_id or '<empty>'}"

    if not refresh_token:
        return False, "missing refresh_token"

    if not id_token:
        return False, "missing id_token"

    return True, "ok"


def _build_authorize_params(state: str, challenge: str) -> dict:
    return {
        "client_id": CODEX_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": CODEX_REDIRECT_URI,
        "scope": CODEX_SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "codex_cli_simplified_flow": "true",
        "id_token_add_organizations": "true",
        "prompt": "login",
        "originator": CODEX_ORIGINATOR,
    }


def prepare_codex_oauth_request() -> dict:
    state = _random_state()
    verifier = _pkce_verifier()
    challenge = _pkce_challenge(verifier)
    params = _build_authorize_params(state, challenge)
    authorization_url = f"{CODEX_AUTH_URL}?{urlencode(params)}"
    return {
        "state": state,
        "code_verifier": verifier,
        "code_challenge": challenge,
        "authorization_url": authorization_url,
        "redirect_uri": CODEX_REDIRECT_URI,
    }


def exchange_codex_callback_url(
    callback_url: str,
    code_verifier: str,
    expected_state: str,
    session_info: dict | None = None,
) -> dict:
    callback_url = (callback_url or "").strip()
    if not callback_url:
        raise RuntimeError("Codex callback URL 为空")

    parsed = urlparse(callback_url)
    qs = parse_qs(parsed.query)
    error_code = qs.get("error", [""])[0]
    error_description = qs.get("error_description", [""])[0]
    if error_code:
        raise RuntimeError(
            f"Codex OAuth callback 返回错误: {error_code}: {error_description or '<empty>'}"
        )

    code = qs.get("code", [""])[0]
    got_state = qs.get("state", [""])[0]
    if not code:
        raise RuntimeError(f"Codex callback URL 缺少 code: {callback_url[:300]}")
    if got_state != expected_state:
        raise RuntimeError(f"Codex callback state 不匹配: expected={expected_state}, got={got_state}")

    token_resp = _exchange_code_for_tokens(code, code_verifier)
    logger.info(
        "[CodexOAuth] manual callback token fields: access=%s refresh=%s id=%s keys=%s",
        bool(token_resp.get("access_token")),
        bool(token_resp.get("refresh_token")),
        bool(token_resp.get("id_token")),
        sorted(token_resp.keys()),
    )
    access_token = (token_resp.get("access_token") or "").strip()
    refresh_token = (token_resp.get("refresh_token") or "").strip()
    id_token = (token_resp.get("id_token") or "").strip()
    is_valid, reason = validate_codex_token_set({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
    })
    if not is_valid:
        raise RuntimeError(f"Codex manual callback token 无效: {reason}")
    account_id = _extract_account_id(access_token, id_token, session_info=session_info)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "account_id": account_id,
    }


def _exchange_code_for_tokens(code: str, verifier: str) -> dict:
    import urllib.request
    import urllib.parse

    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": CODEX_CLIENT_ID,
        "code": code,
        "redirect_uri": CODEX_REDIRECT_URI,
        "code_verifier": verifier,
    }).encode("utf-8")

    req = urllib.request.Request(
        CODEX_TOKEN_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def acquire_codex_tokens(session: BrowserSession, session_info: dict | None = None) -> dict:
    """
    在当前已登录的 auth.openai.com / chatgpt.com 会话上，走一遍 Codex CLI OAuth。

    返回：
        {
            access_token,
            refresh_token,
            id_token,
            account_id,
        }
    """
    request_data = prepare_codex_oauth_request()
    state = request_data["state"]
    verifier = request_data["code_verifier"]
    current_url = request_data["authorization_url"]
    headers = session.get_auth_navigate_headers(referer="https://chatgpt.com/")

    logger.info("[CodexOAuth] 开始获取 Codex OAuth 凭据")
    logger.debug(f"[CodexOAuth] authorize url: {current_url}")

    for step in range(1, 16):
        logger.info(f"[CodexOAuth] 跟随授权链路，第 {step} 跳")
        resp = session.get(current_url, headers=headers, allow_redirects=False)
        logger.info(
            "[CodexOAuth] step=%s status=%s url=%s location=%s content_type=%s",
            step,
            resp.status_code,
            resp.url or current_url,
            resp.headers.get("Location", ""),
            resp.headers.get("Content-Type", ""),
        )

        location = resp.headers.get("Location")
        if location:
            next_url = urljoin(current_url, location)
            logger.debug(f"[CodexOAuth] redirect -> {next_url}")
            if next_url.startswith(CODEX_REDIRECT_URI):
                parsed = urlparse(next_url)
                qs = parse_qs(parsed.query)
                code = qs.get("code", [""])[0]
                got_state = qs.get("state", [""])[0]
                if not code:
                    raise RuntimeError(f"Codex 回调 URL 缺少 code: {next_url}")
                if got_state != state:
                    raise RuntimeError("Codex OAuth state 校验失败")

                token_resp = _exchange_code_for_tokens(code, verifier)
                logger.info(
                    "[CodexOAuth] token exchange fields: access=%s refresh=%s id=%s keys=%s",
                    bool(token_resp.get("access_token")),
                    bool(token_resp.get("refresh_token")),
                    bool(token_resp.get("id_token")),
                    sorted(token_resp.keys()),
                )
                access_token = (token_resp.get("access_token") or "").strip()
                refresh_token = (token_resp.get("refresh_token") or "").strip()
                id_token = (token_resp.get("id_token") or "").strip()
                if not access_token:
                    raise RuntimeError(f"Codex token 交换缺少 access_token: {token_resp}")
                logger.info("[CodexOAuth] access token summary: %s", _token_summary(access_token))
                if id_token:
                    logger.info("[CodexOAuth] id token summary: %s", _token_summary(id_token))
                is_valid, reason = validate_codex_token_set({
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "id_token": id_token,
                })
                if not is_valid:
                    raise RuntimeError(f"Codex token 交换结果无效: {reason}")
                account_id = _extract_account_id(access_token, id_token, session_info=session_info)
                logger.info("[CodexOAuth] 已成功换取 Codex OAuth 凭据")
                return {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "id_token": id_token,
                    "account_id": account_id,
                }
            current_url = next_url
            continue

        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            data = resp.json()
            logger.info("[CodexOAuth] json response keys: %s", sorted(data.keys()))
            continue_url = data.get("continue_url")
            if continue_url:
                current_url = urljoin(current_url, continue_url)
                continue

        if "sign-in-with-chatgpt/codex/consent" in (resp.url or current_url):
            ws_id = _extract_workspace_id(session)
            if not ws_id:
                raise RuntimeError("Codex consent 阶段未能提取 workspace_id")
            logger.info(f"[CodexOAuth] 选择 workspace: {ws_id}")
            select_resp = session.post(
                "https://auth.openai.com/api/accounts/workspace/select",
                headers=session.get_auth_headers(referer=resp.url or current_url),
                data=json.dumps({"workspace_id": ws_id}),
                allow_redirects=False,
            )
            logger.info(
                "[CodexOAuth] workspace/select status=%s location=%s content_type=%s body=%s",
                select_resp.status_code,
                select_resp.headers.get("Location", ""),
                select_resp.headers.get("Content-Type", ""),
                select_resp.text[:300],
            )
            select_location = select_resp.headers.get("Location")
            if select_location:
                current_url = urljoin(current_url, select_location)
                continue
            if "application/json" in select_resp.headers.get("Content-Type", ""):
                select_data = select_resp.json()
                if select_data.get("continue_url"):
                    current_url = urljoin(current_url, select_data["continue_url"])
                    continue
            raise RuntimeError(f"workspace/select 未返回可继续 URL: {select_resp.text[:200]}")

        raise RuntimeError(
            f"Codex OAuth 授权链路中断: status={resp.status_code}, url={resp.url or current_url}"
        )

    raise RuntimeError("Codex OAuth 跟随跳转次数过多，未能拿到 callback code")