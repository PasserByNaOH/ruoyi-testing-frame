"""
test_engine_response.py —— 响应处理与断言执行的单元测试（不依赖服务器／数据库）

覆盖 core/apiutil.py 的 specification_yaml / specification_export /
_attach_response（Phase 1 / 1.4）：
    - **核心**：无论响应是什么格式，"断言必须被执行"——旧实现在解析失败或
      非二进制时会把断言整段跳过
    - 断言被跳过时用例会"红得不是地方"（报 JSONDecodeError，而真实断言从未运行）
    - 附着响应只负责展示，不参与控制流

为什么必须自造响应：现有 YAML 的响应全是正常的 `application/json`，
1.4 的分支一条都走不到，"全量绿"只能证明没回归，证明不了修复生效。

不请求任何 fixture，秒级完成：
    pytest test_runner/test_00_engine -q
"""

import json
from unittest.mock import patch

import pytest

from core.apiutil import ApiEngine

# run_validations 是 core/apiutil 从 utils.assertions 导入的名字，
# 所以必须 patch core.apiutil 里的那一份，测试才能观察到"有没有被调用"。
PATCH_TARGET = "core.apiutil.run_validations"


class _FakeResponse:
    """够用的假响应对象：状态码 / 响应头 / 原始文本 / 二进制内容。"""

    def __init__(self, status_code=200, content_type="application/json", text="",
                 payload=None):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.text = text
        self.content = text.encode("utf-8") if text else b""
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


BASE_INFO = {
    "url": "/system/user/list",
    "method": "get",
    "headers": {"Content-Type": "application/json;charset=UTF-8"},
}


def make_case(**overrides):
    case = {
        "case_name": "单元测试-假用例",
        "validations": [{"type": "status_code", "expected": 200}],
    }
    case.update(overrides)
    return case


@pytest.fixture
def engine():
    eng = ApiEngine()
    # 不让它真的去读 token 注入请求头
    eng.inject_token = lambda headers: headers
    return eng


def run_spec(engine, response, **case_overrides):
    """跑一遍 specification_yaml，返回 (resp, 被 patch 的 run_validations)。"""
    with patch(PATCH_TARGET) as mocked:
        engine.send.run_main = lambda **kwargs: response
        resp = engine.specification_yaml(dict(BASE_INFO), make_case(**case_overrides))
    return resp, mocked


# ═══════════════════════════════════════════════════════════
# 一、核心：断言必须被执行（这正是 1.4 要修的）
# ═══════════════════════════════════════════════════════════

def test_validations_run_on_normal_json(engine):
    """正常情况：当然要跑（基线）。"""
    resp = _FakeResponse(payload={"code": 200})
    _, mocked = run_spec(engine, resp)
    assert mocked.call_count == 1


def test_validations_run_when_content_type_says_json_but_body_is_not(engine):
    """
    ★ 1.4 的核心用例。
    Content-Type 声称是 JSON，响应体却是 HTML（网关／代理插了一层）。
    旧实现：resp.json() 抛错 → 异常把断言带走 → 一行都没跑。
    现在：断言必须执行。
    """
    resp = _FakeResponse(
        content_type="application/json",
        text="<html><body>502 Bad Gateway</body></html>",
        payload=None,          # ← json() 会抛
    )
    _, mocked = run_spec(engine, resp)

    assert mocked.call_count == 1, (
        "响应体不是合法 JSON 时，validations 仍必须被执行（1.4 的核心）"
    )
    called_resp, called_validations = mocked.call_args[0]
    assert called_resp is resp
    assert called_validations == [{"type": "status_code", "expected": 200}]


def test_validations_run_on_non_json_content_type(engine):
    """响应头说是 HTML，同样要跑断言（旧实现在这条路上碰巧是对的，作为回归保护）。"""
    resp = _FakeResponse(
        content_type="text/html",
        text="<html>500</html>",
        payload=None,
    )
    _, mocked = run_spec(engine, resp)
    assert mocked.call_count == 1


def test_validations_run_on_octet_stream(engine):
    """
    ★ 二进制响应也要跑断言。
    旧实现这条分支压根没写 run_validations，**连状态码都不校验**。
    """
    resp = _FakeResponse(
        content_type="application/octet-stream",
        text="",
        payload=None,
    )
    _, mocked = run_spec(engine, resp)
    assert mocked.call_count == 1, "二进制响应也必须执行断言（至少状态码能判）"


def test_status_code_assertion_can_actually_fail_on_binary(engine):
    """证明二进制分支的断言是"真的在判"，不是走了个形式。"""
    resp = _FakeResponse(status_code=500, content_type="application/octet-stream")
    with patch(PATCH_TARGET) as mocked:
        mocked.side_effect = AssertionError("HTTP 状态码断言失败")
        engine.send.run_main = lambda **kwargs: resp
        with pytest.raises(AssertionError, match="状态码断言失败"):
            engine.specification_yaml(dict(BASE_INFO), make_case())


