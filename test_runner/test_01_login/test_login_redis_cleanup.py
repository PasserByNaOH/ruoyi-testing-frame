"""
test_login_redis_cleanup.py —— 登录用例的密码错误计数清理（Phase 1 / 1.8）

覆盖两件事：

  ① 清理逻辑本身（单元测试，用假 Redis）：
     `helpers.clean_pwd_error_count()` 必须按下标清掉**所有**账号的计数，
     而不是只清某一个写死的用户名。

  ② "哪些登录场景会写计数"这个事实（集成测试，用真实 Redis）：
     实测结论 —— **只有"用户存在且密码错误"才会写计数**；
     用户不存在 / 停用 / 已删除 / 空用户名都**不会**写。

     ⚠️ 这个事实必须固定下来，因为它解释了"为什么按下标清理"这件事：
     现在只有一个账号会产生残留，但**换个账号写错密码就会漏清**。

跑法：
    pytest test_runner/test_01_login/test_login_redis_cleanup.py -q
（集成测试需要 SSH 隧道，会自动建立；单测部分不需要）
"""

import pytest

from test_runner.test_01_login.helpers import (
    clean_pwd_error_count,
    prepare_captcha,
)
from utils.debugtalk import DebugTalk


# ═══════════════════════════════════════════════════════════
# 一、清理逻辑（假 Redis，不需要服务器）
# ═══════════════════════════════════════════════════════════

class FakeRedis:
    """只实现 clean_pwd_error_count 用到的三个方法。"""

    def __init__(self, keys=()):
        self.store = {k: "1" for k in keys}
        self.scan_patterns = []
        self.deleted = []

    def scan_iter(self, match=None):
        self.scan_patterns.append(match)
        prefix = (match or "").rstrip("*")
        return iter([k for k in list(self.store) if k.startswith(prefix)])

    def delete(self, *keys):
        self.deleted.extend(keys)
        for k in keys:
            self.store.pop(k, None)

    def exists(self, key):
        return 1 if key in self.store else 0


def test_cleans_all_accounts_not_just_one():
    """★ 核心：多个账号的残留要一次清干净（旧实现只删 LoginTestUser）。"""
    redis = FakeRedis([
        "pwd_err_cnt:LoginTestUser",
        "pwd_err_cnt:no_such_user_xyz",
        "pwd_err_cnt:someone_else",
    ])
    removed = clean_pwd_error_count(redis)

    assert sorted(removed) == sorted([
        "pwd_err_cnt:LoginTestUser",
        "pwd_err_cnt:no_such_user_xyz",
        "pwd_err_cnt:someone_else",
    ])
    assert redis.store == {}, "所有计数都应被清掉"


def test_uses_prefix_pattern_not_hardcoded_username():
    """清理必须按前缀扫描，而不是按某个写死的用户名。"""
    redis = FakeRedis(["pwd_err_cnt:whatever"])
    clean_pwd_error_count(redis)

    expected = DebugTalk.PWD_ERR_KEY_PREFIX + "*"
    assert redis.scan_patterns == [expected]
    assert expected == "pwd_err_cnt:*"


def test_does_not_touch_other_key_prefixes():
    """只清计数，别误伤验证码 / token 等其他 key。"""
    redis = FakeRedis([
        "pwd_err_cnt:LoginTestUser",
        "captcha_codes:abc-123",
        "login_tokens:def-456",
    ])
    clean_pwd_error_count(redis)

    assert redis.store == {
        "captcha_codes:abc-123": "1",
        "login_tokens:def-456": "1",
    }


def test_no_leftover_is_a_noop():
    """没有残留时不调用 delete（避免空参数报错）。"""
    redis = FakeRedis([])
    assert clean_pwd_error_count(redis) == []
    assert redis.deleted == []


# ═══════════════════════════════════════════════════════════
# 二、"哪些场景会写计数"的事实（真实 Redis + 真实接口）
# ═══════════════════════════════════════════════════════════

def _login(base_url, username, password):
    """复刻 helpers.prepare_captcha(mode='valid') + POST /login 的真实链路。"""
    import requests

    payload = {"username": username, "password": password}
    prepare_captcha(base_url=base_url, mode="valid", data=payload)
    return requests.post(
        f"{base_url}/login",
        json=payload,
        headers={"Content-Type": "application/json;charset=UTF-8"},
        timeout=10,
    )


def test_nonexistent_user_does_not_write_counter(base_url, redis_client):
    """
    ★ 用户不存在时**不会**留下计数。

    原因（源码）：`UserDetailsServiceImpl.loadUserByUsername()` 在查到
    "用户为空"时就抛 ServiceException，**走不到** `passwordService.validate(user)`；
    而写计数的那行 `setCacheObject(pwd_err_cnt:username, ...)` 就在 validate 里。
    所以给一个数据库里没有的用户名不可能产生计数 —— 保护机制是"密码错误次数"，
    不是"无效请求次数"。
    """
    username = "no_such_user_xyz"
    key = DebugTalk.PWD_ERR_KEY_PREFIX + username
    redis_client.delete(key)

    resp = _login(base_url, username, "123456")

    assert resp.status_code == 200
    assert redis_client.exists(key) == 0, (
        f"用户不存在却写了计数 {key} —— 说明若依改了认证流程的顺序，"
        f"请重新核对 SysPasswordService.validate 的调用时机"
    )


def test_wrong_password_does_write_counter(base_url, redis_client):
    """
    对照组：**用户存在且密码错误**才会写计数。

    这条同时说明了为什么"按固定用户名清理"迟早会漏 ——
    换一个存在但密码写错的账号，就会产生新的残留。

    注意密码必须落在 5~20 字符之间：`loginPreCheck` 对长度有前置校验，
    太短/太长会在**写计数之前**就被拒（那样就测不到本意了）。
    """
    username = "LoginTestUser"
    password = "wrong_password"          # 14 字符，长度合法但内容错误
    key = DebugTalk.PWD_ERR_KEY_PREFIX + username
    redis_client.delete(key)

    resp = _login(base_url, username, password)

    assert resp.status_code == 200
    assert redis_client.exists(key) == 1, "密码错误却未写计数，与源码不符"
    assert redis_client.get(key) == "1"
