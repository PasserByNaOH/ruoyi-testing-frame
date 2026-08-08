---
project: ruoyi-testing-frame
description: 项目启动文档——每开新对话时首先阅读此文件
last_updated: 2026-08-08
current_phase: 项目完结（Phase 1-6 全部完成）
---

# 若依测试框架改造 · 项目启动文档

> **给新对话的第一句话**（直接粘贴）：
> "阅读 project-startup.md，先阅读整个项目代码，再继续推进若依测试框架改造项目。"

---

## 一、项目背景

将 `Test-Automation-Framework`（一个 Python + pytest + YAML 数据驱动的 API 测试框架）改造成适配**若依管理系统**的自动化测试框架。

### 关键路径

| 内容 | 绝对路径 |
|------|----------|
| 当前工作目录 | `E:\LearningMall\AutoFrame\Manu_Frame\ruoyi-testing-frame` |
| 原框架源码 | `E:\LearningMall\AutoFrame\Test-Automation-Framework` |
| 若依后端源码 | `E:\LearningMall\AutoFrame\RuoYi-Vue` |
| 若依前端源码 | `E:\LearningMall\AutoFrame\RuoYi-Vue\ruoyi-ui` |
| manuTest 学习笔记 | `E:\LearningMall\AutoFrame\Manu_Frame\manuTest` |
| SSH 隧道参考 | `E:\LearningMall\AutoFrame\Manu_Frame\manuTest\4-RedisTest\conftest.py` |
| 框架学习笔记 | `docs/framework-learning-entity-and-repository.md`（新仓库未含，待补充） |
| 手动测试笔记（案例来源） | 本机不存在（案例已在 `test_data/` YAML 中实现） |
| 改造摘要 | `ruoyi-migration-summary.md` |
| 内存文件 | `C:\Users\PasserByNaOH\.claude\projects\E--LearningMall-AutoFrame-Manu-Frame\memory\` |

### 若依环境

| 项目 | 信息 |
|------|------|
| 服务器 | `47.109.149.194:8080` |
| MySQL | Docker，仅绑 `127.0.0.1:3306` |
| Redis | Docker，仅绑 `127.0.0.1:6379` |
| SSH | `root@47.109.149.194:22` |
| 验证码类型 | `math`（算式计算） |
| HTTP 响应 | 永远 200，业务状态码在 JSON body 的 `code` 字段 |

### 参考代码速查

用户可以直接说"阅读若依源码"、"参考 manuTest 的 SSH 实现"等，无需贴路径。

| 速查标签 | 绝对路径 |
|----------|----------|
| 若依后端源码 | `E:\LearningMall\AutoFrame\RuoYi-Vue` |
| 若依前端源码 | `E:\LearningMall\AutoFrame\RuoYi-Vue\ruoyi-ui` |
| 原测试框架源码 | `E:\LearningMall\AutoFrame\Test-Automation-Framework` |
| manuTest（手动测试项目） | `E:\LearningMall\AutoFrame\Manu_Frame\manuTest` |
| manuTest SSH 隧道参考 | `E:\LearningMall\AutoFrame\Manu_Frame\manuTest\4-RedisTest\conftest.py` |
| 手动测试笔记（案例来源） | 本机不存在（案例已在 `test_data/` YAML 中实现） |

---

## 二、最终目录结构（目标）

```
ruoyi-testing-frame/              ← GitHub 仓库根目录
│
├── conf/                         ← 配置层（框架配置）
│   ├── config.ini                ← 数据库/Redis/SSH/API 地址
│   └── setting.py                ← 全局设置常量
│
├── core/                         ← 核心引擎层（原 base/）
│   ├── __init__.py
│   └── apiutil.py                ← 编排引擎：变量替换 → 请求 → 提取 → 断言
│
├── utils/                        ← 工具库层（原 common/）
│   ├── __init__.py
│   ├── assertions.py             ← 断言工具箱（VALIDATORS dict，可扩展）
│   ├── connection.py             ← MySQL/Redis 连接池管理
│   ├── debugtalk.py              ← 热加载函数（${...} 反射调用的方法）
│   ├── readyaml.py               ← YAML 读取 + runtime.yaml 读写
│   ├── recordlog.py              ← 日志（日期命名，WARNING 写文件/INFO 控制台）
│   └── sendrequest.py            ← HTTP 请求封装（不处理响应 JSON）
│
├── test_data/                    ← 测试数据层（纯 YAML，与执行代码彻底分离）
│   └── ruoyi/
│       └── login/
│           └── yamlRead_test.yaml ← 验证码登录测试用例（3 条，在 .gitignore）
│
├── test_runner/                  ← 测试执行层（纯 pytest，执行器）
│   ├── __init__.py
│   ├── conftest.py               ← fixture：SSH 隧道、登录、数据准备
│   ├── test_login.py             ← 登录用例执行器
│   ├── test_user.py              ← 用户管理执行器
│   └── test_role.py              ← 角色管理执行器
│
├── data/                         ← 运行时数据
│   └── runtime.yaml              ← 运行时变量（token、验证码答案等，仿 Postman 环境变量）
│
├── logs/                         ← 日志输出
├── report/                       ← 测试报告（allure）
├── .github/                      ← GitHub Actions（可选）
├── Jenkinsfile                   ← Jenkins 流水线（Phase 5）
├── conftest.py                   ← 根级 fixture（清理 + 报告汇总）
├── run.py                        ← 一键启动入口
├── pytest.ini                    ← pytest 配置
├── pyproject.toml                ← 依赖管理（uv）
├── .gitignore
├── .env.example                  ← 敏感信息模板（不提交到 git）
└── README.md
```

**命名映射（原 → 新）：**

| 旧 | 新 | 理由 |
|----|----|------|
| `base/` | `core/` | 更准确表达"引擎"含义 |
| `common/` | `utils/` | 避免变成垃圾桶目录 |
| `testcase/` | `test_data/` + `test_runner/` | **数据与执行彻底分离** |

---

## 三、Phase 划分

### Phase 0 · 项目初始化 ✅ 完成
**目标：** GitHub 仓库就绪，项目骨架就位，核心模块逐个重建
```
✔ 创建 GitHub 公开仓库 ruoyi-testing-frame
✔ 本地 git init + 关联远程
✔ 搭建目录结构（conf/core/utils/test_data/test_runner/data/logs/report/.github）
✔ 配置 .gitignore（排除 project-startup.md、ruoyi-migration-summary.md）
✔ 逐个重建核心模块（参考原框架思路，改进写法，只保留若依需要的部分）
  ✔ conf/config.ini + conf/setting.py      — 配置层
  ✔ utils/recordlog.py                      — 日志（日期命名，TimedRotatingFileHandler）
  ✔ utils/readyaml.py                       — YAML 读取 + runtime 变量管理
  ✔ utils/sendrequest.py                    — HTTP 请求封装
  ✔ utils/connection.py                     — MySQL/Redis 连接池（待隧道验证）
  ✔ utils/debugtalk.py                      — 热加载函数（timestamp/random_str/captcha/runtime）
  ✔ utils/assertions.py                     — 断言工具箱（VALIDATORS 字典模式）
  ✔ core/apiutil.py                         — 编排引擎（replace_load/extract_data/specification_yaml）
✔ config.ini 已配置（含真实 IP 和密码，不提交 git）
✘ 暂缓：pyproject.toml / uv 依赖管理（pip 手动安装依赖即可）
✘ 暂缓：pytest --collect-only（Phase 1 conftest.py 编写后执行）
```
**分支：** `master`（Phase 0 直接在 master 开发，未按原计划开 feature 分支）

### Phase 1 · SSH 隧道 + conftest.py ✅ 完成

**目标**：打通 MySQL + Redis，框架能连上数据库，pytest --collect-only 能跑通

**实际实现**：
```
新增/修改：
  ├── conftest.py（根目录）
  │     └── ssh_tunnel fixture  → session 级，SSHTunnelForwarder 双端口转发
  │         yield {"tunnel", "redis_port", "mysql_port"} 字典
  ├── pytest.ini                → pytest 基本配置（testpaths/python_files/addopts）
  └── test_runner/test_connect_api/
        └── test_connections.py → Redis ping + MySQL SELECT 1 冒烟验证
