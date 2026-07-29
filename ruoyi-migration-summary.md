---
name: ruoyi-migration-startup-summary
description: 若依适配新对话启动摘要——框架学习完成后的改造起点
date: 2026-07-29
---

# 若依适配新对话启动摘要

## 一、当前状态

已完成对 `Test-Automation-Framework` 的完整分析，笔记在 [framework-learning-entity-and-repository.md](framework-learning-entity-and-repository.md)。

### 框架四层结构

| 层 | 包含 | 核心文件 |
|---|---|---|
| 用例与配置 | YAML 用例、config.ini、extract.yaml | testcase/、data/、conf/ |
| 数据工具 | 9 个 common/ 模块 | readyaml、sendrequest、connection、recordlog 等 |
| 执行引擎 | 编排 + 断言 + 函数工具箱 | apiutil.py、assertions.py、debugtalk.py |
| 启动框架 | pytest + conftest + 入口 | conftest.py、test_*.py、run.py |

### 一条请求的完整链路

```
YAML → parametrize → specification_yaml()
  → replace_load(${...}) → getattr(DebugTalk)
  → SendRequest.run_main() → requests.session.request()
  → json.loads(res.text)
  → extract_data() → jsonpath → write_yaml_data()
  → assert_result() → flag 累加 → assert flag == 0
```

## 二、若依环境信息

| 项目 | 信息 |
|---|---|
| 服务器 | `47.109.149.194:8080`（若依管理系统） |
| MySQL | Docker 运行，仅绑定 `127.0.0.1:3306` |
| Redis | Docker 运行，仅绑定 `127.0.0.1:6379` |
| SSH | `root@47.109.149.194:22` |
| 验证码类型 | `math`（算式计算） |
| 密码加密 | BCrypt（不是 MD5/SHA1） |
| 账户锁定 | 5 次失败 → 锁定 10 分钟，Redis key: `pwd_err_cnt:{username}` |

### 若依响应模型（与 Mock 服务的区别）

```
Mock 服务：HTTP 状态码分散（200/401/500）+ JSON body
若依系统：HTTP 永远 200，状态码在 JSON body 的 code 字段

若依典型响应：
{"code":200, "msg":"操作成功", "data":{...}}
{"code":500, "msg":"验证码错误"}
```

## 三、改造清单（优先级排序）

### 高优先级

**□ 5.2 SSH 隧道方案**
- 在 conftest.py 加 `ssh_tunnel` fixture（`SSHTunnelForwarder`）
- 远程 MySQL 3306 → 本地 13306，远程 Redis 6379 → 本地 16379
- connection.py 不改，config.ini host=127.0.0.1 port=隧道端口
- 依赖：`pip install sshtunnel "paramiko<3.0"`
- 参考：`manuTest/5-RedisLoginTest/conftest.py`

**□ 5.3 替换 Excel 为 openpyxl**
- 新建 `common/excelutil.py`（openpyxl）
- 删除 `common/handleExcel.py`（xlrd/xlwt，只认 .xls）
- 依赖：`pip install openpyxl`

**□ 5.5 新增二进制文件断言**
- apiutil.py：判断 Content-Type，二进制响应跳过 `json.loads()`
- assertions.py：新增 `assert_export_file()` + 注册 key='export'

**□ 5.6 新增 Redis 键值断言**
- assertions.py：新增 `assert_redis_data()` + 注册 key='redis'
- YAML 用法：`validation: - redis: {key: "xxx", operation: exists}`
- 参考：`manuTest/5-RedisLoginTest/` 中的 Redis 验证逻辑

**□ config.ini 改造**
```ini
[api_envi]
host = http://47.109.149.194:8080

[SSH]
host = 47.109.149.194
port = 22
username = root
password = 你的密码

[MYSQL]
host = 127.0.0.1
port = 13306
username = root
password = 你的数据库密码
database = ruoyi

[REDIS]
host = 127.0.0.1
port = 16379
password = 你的Redis密码
db = 0
```

**□ conftest.py 改造**
- 新加 `ssh_tunnel` fixture（session 级）
- `system_login` 改为调若依登录接口
- `datadb_init` 取消注释，实现测试数据准备/清理

**□ debugtalk.py 改造**
- 删除业务随机值方法（`fenceAlarm_*`、`fatigueAlarm_*`、`jurisdictionAlarm_*`）
- 新增若依专用方法（如 `get_captcha_code(uuid)` 从 Redis 拿验证码）
- 加密方法（md5/sha1/base64）若依不用 BCrypt，可删

**□ 编写若依 YAML 用例**
- 若依登录（验证码获取 → 登录 → 提取 token）
- 用户 CRUD（增/删/改/查）
- 角色管理
- 导入导出
- 账户锁定测试

### 低优先级

**□ 5.1 删除 sendrequest.py 中不用的 get()/post() 方法**

**□ 5.4 重构 get_extract_data 数字编码为可读参数名**

## 四、新对话启动模板

在新对话中直接粘贴：

```
我要把一个测试框架改造成适配若依管理系统。框架的完整分析
笔记在 docs/framework-learning-entity-and-repository.md，
启动摘要（改造清单、环境信息）在 docs/ruoyi-migration-summary.md。

首先从 SSH 隧道方案开始——若依部署在云服务器 47.xxx，
MySQL/Redis 在 Docker 里只绑 127.0.0.1，必须先解决连接问题。
参考我 manuTest/5-RedisLoginTest/conftest.py 中已验证的
sshtunnel 方案。
```

## 五、关键参考

| 内容 | 位置 |
|---|---|
| 框架完整学习笔记 | `docs/framework-learning-entity-and-repository.md` |
| manuTest SSH 隧道实现 | `D:\TestingFrame\manuTest\5-RedisLoginTest\conftest.py` |
| manuTest Redis 踩坑记录 | `D:\TestingFrame\manuTest\5-RedisLoginTest\SETUP_NOTES.md` |
| manuTest Redis key 速查 | 同上文档第五节 |
| 若依配置示例 | `D:\TestingFrame\manuTest\5-RedisLoginTest\config.example.ini` |
