"""
test_login_fail.py —— 登录无效等价类测试（13 条）

覆盖三层防线：
  ① 验证码层 — 错误验证码、过期验证码、code缺失
  ② loginPreCheck 前置校验层 — 空用户名、空密码、密码<5位、密码>20位
  ③ authenticate 认证层 — 密码错误、用户不存在、计数 4→5 跨阈值锁定、锁定后正确密码、停用、删除

其中"5次错误触发锁定"是**阈值边界**用例：预置计数 4，本条请求是第 5 次。
  - HTTP 侧断言"密码错误"且**没有**锁定字样 → 证明阈值 > 4
  - Redis 侧断言计数变成 5、倒计时落进 500~600 秒 → 证明第 5 次真的跨过了阈值并挂上了锁定时长
  配合下一条"锁定后正确密码登录"（计数 5 → 被拒）→ 阈值 ≤ 5，两点夹出"阈值 = 5"
"""

import pytest
import os

from core.apiutil import ApiEngine
from utils.readyaml import get_testcase_yaml, FILE_PATH
from test_runner.test_01_login.helpers import prepare_captcha, apply_setup, verify_redis


# 加载测试案例yaml
YAML_PATH = os.path.join(FILE_PATH["YAML"], "ruoyi", "login", "login_fail.yaml")
yaml_data = get_testcase_yaml(YAML_PATH)


# 测试流程
@pytest.mark.parametrize(
    "base_info, case",
    yaml_data,
    ids=[c[1]["case_name"] for c in yaml_data],
)
def test_login_fail(base_url, redis_client, base_info, case):
    # 1. setup（预设 Redis 计数等）
    apply_setup(case, redis_client)

    # 2. 准备请求体 + 验证码
    data = dict(case["json"])
    prepare_captcha(base_url=base_url, mode=case.get("captcha_mode", "valid"), data=data)
    case["json"] = data

    # 3. 执行
    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))

    # 4. Redis 状态校验（用例用 redis_verify 声明，当前只有"5次错误触发锁定"用到）
    verify_redis(redis_client, case)
