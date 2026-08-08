"""
test_business/conftest.py —— 业务流程测试专用 fixtures

提供：
  db_connection       → session 级，SSH 隧道连 MySQL（autocommit=True）
  clean_at_test_data  → session 级 autouse，启动/结束时清理 at_% 用户+角色残留
  ensure_admin_login  → session 级 autouse，admin → runtime.yaml["token"]
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
    cf.read(FILE_PATH["CONFIG"], encoding="utf-8")
    return cf


@pytest.fixture(scope="session")
def db_connection(ssh_tunnel):
    cf = _read_config()
    db = ConnectMysql(
        host="127.0.0.1",
        port=ssh_tunnel["mysql_port"],
        user=cf.get("MYSQL", "username"),
        password=cf.get("MYSQL", "password"),
        database=cf.get("MYSQL", "database"),
    )
    logs.info("MySQL 连接成功（test_business）")
    yield db
    db.close()
    logs.info("MySQL 连接已关闭（test_business）")


def _delete_at_users(db):
    db.execute(
        "DELETE FROM sys_user_role WHERE user_id IN "
        "(SELECT user_id FROM sys_user WHERE user_name LIKE 'at\\_%')"
    )
    db.execute(
        "DELETE FROM sys_user_post WHERE user_id IN "
        "(SELECT user_id FROM sys_user WHERE user_name LIKE 'at\\_%')"
    )
    db.execute(
        "DELETE FROM sys_user WHERE user_name LIKE 'at\\_%'"
    )


def _delete_at_roles(db):
    db.execute(
        "DELETE FROM sys_user_role WHERE role_id IN "
        "(SELECT role_id FROM sys_role WHERE role_name LIKE 'at\\_%')"
    )
    db.execute(
        "DELETE FROM sys_role_menu WHERE role_id IN "
        "(SELECT role_id FROM sys_role WHERE role_name LIKE 'at\\_%')"
    )
    db.execute(
        "DELETE FROM sys_role_dept WHERE role_id IN "
        "(SELECT role_id FROM sys_role WHERE role_name LIKE 'at\\_%')"
    )
    db.execute(
        "DELETE FROM sys_role WHERE role_name LIKE 'at\\_%'"
    )


@pytest.fixture(scope="session", autouse=True)
def clean_at_test_data(db_connection):
    """Session 启动/结束时物理删除 at_% 用户+角色残留（子表→主表顺序）。"""
    _delete_at_users(db_connection)
    _delete_at_roles(db_connection)
    logs.info("已清理 at_% 用户+角色残留（session 启动）")
    yield
    _delete_at_users(db_connection)
    _delete_at_roles(db_connection)
    logs.info("已清理 at_% 用户+角色残留（session 结束）")


@pytest.fixture(scope="session", autouse=True)
def ensure_admin_login(base_url, redis_client):
    cf = _read_config()
    admin_user = cf.get("admin", "username")
    admin_pwd = cf.get("admin", "password")

    captcha_resp = requests.get(
        f"{base_url}/captchaImage",
        headers={"Accept": "application/json"},
        timeout=10,
    ).json()
    uuid = captcha_resp["uuid"]

    code = DebugTalk().get_captcha_code(uuid)
    assert code is not None, f"admin 登录失败：验证码已过期，uuid={uuid}"

    login_resp = requests.post(
        f"{base_url}/login",
        json={"username": admin_user, "password": admin_pwd, "uuid": uuid, "code": code},
        headers={"Content-Type": "application/json;charset=UTF-8"},
        timeout=10,
    )
    token = login_resp.json().get("token", "")
    assert token, f"admin 登录失败：未返回 token，响应: {login_resp.text}"

    write_runtime({"token": token})
    logs.info("admin 登录成功，token 已写入 runtime.yaml")
