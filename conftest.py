"""
pytest 根级 conftest.py —— 基础设施 fixtures

Phase 1: SSH 隧道（Redis + MySQL 双端口转发）
Phase 3: base_url + redis_client（session 级，所有子模块继承）
"""

import allure
import pytest
import redis
import requests
from configparser import ConfigParser
from redis.backoff import NoBackoff
from redis.retry import Retry
from sshtunnel import SSHTunnelForwarder

from conf.setting import FILE_PATH
from utils.debugtalk import DebugTalk
from utils.recordlog import logs

# 探活用的短超时（秒）。不用 conf.setting 的 API_TIMEOUT（60 秒）——
# 那是给业务请求的；"探查服务在不在"不该让人等一分钟。
PROBE_TIMEOUT = 10

# 连接阶段的超时也调短一点：连一个关着的端口，系统 2 秒就返回"拒绝"，
# 没必要按 PROBE_TIMEOUT 干等。
PROBE_CONNECT_TIMEOUT = 2

# redis-py 8.x 默认会**自动重试**（默认 Retry + 指数退避），
# 探活只想知道"现在通不通"，重试会把 2 秒的连接失败放大成 25 秒以上。
PROBE_REDIS_RETRY = Retry(NoBackoff(), 0)


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
# 开跑前的服务探活（Phase 1 / 1.9）
# ═══════════════════════════════════════════════════════════

def probe_backend(base_url, timeout=PROBE_TIMEOUT):
    """
    探一下后端应用是否活着。

    返回 (ok, reason)：
        (True,  None)   —— 通了
        (False, "原因") —— 没通，原因可直接给人看

    选 `/captchaImage` 是因为它**不需要认证、不需要验证码、也不改任何数据**
    （Phase 0.2 已手工验证它返回 200）。

    **本函数绝不抛异常**：它只负责"报告观察到什么"，至于要不要因此中止，
    由调用方决定（异常会毁掉这个分工）。
    """
    url = base_url.rstrip("/") + "/captchaImage"
    try:
        resp = requests.get(
            url, headers={"Accept": "application/json"},
            timeout=(PROBE_CONNECT_TIMEOUT, timeout), verify=False,
        )
        if resp.status_code == 200:
            return True, None
        return False, f"{url} 返回 HTTP {resp.status_code}（预期 200）"
    except requests.RequestException as e:
        # 连接被拒 / 超时 / DNS 失败 / 代理错误 都归一成一句人话
        return False, f"{url} 请求失败：{type(e).__name__}: {e}"


def probe_redis(port, password=None, db=0, timeout=PROBE_TIMEOUT):
    """
    探一下 Redis 是否活着（经 SSH 隧道转发到本地端口）。

    返回 (ok, reason)，同样**不抛异常**。
    """
    client = redis.Redis(
        host="127.0.0.1", port=port, password=password or None, db=db,
        decode_responses=True,
        socket_connect_timeout=min(timeout, PROBE_CONNECT_TIMEOUT),
        socket_timeout=timeout,
        # 关掉 redis-py 默认的自动重试：探活只问"现在通不通"，
        # 重试只会把失败从 2 秒拖成 25 秒以上（实测）
        retry=PROBE_REDIS_RETRY,
        retry_on_error=[],
    )
    try:
        client.ping()
        return True, None
    except Exception as e:
        return False, f"Redis(127.0.0.1:{port}) 连接失败：{type(e).__name__}: {e}"
    finally:
        try:
            client.close()
        except Exception:
            pass


@pytest.fixture(scope="session", autouse=True)
def check_services_alive(ssh_tunnel, base_url):
    """
    开跑前确认"背后的东西都在"，不通就**整体中止并说清是哪一样不通**。

    为什么需要它：框架原先默认"背后一切都是好的"，服务器挂掉时**不会有一句
    "服务不可用"**，而是每条用例各报一次连接错误（实测一次是 89 条一模一样的
    SSH 报错）—— 得自己从里面推断是环境问题而不是用例问题。

    注意：**框架对硬故障本来就是正确失败的**（sendrequest 的 except 全部 raise），
    所以这里不是"加容错"，只是把"83 条吵你"换成"一句话说清"。

    为什么用 pytest.exit 而不是抛异常 / skip：
        抛异常 → 每条用例各自 error 一次，还是刷屏；
        skip  → 每条用例各自 skip 一次，还是刷屏；
        pytest.exit → **整体中止**，只输出这一段原因。

    探活范围：SSH 隧道（本 fixture 依赖 ssh_tunnel，隧道建不起来这里根本到不了）
    ＋ 后端应用 ＋ Redis。一次覆盖三样。
    """
    logs.info("开跑前探活：检查后端与 Redis 是否可用")

    ok, reason = probe_backend(base_url)
    if not ok:
        pytest.exit(
            "被测服务不可用，已中止本次运行（不是用例失败，是环境没就绪）\n"
            f"  后端: {reason}\n"
            "  提示: 服务器重启后需要手工恢复 —— "
            "docker start ruoyi-mysql ruoyi-redis，再启动 ruoyi-admin",
            returncode=1,
        )

    cf = _read_config()
    ok, reason = probe_redis(
        ssh_tunnel["redis_port"],
        password=cf.get("REDIS", "password"),
        db=cf.getint("REDIS", "db"),
    )
    if not ok:
        pytest.exit(
            "被测服务不可用，已中止本次运行（不是用例失败，是环境没就绪）\n"
            f"  Redis: {reason}",
            returncode=1,
        )

    logs.info("探活通过：后端与 Redis 均可用，开始跑用例")


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
