"""
test_role_crud.py —— 角色管理 CRUD + authUser 参数化执行器

覆盖端点：
  test_role_add          → POST   /system/role                     ( 8条)
  test_role_edit         → PUT    /system/role                     ( 8条)
  test_role_delete       → DELETE /system/role/{id}                ( 4条)
  test_role_changeStatus → PUT    /system/role/changeStatus        ( 3条)
  test_role_dataScope    → PUT    /system/role/dataScope           ( 3条)
  test_role_authUser     → *      /system/role/authUser/*          ( 5条)
"""

import os
import pytest

from core.apiutil import ApiEngine
from utils.assertions import run_db_verify
from utils.readyaml import get_testcase_yaml, write_runtime, FILE_PATH
from test_runner.test_03_role.helpers import (
    build_scope_user,
    create_role,
    get_role_id,
)

# ── 加载 YAML ─────────────────────────────────────────────────

_add_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "role_add.yaml")
)

_edit_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "role_edit.yaml")
)

_delete_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "role_delete.yaml")
)

_changeStatus_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "role_changeStatus.yaml")
)

_dataScope_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "role_dataScope.yaml")
)

_authUser_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "role_authUser.yaml")
)


# ── 工具函数 ──────────────────────────────────────────────────

def _setup_role_with_user(base_url, setup_role, case, username_key="assigned_user_id"):
    """
    创建测试角色 + 关联用户，注入 roleId 和 userId 到 runtime。
    返回 role_id。
    """
    role_name = setup_role["role_name"]
    role_key = setup_role.get("role_key", role_name)
    role_id = create_role(base_url, role_name, role_key)

    # 如果指定了 assign_user，创建一个测试用户持有该角色
    username = setup_role.get("assign_user")
    if username:
        user_id = build_scope_user(
            base_url, username, dept_id=103, role_ids=[role_id],
        )
        write_runtime({username_key: user_id})

    return role_id


# ═══════════════════════════════════════════════════════════════
# POST /system/role — 新增角色（8 条）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _add_cases,
    ids=[c[1]["case_name"] for c in _add_cases],
)
def test_role_add(base_url, db_connection, base_info, case):
    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))

    db_rules = case.get("db_verify")
    if db_rules:
        role_name = case["json"]["roleName"]
        role_id = get_role_id(base_url, role_name)
        assert role_id is not None, f"创建后未查到角色: {role_name}"
        write_runtime({"created_role_id": role_id})
        run_db_verify(db_connection, engine.replace_load(db_rules))


# ═══════════════════════════════════════════════════════════════
# PUT /system/role — 编辑角色（8 条）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _edit_cases,
    ids=[c[1]["case_name"] for c in _edit_cases],
)
def test_role_edit(base_url, db_connection, base_info, case):
    setup_role = case.get("setup", {}).get("create_role")
    if setup_role:
        role_name = setup_role["role_name"]
        role_key = setup_role.get("role_key", role_name)
        role_id = create_role(base_url, role_name, role_key)
        case["json"]["roleId"] = role_id

    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))

    db_rules = case.get("db_verify")
    if db_rules:
        run_db_verify(db_connection, engine.replace_load(db_rules))


# ═══════════════════════════════════════════════════════════════
# DELETE /system/role/{roleId} — 删除角色（4 条）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _delete_cases,
    ids=[c[1]["case_name"] for c in _delete_cases],
)
def test_role_delete(base_url, db_connection, base_info, case):
    setup_role = case.get("setup", {}).get("create_role")
    if setup_role:
        role_name = setup_role["role_name"]
        role_key = setup_role.get("role_key", role_name)
        role_id = create_role(base_url, role_name, role_key)
        case["url"] = f"/system/role/{role_id}"

        if setup_role.get("assign_user"):
            username = "at_del_role_user"
            build_scope_user(
                base_url, username, dept_id=103, role_ids=[role_id],
            )

    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))

    db_rules = case.get("db_verify")
    if db_rules:
        run_db_verify(db_connection, engine.replace_load(db_rules))


# ═══════════════════════════════════════════════════════════════
# PUT /system/role/changeStatus — 修改角色状态（3 条）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _changeStatus_cases,
    ids=[c[1]["case_name"] for c in _changeStatus_cases],
)
def test_role_changeStatus(base_url, db_connection, base_info, case):
    setup_role = case.get("setup", {}).get("create_role")
    if setup_role:
        role_name = setup_role["role_name"]
        role_key = setup_role.get("role_key", role_name)
        role_id = create_role(base_url, role_name, role_key)
        case["json"]["roleId"] = role_id

    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))

    db_rules = case.get("db_verify")
    if db_rules:
        run_db_verify(db_connection, engine.replace_load(db_rules))


# ═══════════════════════════════════════════════════════════════
# PUT /system/role/dataScope — 修改角色数据权限（3 条）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _dataScope_cases,
    ids=[c[1]["case_name"] for c in _dataScope_cases],
)
def test_role_dataScope(base_url, db_connection, base_info, case):
    setup_role = case.get("setup", {}).get("create_role")
    if setup_role:
        role_name = setup_role["role_name"]
        role_key = setup_role.get("role_key", role_name)
        role_id = create_role(base_url, role_name, role_key)
        case["json"]["roleId"] = role_id

    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))

    db_rules = case.get("db_verify")
    if db_rules:
        run_db_verify(db_connection, engine.replace_load(db_rules))


# ═══════════════════════════════════════════════════════════════
# /system/role/authUser/* — 角色分配用户 / 取消授权（5 条）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _authUser_cases,
    ids=[c[1]["case_name"] for c in _authUser_cases],
)
def test_role_authUser(base_url, db_connection, base_info, case):
    setup_role = case.get("setup", {}).get("create_role")
    if setup_role:
        _setup_role_with_user(base_url, setup_role, case)

    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case))

    db_rules = case.get("db_verify")
    if db_rules:
        run_db_verify(db_connection, engine.replace_load(db_rules))
