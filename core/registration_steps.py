# -*- coding: utf-8 -*-
"""
Registration Steps Definition
Defines all 12 steps in ChatGPT registration flow
"""
REGISTRATION_STEPS = [
    {
        "id": 1,
        "name": "获取 Providers",
        "description": "从 ChatGPT 获取认证提供商列表",
        "auto": True,
        "duration_estimate": 2
    },
    {
        "id": 2,
        "name": "获取 CSRF Token",
        "description": "获取跨站请求伪造令牌",
        "auto": True,
        "duration_estimate": 1
    },
    {
        "id": 3,
        "name": "发起 OAuth signin",
        "description": "向 OpenAI 发起 OAuth 登录请求",
        "auto": True,
        "duration_estimate": 2
    },
    {
        "id": 4,
        "name": "跟随 authorize URL",
        "description": "建立 auth.openai.com 的 cookies",
        "auto": True,
        "duration_estimate": 3
    },
    {
        "id": 5,
        "name": "等待邮箱验证码",
        "description": "等待用户输入邮箱验证码",
        "auto": False,
        "requires_input": "email_otp",
        "duration_estimate": 0
    },
    {
        "id": 6,
        "name": "获取 Sentinel Token",
        "description": "获取 authorize_continue 的 sentinel token",
        "auto": True,
        "duration_estimate": 1
    },
    {
        "id": 7,
        "name": "提交邮箱验证码",
        "description": "验证邮箱 OTP 代码",
        "auto": True,
        "duration_estimate": 2
    },
    {
        "id": 8,
        "name": "等待手机验证（可选）",
        "description": "等待用户输入手机号和验证码",
        "auto": False,
        "requires_input": "phone_otp",
        "optional": True,
        "duration_estimate": 0
    },
    {
        "id": 9,
        "name": "获取 OAuth Sentinel",
        "description": "获取 oauth_create_account 的 sentinel token",
        "auto": True,
        "duration_estimate": 1
    },
    {
        "id": 10,
        "name": "创建账号",
        "description": "提交用户信息完成注册",
        "auto": True,
        "duration_estimate": 3
    },
    {
        "id": 11,
        "name": "OAuth 回调",
        "description": "完成 OAuth 回调并拉取 accessToken",
        "auto": True,
        "duration_estimate": 5
    },
    {
        "id": 12,
        "name": "生成 CPA 文件",
        "description": "生成 CLIProxyAPI 认证文件",
        "auto": True,
        "duration_estimate": 1
    }
]

def get_step_by_id(step_id):
    for step in REGISTRATION_STEPS:
        if step["id"] == step_id:
            return step
    return None

def get_total_steps():
    return len(REGISTRATION_STEPS)

def get_step_name(step_id):
    step = get_step_by_id(step_id)
    return step["name"] if step else f"Step {step_id}"

def is_auto_step(step_id):
    step = get_step_by_id(step_id)
    return step["auto"] if step else True

def requires_user_input(step_id):
    step = get_step_by_id(step_id)
    return step.get("requires_input") if step else None