"""
test_role/conftest.py —— 角色测试专用 fixtures

提供：
  db_connection        → session 级，SSH 隧道连 MySQL（autocommit=True）
  ensure_admin_login   → session autouse，admin → runtime.yaml["token"]
  clean_at_test_data   → session autouse，启动/结束时物理删除 at_% 角色+用户残留
  isolation_users      → session 级，预置隔离测试的 5 角色 + 7 用户

依赖根 conftest.py 的：
  ssh_tunnel  → SSH 隧道（Redis + MySQL 双端口转发）
  base_url    → 服务器地址
  redis_client → Redis 连接（已注入 DebugTalk）
"""

import allure
import pytest
import requests
from configparser import ConfigParser

from conf.setting import FILE_PATH
from utils.connection import ConnectMysql
from utils.debugtalk import DebugTalk
from utils.readyaml import write_runtime, get_runtime
from utils.recordlog import logs


def _read_config():
    cf = ConfigParser()
    cf.read(FILE_PATH["CONFIG"], encoding="utf-8")
    return cf


# ═══════════════════════════════════════════════════════════════
# 数据库连接
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def db_connection(ssh_tunnel):
    """
    依赖根 ssh_tunnel，走 SSH 隧道本地端口连 MySQL。
    ConnectMysql 内置 autocommit=True，每次 SELECT 都是最新快照。
    """
    cf = _read_config()
    db = ConnectMysql(
        host="127.0.0.1",
        port=ssh_tunnel["mysql_port"],
        user=cf.get("MYSQL", "username"),
        password=cf.get("MYSQL", "password"),
        database=cf.get("MYSQL", "database"),
    )
    logs.info("MySQL 连接成功（test_role）")

    yield db

    db.close()
    logs.info("MySQL 连接已关闭（test_role）")


# ═══════════════════════════════════════════════════════════════
# 数据清理（物理删除 at_% 测试数据）
# ═══════════════════════════════════════════════════════════════

def _delete_at_users(db):
    """
    物理删除所有 at_% 前缀的测试用户。
    清理顺序：子表（user_role / user_post）→ 主表（sys_user）。
    """
    db.execute(
        "DELETE FROM sys_user_role WHERE user_id IN "
        "(SELECT user_id FROM sys_user WHERE user_name LIKE 'at\\_%')"
    )
    db.execute(
        "DELETE FROM sys_user_post WHERE user_id IN "
        "(SELECT user_id FROM sys_user WHERE user_name LIKE 'at\\_%')"
    )
    db.execute(
        "DELETE FROM sys_user WHERE user_name LIKE 'at\\_%'"
    )


def _delete_at_roles(db):
    """
    物理删除所有 at_% 前缀的测试角色。
    清理顺序：中间表（user_role / role_menu / role_dept）→ 主表（sys_role）。
    """
    # 解除用户-角色关联
    db.execute(
        "DELETE FROM sys_user_role WHERE role_id IN "
        "(SELECT role_id FROM sys_role WHERE role_name LIKE 'at\\_%')"
    )
    # 删除角色-菜单关联
    db.execute(
        "DELETE FROM sys_role_menu WHERE role_id IN "
        "(SELECT role_id FROM sys_role WHERE role_name LIKE 'at\\_%')"
    )
    # 删除角色-部门关联
    db.execute(
        "DELETE FROM sys_role_dept WHERE role_id IN "
        "(SELECT role_id FROM sys_role WHERE role_name LIKE 'at\\_%')"
    )
    # 删除角色
    db.execute(
        "DELETE FROM sys_role WHERE role_name LIKE 'at\\_%'"
    )


@pytest.fixture(scope="session", autouse=True)
def clean_at_test_data(db_connection):
    """
    Session 启动时物理删除所有 at_% 残留（应对上次运行中断）。
    Session 结束时再清一次，不留痕迹。
    ConnectMysql autocommit=True，每次 execute 即时生效。
    """
    _delete_at_users(db_connection)
    _delete_at_roles(db_connection)
    logs.info("已清理 at_% 残留数据（session 启动）")

    yield

    _delete_at_users(db_connection)
    _delete_at_roles(db_connection)
    logs.info("已清理 at_% 残留数据（session 结束）")


# ═══════════════════════════════════════════════════════════════
# admin 登录
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="session", autouse=True)
def ensure_admin_login(base_url, redis_client):
    """
    Session 启动时用 admin 登录，token 写入 runtime.yaml。
    所有 CRUD 用例通过 inject_token() 自动获得 admin 权限。
    隔离用例显式引用 Authorization header 时 inject_token 自动跳过。
    """
    cf = _read_config()
    admin_user = cf.get("admin", "username")
    admin_pwd = cf.get("admin", "password")

    # 1. 获取验证码
    captcha_resp = requests.get(
        f"{base_url}/captchaImage",
        headers={"Accept": "application/json"},
        timeout=10,
    ).json()
    uuid = captcha_resp["uuid"]

    # 2. 从 Redis 读取验证码答案
    code = DebugTalk().get_captcha_code(uuid)
    assert code is not None, f"admin 登录失败：验证码已过期，uuid={uuid}"

    # 3. 登录
    login_resp = requests.post(
        f"{base_url}/login",
        json={
            "username": admin_user,
            "password": admin_pwd,
            "uuid": uuid,
            "code": code,
        },
        headers={"Content-Type": "application/json;charset=UTF-8"},
        timeout=10,
    )
    token = login_resp.json().get("token", "")
    assert token, f"admin 登录失败：未返回 token，响应: {login_resp.text}"

    # 4. 写入 runtime.yaml（token 供 inject_token 默认读取，
    #    admin_token 供隔离用例显式引用）
    write_runtime({"token": token, "admin_token": token})
    logs.info("admin 登录成功，token 已写入 runtime.yaml")


