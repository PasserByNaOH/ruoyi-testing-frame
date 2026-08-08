"""
pytest 根级 conftest.py —— 基础设施 fixtures

Phase 1: SSH 隧道（Redis + MySQL 双端口转发）
Phase 3: base_url + redis_client（session 级，所有子模块继承）
"""

import allure
import pytest
import redis
from configparser import ConfigParser
from sshtunnel import SSHTunnelForwarder

from conf.setting import FILE_PATH
from utils.debugtalk import DebugTalk
from utils.recordlog import logs


def _read_config():
    """读取 conf/config.ini，返回 ConfigParser 对象。"""
    cf = ConfigParser()
    cf.read(FILE_PATH['CONFIG'], encoding='utf-8')
    return cf


@pytest.fixture(scope="session")
def ssh_tunnel():
    """
    建立 SSH 隧道，转发 Redis 6379 + MySQL 3306。
    session 级：整个测试会话只建一次，结束后自动 stop()。
    返回字典：{tunnel, redis_port, mysql_port}
    """
    cf = _read_config()

    ssh_host = cf.get("SSH", "host")
    ssh_port = cf.getint("SSH", "port")
    ssh_user = cf.get("SSH", "username")
    ssh_pwd  = cf.get("SSH", "password")

    redis_host = cf.get("REDIS", "host")
    redis_port = cf.getint("REDIS", "port")
    mysql_host = cf.get("MYSQL", "host")
    mysql_port = cf.getint("MYSQL", "port")

    tunnel = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=ssh_user,
        ssh_password=ssh_pwd,
        remote_bind_addresses=[
            (redis_host, redis_port),
            (mysql_host, mysql_port),
        ],
    )
    with allure.step("前置-SSH隧道"):
        tunnel.start()
        logs.info(f"SSH 隧道已建立 → Redis 本地端口: {tunnel.local_bind_ports[0]}, "
                  f"MySQL 本地端口: {tunnel.local_bind_ports[1]}")

    yield {
        "tunnel": tunnel,
        "redis_port": tunnel.local_bind_ports[0],
        "mysql_port": tunnel.local_bind_ports[1],
    }

    tunnel.stop()
    logs.info("SSH 隧道已关闭")


@pytest.fixture(scope="session")
def base_url():
    """服务器地址，所有 API 测试共用。"""
    cf = _read_config()
    return cf.get("api_envi", "host")


@pytest.fixture(scope="session")
def redis_client(ssh_tunnel):
    """
    SSH 隧道连接 Redis，注入 DebugTalk。
    session 级：只连一次，全局复用。
    """
    cf = _read_config()

    r = redis.Redis(
        host="127.0.0.1",
        port=ssh_tunnel["redis_port"],
        password=cf.get("REDIS", "password") or None,
        db=cf.getint("REDIS", "db"),
        decode_responses=True,
    )
    with allure.step("前置-Redis连接"):
        r.ping()
        logs.info("Redis 连接成功，注入 DebugTalk")
        DebugTalk.set_redis_client(r)

    yield r

    r.close()
    logs.info("Redis 连接已关闭")


# ═══════════════════════════════════════════════════════════
# Allure 报告钩子 —— epic / feature 自动映射
# ═══════════════════════════════════════════════════════════

def pytest_collection_modifyitems(items):
    """根据测试文件所在目录自动添加 epic + feature 标记。"""
    for item in items:
        item.add_marker(allure.epic("若依管理系统"))

        path = str(item.fspath)
        if "test_01_login" in path:
            item.add_marker(allure.feature("登录"))
        elif "test_02_user" in path:
            item.add_marker(allure.feature("用户管理"))
        elif "test_03_role" in path:
            item.add_marker(allure.feature("角色权限"))
        elif "test_04_user_excel" in path:
            item.add_marker(allure.feature("Excel导入导出"))
        elif "test_05_business" in path:
            item.add_marker(allure.feature("业务流程"))
