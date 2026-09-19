"""
test_login/helpers.py —— 登录测试可复用工具

供 test_login_success / test_login_fail 共用，避免重复代码。
"""

import requests

from utils.debugtalk import DebugTalk
from utils.recordlog import logs


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


def verify_redis(redis_client, case):
    """
    校验用例声明的 Redis 状态变化（YAML 里的 redis_verify 块）。

    为什么需要它：锁定类用例的"结果"不全在 HTTP 响应里——
      ① 第 5 次错误抛的是"密码错误"，真正的锁定要到下一次请求才体现；
      ② 锁定倒计时（10 分钟 TTL）只在"第 5 次错误"那一刻由若依写入
         （setCacheObject(key, 5, lockTime, MINUTES)），不查 Redis 就永远验证不到。

    支持的声明：
      counter:      期望错误计数值
      ttl_between:  [下界, 上界] —— 期望剩余倒计时落在该区间内
    """
    verify = case.get("redis_verify")
    if not verify:
        return

    username = case["json"]["username"]
    key = "pwd_err_cnt:" + username

    if "counter" in verify:
        expected = str(verify["counter"])
        # 复用 DebugTalk 的取值逻辑（若依用 FastJson 序列化，需要还原类型）
        actual = DebugTalk().get_pwd_error_count(username)
        assert actual == expected, (
            f"Redis 错误计数不符\n"
            f"  key:  {key}\n"
            f"  实际: {actual!r}\n"
            f"  预期: {expected!r}"
        )
        logs.info(f"Redis 校验通过: {key} = {actual}")

    if "ttl_between" in verify:
        low, high = verify["ttl_between"]
        ttl = redis_client.ttl(key)
        assert low < ttl <= high, (
            f"锁定倒计时超出预期区间\n"
            f"  key:  {key}\n"
            f"  实际: {ttl} 秒\n"
            f"  预期: {low} < ttl <= {high}\n"
            f"  （-1 = key 存在但没设过期时间；-2 = key 不存在）"
        )
        logs.info(f"Redis 校验通过: {key} 剩余倒计时 {ttl} 秒")
