# -*- coding: utf-8 -*-
"""
注册成功后的"自动触发 flow"配置。

注册流程结束后会用拿到的 access_token 调用一次远端 flow 启动接口
（fire-and-forget，不等结果，不影响注册主流程）。

如要临时关闭，把 ENABLE_FLOW_TRIGGER 改成 False 即可。
"""

# 总开关
ENABLE_FLOW_TRIGGER = False

# 目标接口
FLOW_TRIGGER_URL = "http://162.211.183.196:8888/api/flows/from-token"

# Bearer 令牌（写到 Authorization 头）
FLOW_TRIGGER_BEARER = "Zyz44944"

# Cookie（保留与抓包一致即可；服务端校验 plus_admin_session）
FLOW_TRIGGER_COOKIE = (
    "http_Path=%2Fwww%2Fwwwroot%2Fplus-subai; "
    "plus_admin_session=1778640218.60df00697a334e11ad7608a5eb883e1dce3d0c7d34452804582ca20245fe3e03"
)

# 请求体模板。运行时会把 access_token 字段替换成本次注册成功的 token，
# 其他字段保持原样发送。
FLOW_TRIGGER_PAYLOAD = {
    "agent_id": "",
    "unlink_after_success": True,
    "plan_name": "chatgptplusplan",
    "ui_mode": "hosted",
    "region": "ID",
    "workspace_name": "MyTeam",
    "seat_quantity": 5,
    "access_token": "",  # 由 trigger_flow() 在调用时填入
}

# 单次请求超时（秒）。设短一点，反正 fire-and-forget。
FLOW_TRIGGER_TIMEOUT = 10
