"""
test_user.py —— 用户管理所有 CRUD 用例的参数化执行器

覆盖 5 个端点、25 条用例：
  test_user_add           → POST   /system/user              (11条)
  test_user_edit          → PUT    /system/user              ( 4条)
  test_user_delete        → DELETE /system/user/{id}          ( 4条)
  test_user_resetPwd      → PUT    /system/user/resetPwd     ( 3条)
  test_user_changeStatus  → PUT    /system/user/changeStatus ( 3条)
"""

import os
import pytest

from core.apiutil import ApiEngine
from utils.readyaml import get_testcase_yaml, FILE_PATH
from test_runner.test_user.helpers import create_user, get_user_id

# ── 加载 YAML ─────────────────────────────────────────────────

_add_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "user_add.yaml")
)

_edit_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "user_edit.yaml")
)

_delete_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "user_delete.yaml")
)

_resetPwd_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "user_resetPwd.yaml")
)

# ═══════════════════════════════════════════════════════════════
# POST /system/user — 新增用户（11 条）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _add_cases,
    ids=[c[1]["case_name"] for c in _add_cases],
)
def test_user_add(base_url, base_info, case):
    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))


# ═══════════════════════════════════════════════════════════════
# PUT /system/user — 编辑用户（4 条）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _edit_cases,
    ids=[c[1]["case_name"] for c in _edit_cases],
)
def test_user_edit(base_url, base_info, case):
    username = case["setup"]["create_user"]
    user_id = create_user(base_url, username)

    # userId 一定需要注入；userName 只在 YAML 未指定时用前置用户的
    case["json"]["userId"] = user_id
    if "userName" not in case["json"]:
        case["json"]["userName"] = username

    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))


# ═══════════════════════════════════════════════════════════════
# DELETE /system/user/{id} — 删除用户（3 条）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _delete_cases,
    ids=[c[1]["case_name"] for c in _delete_cases],
)
def test_user_delete(base_url, base_info, case):
    username = case.get("setup", {}).get("create_user")
    if username:
        user_id = create_user(base_url, username)
        case["url"] = f"/system/user/{user_id}"

    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))


# ═══════════════════════════════════════════════════════════════
# PUT /system/user/resetPwd — 重置密码（3 条）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _resetPwd_cases,
    ids=[c[1]["case_name"] for c in _resetPwd_cases],
)
def test_user_resetPwd(base_url, base_info, case):
    username = case.get("setup", {}).get("create_user")
    if username:
        user_id = create_user(base_url, username)
        case["json"]["userId"] = user_id
        case["json"]["userName"] = username

    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))
