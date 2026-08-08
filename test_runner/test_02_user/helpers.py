"""
test_user/helpers.py —— 用户管理测试可复用工具

供 test_user.py 使用，避免重复代码。
"""

import requests
from utils.readyaml import get_runtime, write_runtime
from utils.recordlog import logs


def get_user_id(base_url, username):
    """
    通过 /system/user/list 查询 userId。
    返回 int 类型的 userId，不存在返回 None。
    """
    token = get_runtime("token")
    resp = requests.get(
        f"{base_url}/system/user/list",
        params={"userName": username},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    rows = resp.json().get("rows", [])
    if rows:
        return rows[0]["userId"]
    logs.warning(f"未找到用户: {username}")
    return None


def create_user(base_url, username):
    """
    POST /system/user 创建前置测试用户，返回 userId。
    默认字段：deptId=103, password="123456", postIds=[2], roleIds=[2]。
    """
    data = {
        "deptId": 103,
        "userName": username,
        "nickName": username,
        "password": "123456",
        "sex": "0",
        "status": "0",
        "postIds": [2],
        "roleIds": [2],
    }

    token = get_runtime("token")
    resp = requests.post(
        f"{base_url}/system/user",
        json=data,
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )

    result = resp.json()
    if result.get("code") != 200:
        logs.error(f"创建前置用户失败 [{username}]: {result}")
        raise RuntimeError(f"创建前置用户失败: {result.get('msg')}")

    # POST 不返回 userId，需要查询
    user_id = get_user_id(base_url, username)
    write_runtime({"created_user_id": user_id})
    logs.info(f"前置用户已创建: {username} (userId={user_id})")
    return user_id
