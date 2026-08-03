"""
debug_edit.py —— 编辑用户分步调试脚本

每一步执行后暂停，在 DBeaver 里刷新 sys_user 表观察变化。
用法：python debug_edit.py
"""

import requests
import pymysql
from configparser import ConfigParser
from sshtunnel import SSHTunnelForwarder

from conf.setting import FILE_PATH
from utils.debugtalk import DebugTalk

cf = ConfigParser()
cf.read(FILE_PATH["CONFIG"], encoding="utf-8")
host = cf.get("api_envi", "host")

# ═══════════════════════════════════════════════════════════════
# Step 1: 建立 SSH 隧道 + MySQL 连接
# ═══════════════════════════════════════════════════════════════
input("\n[Step 1] 建立 SSH 隧道... (按回车)")

tunnel = SSHTunnelForwarder(
    (cf.get("SSH", "host"), cf.getint("SSH", "port")),
    ssh_username=cf.get("SSH", "username"),
    ssh_password=cf.get("SSH", "password"),
    remote_bind_addresses=[
        ("127.0.0.1", cf.getint("REDIS", "port")),
        ("127.0.0.1", cf.getint("MYSQL", "port")),
    ],
)
tunnel.start()
redis_port = tunnel.local_bind_ports[0]
mysql_port = tunnel.local_bind_ports[1]
print(f"隧道已建立 → Redis 端口: {redis_port}, MySQL 端口: {mysql_port}")

conn = pymysql.connect(
    host="127.0.0.1", port=mysql_port,
    user=cf.get("MYSQL", "username"), password=cf.get("MYSQL", "password"),
    database=cf.get("MYSQL", "database"), charset="utf8mb4",
)
cur = conn.cursor(pymysql.cursors.DictCursor)

import redis
r = redis.Redis(host="127.0.0.1", port=redis_port,
                password=cf.get("REDIS", "password") or None,
                db=cf.getint("REDIS", "db"), decode_responses=True)
DebugTalk.set_redis_client(r)
print("MySQL + Redis 连接成功")

# ═══════════════════════════════════════════════════════════════
# Step 2: 清理 + 登录 admin
# ═══════════════════════════════════════════════════════════════
input("\n[Step 2] 清理旧数据 + 登录 admin... (按回车)")

cur.execute("DELETE FROM sys_user WHERE user_name = 'at_debug_x'")
conn.commit()
print("已清理 at_debug_x")

captcha_resp = requests.get(f"{host}/captchaImage",
                            headers={"Accept": "application/json"}, timeout=10).json()
uuid = captcha_resp["uuid"]
code = DebugTalk().get_captcha_code(uuid)
print(f"验证码: uuid={uuid}, code={code}")

login_resp = requests.post(
    f"{host}/login",
    json={"username": cf.get("admin", "username"),
          "password": cf.get("admin", "password"),
          "uuid": uuid, "code": code},
    headers={"Content-Type": "application/json;charset=UTF-8"}, timeout=10,
)
token = login_resp.json()["token"]
headers = {"Content-Type": "application/json;charset=UTF-8",
           "Authorization": f"Bearer {token}"}
print(f"admin 登录成功, token={token[:20]}...")

# ═══════════════════════════════════════════════════════════════
# Step 3: 创建用户 at_debug_x
# ═══════════════════════════════════════════════════════════════
input("\n[Step 3] 创建 at_debug_x... (按回车，然后去 DBeaver 刷新 sys_user)")

add_body = {
    "deptId": 103, "userName": "at_debug_x", "nickName": "调试用户",
    "password": "123456", "sex": "0", "status": "0",
    "postIds": [2], "roleIds": [2],
}
add_resp = requests.post(f"{host}/system/user", json=add_body, headers=headers, timeout=10)
print(f"POST /system/user → code={add_resp.json()['code']}, msg={add_resp.json()['msg']}")

# 查 userId
list_resp = requests.get(f"{host}/system/user/list",
                         params={"userName": "at_debug_x"},
                         headers=headers, timeout=10)
rows = list_resp.json().get("rows", [])
user_id = rows[0]["userId"] if rows else None
print(f"查到的 userId = {user_id}")

# MySQL 直接查
cur.execute("SELECT * FROM sys_user WHERE user_name = 'at_debug_x'")
db_row = cur.fetchone()
print(f"MySQL 直接查: {dict(db_row) if db_row else '不存在！'}")

input("\n>>> 去 DBeaver 看一眼 sys_user，有没有 at_debug_x？(按回车继续)")

# ═══════════════════════════════════════════════════════════════
# Step 4: 编辑 at_debug_x
# ═══════════════════════════════════════════════════════════════
input("\n[Step 4] 编辑 at_debug_x... (按回车)")

edit_body = {
    "deptId": 103, "userId": user_id, "userName": "at_debug_x",
    "nickName": "编辑后-调试用户",
    "phonenumber": "13900139001", "email": "debug@test.com",
    "sex": "1", "status": "0", "postIds": [3], "roleIds": [2],
}
edit_resp = requests.put(f"{host}/system/user", json=edit_body, headers=headers, timeout=10)
print(f"PUT /system/user → code={edit_resp.json()['code']}, msg={edit_resp.json()['msg']}")
print(f"发送的 body: nickName=编辑后-调试用户, email=debug@test.com, phone=13900139001, sex=1")

input("\n>>> 去 DBeaver 刷新，nick_name 变成 '编辑后-调试用户' 了吗？(按回车继续)")

# MySQL 确认
cur.execute("SELECT * FROM sys_user WHERE user_name = 'at_debug_x'")
after_row = cur.fetchone()
print(f"MySQL 查询结果: {dict(after_row) if after_row else '不存在！'}")

# ═══════════════════════════════════════════════════════════════
# 清理
# ═══════════════════════════════════════════════════════════════
input("\n[最后] 清理 at_debug_x... (按回车)")
cur.execute("DELETE FROM sys_user WHERE user_name = 'at_debug_x'")
conn.commit()
cur.close()
conn.close()
tunnel.stop()
print("清理完毕，连接已关闭。")
