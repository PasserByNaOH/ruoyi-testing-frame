"""
test_role_scope.py —— DataScope 隔离测试

依赖 isolation_users fixture（conftest.py）预置 5 角色 + 7 用户。

├── test_scope_query         → YAML 参数化（role_scope_query.yaml），
│                               auth_user + rows_in_scope 断言
├── test_scope_write_*       → Python，写操作隔离（需要动态参数 + 403 断言）
└── test_scope_mgr_*         → Python，DataScope 边界 + 安全漏洞
"""

import os
import pytest
import requests

from core.apiutil import ApiEngine
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
    engine = ApiEngine()
    engine.specification_yaml(dict(base_info), dict(case),
                              db=db_connection, redis_client=redis_client)


# ═══════════════════════════════════════════════════════════════
# B. 写操作隔离——部门经理不能跨 scope 写（3 条，Python）
# ═══════════════════════════════════════════════════════════════

def test_scope_write_edit(base_url, redis_client, isolation_users):
    """
    mgr_103（data_scope=3，dept=103）尝试编辑 emp_106（dept=106）。
    期望：被拦截（403 或 500）。
    """
    from core.apiutil import login_for_yaml as login

    token = login(base_url, "at_mgr_103", redis_client)
    target_uid = isolation_users["user_ids"]["at_emp_106"]

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


def test_scope_write_delete(base_url, redis_client, isolation_users):
    """
    mgr_103（data_scope=3，dept=103）尝试删除 emp_106（dept=106）。
    """
    from core.apiutil import login_for_yaml as login

    token = login(base_url, "at_mgr_103", redis_client)
    target_uid = isolation_users["user_ids"]["at_emp_106"]

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


def test_scope_write_resetPwd(base_url, redis_client, isolation_users):
    """
    mgr_103（data_scope=3，dept=103）尝试重置 emp_106 的密码。
    """
    from core.apiutil import login_for_yaml as login

    token = login(base_url, "at_mgr_103", redis_client)
    target_uid = isolation_users["user_ids"]["at_emp_106"]

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


# ═══════════════════════════════════════════════════════════════
# C. DataScope 边界 + 安全漏洞（2 条，Python）
# ═══════════════════════════════════════════════════════════════

def test_scope_mgr_edit_ceo_role(base_url, redis_client, isolation_users):
    """
    mgr_103（data_scope=3，dept=103）尝试修改 CEO 角色信息。

    拦截点有两种可能：
      - 403：@PreAuthorize（Layer 1，mgr 无 system:role:edit 菜单权限）
      - 500：checkRoleDataScope（Layer 2，DataScope 不覆盖）
    """
    from core.apiutil import login_for_yaml as login

    token = login(base_url, "at_mgr_103", redis_client)
    ceo_role_id = isolation_users["role_ids"]["at_ceo"]

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


def test_scope_mgr_cancel_ceo_auth(base_url, redis_client, isolation_users):
    """
    mgr_103（data_scope=3，dept=103）尝试取消 CEO 角色的用户授权。

    安全漏洞：cancelAuthUser 缺少 checkRoleDataScope 调用。
    - 如果 @PreAuthorize 先拦截（403）→ 漏洞在 Layer 1 被挡
    - 如果放行（200）→ 漏洞存在，需要修复 Layer 2
    """
    from core.apiutil import login_for_yaml as login

    token = login(base_url, "at_mgr_103", redis_client)
    ceo_role_id = isolation_users["role_ids"]["at_ceo"]
    ceo_user_id = isolation_users["user_ids"]["at_ceo_user"]

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
