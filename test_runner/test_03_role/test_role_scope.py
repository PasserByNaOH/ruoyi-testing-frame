"""
test_role_scope.py —— DataScope 隔离测试

依赖 isolation_users fixture（conftest.py）预置 5 角色 + 7 用户。

├── test_scope_query         → YAML 参数化（role_scope_query.yaml），
│                               登录由 test 函数处理，rows_in_scope 断言
├── test_scope_write_*       → Python，写操作隔离（需要动态参数 + 403 断言）
└── test_scope_mgr_*         → Python，DataScope 边界 + 安全漏洞
"""

import os
import pytest
import requests

from core.apiutil import ApiEngine, login_for_yaml
from test_runner.test_03_role.helpers import assert_db_unchanged, db_row
from utils.readyaml import get_runtime, get_testcase_yaml, FILE_PATH
from utils.recordlog import logs

# ── 加载 YAML ─────────────────────────────────────────────────

_scope_query_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "role_scope_query.yaml")
)


# ═══════════════════════════════════════════════════════════════
# A. 5 种 DataScope 查询隔离 + 跨部门（6 条，YAML 驱动）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "base_info, case",
    _scope_query_cases,
    ids=[c[1]["case_name"] for c in _scope_query_cases],
)
def test_scope_query(base_url, db_connection, redis_client,
                     isolation_users, base_info, case):
    # 以 validations 中 rows_in_scope 指定的用户身份登录
    username = case["validations"][-1]["username"]
    token = login_for_yaml(base_url, username, redis_client)
    case.setdefault("headers", {})
    case["headers"]["Authorization"] = f"Bearer {token}"

    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case), db=db_connection)


# ═══════════════════════════════════════════════════════════════
# B. 写操作隔离——部门经理不能跨 scope 写（3 条，Python）
# ═══════════════════════════════════════════════════════════════

def test_scope_write_edit(base_url, db_connection, redis_client, isolation_users):
    """
    mgr_103（data_scope=3，dept=103）尝试编辑 emp_106（dept=106）。

    前置：隔离角色已授予 system:user:edit，请求会穿过 @PreAuthorize（菜单权限层），
    由 Service 层的 checkUserDataScope 拒绝（返回 500）——这才是在测数据权限。
    期望：被拒绝，且 emp_106 的数据一点没变。
    """
    token = login_for_yaml(base_url, "at_mgr_103", redis_client)
    target_uid = isolation_users["user_ids"]["at_emp_106"]

    sql = ("SELECT nick_name, dept_id, sex, status "
           "FROM sys_user WHERE user_id = %s")
    params = [target_uid]
    before = db_row(db_connection, sql, params)

    resp = requests.put(
        f"{base_url}/system/user",
        json={
            "userId": target_uid,
            "userName": "at_emp_106",
            "nickName": "被越权修改",
            "deptId": 106, "sex": "0", "status": "0",
            "postIds": [2],
            "roleIds": [isolation_users["role_ids"]["at_emp"]],
        },
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )
    assert resp.json()["code"] in (403, 500), (
        f"mgr_103 不应能编辑 emp_106: {resp.json()}"
    )

    assert_db_unchanged(
        db_connection, sql, params, before,
        desc="mgr_103 越权编辑 emp_106（昵称/部门）",
    )


def test_scope_write_delete(base_url, db_connection, redis_client, isolation_users):
    """
    mgr_103（data_scope=3，dept=103）尝试删除 emp_106（dept=106）。

    前置：已授予 system:user:remove，请求穿过菜单权限层，
    由 deleteUserByIds 里的 checkUserDataScope 拒绝（返回 500）。
    期望：被拒绝，且 emp_106 没有被逻辑删除（del_flag 仍为 0）。
    """
    token = login_for_yaml(base_url, "at_mgr_103", redis_client)
    target_uid = isolation_users["user_ids"]["at_emp_106"]

    sql = "SELECT del_flag FROM sys_user WHERE user_id = %s"
    params = [target_uid]
    before = db_row(db_connection, sql, params)
    assert before is not None and before["del_flag"] == "0", (
        f"前置异常：emp_106 在越权测试前不是有效状态，本条用例无意义: {before}"
    )

    resp = requests.delete(
        f"{base_url}/system/user/{target_uid}",
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )
    assert resp.json()["code"] in (403, 500), (
        f"mgr_103 不应能删除 emp_106: {resp.json()}"
    )

    assert_db_unchanged(
        db_connection, sql, params, before,
        desc="mgr_103 越权删除 emp_106",
    )


def test_scope_write_resetPwd(base_url, db_connection, redis_client, isolation_users):
    """
    mgr_103（data_scope=3，dept=103）尝试重置 emp_106 的密码。

    前置：已授予 system:user:resetPwd，请求穿过菜单权限层，
    由 resetPwd 的 checkUserDataScope 拒绝（返回 500）。
    期望：被拒绝，且密码哈希没有变化（对比越权前的快照）。
    """
    token = login_for_yaml(base_url, "at_mgr_103", redis_client)
    target_uid = isolation_users["user_ids"]["at_emp_106"]

    sql = "SELECT password FROM sys_user WHERE user_id = %s"
    params = [target_uid]
    before = db_row(db_connection, sql, params)

    resp = requests.put(
        f"{base_url}/system/user/resetPwd",
        json={"userId": target_uid, "password": "654321"},
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )
    assert resp.json()["code"] in (403, 500), (
        f"mgr_103 不应能重置 emp_106 密码: {resp.json()}"
    )

    assert_db_unchanged(
        db_connection, sql, params, before,
        desc="mgr_103 越权重置 emp_106 密码（密码哈希）",
    )


