"""
test_engine_assertions.py —— HTTP 断言函数的单元测试（不依赖服务器／数据库）

覆盖 utils/assertions.py（Phase 1 / 1.4）：
    - status_code 只看状态码，任何响应都能判
    - body_code / token_not_empty / token_absent / rows_in_scope 需要合法 JSON，
      拿到非 JSON 响应时必须给出**能定位的失败信息**，而不是裸的 JSONDecodeError
    - try_parse_json 只负责解析，不参与控制流

对应旧行为：解析失败时抛 `JSONDecodeError: Expecting value: line 1 column 1`，
看不出到底是网关插了一层、还是接口改了、还是断言写错了。

不请求任何 fixture，秒级完成：
    pytest test_runner/test_00_engine -q
"""

import pytest

from utils.assertions import (
    assert_body_code,
    assert_status_code,
    assert_token_absent,
    assert_token_not_empty,
    try_parse_json,
)


class _FakeResponse:
    def __init__(self, status_code=200, content_type="application/json",
                 text="", payload=None):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


HTML_502 = _FakeResponse(
    status_code=502,
    content_type="text/html",
    text="<html><body>502 Bad Gateway</body></html>",
    payload=None,
)

JSON_OK = _FakeResponse(payload={"code": 200, "msg": "操作成功", "token": "abc"})


# ═══════════════════════════════════════════════════════════
# try_parse_json：只解析，不判断
# ═══════════════════════════════════════════════════════════

def test_try_parse_json_returns_body_for_valid_json():
    assert try_parse_json(JSON_OK) == {"code": 200, "msg": "操作成功", "token": "abc"}


def test_try_parse_json_returns_none_for_invalid_json():
    assert try_parse_json(HTML_502) is None


def test_try_parse_json_never_raises():
    """它绝不能再抛异常——否则又会变成"解析失败带走断言"。"""
    try_parse_json(HTML_502)   # 不抛即通过


# ═══════════════════════════════════════════════════════════
# status_code：与响应体无关，任何响应都能判
# ═══════════════════════════════════════════════════════════

def test_status_code_passes_regardless_of_body():
    assert_status_code(HTML_502, {"expected": 502})


def test_status_code_fails_with_clear_message():
    with pytest.raises(AssertionError) as exc:
        assert_status_code(HTML_502, {"expected": 200})
    message = str(exc.value)
    assert "502" in message and "200" in message


# ═══════════════════════════════════════════════════════════
# 需要 JSON 的断言：非 JSON 响应要给"说人话"的报错
# ═══════════════════════════════════════════════════════════

def test_body_code_passes_on_valid_json():
    assert_body_code(JSON_OK, {"expected": 200})


def test_body_code_reports_non_json_clearly():
    """
    ★ 核心：以前这里会抛 JSONDecodeError，看不出问题出在哪。
    现在必须说明"响应不是合法 JSON"，并带上状态码 / Content-Type / 响应片段。
    """
    with pytest.raises(AssertionError) as exc:
        assert_body_code(HTML_502, {"expected": 200})

    message = str(exc.value)
    assert "不是合法 JSON" in message, "报错应说清是响应格式问题"
    assert "502" in message, "应带 HTTP 状态码"
    assert "text/html" in message, "应带 Content-Type，便于识别网关／代理"
    assert "502 Bad Gateway" in message, "应带响应片段，便于直接定位"


def test_token_not_empty_reports_non_json_clearly():
    with pytest.raises(AssertionError) as exc:
        assert_token_not_empty(HTML_502, {})
    assert "不是合法 JSON" in str(exc.value)


def test_token_absent_reports_non_json_clearly():
    with pytest.raises(AssertionError) as exc:
        assert_token_absent(HTML_502, {})
    assert "不是合法 JSON" in str(exc.value)


def test_token_not_empty_passes_on_valid_json():
    assert_token_not_empty(JSON_OK, {})


def test_token_not_empty_fails_when_token_empty():
    resp = _FakeResponse(payload={"code": 200, "token": ""})
    with pytest.raises(AssertionError, match="未返回 token"):
        assert_token_not_empty(resp, {})


def test_token_absent_passes_when_no_token():
    resp = _FakeResponse(payload={"code": 500, "msg": "密码错误"})
    assert_token_absent(resp, {})


def test_token_absent_fails_when_token_present():
    with pytest.raises(AssertionError, match="不应返回 token"):
        assert_token_absent(JSON_OK, {})


# ═══════════════════════════════════════════════════════════
# rows_in_scope：需要 db，这里只验证"非 JSON 时先报格式问题"
# ═══════════════════════════════════════════════════════════

def test_rows_in_scope_reports_non_json_clearly():
    from utils.assertions import assert_rows_in_scope

    with pytest.raises(AssertionError) as exc:
        assert_rows_in_scope(HTML_502, {"username": "admin"}, db=object())
    assert "不是合法 JSON" in str(exc.value)


def test_rows_in_scope_requires_db():
    from utils.assertions import assert_rows_in_scope

    with pytest.raises(AssertionError, match="需要 db 参数"):
        assert_rows_in_scope(JSON_OK, {"username": "admin"}, db=None)