# ═══════════════════════════════════════════════════════════
# 二、提取也要照跑（不能因为格式问题被跳过）
# ═══════════════════════════════════════════════════════════

def test_extract_runs_before_validations(engine):
    """有 extract 规则时，提取要执行，且顺序在断言之前。"""
    resp = _FakeResponse(payload={"code": 200, "token": "abc"})
    order = []

    engine.extract_data = lambda rules, text: order.append("extract")

    with patch(PATCH_TARGET) as mocked:
        mocked.side_effect = lambda *a, **k: order.append("validate")
        engine.send.run_main = lambda **kwargs: resp
        engine.specification_yaml(
            dict(BASE_INFO), make_case(extract={"token": "$.token"})
        )

    assert order == ["extract", "validate"]


def test_extract_failure_propagates(engine):
    """1.3 起提取失败会抛错，不能被 1.4 的改动吞掉。"""
    resp = _FakeResponse(payload={"code": 200})

    def boom(rules, text):
        raise RuntimeError("提取变量失败 [token]")

    engine.extract_data = boom
    with patch(PATCH_TARGET):
        engine.send.run_main = lambda **kwargs: resp
        with pytest.raises(RuntimeError, match="提取变量失败"):
            engine.specification_yaml(
                dict(BASE_INFO), make_case(extract={"token": "$.token"})
            )


# ═══════════════════════════════════════════════════════════
# 三、附着响应：只负责展示，不参与控制流
# ═══════════════════════════════════════════════════════════

def test_attach_response_returns_none_on_bad_json(engine):
    """附着函数自己不应该抛异常——否则又会变成"解析失败带走断言"。"""
    resp = _FakeResponse(content_type="application/json", text="not json at all")
    assert engine._attach_response(resp) is None


def test_attach_response_returns_none_on_octet_stream(engine):
    resp = _FakeResponse(content_type="application/octet-stream", text="")
    assert engine._attach_response(resp) is None


def test_attach_response_handles_valid_json(engine):
    resp = _FakeResponse(payload={"code": 200, "msg": "成功"})
    assert engine._attach_response(resp) is None


# ═══════════════════════════════════════════════════════════
# 四、specification_export 的镜像问题
# ═══════════════════════════════════════════════════════════

EXPORT_BASE_INFO = {
    "url": "/system/user/export",
    "method": "post",
    "headers": {"Content-Type": "application/json;charset=UTF-8"},
}


def test_export_validations_run_on_binary(engine):
    """正常情况：导出返回二进制，断言要跑。"""
    resp = _FakeResponse(
        content_type="application/vnd.openxmlformats-officedocument"
                     ".spreadsheetml.sheet",
        text="PK\x03\x04fake",
    )
    with patch(PATCH_TARGET) as mocked:
        engine.send.run_main = lambda **kwargs: resp
        engine.specification_export(
            dict(EXPORT_BASE_INFO),
            {"case_name": "导出", "validations": [{"type": "excel_content"}]},
        )
    assert mocked.call_count == 1


def test_export_validations_run_when_response_is_not_binary(engine):
    """
    ★ 导出失败时服务端返回 JSON／HTML 错误，断言同样必须执行。
    旧实现：只 logs.warning，一条断言都不跑。
    """
    resp = _FakeResponse(
        status_code=500,
        content_type="application/json",
        text='{"code":500,"msg":"导出失败"}',
        payload={"code": 500, "msg": "导出失败"},
    )
    with patch(PATCH_TARGET) as mocked:
        engine.send.run_main = lambda **kwargs: resp
        engine.specification_export(
            dict(EXPORT_BASE_INFO),
            {"case_name": "导出", "validations": [{"type": "status_code", "expected": 200}]},
        )
    assert mocked.call_count == 1, (
        "导出返回非二进制时，validations 仍必须被执行（1.4 的镜像问题）"
    )


def test_export_status_code_assertion_can_fail(engine):
    """证明导出分支的断言是真的在执行。"""
    resp = _FakeResponse(
        status_code=500,
        content_type="text/html",
        text="<html>500</html>",
    )
    with patch(PATCH_TARGET) as mocked:
        mocked.side_effect = AssertionError("HTTP 状态码断言失败")
        engine.send.run_main = lambda **kwargs: resp
        with pytest.raises(AssertionError, match="状态码断言失败"):
            engine.specification_export(
                dict(EXPORT_BASE_INFO),
                {"case_name": "导出",
                 "validations": [{"type": "status_code", "expected": 200}]},
            )
