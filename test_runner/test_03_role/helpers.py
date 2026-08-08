"""
test_role/helpers.py —— 角色测试可复用工具

供 test_role_crud / test_role_scope / test_role_integration 共用。
"""

import requests

from utils.assertions import coerce_db_param
from utils.debugtalk import DebugTalk
from utils.readyaml import get_runtime, write_runtime
from utils.recordlog import logs


# ═══════════════════════════════════════════════════════════════
# 多用户登录
# ═══════════════════════════════════════════════════════════════

def login_as_user(base_url, redis_client, username, password="123456"):
    """
    以指定用户登录，token 写入 runtime.yaml["{username}_token"]。

    如果 runtime 中已有该用户的 token，先通过 /getInfo 验证是否过期；
    过期则重新登录。避免每个用例重复调 /login。
    """
    token_key = f"{username}_token"
    existing = get_runtime(token_key)

    if existing:
        # 验证 token 是否仍然有效
        resp = requests.get(
            f"{base_url}/getInfo",
            headers={"Authorization": f"Bearer {existing}"},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json().get("code") == 200:
            logs.info(f"用户 [{username}] 复用已有 token")
            return existing
        logs.info(f"用户 [{username}] token 已过期，重新登录")

    # 1. 获取验证码
    captcha_resp = requests.get(
        f"{base_url}/captchaImage",
        headers={"Accept": "application/json"},
        timeout=10,
    ).json()
    uuid = captcha_resp["uuid"]

    # 2. Redis 取验证码答案
    code = DebugTalk().get_captcha_code(uuid)
    assert code is not None, f"[{username}] 验证码已过期，uuid={uuid}"

    # 3. 登录
    login_resp = requests.post(
        f"{base_url}/login",
        json={
            "username": username,
            "password": password,
            "uuid": uuid,
            "code": code,
        },
        headers={"Content-Type": "application/json;charset=UTF-8"},
        timeout=10,
    )
    token = login_resp.json().get("token", "")
    assert token, (
        f"[{username}] 登录失败，未返回 token\n"
        f"  响应: {login_resp.text}"
    )

    # 4. 写入 runtime.yaml
    write_runtime({token_key: token})
    logs.info(f"用户 [{username}] 登录成功, token → runtime.{token_key}")
    return token


# ═══════════════════════════════════════════════════════════════
# DataScope 范围计算（复用 DataScopeAspect 的 SQL 逻辑）
# ═══════════════════════════════════════════════════════════════

def get_user_scope(db, username):
    """
    计算指定用户的数据权限范围。
    复用若依 DataScopeAspect 的 5 条 SQL 规则，返回验证所需信息。

    参数:
        db:       ConnectMysql 实例（autocommit=True）
        username: 用户名

    返回:
        {
            "user_id":          int,     # 用户自己的 userId
            "dept_id":          int,     # 用户自己的 deptId
            "allowed_dept_ids": set | None,
                # None   → data_scope=1（全部），不限制部门
                # set()  → 具体部门集合
            "is_self_only":     bool,
                # True → data_scope=5（仅本人），不按部门过滤，
                #         需要按 userId 验证
        }
    """
    # 1. 查用户基本信息
    user_rows = db.query(
        "SELECT user_id, dept_id FROM sys_user WHERE user_name = %s",
        [username],
    )
    assert user_rows, f"用户不存在: {username}"
    user_id = user_rows[0]["user_id"]
    dept_id = user_rows[0]["dept_id"]

    # 2. 查用户所有启用角色的 data_scope
    roles = db.query(
        "SELECT r.role_id, r.data_scope FROM sys_role r "
        "JOIN sys_user_role ur ON r.role_id = ur.role_id "
        "WHERE ur.user_id = %s AND r.status = '0' AND r.del_flag = '0'",
        [user_id],
    )

    # 3. 按 data_scope 值分类计算部门范围
    allowed_dept_ids = set()
    is_self_only = False

    for role in roles:
        ds = role["data_scope"]

        if ds == "1":
            # 全部数据权限 → 不限制
            return {
                "user_id": user_id,
                "dept_id": dept_id,
                "allowed_dept_ids": None,
                "is_self_only": False,
            }

        elif ds == "2":
            # 自定义数据权限 → sys_role_dept 表查关联部门
            depts = db.query(
                "SELECT dept_id FROM sys_role_dept WHERE role_id = %s",
                [role["role_id"]],
            )
            allowed_dept_ids.update(d["dept_id"] for d in depts)

        elif ds == "3":
            # 本部门数据权限 → 仅自己的 dept
            allowed_dept_ids.add(dept_id)

        elif ds == "4":
            # 本部门及以下 → FIND_IN_SET 利用 ancestors 一次查出自己+所有子孙
            subs = db.query(
                "SELECT dept_id FROM sys_dept "
                "WHERE dept_id = %s OR FIND_IN_SET(%s, ancestors)",
                [dept_id, dept_id],
            )
            allowed_dept_ids.update(d["dept_id"] for d in subs)

        elif ds == "5":
            is_self_only = True

    # 仅本人：如果同时有 data_scope=2/3/4 的角色，走部门过滤；
    # 只有当所有角色都是 data_scope=5 时，才走 userId 验证。
    if is_self_only and not allowed_dept_ids:
        return {
            "user_id": user_id,
            "dept_id": dept_id,
            "allowed_dept_ids": None,
            "is_self_only": True,
        }

    return {
        "user_id": user_id,
        "dept_id": dept_id,
        "allowed_dept_ids": allowed_dept_ids or None,
        "is_self_only": False,
    }


# ═══════════════════════════════════════════════════════════════
# DataScope 范围验证
# ═══════════════════════════════════════════════════════════════

def assert_rows_in_scope(rows, scope, dept_field="deptId", user_field="userId"):
    """
    断言 rows 中所有行都在 scope 范围内。

    参数:
        rows:        API 返回的列表
        scope:       get_user_scope() 的返回值
        dept_field:  rows 中表示部门 ID 的字段名
        user_field:  rows 中表示用户 ID 的字段名
    """
    if scope["is_self_only"]:
        # 仅本人 → 最多一条记录，且 userId 等于自己
        assert len(rows) <= 1, (
            f"仅本人权限但返回了 {len(rows)} 条记录\n"
            f"  预期: ≤1 条\n"
            f"  实际 rows userIds: {[r.get(user_field) for r in rows]}"
        )
        if rows:
            actual_user = rows[0].get(user_field)
            assert actual_user == scope["user_id"], (
                f"仅本人权限但返回了其他用户的数据\n"
                f"  预期 userId: {scope['user_id']}\n"
                f"  实际 userId: {actual_user}"
            )

    elif scope["allowed_dept_ids"] is not None:
        # 有部门范围限制 → 每行的部门必须在集合内
        for row in rows:
            actual_dept = row.get(dept_field)
            assert actual_dept in scope["allowed_dept_ids"], (
                f"DataScope 泄漏：行中 {dept_field}={actual_dept} "
                f"不在允许范围 {scope['allowed_dept_ids']} 内\n"
                f"  用户 dept_id: {scope['dept_id']}\n"
                f"  行数据: {row}"
            )

    # scope["allowed_dept_ids"] is None 且 is_self_only=False
    # → data_scope=1（全部），不限制，总是通过


# ═══════════════════════════════════════════════════════════════
# 角色 CRUD 工具
# ═══════════════════════════════════════════════════════════════

def create_role(base_url, role_name, role_key, data_scope="1",
                menu_ids=None, dept_ids=None, role_sort=10, status="0"):
    """
    POST /system/role 创建测试角色，返回 role_id。

    token 从 runtime.yaml 读取（由 ensure_admin_login 写入）。
    同时把 role_id 写入 runtime["created_role_id"]，供后续用例引用。
    """
    token = get_runtime("token")
    body = {
        "roleName": role_name,
        "roleKey": role_key,
        "roleSort": role_sort,
        "status": status,
        "dataScope": data_scope,
        "menuIds": menu_ids or [],
        "deptIds": dept_ids or [],
    }

    resp = requests.post(
        f"{base_url}/system/role",
        json=body,
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )

    result = resp.json()
    if result.get("code") != 200:
        logs.error(f"创建角色失败 [{role_name}]: {result}")
        raise RuntimeError(f"创建角色失败: {result.get('msg')}")

    # POST 不返回 roleId，通过列表查询
    role_id = get_role_id(base_url, role_name)
    write_runtime({"created_role_id": role_id})
    logs.info(f"角色已创建: {role_name} (roleId={role_id})")
    return role_id


def get_role_id(base_url, role_name):
    """
    通过 /system/role/list 查询 roleId。
    返回 int，不存在返回 None。
    """
    token = get_runtime("token")
    resp = requests.get(
        f"{base_url}/system/role/list",
        params={"roleName": role_name, "pageSize": 10},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    rows = resp.json().get("rows", [])
    if rows:
        return rows[0]["roleId"]
    logs.warning(f"未找到角色: {role_name}")
    return None


# ═══════════════════════════════════════════════════════════════
# 隔离测试用户预置工具
# ═══════════════════════════════════════════════════════════════

def build_scope_user(base_url, username, dept_id, role_ids,
                     password="123456", nick_name=None):
    """
    POST /system/user 创建隔离测试用户，返回 userId。

    用于 isolation 预置 fixture 中批量创建不同部门、不同角色的测试用户。
    """
    token = get_runtime("token")
    body = {
        "deptId": dept_id,
        "userName": username,
        "nickName": nick_name or username,
        "password": password,
        "sex": "0",
        "status": "0",
        "postIds": [2],
        "roleIds": role_ids,
    }

    resp = requests.post(
        f"{base_url}/system/user",
        json=body,
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )

    result = resp.json()
    if result.get("code") != 200:
        logs.error(f"创建隔离用户失败 [{username}]: {result}")
        raise RuntimeError(f"创建隔离用户失败: {result.get('msg')}")

    # 查询 userId
    token_val = get_runtime("token")
    list_resp = requests.get(
        f"{base_url}/system/user/list",
        params={"userName": username},
        headers={"Authorization": f"Bearer {token_val}"},
        timeout=10,
    )
    rows = list_resp.json().get("rows", [])
    user_id = rows[0]["userId"] if rows else None
    logs.info(f"隔离用户已创建: {username} (userId={user_id}, dept={dept_id})")
    return user_id
