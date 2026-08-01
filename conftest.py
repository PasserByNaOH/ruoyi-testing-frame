"""
pytest 根级 conftest.py —— 基础设施 fixtures

Phase 1: SSH 隧道（Redis + MySQL 双端口转发）
"""

import pytest
from configparser import ConfigParser
from sshtunnel import SSHTunnelForwarder

from conf.setting import FILE_PATH
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
