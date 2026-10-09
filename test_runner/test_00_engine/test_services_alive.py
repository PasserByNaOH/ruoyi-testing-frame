"""
test_services_alive.py —— 开跑前服务探活的单元测试（Phase 1 / 1.9）

覆盖根 conftest.py 的 probe_backend / probe_redis：

    - 服务正常时返回 (True, None)
    - 服务不可达时返回 (False, 可读原因)，**绝不抛异常**
      （抛异常会毁掉"探活只负责报告、调用方决定是否中止"的分工）
    - 返回码非 200 时也要判为不可用

为什么要专门测"不可达"：这是本项存在的唯一理由 —— 服务器挂掉时要给出
*一句人话*，而不是让 83 条用例各报一次连接错误。而"不可达"完全可以离线造
（探一个没人监听的端口即可），不必真把服务器搞挂。

这里的 1 号端口（tcpmux）几乎不可能有服务监听，是标准的"关着的门"。

跑法：
    pytest test_runner/test_00_engine/test_services_alive.py -q
"""

import socket
import time

import pytest

from conftest import PROBE_TIMEOUT, probe_backend, probe_redis

# 探"关着的门"用的地址：127.0.0.1:1 通常无人监听，连上去立刻被拒
UNREACHABLE = "http://127.0.0.1:1"
UNREACHABLE_PORT = 1


def test_unreachable_port_is_actually_closed():
    """先证明这个端口真的是关着的，否则下面的用例就失去意义。"""
    with socket.socket() as s:
        s.settimeout(2)
        with pytest.raises(OSError):
            s.connect(("127.0.0.1", UNREACHABLE_PORT))


# ═══════════════════════════════════════════════════════════
# probe_backend
# ═══════════════════════════════════════════════════════════

def test_probe_backend_success():
    """真实环境：后端活着 → (True, None)。"""
    from configparser import ConfigParser

    from conf.setting import FILE_PATH

    cf = ConfigParser()
    cf.read(FILE_PATH["CONFIG"], encoding="utf-8")
    base_url = cf.get("api_envi", "host")

    ok, reason = probe_backend(base_url)
    assert ok is True, f"探活失败，但服务应该是活的：{reason}"
    assert reason is None


def test_probe_backend_unreachable_returns_reason():
    """
    ★ 服务器挂了：必须返回可读原因，且不抛异常。

    顺带验证 base_url 末尾多余斜杠不会拼出 `//captchaImage`。
    这两点合成一条，是为了少探一次"关着的端口"——每次那样的探测都要等
    TCP 超时（约 2 秒），本文件已经有 3 次，不宜再多。
    """
    ok, reason = probe_backend(UNREACHABLE + "/", timeout=3)

    assert ok is False
    assert reason is not None
    assert "captchaImage" in reason, "原因里要带上是哪个地址探不通"
    assert "//captchaImage" not in reason, "末尾斜杠没有被规整掉"
    # 不能把异常本身抛出去（那会变成 83 条 error）
    assert isinstance(reason, str)


def test_probe_backend_unreachable_is_quick():
    """
    连一个关着的端口，不该干等到 PROBE_TIMEOUT。

    实现依据：requests 的 timeout 传 (连接超时, 读取超时) 元组。
    这里给 timeout=30 却要求 10 秒内返回 —— 若连接超时没生效就会红。
    """
    t0 = time.time()
    ok, _ = probe_backend(UNREACHABLE, timeout=30)
    elapsed = time.time() - t0

    assert ok is False
    assert elapsed < 10, (
        f"探一个关着的端口花了 {elapsed:.1f}s —— 连接超时没有生效，"
        f"应使用 timeout=(PROBE_CONNECT_TIMEOUT, read_timeout)"
    )


# ═══════════════════════════════════════════════════════════
# probe_redis
# ═══════════════════════════════════════════════════════════

def test_probe_redis_unreachable_returns_reason():
    """
    ★ Redis 挂了：同样返回可读原因，不抛异常（"不抛异常"由本用例隐含覆盖）。

    这条同时钉住一个**性能回归**：redis-py 8.x 默认会自动重试（指数退避），
    会把一次 2 秒的连接失败放大到 25 秒以上。所以必须显式
    `retry=Retry(NoBackoff(), 0)`，下面的耗时断言就是防止它被改回去。
    """
    t0 = time.time()
    ok, reason = probe_redis(UNREACHABLE_PORT, timeout=3)
    elapsed = time.time() - t0

    assert ok is False
    assert reason is not None
    assert "Redis" in reason
    assert str(UNREACHABLE_PORT) in reason, "原因里要带上是哪个端口"
    assert elapsed < 10, (
        f"探一个关着的 Redis 端口花了 {elapsed:.1f}s —— redis-py 8.x 的默认"
        f"自动重试会让失败被放大数倍，必须显式关掉（retry=Retry(NoBackoff(), 0)）"
    )


def test_probe_timeout_is_short():
    """
    探活超时必须是"短"的：不能沿用业务请求的 API_TIMEOUT(60 秒)，
    否则服务器挂掉时开跑前要白等一分钟。
    """
    assert PROBE_TIMEOUT <= 15, "探活超时过长，环境不通时会白等"
