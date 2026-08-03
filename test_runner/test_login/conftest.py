"""
test_login/conftest.py —— 登录测试专用 fixtures

base_url、redis_client 已提至根 conftest.py，本文件只保留登录特有的 fixtures。
"""

import pytest

from utils.readyaml import clear_runtime
from utils.recordlog import logs


@pytest.fixture(scope="session", autouse=True)
def clean_runtime_on_start():
    """session 开始时清空 runtime.yaml，防止上次运行的旧 token 残留。"""
    clear_runtime()
    logs.info("runtime.yaml 已清空（session 开始）")
    yield


@pytest.fixture(autouse=True)
def clean_pwd_error_count(redis_client):
    """每个测试后删除 LoginTestUser 的密码错误计数，保证用例间独立。"""
    yield
    redis_client.delete("pwd_err_cnt:LoginTestUser")
