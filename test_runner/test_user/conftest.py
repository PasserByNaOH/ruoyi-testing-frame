"""
test_user/conftest.py —— 用户管理测试专用 fixtures

提供：
  db_connection       → session 级，走 SSH 隧道连 MySQL（autocommit=True，物理删除/DB验证用）
  clean_at_users      → session 级 autouse，启动/结束时清理 at_% 残留
  ensure_admin_login  → session 级 autouse，登录 admin → token 写入 runtime.yaml
"""

import pytest
import requests
from configparser import ConfigParser

from conf.setting import FILE_PATH
from utils.connection import ConnectMysql
from utils.debugtalk import DebugTalk
from utils.readyaml import write_runtime
from utils.recordlog import logs


def _read_config():
    cf = ConfigParser()
    cf.read(FILE_PATH['CONFIG'], encoding='utf-8')
    return cf


@pytest.fixture(scope="session")
def db_connection(ssh_tunnel):
    """依赖根 ssh_tunnel，走 SSH 隧道本地端口连 MySQL（autocommit=True）。"""
    cf = _read_config()
    db = ConnectMysql(
        host="127.0.0.1",
        port=ssh_tunnel["mysql_port"],
        user=cf.get("MYSQL", "username"),
        password=cf.get("MYSQL", "password"),
        database=cf.get("MYSQL", "database"),
    )
    logs.info("MySQL 连接成功（test_user）")

    yield db

    db.close()
    logs.info("MySQL 连接已关闭（test_user）")


def _delete_at_users(db):
    """物理删除所有 at_% 前缀的测试用户 + 单字符边界值用户（先子表后主表）。"""
    db.execute(
        "DELETE FROM sys_user_role WHERE user_id IN "
        "(SELECT user_id FROM sys_user WHERE user_name LIKE 'at\\_%' OR user_name = 'a')"
    )
    db.execute(
        "DELETE FROM sys_user_post WHERE user_id IN "
        "(SELECT user_id FROM sys_user WHERE user_name LIKE 'at\\_%' OR user_name = 'a')"
    )
    db.execute(
        "DELETE FROM sys_user WHERE user_name LIKE 'at\\_%' OR user_name = 'a'"
    )


@pytest.fixture(scope="session", autouse=True)
def clean_at_users(db_connection):
    """
    Session 启动时物理删除所有 at_% 残留用户（应对上次运行中断的情况）。
    Session 结束时再删一次，不留痕迹。
    ConnectMysql autocommit=True，每次 execute 即时生效，无需手动 commit。
    """
    _delete_at_users(db_connection)
    logs.info("已清理 at_% 残留用户（session 启动）")

    yield

    _delete_at_users(db_connection)
    logs.info("已清理 at_% 残留用户（session 结束）")


@pytest.fixture(scope="session", autouse=True)
def ensure_admin_login(base_url, redis_client):
    """
    Session 启动时用 admin 登录，token 写入 runtime.yaml。
    后续所有增删改查用例通过 inject_token() 自动获得 admin 权限。
    """
    cf = _read_config()
    admin_user = cf.get("admin", "username")
    admin_pwd = cf.get("admin", "password")

    # 1. 获取验证码
    captcha_resp = requests.get(
        f"{base_url}/captchaImage",
        headers={"Accept": "application/json"},
        timeout=10,
    ).json()
    uuid = captcha_resp["uuid"]

    # 2. 从 Redis 读取验证码答案
    code = DebugTalk().get_captcha_code(uuid)
    assert code is not None, f"admin 登录失败：验证码已过期，uuid={uuid}"

    # 3. 登录
    login_resp = requests.post(
        f"{base_url}/login",
        json={"username": admin_user, "password": admin_pwd, "uuid": uuid, "code": code},
        headers={"Content-Type": "application/json;charset=UTF-8"},
        timeout=10,
    )
    token = login_resp.json().get("token", "")
    assert token, f"admin 登录失败：未返回 token，响应: {login_resp.text}"

    # 4. 写入 runtime.yaml
    write_runtime({"token": token})
    logs.info(f"admin 登录成功，token 已写入 runtime.yaml")
