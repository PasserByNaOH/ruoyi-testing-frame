"""
test_login/helpers.py —— 登录测试可复用工具

供 test_login_success / test_login_fail 共用，避免重复代码。
"""

import requests
from utils.debugtalk import DebugTalk


def prepare_captcha(base_url, mode, data):
    """
    根据 captcha_mode 将 uuid 和 code 填入 data（原地修改）。

    valid     → GET /captchaImage 拿 uuid + Redis 取正确 code
    wrong     → GET /captchaImage 拿 uuid，code 保留 YAML 给的假值
    fake_uuid → 什么都不做（YAML 已带假 uuid + code）
    missing   → 什么都不做（YAML 只带 uuid，无 code）
    skip      → 什么都不做（不需要验证码的接口）
    """
    if mode in ("valid", "wrong"):
        captcha_resp = requests.get(
            f"{base_url}/captchaImage",
            headers={"Accept": "application/json"},
            timeout=10,
        ).json()
        data["uuid"] = captcha_resp["uuid"]

        if mode == "valid":
            code = DebugTalk().get_captcha_code(data["uuid"])
            assert code is not None, f"验证码已过期，uuid={data['uuid']}"
            data["code"] = code
        # mode == "wrong": code 保留 YAML 的假值

    # fake_uuid / missing / skip → 不调接口
    return data


def apply_setup(case, redis_client):
    """
    测试前执行 YAML 中 setup 块的操作。
    当前支持 setup.redis → redis_client.set(key, value)。
    """
    setup = case.get("setup", {})
    for key, value in setup.get("redis", {}).items():
        redis_client.set(key, value)
