"""
test_login_success.py —— 登录有效等价类测试（2 条）

LOGIN-01 正常登录 → 提取 token 到 runtime.yaml
LOGIN-02 Token 验证 → 调 /getInfo，验证 Redis 写入
"""

import pytest
import os

from core.apiutil import ApiEngine
from utils.readyaml import get_testcase_yaml, FILE_PATH
from test_runner.test_01_login.helpers import prepare_captcha


# 加载测试案例yaml
YAML_PATH = os.path.join(FILE_PATH["YAML"], "ruoyi", "login", "login_success.yaml")
yaml_data = get_testcase_yaml(YAML_PATH)


# 测试流程
@pytest.mark.parametrize(
    "base_info, case",
    yaml_data,
    ids=[c[1]["case_name"] for c in yaml_data],
)
def test_login_success(base_url, redis_client, base_info, case):
    """
    base_url     — conftest fixture，服务器地址
    redis_client — conftest fixture，已被清理（声明它以触发 autouse 清理）
    """
    captcha_mode = case.get("captcha_mode", "valid")
    if captcha_mode != "skip":
        data = dict(case["json"])
        prepare_captcha(base_url=base_url, mode=captcha_mode, data=data)
        case["json"] = data

    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))