```

**验收通过**：
- ✅ SSH 隧道 → Redis 本地端口 + MySQL 本地端口
- ✅ Redis ping 通
- ✅ MySQL SELECT 1 返回 1
- ✅ pytest --collect-only 收集到 2 条用例

**踩坑记录**：
- paramiko 3.x 移除了 DSSKey，sshtunnel 不兼容 → 锁定 `paramiko<3.0`
- pymysql `charset="utf-8"` 报 NoneType encoding → 改用 `charset="utf8mb4"`

**对应手动案例**：基础设施，不直接对应案例

**工时**：~2h

---

### Phase 2 · 登录全链路 ✅ 完成

**目标**：跑通 15 条登录用例（12 条计划 → 分析代码分支后扩展至 15 条）

**实际实现**：
```
新增：
  ├── test_data/ruoyi/login/
  │     ├── login_success.yaml     → 2 条有效等价类（正常登录 + token 验证）
  │     └── login_fail.yaml        → 13 条无效等价类（验证码层3 + 前置校验层4 + 认证层6）
  └── test_runner/test_login/
        ├── conftest.py            → base_url / redis_client / clean_runtime / clean_pwd_error_count fixtures
        ├── helpers.py             → prepare_captcha() + apply_setup() 复用工具
        ├── test_login_success.py  → success 用例参数化执行器
        └── test_login_fail.py     → fail 用例参数化执行器

修改：
  ├── core/apiutil.py              → inject_token() 实现
  │                                 → specification_yaml() 支持用例级覆盖 url/method/headers
  │                                 → replace_load 修复 list 类型不还原的 bug
  └── .gitignore                   → 新增 problem.md 和 data/runtime.yaml
```

**15 条用例覆盖三层防线**：
- 关卡① 验证码层：错误验证码 / 过期验证码 / code字段缺失
- 关卡② loginPreCheck：空用户名 / 空密码 / 密码<5位 / 密码>20位
- 关卡③ authenticate：密码错误 / 用户不存在 / 5次锁定 / 锁定后正确密码 / 停用用户 / 已删除用户

**关键设计**：
- `captcha_mode` 枚举（valid/wrong/fake_uuid/missing/skip）桥接 YAML 数据声明与命令式验证码获取
- `setup.redis` 机制预设 Redis 计数器（锁定案例）
- autouse fixture 自动清理 `pwd_err_cnt:LoginTestUser`
- `dict(case)` 浅拷贝防 pop 掏空原数据
- `token_absent` 断言验证失败登录不返回 token

**踩坑记录**：见 `problem.md`（5 个问题：YAML data vs json、replace_load list 类型、specification_yaml pop、captcha_mode 设计、conftest autouse 顺序）

**验收结果**：✅ 15 passed, 2 warnings（TripleDES 弃用，与代码无关）

**对应手动案例**：B2 笔记中的 LOGIN-01~12 全覆盖 + 代码分支分析补充 3 条

**工时**：~10h

---

### Phase 3 · 用户管理 CRUD ✅ 完成

**目标**：跑通 25 条用户管理用例（5 端点：add/edit/delete/resetPwd/changeStatus），含 HTTP 断言 + DB 验证

**实际实现**：
```
新增：
  ├── test_runner/test_user/
  │     ├── conftest.py            → db_connection（ConnectMysql + autocommit=True）
  │     │                            clean_at_users（session 级，物理删除 at_% 残留）
  │     │                            ensure_admin_login（session autouse，admin 自动登录）
  │     ├── helpers.py             → create_user() / get_user_id() 可复用工具
  │     └── test_user.py           → 5 参数化函数，25 条用例
  └── test_data/ruoyi/system/
        ├── user_add.yaml          → 11 条（正常+唯一性+Bean校验+前后端缺口）
        ├── user_edit.yaml         →  4 条（正常+用户名/手机/邮箱重复）
        ├── user_delete.yaml       →  3 条（正常+删自己+删不存在）
        ├── user_resetPwd.yaml     →  3 条（正常+重置admin+不存在用户）
        └── user_changeStatus.yaml →  4 条（停用+启用+停用admin + db_verify）

修改：
  ├── utils/connection.py          → ConnectMysql: autocommit=True, params 支持,
  │                                   utf8mb4 charset, 可选构造参数
  ├── utils/assertions.py          → 新增 run_db_verify() + coerce_db_param()
  │                                   (声明式 DB 验证：exists/count/eq/not_empty)
  └── conftest.py（根目录）         → 提升 base_url + redis_client 为 session fixture