# ═══════════════════════════════════════════════════════════════
# C. DataScope 边界 + 安全漏洞（2 条，Python）
# ═══════════════════════════════════════════════════════════════

def test_scope_mgr_edit_ceo_role(base_url, db_connection, redis_client, isolation_users):
    """
    mgr_103（data_scope=3，dept=103）尝试修改 CEO 角色信息。

    前置：已授予 system:role:edit，请求会穿过 @PreAuthorize（菜单权限层），
    由 checkRoleDataScope 拒绝（返回 500）——即真正打在数据权限层上。

    无论哪一层挡下，都必须确认 CEO 角色的字段和菜单授权都没被改动——
    请求体里带的是 menuIds: []，一旦写进去 CEO 的菜单会被清空。
    """
    token = login_for_yaml(base_url, "at_mgr_103", redis_client)
    ceo_role_id = isolation_users["role_ids"]["at_ceo"]

    role_sql = ("SELECT role_name, role_key, role_sort, data_scope, status "
                "FROM sys_role WHERE role_id = %s")
    role_params = [ceo_role_id]
    before_role = db_row(db_connection, role_sql, role_params)

    menu_sql = "SELECT COUNT(*) AS cnt FROM sys_role_menu WHERE role_id = %s"
    menu_params = [ceo_role_id]
    before_menu = db_row(db_connection, menu_sql, menu_params)
    assert before_menu["cnt"] >= 1, (
        f"前置异常：CEO 角色本来就没有菜单授权，"
        f"『菜单未被清空』这条校验会成为空断言: {before_menu}"
    )

    resp = requests.put(
        f"{base_url}/system/role",
        json={
            "roleId": ceo_role_id,
            "roleName": "at_ceo",
            "roleKey": "at_ceo",
            "roleSort": 10, "status": "0",
            "dataScope": "1", "menuIds": [], "deptIds": [],
        },
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )
    result = resp.json()
    assert result["code"] != 200, (
        f"mgr_103 不应能修改 CEO 角色: {result}"
    )

    assert_db_unchanged(
        db_connection, role_sql, role_params, before_role,
        desc="mgr_103 越权修改 CEO 角色（名称/权限字符/排序/数据范围）",
    )
    assert_db_unchanged(
        db_connection, menu_sql, menu_params, before_menu,
        desc="mgr_103 越权清空 CEO 角色的菜单授权",
    )


def test_scope_mgr_cancel_ceo_auth(base_url, db_connection, redis_client, isolation_users):
    """
    mgr_103（data_scope=3，dept=103）尝试取消 CEO 角色的用户授权。

    安全漏洞：cancelAuthUser 缺少 checkRoleDataScope 调用。

    前置：已授予 system:role:edit，所以请求能穿过 @PreAuthorize（第一层挡不住），
    而 cancelAuthUser 本身又没有第二层校验 → 预期漏洞被复现（返回 200），
    复现后立刻用 admin 把关联恢复回去。

    两种结果都要落到数据库上验证：
    - 被拦截 → sys_user_role 里的关联必须原样还在
    - 被放行 → 关联确实被删掉了（漏洞成立），随后由 admin 恢复
    """
    token = login_for_yaml(base_url, "at_mgr_103", redis_client)
    ceo_role_id = isolation_users["role_ids"]["at_ceo"]
    ceo_user_id = isolation_users["user_ids"]["at_ceo_user"]

    bind_sql = ("SELECT COUNT(*) AS cnt FROM sys_user_role "
                "WHERE role_id = %s AND user_id = %s")
    bind_params = [ceo_role_id, ceo_user_id]
    before_bind = db_row(db_connection, bind_sql, bind_params)
    assert before_bind["cnt"] == 1, (
        f"前置异常：CEO 用户与 CEO 角色的关联不唯一，本条用例无意义: {before_bind}"
    )

    resp = requests.put(
        f"{base_url}/system/role/authUser/cancel",
        json={"roleId": ceo_role_id, "userId": ceo_user_id},
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )
    result = resp.json()
    if result["code"] == 200:
        logs.warning(
            "⚠️ 安全漏洞确认：mgr_103 成功取消了 CEO 角色的用户授权！\n"
            "   原因：cancelAuthUser 缺少 checkRoleDataScope 调用"
        )
        # 漏洞成立 → 库里这条关联应该已经不在了
        after_bind = db_row(db_connection, bind_sql, bind_params)
        assert after_bind["cnt"] == before_bind["cnt"] - 1, (
            f"接口返回 200 但 sys_user_role 关联没被删除，"
            f"说明漏洞并未真正生效: {before_bind} → {after_bind}"
        )
        logs.warning(f"已确认关联被删除: {before_bind} → {after_bind}")

        # 修复：重新加回授权
        admin_token = get_runtime("admin_token")
        requests.put(
            f"{base_url}/system/role/authUser/selectAll",
            params={"roleId": ceo_role_id, "userIds": ceo_user_id},
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Authorization": f"Bearer {admin_token}",
            },
            timeout=10,
        )
        logs.info("已恢复 CEO 角色-用户关联")
    else:
        logs.info(f"漏洞在 Layer 1 被挡: code={result['code']}, msg={result.get('msg')}")
        assert_db_unchanged(
            db_connection, bind_sql, bind_params, before_bind,
            desc="mgr_103 越权取消 CEO 角色的用户授权",
        )
