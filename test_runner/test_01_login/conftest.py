"""
test_login/conftest.py —— 登录测试专用 fixtures

base_url、redis_client 已提至根 conftest.py，本文件只保留登录特有的 fixtures。
"""

import allure
import pytest

from utils.readyaml import clear_runtime
from utils.recordlog import logs
from test_runner.test_01_login.helpers import clean_pwd_error_count as _clean


@pytest.fixture(scope="session", autouse=True)
def clean_runtime_on_start():
    """session 开始时清空 runtime.yaml，防止上次运行的旧 token 残留。"""
    clear_runtime()
    logs.info("runtime.yaml 已清空（session 开始）")
    yield


@pytest.fixture(autouse=True)
def clean_pwd_error_count(redis_client):
    """
    每个登录用例跑完后，清掉所有账号的密码错误计数，保证用例之间互不干扰。

    具体逻辑与理由见 helpers.clean_pwd_error_count()（抽出去是为了可单测）。
    """
    yield
    _clean(redis_client)


# ═══════════════════════════════════════════════════════════
# Allure 钩子 —— story 按文件自动映射
# ═══════════════════════════════════════════════════════════

def pytest_collection_modifyitems(items):
    for item in items:
        path = str(item.fspath)
        if "test_login_success" in path:
            item.add_marker(allure.story("登录成功"))
        elif "test_login_fail" in path:
            item.add_marker(allure.story("登录失败"))
