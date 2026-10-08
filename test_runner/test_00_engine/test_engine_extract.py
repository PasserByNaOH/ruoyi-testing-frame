"""
test_engine_extract.py —— 数据提取（extract）的单元测试（不依赖服务器／数据库）

覆盖 core/apiutil.py 的 _resolve_extract / extract_data（Phase 1 / 1.3）：
    - jsonpath 成功提取（含 0 / '' / False / [] 这些合法的"空值"）
    - jsonpath 未匹配、匹配到 null、响应不是合法 JSON → 必须抛错
    - 正则成功 / 未匹配 / 表达式不合法 → 必须抛错
    - 无法识别的表达式 → 必须抛错
    - extract_data 端到端：成功才写 runtime，失败必须抛且不留下半个状态

为什么要有这个文件：上面这些失败分支在真实服务器上**无法稳定复现**，
只能靠自造响应文本来触发，所以单测是唯一可靠的覆盖手段。

不请求任何 fixture，秒级完成：
    pytest test_runner/test_00_engine -q
"""

import json
from unittest.mock import patch

import pytest

from core.apiutil import ApiEngine, _resolve_extract

# extract_data 是引擎实例方法，单测里共用一个实例（写 runtime 已被 mock 掉）
engine = ApiEngine()

# ── 自造的响应文本，模拟若依的真实返回 ──

RESP_TOKEN = json.dumps({"code": 200, "msg": "操作成功", "token": "abc.def.ghi"})

RESP_ROWS = json.dumps({
    "total": 2,
    "rows": [{"userId": 701, "roleId": 534}, {"userId": 702, "roleId": 535}],
})

# 字段存在、值是 null —— 这是 1.3 要重点拦下的情况
RESP_NULL_USER = json.dumps({"total": 1, "rows": [{"userId": None}]})

# 合法的"空值"：0 / '' / False / [] 都不是 null，必须正常提取
RESP_FALSY = json.dumps({
    "data": {"count": 0, "empty": "", "flag": False, "items": []},
})

# 正则提取用的响应文本（注意：json.dumps 默认在冒号后带空格，正则要匹配得上）
RESP_TOKEN_RAW = '{"code": 200, "msg": "操作成功", "token": "abc.def.ghi"}'

RESP_HTML = "<html><body>502 Bad Gateway</body></html>"


# ═══════════════════════════════════════════════════════════
# 一、jsonpath 成功路径
# ═══════════════════════════════════════════════════════════

def test_jsonpath_extracts_token():
    assert _resolve_extract("token", "$.token", RESP_TOKEN) == "abc.def.ghi"


def test_jsonpath_extracts_first_row_id():
    assert _resolve_extract("flow_user_id", "$.rows[0].userId", RESP_ROWS) == 701


@pytest.mark.parametrize("field, expected", [
    ("count", 0),
    ("empty", ""),
    ("flag", False),
    ("items", []),
])
def test_jsonpath_accepts_legitimately_falsy_values(field, expected):
    """0 / '' / False / [] 是合法值，不能当成"没提取到"。"""
    assert _resolve_extract(field, f"$.data.{field}", RESP_FALSY) == expected


# ═══════════════════════════════════════════════════════════
# 二、jsonpath 失败路径 —— 每一条都必须抛错
# ═══════════════════════════════════════════════════════════

def test_jsonpath_no_match_raises():
    with pytest.raises(RuntimeError) as exc:
        _resolve_extract("token", "$.token", json.dumps({"code": 401}))
    assert "jsonpath 未匹配" in str(exc.value)
    assert "$.token" in str(exc.value), "错误信息里应带表达式，便于定位"


def test_jsonpath_index_out_of_range_raises():
    with pytest.raises(RuntimeError) as exc:
        _resolve_extract("uid", "$.rows[99].userId", RESP_ROWS)
    assert "jsonpath 未匹配" in str(exc.value)


def test_jsonpath_null_value_raises():
    """★ 1.3 的核心：字段在、值是 null，必须报错而不是写入 None。"""
    with pytest.raises(RuntimeError) as exc:
        _resolve_extract("flow_user_id", "$.rows[0].userId", RESP_NULL_USER)
    assert "null" in str(exc.value)
    assert "$.rows[0].userId" in str(exc.value)