# ═══════════════════════════════════════════════════════════════
# 隔离测试预置数据
# ═══════════════════════════════════════════════════════════════

# 隔离角色定义：5 种 DataScope，仅授予 system:user:list 菜单权限
_ISOLATION_ROLES = [
    {"role_name": "at_ceo",       "role_key": "at_ceo",       "data_scope": "1"},
    {"role_name": "at_custom",    "role_key": "at_custom",    "data_scope": "2"},
    {"role_name": "at_mgr",       "role_key": "at_mgr",       "data_scope": "3"},
    {"role_name": "at_mgr_child", "role_key": "at_mgr_child", "data_scope": "4"},
    {"role_name": "at_emp",       "role_key": "at_emp",       "data_scope": "5"},
]

# 隔离用户定义
_ISOLATION_USERS = [
    {"username": "at_ceo_user",        "role_name": "at_ceo",       "dept_id": 103},
    {"username": "at_mgr_103",         "role_name": "at_mgr",       "dept_id": 103},
    {"username": "at_mgr_child_103",   "role_name": "at_mgr_child", "dept_id": 103},
    {"username": "at_emp_103",         "role_name": "at_emp",       "dept_id": 103},
    {"username": "at_custom_user",     "role_name": "at_custom",    "dept_id": 103},
    {"username": "at_mgr_106",         "role_name": "at_mgr",       "dept_id": 106},
    {"username": "at_emp_106",         "role_name": "at_emp",       "dept_id": 106},
]

# 所有角色共用：系统管理目录 + 用户管理菜单 + 用户查询按钮
_ISOLATION_MENU_IDS = [1, 100, 1000]


@pytest.fixture(scope="session")
def isolation_users(base_url, db_connection):
    """
    预置隔离测试的 5 个角色 + 7 个用户（session 级）。

    - 仅 test_role_scope.py 请求该 fixture 时才创建，CRUD 测试不受影响
    - 所有数据 at_ 前缀，session 结束时由 clean_at_test_data 自动清理
    - 返回 {role_name: role_id, username: user_id} 字典供测试直接引用
    """
    from test_runner.test_03_role.helpers import (
        build_scope_user,
        create_role,
        get_role_id,
    )

    token = get_runtime("token")
    role_ids = {}
    user_ids = {}

    # ── 1. 创建 5 个角色 ──
    for r in _ISOLATION_ROLES:
        role_id = create_role(
            base_url,
            role_name=r["role_name"],
            role_key=r["role_key"],
            data_scope=r["data_scope"],
            menu_ids=_ISOLATION_MENU_IDS,
        )
        role_ids[r["role_name"]] = role_id
        logs.info(f"隔离角色准备: {r['role_name']} (roleId={role_id}, "
                  f"data_scope={r['data_scope']})")

    # ── 2. 为 at_custom（data_scope=2）设置部门关联 ──
    custom_role_id = role_ids["at_custom"]
    resp = requests.put(
        f"{base_url}/system/role/dataScope",
        json={"roleId": custom_role_id, "dataScope": "2", "deptIds": [103, 105]},
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )
    assert resp.json().get("code") == 200, (
        f"设置 at_custom DataScope 失败: {resp.text}"
    )
    logs.info(f"隔离角色 at_custom: dataScope=2, deptIds=[103,105]")

    # ── 3. 创建 7 个用户 ──
    for u in _ISOLATION_USERS:
        rid = role_ids[u["role_name"]]
        user_id = build_scope_user(
            base_url,
            username=u["username"],
            dept_id=u["dept_id"],
            role_ids=[rid],
        )
        user_ids[u["username"]] = user_id
        logs.info(f"隔离用户准备: {u['username']} (userId={user_id}, "
                  f"role={u['role_name']}, dept={u['dept_id']})")

    # ── 4. 写入 runtime.yaml 供 YAML 引用 ──
    _runtime_map = {}
    for name, rid in role_ids.items():
        _runtime_map[f"isolation_{name}_role"] = rid
    for name, uid in user_ids.items():
        _runtime_map[f"isolation_{name}"] = uid
    write_runtime(_runtime_map)

    return {"role_ids": role_ids, "user_ids": user_ids}


# ═══════════════════════════════════════════════════════════
# Allure 钩子 —— story 按文件 + 函数名自动映射
# ═══════════════════════════════════════════════════════════

def pytest_collection_modifyitems(items):
    for item in items:
        path = str(item.fspath)
        fn = item.originalname

        # ── DataScope 隔离（test_role_scope.py）──
        if "test_role_scope" in path:
            item.add_marker(allure.story("DataScope隔离"))
            continue

        # ── 角色 CRUD（test_role_crud.py）──
        if "test_role_add" in fn:
            item.add_marker(allure.story("新增角色"))
        elif "test_role_edit" in fn:
            item.add_marker(allure.story("编辑角色"))
        elif "test_role_delete" in fn:
            item.add_marker(allure.story("删除角色"))
        elif "test_role_changeStatus" in fn:
            item.add_marker(allure.story("角色状态"))
        elif "test_role_dataScope" in fn:
            item.add_marker(allure.story("DataScope设置"))
        elif "test_role_authUser" in fn:
            item.add_marker(allure.story("用户授权"))
