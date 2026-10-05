"""
test_engine_replace.py —— ${} 变量替换引擎的单元测试（不依赖服务器／数据库）

覆盖 core/apiutil.py 的 replace_load 结构化替换（Phase 1 / 1.2）：
    - 类型保真：占位符独占整串时返回原始类型，不再被 JSON 文本转成字符串
    - 文本拼接：占位符只占字符串一段时仍是字符串
    - 结构化：dict / list / 嵌套结构递归遍历，标量原样保留
    - 错误处理：语法不合法、函数不存在、参数个数不对，一律抛 PlaceholderError

不请求任何 fixture，所以跑的时候不会建 SSH 隧道，秒级完成：
    pytest test_runner/test_00_engine -q
"""

import pytest

from core.apiutil import ApiEngine, PlaceholderError
from utils.debugtalk import DebugTalk

# 用例里要写 ${...} 字面量，但源文件里直接写容易被编辑器／工具误处理，
# 所以统一用这两个常量拼出来，可读性也不差。
OP = "${"
CL = "}"


def ph(expr):
    """把一个表达式包成 ${expr} 占位符。"""
    return OP + expr + CL


@pytest.fixture(scope="module")
def engine():
    return ApiEngine()


@pytest.fixture(scope="module")
def uid():
    """data/runtime.yaml 里的 created_user_id（int）。"""
    value = DebugTalk().get_runtime("created_user_id")
    assert value is not None, "runtime.yaml 缺少 created_user_id，请先跑一遍主用例"
    return value


# ═══════════════════════════════════════════════════════════
# 一、类型保真：这是 1.2 的核心
# ═══════════════════════════════════════════════════════════

def test_whole_placeholder_in_dict_keeps_int(engine, uid):
    """db_verify 的 where 写法：改造前会变成字符串 '751'。"""
    out = engine.replace_load({"user_id": ph("get_runtime(created_user_id)")})
    assert out == {"user_id": uid}
    assert isinstance(out["user_id"], int), (
        f"占位符独占整串时应返回原始类型，实际是 {type(out['user_id']).__name__}"
    )


def test_whole_placeholder_in_list_keeps_int(engine, uid):
    """business_flow 的 roleIds 写法：接口是 Long[]，元素必须是 int。"""
    out = engine.replace_load({"roleIds": [ph("get_runtime(created_user_id)")]})
    assert out == {"roleIds": [uid]}
    assert isinstance(out["roleIds"][0], int), (
        f"list 元素应为 int，实际是 {type(out['roleIds'][0]).__name__}"
    )


def test_bare_string_whole_placeholder_keeps_type(engine):
    """顶层裸字符串入参同样保真。"""
    out = engine.replace_load(ph("timestamp()"))
    assert isinstance(out, int)
    assert out > 0


def test_nested_dict_keeps_type(engine, uid):
    out = engine.replace_load(
        {"outer": {"inner": ph("get_runtime(created_user_id)")}}
    )
    assert out == {"outer": {"inner": uid}}
    assert isinstance(out["outer"]["inner"], int)


def test_params_form_keeps_type(engine, uid):
    out = engine.replace_load(
        {"roleId": ph("get_runtime(created_user_id)"), "pageNum": 1}
    )
    assert out == {"roleId": uid, "pageNum": 1}
    assert isinstance(out["roleId"], int)
    assert isinstance(out["pageNum"], int)


# ═══════════════════════════════════════════════════════════
# 二、文本拼接：占位符只占一段时，结果仍应是字符串
# ═══════════════════════════════════════════════════════════

def test_segment_of_url_becomes_string(engine, uid):
    out = engine.replace_load("/system/user/" + ph("get_runtime(created_user_id)"))
    assert out == f"/system/user/{uid}"
    assert isinstance(out, str)


def test_multiple_placeholders_are_all_expanded(engine):
    """批量删除的 URL 写法：/system/user/${a},${b}"""
    out = engine.replace_load(
        ph("timestamp()") + "," + ph("timestamp_thirteen()")
    )
    assert isinstance(out, str)
    assert out.count(",") == 1
    first, second = out.split(",")
    assert first.isdigit() and second.isdigit()


def test_zero_arg_call_passes_no_argument(engine):
    """${random_str()} 是真正的零参调用，用默认长度 8。"""
    out = engine.replace_load(ph("random_str()"))
    assert isinstance(out, str)
    assert len(out) == 8


def test_literal_argument_is_passed(engine):
    out = engine.replace_load(ph("random_str(4)"))
    assert isinstance(out, str)
    assert len(out) == 4


# ═══════════════════════════════════════════════════════════
# 三、结构化：标量与无占位符内容原样保留
# ═══════════════════════════════════════════════════════════

def test_scalars_are_preserved(engine):
    data = {"a": 1, "b": True, "c": None, "d": [1, 2], "e": 3.5}
    out = engine.replace_load(data)
    assert out == data
    assert out["b"] is True
    assert out["c"] is None
    assert isinstance(out["a"], int)
    assert isinstance(out["e"], float)


def test_plain_text_without_placeholder_unchanged(engine):
    assert engine.replace_load("编辑后昵称") == "编辑后昵称"


def test_input_is_not_mutated(engine, uid):
    """replace_load 必须返回新结构，不能就地改动调用方的数据。"""
    original = {"user_id": ph("get_runtime(created_user_id)")}
    snapshot = dict(original)
    engine.replace_load(original)
    assert original == snapshot, "replace_load 不应修改传入的容器"


# ═══════════════════════════════════════════════════════════
# 四、错误处理：都要抛 PlaceholderError，且信息可定位
# ═══════════════════════════════════════════════════════════

def test_unpaired_brace_raises(engine):
    with pytest.raises(PlaceholderError):
        engine.replace_load(OP + "timestamp(")


def test_unknown_function_raises(engine):
    with pytest.raises(PlaceholderError) as exc:
        engine.replace_load(ph("no_such_function()"))
    assert "no_such_function" in str(exc.value)


def test_wrong_argument_count_raises(engine):
    with pytest.raises(PlaceholderError):
        engine.replace_load(ph("timestamp(1, 2)"))


def test_private_method_is_refused(engine):
    """不允许通过 ${} 调到 DebugTalk 的内部方法。"""
    with pytest.raises(PlaceholderError):
        engine.replace_load(ph("__init__()"))


def test_error_is_raised_not_silently_skipped(engine):
    """缺陷回归保护：替换失败必须是异常，而不是留下未替换的文本继续跑。"""
    with pytest.raises(PlaceholderError):
        engine.replace_load({"user_id": ph("no_such_function()")})