def test_error_message_contains_response_snippet():
    """错误信息必须带响应片段，否则定位不到是接口变了还是数据没造出来。"""
    with pytest.raises(RuntimeError) as exc:
        _resolve_extract("token", "$.token", RESP_HTML)
    message = str(exc.value)
    assert "响应片段" in message
    assert "502 Bad Gateway" in message


def test_non_json_response_raises():
    """网关插了一层、返回 HTML 时，应报"不是合法 JSON"而不是别的怪错。"""
    with pytest.raises(RuntimeError) as exc:
        _resolve_extract("token", "$.token", RESP_HTML)
    assert "不是合法 JSON" in str(exc.value)


# ═══════════════════════════════════════════════════════════
# 三、正则分支 —— 现有 YAML 一条都走不到，只能靠单测覆盖
# ═══════════════════════════════════════════════════════════

def test_regex_extracts_group_one():
    """正则要走 (.*?) 的第 1 个捕获组；这里按真实报文的空格写法匹配。"""
    assert _resolve_extract("t", r'"token": "(.*?)"', RESP_TOKEN_RAW) == "abc.def.ghi"


def test_regex_no_match_raises():
    with pytest.raises(RuntimeError) as exc:
        _resolve_extract("t", r'"nothere": "(.*?)"', RESP_TOKEN_RAW)
    assert "正则未匹配" in str(exc.value)


def test_regex_whitespace_mismatch_raises():
    """响应格式和正则对不上时必须报错，不能静默放过（真实踩过的坑）。"""
    with pytest.raises(RuntimeError) as exc:
        _resolve_extract("t", r'"token":"(.*?)"', RESP_TOKEN_RAW)
    assert "正则未匹配" in str(exc.value)


def test_invalid_regex_raises():
    with pytest.raises(RuntimeError) as exc:
        _resolve_extract("t", r"(unclosed", RESP_TOKEN)
    assert "正则表达式不合法" in str(exc.value)


# ═══════════════════════════════════════════════════════════
# 四、无法识别的表达式
# ═══════════════════════════════════════════════════════════

def test_unrecognized_expression_raises():
    with pytest.raises(RuntimeError) as exc:
        _resolve_extract("t", "token", RESP_TOKEN)
    assert "无法识别" in str(exc.value)


# ═══════════════════════════════════════════════════════════
# 五、extract_data 端到端：写 runtime + 失败不留半个状态
# ═══════════════════════════════════════════════════════════
#
# 这里把 write_runtime 换成内存记录，**不碰真实的 data/runtime.yaml**：
#   · 单测不该有真实文件副作用（跑完不该改动别人的运行状态）
#   · 也不该依赖该文件的写权限（本项目已出现过权限导致的假失败）
# 这样既能断言"写了什么"，也能断言"失败时什么都没写"。

WRITE_TARGET = "core.apiutil.write_runtime"


def test_extract_data_writes_value():
    with patch(WRITE_TARGET) as mocked:
        engine.extract_data({"token": "$.token"}, RESP_TOKEN)
    mocked.assert_called_once_with({"token": "abc.def.ghi"})


def test_extract_data_raises_and_does_not_write():
    """失败时既要抛错，也不能把半成品写进 runtime。"""
    with patch(WRITE_TARGET) as mocked:
        with pytest.raises(RuntimeError):
            engine.extract_data({"missing_key": "$.nope"}, RESP_TOKEN)
    mocked.assert_not_called()


def test_extract_data_stops_at_first_failure():
    """多条规则时，前一条失败就应中止，不再处理后面的。"""
    with patch(WRITE_TARGET) as mocked:
        with pytest.raises(RuntimeError):
            engine.extract_data(
                {"bad": "$.nope", "good": "$.token"},
                RESP_TOKEN,
            )
    mocked.assert_not_called()


def test_extract_data_writes_every_rule():
    """全部成功时，每条规则各写一次。"""
    with patch(WRITE_TARGET) as mocked:
        engine.extract_data(
            {"uid": "$.rows[0].userId", "rid": "$.rows[0].roleId"},
            RESP_ROWS,
        )
    assert mocked.call_count == 2
    mocked.assert_any_call({"uid": 701})
    mocked.assert_any_call({"rid": 534})