```

**25 条用例覆盖 5 端点**：
- POST /system/user — 11 条（USER-01 正常 / 02a-c 唯一性 / 02d-f Bean 校验 / 03a-d 前后端缺口）
- PUT /system/user — 4 条（正常编辑 / 用户名/手机/邮箱重复）
- DELETE /system/user/{id} — 3 条（正常删除 / 删自己 / 删不存在）
- PUT /system/user/resetPwd — 3 条（正常重置 / 重置 admin / 不存在用户）
- PUT /system/user/changeStatus — 4 条（停用 / 启用 / 停用admin）

**DB 验证覆盖 5 个正常用例**：
- add: sys_user exists + role/post 关联 count=2
- edit: nick_name 更新 + role/post 关联 count=1
- delete: del_flag='2' + role/post 清空
- resetPwd: password 非空
- changeStatus: status='1'

**关键设计**：
- `run_db_verify` 声明式 DB 断言（table/where/expect/value），SQL 参数化防注入
- `coerce_db_param` 修复 `${}` 替换导致的 str/int 类型不匹配（`"191"` → `191`）
- `create_user()` 自动写入 `created_user_id` 到 runtime.yaml，供 `db_verify` 的 `where` 用
- 每用例独立前置用户（`setup.create_user`），session 结束时物理删除三表残留

**踩坑记录**：见 `problem.md`（§6 REPEATABLE READ 快照 + §7 `%` 格式符问题 + §3 空昵称 MyBatis 动态 SQL + §3 YAML `${` + `{}` 嵌套冲突）

**工时**：~10h（含 DB 验证专项排查 ~3h）

**分支**：`feature/phase3-db-verify-v2` → merged to master（commit `5f01840`）

---

### Phase 4 · 角色权限 + 二进制文件

**目标 A** ✅ 完成：角色 CRUD + DataScope 隔离（42 条用例）  
**目标 B** ✅ 完成：用户 Excel 导入导出（1 条业务流程用例）

#### Goal A 实际实现

```
新增：
  ├── test_data/ruoyi/system/
  │     ├── role_add.yaml          →  8条（正常+唯一性+Bean校验）
  │     ├── role_edit.yaml         →  8条（正常+唯一性+admin保护+Bean校验）
  │     ├── role_delete.yaml       →  4条（正常+已分配+admin保护+不存在）
  │     ├── role_changeStatus.yaml →  3条（正常+admin保护+不存在）
  │     ├── role_dataScope.yaml    →  3条（正常+admin保护+不存在）
  │     ├── role_authUser.yaml     →  5条（已分配/未分配/取消/批量授权/不存在）
  │     └── role_scope_query.yaml  →  6条（5种DataScope + 跨部门隔离）
  └── test_runner/test_role/
        ├── conftest.py            → db_connection / clean_at_test_data / ensure_admin_login 
        │                            / isolation_users fixture（5角色+7用户，session 级）
        ├── helpers.py             → login_as_user / get_user_scope / assert_rows_in_scope
        │                            / create_role / get_role_id / build_scope_user
        ├── test_role_crud.py      → 6 参数化函数，31 条用例
        └── test_role_scope.py     → YAML query(6) + Python write(3) + Python boundary(2)

修改：
  ├── core/apiutil.py              → specification_yaml() 新增 db + redis_client 参数
  │                                 → 新增 login_for_yaml() — 每次新登录，不缓存
  │                                 → specification_yaml 支持 auth_user 字段
  └── utils/assertions.py          → 新增 rows_in_scope 断言（复用 DataScopeAspect SQL）
                                    → run_validations 加 **kwargs 透传
```

**42 条用例覆盖**：
- 新增角色 8 条（ROLE-01/02 还原 + Bean 校验补充）
- 编辑角色 8 条（新增：唯一性（编辑时排除自身）/ admin 保护 / Bean 校验）
- 删除角色 4 条（ROLE-03 还原 + 正常删除 + admin 保护 + 不存在）
- 状态修改 3 条（新增：手动未测）
- DataScope 修改 3 条（新增：手动未测）
- authUser 5 条（新增：手动未测，检查了 cancelAuthUser 安全漏洞）
- 查询隔离 6 条（ROLE-05 还原 — 5 种 DataScope + 同角色跨部门）
- 写隔离 3 条（新增：编辑/删除/重置密码 → 403 拦截）
- DataScope 边界 2 条（新增：修改 CEO 角色 → 拦截 + cancelAuthUser 无 checkRoleDataScope）

**关键设计**：
- `rows_in_scope` 断言：CSS 中 DataScopeAspect 的 5 条 SQL 规则文本，YAML 中只需指定 `username` 即可验证
- `auth_user` 字段：YAML 中指定非 admin 身份，引擎自动登录注入 token
- `login_for_yaml()`：每次新登录不缓存，消除 stale token 问题
- `isolation_users` fixture：session 级预置 5 角色 + 7 用户，仅在 scope 测试中被引用
- 角色删除是逻辑删除（`del_flag='2'`），非物理删除
- `cancelAuthUser` 缺少 `checkRoleDataScope`——但 `@PreAuthorize` 在 Layer 1 先拦截了（安全漏洞需特定条件才暴露）

**踩坑记录**：见 `problem.md`（§8 角色逻辑删除 / §9 stale token / §10 cancelAuthUser / §11 YAML auth_user 集成）

**工时**：~12h

**分支**：`feature/phase4-role-permission` → merged to master


#### Goal B 实际实现

```
新增：
  ├── utils/excel_utils.py              → create_user_import_excel() — openpyxl 生成 .xlsx 到 data/excel/
  ├── test_data/ruoyi/system/
  │     └── user_import_export.yaml      → 1条业务流程用例（导入→导出）
  └── test_runner/test_user_excel/
        ├── conftest.py                  → db_connection / clean_at_users / ensure_admin_login
        └── test_user_import_export.py   → 导入→DB验证→导出→Excel解析→内容比对

修改：
  ├── core/apiutil.py                    → 新增 specification_export() 处理二进制响应（隔离于 specification_yaml）
  └── utils/assertions.py                → assert_excel_content 从空壳实现为完整断言
                                          （has_headers / row_contains / min_rows / max_rows / row_count）
```

**1 条业务流程用例覆盖端到端**：
- 生成 Excel（2 个用户：登录名称/用户名称/邮箱/手机号/性别/状态/部门）
- POST /system/user/importData（multipart file + updateSupport=false）
- 6 条 DB 验证（每用户 exists + sex/status 字段验证，含 readConverterExp 映射 男→"0"）
- POST /system/user/export（params userName 模糊过滤）
- 结构断言：11 列表头完整 + min_rows>=2
- 内容比对：Python 逐行比对 6 个共有字段 + deptId→deptName DB 转换

**关键设计**：
- `specification_export()` 与 `specification_yaml()` 隔离——前者处理二进制响应，后者处理 JSON 响应；导入用 yaml（JSON 响应），导出用 export（二进制响应）
- `excel_content` 断言：传什么验什么（has_headers/row_contains/min_rows/row_count），内容精确比对由 test 函数 Python 代码完成
- Excel 文件落盘 `data/excel/`：导入文件可打开检查，导出文件可人工核验
- 导入 Excel 使用人可读值（"男"/"正常"），RuoYi 的 `reverseByExp` 导入时自动转机器值（"0"），`convertByExp` 导出时转回人可读值——因此导入和导出的 sex/status 值可直接比对
- **不直接比两个 Excel**：导入导出列头不同（导入 7 列 vs 导出 11 列），比对策略是对 6 个共有字段逐行匹配

**踩坑记录**：见 `problem.md`（§12 `{}` falsy / §13 specification_export 被覆盖 / §14 openpyxl 依赖）

**工时**：~4h

**分支**：`feature/phase4-excel-import-export` → merged to master


#### 业务流程测试

```
新增：
  ├── test_data/ruoyi/system/
  │     └── business_flow.yaml             → 1条 6 步核心链路
  └── test_runner/test_business/
        ├── conftest.py                     → db_connection / clean_at_test_data（用户+角色双清理）
        │                                     ensure_admin_login
        └── test_business_flow.py           → 遍历 steps、replace_load 解析 ${}、extract_data 串联

零新增框架代码，完全复用现有 specification_yaml + replace_load + extract_data。
```

**6 步核心链路**：
1. POST /system/role → 创建角色
2. GET /system/role/list → 查询角色 ID（extract → runtime.yaml）
3. POST /system/user → 创建用户并分配角色（通过 `${get_runtime(flow_role_id)}` 引用步骤 2 的数据）
4. GET /system/user/list → 验证用户已创建（extract userId → runtime.yaml）
5. DELETE /system/user/{id} → 删除用户（URL 用 `${get_runtime(flow_user_id)}`）
6. DELETE /system/role/{id} → 删除角色

**关键设计**：
- 步骤间数据通过 `extract` → runtime.yaml → `${get_runtime(key)}` 串联，和原框架的 `extract.yaml` 模式等价
- URL 中的 `${}` 也需要 replace_load 解析（不仅是 json/params）
- conftest 清理覆盖用户+角色双表（因为流程同时涉及两者）

**工时**：~1h


**分支**：`feature/phase4-role-permission` → merged to master

---

### Phase 5 · 收尾 ✅ 完成

**目标**：README、环境搭建、仓库清理、打 tag v1.0

**实际实现**：
```
新增/修改：
  ├── README.md                     → 项目介绍 + 案例覆盖表（85 条）+ 运行说明
  ├── conf/config.example.ini       → 占位符模板（沿用已有，命名 config.example.ini）
  ├── conda env testframe           → Python 3.12 + 全量依赖（paramiko 2.12.0 < 3.0）
  ├── 仓库清理                       → 取消追踪 runtime.yaml（含 token）/ excel 产物 /
  │                                    debug_edit.py / .vscode，补充 .gitignore
  ├── project-startup.md 路径更新    → D:\TestingFrame → E:\LearningMall\AutoFrame\Manu_Frame
  ├── 清理自测 __main__ 代码         → 保留（不影响 pytest 收集，仅供开发自测）
  └── git tag v1.0
```

**用例统计修正（本次核对 YAML 实测）**：
- 用户管理实际 **24 条**（早期文档写 25）：`user_changeStatus` 为 3 条（停用/启用/停用admin）
- 全量 **83 条** = 登录 15 + 用户 24 + 角色 42 + Excel 1 + 业务流 1（连接冒烟已移除，纯基础设施非业务用例）

**关键环境变化**：
- 机器从 D:\TestingFrame 迁移到 E:\LearningMall\AutoFrame\Manu_Frame（路径已同步更新）
- pytest 从 8.4.2 → 9.1.1（85 条用例收集 + 运行兼容）
- `data/runtime.yaml` 曾误提交含真实 JWT token，已取消追踪（历史记录仍残留，登录 token 30 分钟过期，风险可控）

**工时**：~4h

---

### Phase 6 · CI/CD（Jenkins 集成）✅ 完成

**目标**：Jenkins 自动化构建 + Allure 报告归档 + Pipeline as Code

**实际实现**：

```
新增/修改：
  ├── Jenkinsfile                    → Declarative Pipeline（4 阶段：登录/用户/角色/文件与业务流）
  ├── utils/jenkins.py              → Jenkins API 封装（python-jenkins 库）
  │                                   get_build_status / get_report_stats / build_info_summary
  ├── setup-vm.sh                    → Ubuntu 22.04 VM 一键部署脚本（Java 21 + Jenkins war + uv + Allure）
  ├── conf/config.example.ini         → 新增 [JENKINS] 节（url/username/password/job_name）
  └── problem.md                      → 新增 §15-§26（12 个 Phase 6 踩坑记录）
```

**部署架构**：

```
Windows 开发机                      GitHub                         VMware Ubuntu 22.04 VM
┌─────────────────┐     push       ┌──────────┐     git pull       ┌──────────────────────────┐
│  ruoyi-testing-  │ ────────────→ │ 公开仓库  │ ←─────────────── │  Jenkins                  │
│  frame (VS Code) │               └──────────┘                   │  ├─ war 包（9090 端口）    │
│  ├─ 编写用例     │                                               │  ├─ uv 管理 Python 依赖    │
│  ├─ git commit   │                                               │  ├─ Allure CLI 2.32.0      │
│  └─ git push     │                                               │  ├─ SSH 隧道 → 云服务器     │
└─────────────────┘                                               │  │   (Redis + MySQL)        │
                                                                  │  └─ Pipeline Job           │
                                                                  │      ├─ Stage 1: 登录 15 条│
云服务器 47.109.149.194                                           │      ├─ Stage 2: 用户 24 条│
┌─────────────────────────┐                                       │      ├─ Stage 3: 角色 42 条│
│  RuoYi-Vue :8080        │ ←── SSH 隧道 ─────────────────────── │      └─ Stage 4: 文件+业务  │
│  MySQL Docker :3306     │                                         │            2 条             │
│  Redis Docker :6379     │                                         └──────────────────────────┘
└─────────────────────────┘
```

**Jenkinsfile 最终版本**（Declarative Pipeline + customWorkspace）：

```groovy
pipeline {
    agent {
        node {
            label 'built-in'
            customWorkspace '/var/lib/jenkins/ruoyi-testing-frame'
        }
    }
    environment {
        JAVA_TOOL_OPTIONS = '-Dfile.encoding=UTF-8'
    }
    stages {
        stage('1. 登录测试') {
            steps {
                sh '''
                    cd /var/lib/jenkins/ruoyi-testing-frame
                    uv run pytest test_runner/test_login/ \
                        --alluredir=report/temp --clean-alluredir -v
                '''
            }
        }
        stage('2. 用户管理') {
            steps {
                sh '''
                    cd /var/lib/jenkins/ruoyi-testing-frame
                    uv run pytest test_runner/test_user/ --alluredir=report/temp -v
                '''
            }
        }
        stage('3. 角色权限') {
            steps {
                sh '''
                    cd /var/lib/jenkins/ruoyi-testing-frame
                    uv run pytest test_runner/test_role/ --alluredir=report/temp -v
                '''
            }
        }
        stage('4. 文件与业务流') {
            steps {
                sh '''
                    cd /var/lib/jenkins/ruoyi-testing-frame
                    uv run pytest test_runner/test_user_excel/ \
                        test_runner/test_business/ --alluredir=report/temp -v
                '''
            }
        }
    }
    post {
        always {
            allure includeProperties: false, results: [[path: 'report/temp']]
            script {
                def buildResult = currentBuild.result ?: 'SUCCESS'
                echo "构建结果: ${buildResult}"
            }
        }
    }
}
```

**区别于源框架的改进**：
- 用 Jenkinsfile（Pipeline as Code）替代手工配置，CI 流程版本可控
- 用 `uv` 替代 conda 管理 VM 上的 Python 依赖（更轻量，无需 conda 镜像）
- `utils/jenkins.py` 扩展为：查询状态 + 测试报告统计 + 控制台日志 + Allure 链接提取
- 4 阶段分离构建，便于定位失败阶段
- `customWorkspace` 解决 Pipeline 的 Allure 插件路径问题

**Jenkins 环境信息**（最终）：
| 项目 | 值 |
|------|-----|
| 宿主机 | Windows 11 + VMware Workstation |
| VM 系统 | Ubuntu 22.04.5 LTS |
| VM IP | 192.168.119.144 |
| Jenkins 端口 | :9090 |
| Jenkins 版本 | 2.548（2026-08） |
| Java | OpenJDK 21.0.9 |
| Python | 3.12（uv 管理 .venv） |
| Allure CLI | 2.32.0 |
| 项目路径 | `/var/lib/jenkins/ruoyi-testing-frame/` |
| 登录凭据 | admin / admin |

**踩坑记录**：见 `problem.md` §15-§26（12 个问题：Jenkins apt 镜像失败 / Java 21 升级 / war 部署 / git 权限 / uv PATH / Allure 安装 / workspace 路径不匹配 等）

**工时**：~16h（含 CI/CD 概念学习 + VM 部署 + Jenkins 调试 + 83 条用例跑通 + 文档编写）

---

### 总预估

```
Phase 0  ████████████████████ ✅ 100%  项目初始化
Phase 1  ████████████████████ ✅ 100%  SSH + conftest            4-6h
Phase 2  ████████████████████ ✅ 100%  登录 15 案例              ~10h
Phase 3  ████████████████████ ✅ 100%  用户 CRUD 24 案例        ~10h
Phase 4  ████████████████████ ✅ A+B 完成                    ~16h
Phase 5  ████████████████████ ✅ 100%  收尾                     3-4h
Phase 6  ████████████████████ ✅ 100%  Jenkins CI/CD            ~16h
──────────────────────────────────────────────────────
合计                                           62-69h（约 16-18 天）
```

> **案例来源**：手动测试笔记 `C:\Users\PasserByNaOH\Desktop\实习学习笔记\笔记\Ruoyi\Vue\` 中的 ~35 条案例（B2 登录 / C1 用户管理 / D 角色管理 / C2 部门岗位 + 导出 / E 独立模块），框架目标是复现这些手动案例。

---

## 四、Git 工作流

### 主力：Feature Branch Workflow
```
master ───────────────────────────────────────────────→
  │
  ├── feature/phase3-db-verify-v2 ──→ merge（Phase 3 DB 验证）
  ├── feature/phase4-role-permission ──→ merge（Phase 4 角色权限）
  ├── feature/phase4-excel-import-export ──→ merge（Phase 4 Excel）
  ├── tag v1.0（Phase 5 收尾：README + Allure + 清理）
  └── Phase 6 Jenkins CI/CD（直接在 master 开发，commit 5498e65）
```

### 决策规则
- **简单改动**（修 import、改配置、加注释）→ 直接在 main
- **多文件/有风险**（加功能、改核心逻辑）→ 开 branch → merge
- **不确定** → 开 branch，安全第一

---

## 五、关键设计决策（已确认）

1. **数据与执行彻底分离** — YAML 在 `test_data/`，test_*.py 在 `test_runner/`
2. **真环境测试** — 直接打云服务器，不 mock
3. **登录优先** — 先跑通验证码→登录→token，再铺开面
4. **Jenkins 收尾** — 大部分用例完成后再接入 CI/CD
5. **GitHub 公开仓库** — 跨机器开发 + 面试展示
6. **测试范围** — 系统管理模块（约 10 个控制器），不含代码生成/定时任务
7. **VALIDATORS 字典模式** — 替代 if/elif 链，加新断言只需写函数 + 加一行映射
8. **Redis 类属性共享** — `DebugTalk._redis_client` 为 class attribute，所有 getattr 创建的新实例共享同一连接
9. **rfind('${') 嵌套解析** — 从最内层 `${` 开始替换，支持 `${outer(${inner})}` 嵌套
10. **config.ini 真实值不上传** — `.gitignore` 排除 `conf/config.ini`，手动创建 `config.ini.example` 模板
11. **Content-Type 分支处理** — `application/json` → 提取+断言，`octet-stream` → 占位（Phase 4 Excel）
12. **runtime.yaml 全量读写** — `write_runtime` = read→merge→write（非 append），`clear_runtime` 清空
13. **conftest.py 放根目录** — session 级 fixture 全项目共享，子目录测试自动继承；Phase 1 只放 SSH 隧道，redis_client/db_connection 等业务 fixture 在后续 Phase 按需追加（需求驱动，不预写）
14. **SSH 隧道单连接双转发** — 一条 SSH 连接用 `remote_bind_addresses` 同时转发 Redis 6379 + MySQL 3306，yield 字典 `{"tunnel", "redis_port", "mysql_port"}` 提高可读性
15. **paramiko 版本锁定 `<3.0`** — paramiko 3.x 移除 DSSKey，sshtunnel 不兼容；pymysql charset 用 `utf8mb4` 而非 `utf-8`
16. **ConnectMysql autocommit=True** — 避免 MySQL REPEATABLE READ 导致 DB 验证读到旧快照。每条 SQL 独立事务，API 提交后立即可见
17. **ConnectMysql.query/execute 参数化** — 无参数时不传第二参（避免 `%` 被 pymysql 当格式符），有参数时传 params 防 SQL 注入
18. **声明式 DB 验证** — `run_db_verify(rules)` 支持 exists/count/eq/not_empty 四种 expect，在 YAML 的 `db_verify` 块声明，不写 SQL
19. **created_user_id 写入 runtime** — `create_user()` 自动把查到的 userId 写入 runtime.yaml，供 `db_verify` 的 `where` 用 `${get_runtime(created_user_id)}` 引用
20. **每用例独立用户 + 物理删除** — `setup.create_user` 为每条用例创建独立前置用户；session 结束时 `clean_at_users` 物理删除三表残留（子表→主表），保证可重复运行
21. **若依逻辑删除 `del_flag='2'`** — 删除接口走 `userMapper.deleteUserById` → SET del_flag='2'，user_name 唯一性仍然生效，因此每个测试用户必须有唯一用户名
22. **MyBatis `<if>` 空字符串陷阱** — `updateUser` 的 `<if nickName != null and nickName != ''>` 会把空字符串跳过，导致 `nick_name` 列无默认值时 DB 报错（USER-03c）
23. **YAML `${` + `{}` 流映射冲突** — `where: {user_id: "${get_runtime(...)}"}` 中 `${` 被 YAML 误解析，值必须用双引号包裹
24. **`rows_in_scope` 断言** — 复用 DataScopeAspect 的 5 条 SQL 规则，在 YAML 中声明 `type: rows_in_scope` + `username: xxx` 即可验证用户查询隔离。计算逻辑移至 assertions.py，不依赖 test_role/helpers.py
25. **`auth_user` YAML 字段** — `specification_yaml` 新增参数 `db` + `redis_client`，如果 case 中有 `auth_user` 字段则自动调 `login_for_yaml` 登录并将 token 注入 header。`inject_token` 检测到已有 Authorization → 跳过
26. **`login_for_yaml()` — 不缓存策略** — 每次完整走 `/captchaImage` → Redis → `/login` 流程。隔离测试每次切换用户多 1 秒，但消除了 `login_as_user` 的 stale token 问题（旧 token 在角色重建后权限失效）
27. **isolation_users fixture** — session 级、非 autouse，仅被 `test_role_scope.py` 请求时触发。定义在 conftest.py 中，数据定义用常量 `_ISOLATION_ROLES` / `_ISOLATION_USERS`；创建后写关键 ID 到 runtime.yaml 供 YAML 引用
28. **角色管理端点安全审查** — `cancelAuthUser` / `cancelAuthUserAll` 缺少 `checkRoleDataScope`（对比 `selectAuthUserAll` 有）。当前被 `@PreAuthorize("system:role:edit")` 在 Layer 1 保护，漏洞仅在"用户有角色编辑菜单但 DataScope 受限"时暴露
29. **`specification_export` 二进制导出引擎** — 新增独立方法处理 Excel 等二进制响应，与 `specification_yaml`（JSON 响应）隔离。不处理 json/data/extract/files，只处理 params + 二进制断言
30. **excel_content 传什么验什么** — 支持 has_headers / row_contains / min_rows / max_rows / row_count，可组合使用。内容精确比对由 test 函数 Python 代码完成，避免 YAML 硬编码导出期望值
31. **导入导出不直接比对 Excel** — 导入 7 列 vs 导出 11 列，列头不同。比对策略：对 6 个共有字段逐行匹配，deptId 查 DB 转 deptName 后比对
32. **Excel 文件落盘 data/excel/** — 导入文件和导出结果都保存到磁盘，方便人工打开检查调试
33. **业务流程 steps 串行模式** — YAML 中 `steps` 列表定义多步操作，test 函数遍历执行。步骤间通过 `extract` → runtime.yaml → `${get_runtime(key)}` 串联数据，和原框架 `extract.yaml` 模式等价。不另写引擎，完全复用 `specification_yaml` + `replace_load` + `extract_data`
34. **Jenkins Declarative Pipeline + customWorkspace** — 用 `customWorkspace` 让 Jenkins workspace 指向项目实际目录（`/var/lib/jenkins/ruoyi-testing-frame/`），解决 `allure` 步骤路径相对于默认 workspace 找不到报告的问题。Pipeline 和 Freestyle 两种模式均适用
35. **uv 替代 conda 于 VM** — Ubuntu VM 上使用 uv 管理 Python 依赖，`/usr/local/bin/uv` 软链接解决 jenkins 用户 PATH 不包含 `~/.local/bin` 的问题
36. **Jenkins war 包部署** — 因清华镜像的 Jenkins apt 源不兼容，改用 `jenkins.war` 直接下载 + systemd 服务启动，`JAVA_OPTS` 环境变量无效，`-Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true` 需直接写在 `ExecStart` 中
37. **jenkins 用户权限模型** — Jenkins 服务以 `jenkins` 用户运行，项目目录需 `chown -R jenkins:jenkins`；jenkins 用户需 home 目录（`/home/jenkins`）以执行 `git config --global`；Allure 报告文件属主冲突（jenkins 写 → aaa 无写权限）需 `chown -R aaa:aaa report/`
38. **SCM 本地路径安全限制** — Jenkins Git Plugin 默认禁止本地路径 checkout（安全策略）。VM 上的工作流改为：Windows git push → GitHub → VM git pull → Jenkins "Build Now"（不通过 Git Plugin 拉取，直接执行 shell）

---

## 六、工作方式约定

### 6.1 代码编写策略

**原框架当"设计文档"读，不当"代码库"搬。** 每个模块三步走：

1. **理解设计意图** — 原框架这个模块做了什么？架构思想是什么？
2. **改进坏味道** — 数字编码改为可读参数名、删除冗余逻辑、精简无用分支
3. **只写若依需要的** — 不要 ClickHouse/MongoDB/CSV/XML，只要 MySQL + Redis + HTTP

### 6.2 操作约定

0. **先读全项目再开始** — 每 Phase 开启新对话时，先阅读整个项目代码（所有 .py、config.ini 等），了解当前状态后再动手
1. **先列 todo 再动手** — 每 Phase 开始时先列出 todo-list 讨论确认，再按顺序逐项推进
2. **一次只做一个内容** — 完成当前项并确认后，再讨论下一项；不等当前项完成不提前讨论后面
3. **代码默认手敲** — 给出代码让用户自己打，不直接写文件；除非用户明确说"直接帮我改"或"自动生成"才执行写操作
4. **先讨论再敲代码** — 每个文件先确认设计方案（结构、命名、边界），同意后再给代码
5. **阶段性提交** — 每 Phase 结束 git commit + push，确保远端有完整备份

### 6.3 空 __init__.py

`conf/`、`core/`、`utils/`、`test_runner/` 是 Python 包目录，**必须**保留 `__init__.py`（空文件），否则 `from conf.setting import ...` 报 `ModuleNotFoundError`。不放 import，但文件本身不能删。

### 6.4 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: No module named 'conf'` | 删了 `conf/__init__.py` | 在 `conf/`、`utils/`、`core/` 下建空 `__init__.py` |
| `python -u utils/readyaml.py` 找不到模块 | `-u` 是 unbuffered，不是模块模式 | 用 `python -m utils.readyaml`（从项目根目录执行） |
| `${random_str(6)}` 报 TypeError | `${}` 解析器传入的是字符串 `"6"` | 函数内部 `int(length)` 转换 |
| `${outer(${inner})}` 解析错误 | `index('${')` 匹配到最外层 `${` | 改用 `rfind('${')` 从内向外解析 |
| 若依服务器 502 | Java 进程被 OOM Killer 杀掉（1.6G 服务器，Xmx 1024m） | `java -Xmx256m -Xms128m -jar ruoyi-admin.jar` 重启 |
| `AttributeError: module 'paramiko' has no attribute 'DSSKey'` | paramiko 3.x 移除 DSSKey，sshtunnel 不兼容 | `pip install "paramiko<3.0"` |
| `'NoneType' object has no attribute 'encoding'` | pymysql `charset="utf-8"` 格式不对 | 改用 `charset="utf8mb4"`（无横线） |
| `TypeError: not enough arguments for format string` | `cursor.execute(sql, ())` 空tuple导致SQL中`%`被当格式符 | 无参数时不传第二参：`if params: cursor.execute(sql, params) else: cursor.execute(sql)` |
| DB 验证查询不到更新后的数据 | `autocommit=False` + REPEATABLE READ 快照 | `pymysql.connect(..., autocommit=True)` |
| YAML `where: {user_id: ${...}}` 解析报错 | `${` 在 YAML 流映射 `{}` 中触发解析歧义 | 值用双引号包裹：`"${get_runtime(created_user_id)}"` |
| Jenkins `allure` 步骤不显示报告 | workspace 路径 ≠ 项目路径，`allure` results 相对于 workspace | `customWorkspace` 指向项目目录 |
| Jenkins `uv: not found` | jenkins 用户 PATH 不含 `~/.local/bin` | `sudo ln -sf /home/aaa/.local/bin/uv /usr/local/bin/uv` |
| Jenkins 构建后 `report/` 文件属主冲突 | jenkins 用户写的报告文件 aaa 无法覆盖 | `sudo chown -R aaa:aaa report/` |
| Jenkins war 服务 `JAVA_OPTS` 不生效 | systemd 的 `Environment=` 对 Jenkins war 无效 | JVM 参数直接写在 `ExecStart` 中 |
| Jenkins `git config --global` 失败 | jenkins 用户无 home 目录 | `sudo mkdir -p /home/jenkins && sudo chown jenkins:jenkins /home/jenkins` |

### 6.5 Phase 切换约定

1. **每 Phase 开启新对话** — 上下文干净，避免 token 膨胀。新对话开头粘贴启动语即可。
2. **每 Phase 结束后同步计划** — 关闭对话前更新 `project-startup.md`：
   - 当前 Phase 标记 `✅ 完成`
   - 更新 `last_updated` 日期
   - 在"对话记录"中记录本 Phase 的关键内容
   - 将本次讨论中确认的设计决策补入第五节
3. **git commit + push** — Phase 结束必须推送，确保远端有完整备份。记得先设 `git config --global https.proxy http://127.0.0.1:7897`。

---

## 七、注意事项

- SSH/数据库/Redis 密码已填入真实 config.ini，在 `.gitignore` 中排除
- 后续需创建 `conf/config.ini.example` 模板（占位符版本）供 GitHub 参考
- 若依响应模型：HTTP 永远 200，业务状态码在 `body.code` 字段
- 验证码是 `math` 类型，答案存在 Redis：`captcha_codes:{uuid}`
- 账户锁定 Redis key：`pwd_err_cnt:{username}`

---

## 八、对话记录

### 2026-07-29
- 阅读 ruoyi-migration-summary.md，完成框架分析
- 讨论并确认了整体规划、目录结构、Git 策略
- 确认：数据/执行分离、Phase 划分、branch 工作流

### 2026-07-30
- 本地 git init + GitHub 公开仓库创建（gh CLI + 代理配置）
- 搭建完整目录结构
- 配置 .gitignore（排除 project-startup.md、ruoyi-migration-summary.md）
- **改变策略：** 原框架不直接搬代码，改为参考思路 + 改进写法 + 只保留若依需要的部分
- 原因：原框架存在数字编码随意性（如 get_extract_data 用 0/-1/-2 代表不同行为）、大量不相关组件（ClickHouse/MongoDB/CSV）
- 已删除所有 copy 过来的 .py 文件，准备从零逐个重建
- 当前状态：目录结构就绪，核心模块待逐个重建

### 2026-07-31
- **逐个重建全部完成：** conf/setting.py → utils/recordlog.py → readyaml.py → sendrequest.py → connection.py → debugtalk.py → assertions.py → core/apiutil.py
- 每个模块含 `__main__` 自测代码，自测入口均从 config.ini 读取 IP（不暴露硬编码）
- `FILE_PATH['EXTRACT']` 更名为 `FILE_PATH['RUNTIME']`，消除与 Excel 提取的歧义
- `sendrequest.py` 修复缩进 bug（return 在 for 循环内导致提前退出）
- `replace_load` 修复嵌套 `${}` 解析：`index('${')` → `rfind('${')`（从内向外替换）
- `random_str` 兼容 `${}` 传入字符串参数：`int(length)` 转换
- 若依服务器因 OOM 重启（Java Xmx 降到 256m），MySQL/Redis/Nginx 在 Docker 中正常运行
- apiutil.py 从 utils/ 挪到 core/（用户手误后手动 mv）
- 恢复所有 `__init__.py` 解决 ModuleNotFoundError（记录在 6.4 节）
- config.ini 真实值已写入（含密码），确认在 .gitignore 中排除
- 日志文件命名从 test.log 改为日期格式（test.YYYYMMDD.log）
- 用户确认：SSH 隧道放在 conftest.py（非 connection.py），由 fixture 注入到 DebugTalk
- 用户确认：若依 Cookie "rememberMe" 与本框架无关（若依用 Bearer token）
- 暂未 git commit + push（待用户设 git HTTP 代理后执行）

### 2026-07-31（下午）— Phase 计划重调

- **阅读手动测试笔记**：`C:\Users\PasserByNaOH\Desktop\实习学习笔记\笔记\Ruoyi\Vue\` 中的 B2/C1/C2/D/E
- **评估结果**：手动案例 ~35 条，覆盖登录（12条）/用户CRUD（12条）/角色权限（6条）/部门（4条）/导出（2条）/独立模块（4条）
- **方法论亮点**：等价类+边界值贯穿始终、发现前后端校验不一致（USER-03系列）、DataScope 数据权限隔离（ROLE-05/ROLE-04）、Redis 副作用间接验证
- **不足**：Excel 导入未测、批量删除未测、角色-用户批量授权未走通
- **结论**：覆盖范围合格，足够找实习。~35 条案例覆盖了登录全异常链 + 用户完整 CRUD + RBAC 双层权限模型
- **新 Phase 计划**：Phase 1 SSH隧道 → Phase 2 登录12案例 → Phase 3 用户CRUD → Phase 4 角色+二进制 → Phase 5 收尾，总 33-42h
- **新增约定（6.5）**：每 Phase 开启新对话、每 Phase 结束同步 project-startup.md、git commit + push
- **git push 已执行**（f3061f6），远端仓库已同步

### 2026-08-01 — Phase 1 完成

- **conftest.py 设计调整**：从 test_runner/ 移到根目录，fixture 全项目共享；只放 ssh_tunnel（单隧道双转发），redis_client 等业务 fixture 留到 Phase 2 按需追加
- **测试目录**：`test_runner/test_connect_api/`（非原计划 test_smoke.py），集中验证 Redis/MySQL 连通性
- **验收结果**：SSH 隧道打通，Redis ping 通，MySQL SELECT 1 返回 1，pytest 收集 2 条用例
- **踩坑修复**：paramiko 3.x 不兼容 sshtunnel → 锁定 `paramiko<3.0`；pymysql `charset="utf-8"` → `utf8mb4`
- **config.ini SSH host 修复**：移除了误带的 `:8080` 后缀
- **git push 已执行**（9283180），远端仓库已同步
- **设计决策确认**：连接测试用 try/except/finally（非 assert），失败先记日志再抛；yield 字典替代索引提高可读性；Phase 1 不预写后续不用的 fixture

### 2026-08-02 — Phase 2 完成

- **用例扩展**：通过分析若依 `SysLoginService`、`UserDetailsServiceImpl`、`SysPasswordService` 源码分支，从原计划 12 条扩展到 15 条（补充：用户不存在、code字段缺失、空密码）
- **captcha_mode 设计**：YAML 用 `captcha_mode` 枚举（valid/wrong/fake_uuid/missing/skip）告诉 test 函数验证码策略，桥接声明式 YAML 与命令式 Redis 交互
- **YAML data vs json 踩坑**：`data=` 发送 form-encoded，若依 `@RequestBody` 只认 JSON → 全部改用 `json:`
- **replace_load bug 修复**：出口判断只还原 dict 不还原 list → validations list 被当字符串遍历 → `TypeError: string indices must be integers` → 改为 `isinstance(data, (dict, list))`
- **specification_yaml pop 防护**：引擎内部大量 `.pop()` 掏空原 dict → 传入前 `dict(case)` 浅拷贝
- **test_login 目录结构**：conftest.py（fixtures）+ helpers.py（prepare_captcha/apply_setup）+ 两个 test 文件，保持简洁
- **conftest fixtures**：`base_url` + `redis_client`（session 级注入 DebugTalk）+ `clean_runtime_on_start` + `clean_pwd_error_count`（autouse function 级）
- **inject_token 实现**：runtime.yaml 读取 token → 自动注入 Bearer Authorization header，跳过已显式指定的用例
- **15 条用例全部通过**，2 个 paramiko/CryptographyDeprecationWarning 与代码无关
- **git commit + push 已执行**（2de9f1c）
- **用户偏好记录**：conda 环境 `testframe`，测试手动执行不自动跑

### 2026-08-03~04 — Phase 3 完成

- **用例扩展**：通过分析手动测试笔记 + 若依源码，从原计划 ~12 条扩展到 25 条（覆盖 5 端点 + Bean 校验 + 前后端缺口 + 唯一性冲突）
- **Layer 分离**：根 conftest = 基础设施（base_url/redis_client/ssh_tunnel），test_user/conftest = 用户模块专属（db_connection/clean_at_users/ensure_admin_login）
- **每用例独立前置用户**：`setup.create_user` + 物理删除三表残留，保证可重复运行
- **空昵称踩坑**：MyBatis `<if nickName != null and nickName != ''>` 跳过空字符串 → `nick_name` 无默认值 → DB error（修改断言为 code=500）
- **YAML `${` 流映射冲突**：`where: {user_id: "${get_runtime(...)}"}` 需要双引号包裹，否则 YAML 解析器报错
- **DB 验证方案设计**：声明式 `run_db_verify`（exists/count/eq/not_empty），SQL 参数化在 connection 层封装，YAML 用 `db_verify` 块声明
- **`coerce_db_param` 类型还原**：`replace_load` 的 `${}` 替换后 int 变 str（`191` → `"191"`），需在 DB 验证前还原
- **DB 验证专项排查（~3h）**：debug_edit.py 验证 API 正常 → 定位 REPEATABLE READ 快照 → autocommit=True 修复 → `%` 格式符问题修复
- **MySQL 事务隔离学习**：READ UNCOMMITTED / READ COMMITTED / REPEATABLE READ / SERIALIZABLE 四级对比，抢票场景的行锁（FOR UPDATE）
- **所有 25 条用例全部通过**（HTTP 断言 + DB 验证）
- **git commit + push 已执行**（5f01840，分支 feature/phase3-db-verify-v2 → master）
- **project-startup.md 已同步**（更新 Phase 3 实现细节、设计决策、对话记录）
- **文档可见化**：problem.md / project-startup.md / ruoyi-migration-summary.md 从 .gitignore 移除，已同步 GitHub

### 2026-08-04 — Phase 4 Goal A 完成

- **完整 gap 分析**：对比手动测试笔记（仅 ROLE-01~05，5条）与若依源码，发现漏测 edit/delete/changeStatus/dataScope/authUser 端点，DataScope 仅测了模式 3 和 5
- **YAML 渐进式构建**：role_add → edit → delete → changeStatus → dataScope → authUser → scope_query，每写完一组立刻跑 pytest
- **角色删除踩坑**：断言 `count=0` 失败 → 发现若依角色是逻辑删除（`del_flag='2'`）非物理删除（和用户一样）
- **DataScope 隔离方案**：5 种模式 + 跨部门 + 写操作 + 安全边界共 11 条；isolation_users fixture 预置 5 角色 + 7 用户
- **Token 缓存问题**：`login_as_user` 缓存旧 token → 角色重建后权限失效 → 全部 403。放弃缓存 → 新增 `login_for_yaml()` 每次新登录
- **框架扩展**：`auth_user` YAML 字段 + `rows_in_scope` 断言 → 6 条查询隔离从 Python 转 YAML
- **安全审查**：确认 `cancelAuthUser`/`cancelAuthUserAll` 缺少 `checkRoleDataScope`，但 `@PreAuthorize` 在 Layer 1 拦截；漏洞需特定条件才暴露
- **42 条全部通过**，数据 `at_` 前缀自动清理
- **git push 已执行**（ebc89a6，branch feature/phase4-role-permission → master）
- **project-startup.md + problem.md 已同步**

### 2026-08-05 — Phase 4 Goal B 完成

- **端到端业务流设计**：导入→DB验证→导出→内容比对，一条用例覆盖完整流程
- **specification_export 隔离**：新增独立方法处理二进制响应，不干扰 specification_yaml 的 JSON 流程
- **assert_excel_content 实现**：传什么验什么（has_headers/row_contains/min_rows/row_count），内容精确比对由 test 函数 Python 代码完成
- **字段映射分析**：导入 7 列（人可读值，reverseByExp 转机器值）vs 导出 11 列（convertByExp 转回人可读值）→ 6 个共有字段可直接比对
- **踩坑**：`{}` falsy 回退、specification_export 被覆盖、openpyxl 需单独安装到 testframe 环境
- **1 条用例全部通过**
- **导入文件 + 导出文件落盘 data/excel/ 可人工检查**
- **git 待 commit + push**（分支 feature/phase4-excel-import-export）
- **project-startup.md + problem.md 已同步**

### 2026-08-05（下午）— 业务流测试 + auth_user 重构

- **auth_user 解耦**：将登录逻辑从 `specification_yaml` 移出到 test 函数——从 engine 里删 7 行 + 从 YAML 删 6 个 `auth_user` 字段 + test 函数加 4 行 `login_for_yaml`
- **业务流测试**：参考原框架 BusinessScenario 模式，用 YAML `steps` 列表 + Python 遍历实现 6 步核心链路（创建角色→创建用户→删用户→删角色），零新增框架代码
- **44 条全部通过**
- **git commit + push 待执行**
- **project-startup.md + problem.md 已同步**

### 2026-08-06 — 换机迁移 + Phase 5 完成 + Phase 6 规划

- **换机器**：项目从 D:\TestingFrame 迁移到 E:\LearningMall\AutoFrame\Manu_Frame（git clone），若依源码/原框架在 `E:\LearningMall\AutoFrame\` 下
- **环境搭建**：新建 conda env `testframe`（Python 3.12.9），安装全量依赖 + allure-pytest 2.16.0 + Allure CLI 2.43.0（npm）
- **用例统计修正**：逐 YAML 核对后确认全量 **83 条**（移除连接冒烟后）= 登录 15 + 用户 24 + 角色 42 + Excel 1 + 业务流 1
- **config.ini 引号陷阱**：`config.example.ini` 模板中 `host = http://"ip":8080` 导致用户替换后 ConfigParser 值含字面引号，已修复模板为 `<服务器IP>` 占位符
- **README.md**：项目介绍 + 83 条案例覆盖表 + 运行说明 + 设计思路
- **Allure 报告集成**（Tier 1/2/3）：epic/feature/story 导航树（7 个 conftest 钩子）+ 请求/响应附着（apiutil.py）+ 断言附着（assertions.py）+ `allure.dynamic.title()` 用 YAML case_name
- **run.py**：一键全量回归 + 自动探测 `E:\Env\jdk*`（高版本优先）+ `allure generate` + `allure open`
- **仓库清理**：取消追踪 `data/runtime.yaml`（发现含真实 JWT token）/ excel 产物 / debug_edit.py / .vscode / test_connect_api（纯基础设施）；补充 .gitignore
- **MIT 许可证**：添加 LICENSE 文件
- **git commit + push + tag v1.0** 已执行（3c9e8cd → ad22f46）
- **Phase 6 规划**：确定使用 Jenkins（参考源框架），写入 Jenkinsfile + `utils/jenkins.py` + Docker 部署方案到 project-startup.md，工时预估 8-12h

### 2026-08-06~07 — Phase 6 完成

- **CI/CD 概念学习**：CI（持续集成）— 每次代码变更自动测试验证旧功能不被破坏；CD（持续交付/部署）— CI 通过后自动打包部署。从开发和测试两个视角理解了完整流程
- **Jenkins 部署（VMware Ubuntu 22.04）**：非 Docker 部署，直接 `jenkins.war` + systemd 启动在 9090 端口
- **清华镜像 Jenkins apt 不可用**：GPG key 404，改用 war 包下载 + 手动创建 systemd 服务
- **Java 17→21 升级**：最新 Jenkins 2.548 要求 Java 21，`sudo apt install openjdk-21-jdk`
- **uv 替代 conda**：VM 上使用 uv 管理 Python 依赖（`uv pip install -r requirements.txt`），解决 jenkins 用户 PATH 不含 `~/.local/bin` 问题
- **jenkins 用户权限体系**：Jenkins 服务以 `jenkins` 用户运行，项目目录需 `chown`；home 目录需手动创建；Allure 报告写权限冲突
- **git 本地 checkout 安全限制**：Jenkins Git Plugin 禁止本地路径 → 添加 `-Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true` → 参数进 `ExecStart` 非 `JAVA_OPTS`（后者不生效）
- **工作流**：Windows dev → git push GitHub → VM git pull → Jenkins "Build Now"
- **Jenkinsfile**：Declarative Pipeline，4 阶段分离（登录 15 → 用户 24 → 角色 42 → 文件+业务 2），`customWorkspace` 解决 Allure 路径问题
- **Allure 插件路径之谜（核心踩坑）**：Pipeline `allure` 步骤不显示报告 → 排查发现 workspace ≠ 项目目录 → `customWorkspace '/var/lib/jenkins/ruoyi-testing-frame'` 修复；Freestyle 用 "Use custom workspace" 同理
- **Problem #25 更新**：从"放弃插件"纠正为 workspace 路径不匹配 + customWorkspace 解法
- **`utils/jenkins.py`**：`JenkinsClient` 类，延迟初始化避免 import 报错，提供 `get_build_status` / `get_report_stats` / `extract_allure_url` / `build_info_summary`
- **83 条用例全量 4 阶段全部通过**，Allure 报告在 Jenkins 侧边栏正常显示
- **project-startup.md + problem.md 已同步**（Phase 6 完成状态，12 个踩坑记录）
- **git commit + push 已执行**（5498e65）

### 2026-08-08 — DingTalk 通知 + 目录解耦 + 项目完结

- **DingTalk 通知（Jenkinsfile post 块）**：`success` / `failure` 分别通过 `curl` POST 到钉钉机器人 Webhook 发 Markdown 消息。Webhook URL 存 Jenkins 凭据（`dingtalk-webhook`），`environment` 块中 `credentials()` 注入为环境变量
- **DingTalk 安全设置**：机器人选"自定义关键词"模式，关键词 `构建`。所有消息标题/正文必须包含该关键词，否则 `errcode: 310000`
- **群聊 @机器人 vs Webhook**：钉钉群内 @机器人发消息是 chatbot 模式，需要 outging 回调服务；自定义 Webhook 是**主动推送**模式，不需要回调，只负责 POST 发消息
- **`utils/jenkins.py`**：新增 `DingTalkNotifier` 类（`send` / `send_build_success` / `send_build_failure`），供 Python 脚本手动发钉钉通知。命令行入口 `python -m utils.jenkins dingtalk-test` 测试连通性
- **Jenkinsfile 与 utils/jenkins.py 的关系**：两者独立运行 —— Jenkinsfile 用 Groovy `curl` 在 Pipeline 内发通知，`utils/jenkins.py` 用 Python `urllib` 在本地开发机上手动发。互不调用，是同一功能的两套实现
- **`skipDefaultCheckout()`**：解决 Jenkins SCM checkout 后销毁 `ws` context 导致 `allure` 和 `writeFile` 在 `post` 中报 `MissingContextVariableException`
- **VM 文件权限（共享组 + SGID）**：`groupadd dev` + `usermod -a -G dev aaa; usermod -a -G dev jenkins` + `chown -R jenkins:dev` + `chmod -R g+rwxs` — root/aaa/jenkins 三个用户均可读写项目文件，新文件自动继承 `dev` 组
- **VM 本地仓库（无 GitHub 连接）**：删除 `.git` → `git init` → `git add .` → `git commit`，不关联远程仓库。工作流：Windows push GitHub（备份）+ Xftp 手动传文件到 VM + VM 本地 commit
- **云服务器恢复**：Jenkins 测试期间 CPU 满载 → `reboot` → Docker MySQL/Redis `docker start` → RuoYi `nohup java -Xmx256m -Xms128m -jar ruoyi-admin.jar`
- **Jenkinsfile 目录自发现**：硬编码 4 stage → `ls -d test_runner/test_0*/ | sort` 扫描目录 + `for` 循环动态生成 stage。加模块只需创建 `test_0N_xxx/` 目录 push，无需改 Jenkinsfile
- **目录编号化**：`test_login` → `test_01_login`，`test_user` → `test_02_user`，`test_role` → `test_03_role`，`test_user_excel` → `test_04_user_excel`，`test_business` → `test_05_business`。格式 `test_NN_xxx`：Python import 合法（字母开头），`ls | sort` 自然排序
- **Conftest Allure 映射 + Python import 同步更新**：根 `conftest.py` 路径检测更新为 `test_01_login` 等；5 处 `from test_runner.test_*` import 同步更新
- **Problem #25-#27 已同步**，project-startup.md 更新至 2026-08-08
- **git commit + push 已执行**（b916636）
