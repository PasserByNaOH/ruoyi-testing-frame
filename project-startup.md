---
project: ruoyi-testing-frame
description: 项目启动文档——每开新对话时首先阅读此文件
last_updated: 2026-08-02
current_phase: Phase 2 完成 → Phase 3 准备开始
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
| 当前工作目录 | `d:\TestingFrame\ruoyi-testing-frame` |
| 原框架源码 | `D:\TestingFrame\Test-Automation-Framework` |
| 若依后端源码 | `D:\TestingFrame\RuoYi-Vue2` |
| 若依前端源码 | `D:\TestingFrame\RuoYi-Vue2\ruoyi-ui` |
| manuTest 学习笔记 | `D:\TestingFrame\manuTest` |
| SSH 隧道参考 | `D:\TestingFrame\manuTest\5-RedisLoginTest\conftest.py` |
| 框架学习笔记 | `docs/framework-learning-entity-and-repository.md` |
| 手动测试笔记（案例来源） | `C:\Users\PasserByNaOH\Desktop\实习学习笔记\笔记\Ruoyi\Vue\` |
| 改造摘要 | `ruoyi-migration-summary.md` |
| 内存文件 | `C:\Users\PasserByNaOH\.claude\projects\d--TestingFrame-ruoyi-testing-frame\memory\` |

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
| 若依后端源码 | `D:\TestingFrame\RuoYi-Vue2` |
| 若依前端源码 | `D:\TestingFrame\RuoYi-Vue2\ruoyi-ui` |
| 原测试框架源码 | `D:\TestingFrame\Test-Automation-Framework` |
| manuTest（手动测试项目） | `D:\TestingFrame\manuTest` |
| manuTest SSH 隧道参考 | `D:\TestingFrame\manuTest\5-RedisLoginTest\conftest.py` |
| 手动测试笔记（案例来源） | `C:\Users\PasserByNaOH\Desktop\实习学习笔记\笔记\Ruoyi\Vue\` |

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

### Phase 3 · 用户管理 CRUD

**目标**：跑通 USER-01~06 + 前后端校验不一致案例

```
新增/修改：
  ├── test_data/ruoyi/system/
  │     ├── user_add.yaml          → USER-01/02a/02b/02c
  │     ├── user_edit.yaml         → USER-04/04a/04b/04c
  │     ├── user_delete.yaml       → USER-05
  │     ├── user_resetPwd.yaml     → USER-06
  │     └── user_validate_gap.yaml → USER-03a/03b/03c/03d 前后端校验差异
  ├── test_runner/test_user.py     → 参数化执行器
  └── utils/assertions.py          → 补充 body_not_contains 等断言
```

**对应手动案例**：C1 笔记中的 USER-01~06 全覆盖（含无效等价类）

**工时**：8-10h

---

### Phase 4 · 角色权限 + 二进制文件

**目标 A**：跑通 ROLE-01~05（角色 CRUD + DataScope 隔离）  
**目标 B**：跑通 EXPORT-01/02（二进制下载）+ Excel 导入

```
新增/修改：
  ├── test_data/ruoyi/system/
  │     ├── role_*.yaml            → ROLE-01~05
  │     ├── user_export.yaml       → EXPORT-01/02 导出
  │     └── user_import.yaml       → Excel 导入（新增，手动未测）
  ├── test_runner/test_role.py
  ├── core/apiutil.py              → handle_file_upload() 实现
  ├── utils/excelutil.py           → openpyxl 读取/断言（新建）
  └── utils/assertions.py          → assert_excel_content() 实现
```

**对应手动案例**：D 笔记 ROLE-01~05 + C2 笔记 EXPORT-01/02 + 导入（补充）

**工时**：10-12h

---

### Phase 5 · 收尾

**目标**：README、config.ini.example、打 tag v1.0

```
  ├── README.md                    → 项目介绍 + 案例覆盖表 + 运行说明
  ├── conf/config.ini.example      → 占位符模板
  ├── 清理自测 __main__ 代码        → 可选：用 pytest 替代
  └── git tag v1.0
```

**工时**：3-4h

---

### 总预估

```
Phase 0  ████████████████████ ✅ 100%  完成
Phase 1  ████████████████████ ✅ 100%   SSH + conftest          4-6h
Phase 2  ████████████████████ ✅ 100%  登录 15 案例              ~10h
Phase 3  ░░░░░░░░░░░░░░░░░░░░   0%    用户 CRUD                8-10h
Phase 4  ░░░░░░░░░░░░░░░░░░░░   0%    角色权限 + 二进制        10-12h
Phase 5  ░░░░░░░░░░░░░░░░░░░░   0%    收尾                     3-4h
──────────────────────────────────────────────────────
合计                                           33-42h（约 9-11 天）
```

> **案例来源**：手动测试笔记 `C:\Users\PasserByNaOH\Desktop\实习学习笔记\笔记\Ruoyi\Vue\` 中的 ~35 条案例（B2 登录 / C1 用户管理 / D 角色管理 / C2 部门岗位 + 导出 / E 独立模块），框架目标是复现这些手动案例。

---

## 四、Git 工作流

### 主力：Feature Branch Workflow
```
main ────────────────────────────────────────────────→
  │
  ├── feature/phase0-init ────→ merge (PR)
  ├── feature/phase1-infra ────→ merge (PR)
  ├── feature/phase2-adapt ────→ merge (PR)
  ├── feature/phase3-login ────→ merge (PR)
  ├── feature/phase4-user ─────→ merge (PR)
  ├── feature/phase4-role ─────→ merge (PR)
  ├── feature/phase5-jenkins ──→ merge (PR)
  └── v1.0 tag
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
