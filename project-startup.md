---
project: ruoyi-testing-frame
description: 项目启动文档——每开新对话时首先阅读此文件
last_updated: 2026-07-29
current_phase: Phase 0（即将开始）
---

# 若依测试框架改造 · 项目启动文档

> **给新对话的第一句话**（直接粘贴）：
> "阅读 project-startup.md 和 ruoyi-migration-summary.md，继续推进若依测试框架改造项目。"

---

## 一、项目背景

将 `Test-Automation-Framework`（一个 Python + pytest + YAML 数据驱动的 API 测试框架）改造成适配**若依管理系统**的自动化测试框架。

### 关键路径

| 内容 | 绝对路径 |
|------|----------|
| 当前工作目录 | `d:\TestingFrame\AA-ruoyi-testingFrame` |
| 原框架源码 | `D:\TestingFrame\Test-Automation-Framework` |
| 若依后端源码 | `D:\TestingFrame\RuoYi-Vue2` |
| 若依前端源码 | `D:\TestingFrame\RuoYi-Vue2\ruoyi-ui` |
| manuTest 学习笔记 | `D:\TestingFrame\manuTest` |
| SSH 隧道参考 | `D:\TestingFrame\manuTest\5-RedisLoginTest\conftest.py` |
| 框架学习笔记 | `docs/framework-learning-entity-and-repository.md` |
| 改造摘要 | `ruoyi-migration-summary.md` |
| 内存文件 | `C:\Users\PasserByNaOH\.claude\projects\d--TestingFrame-AA-ruoyi-testingFrame\memory\` |

### 若依环境

| 项目 | 信息 |
|------|------|
| 服务器 | `47.109.149.194:8080` |
| MySQL | Docker，仅绑 `127.0.0.1:3306` |
| Redis | Docker，仅绑 `127.0.0.1:6379` |
| SSH | `root@47.109.149.194:22` |
| 验证码类型 | `math`（算式计算） |
| HTTP 响应 | 永远 200，业务状态码在 JSON body 的 `code` 字段 |

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
│   ├── apiutil.py                ← 编排引擎 + 断言调度
│   └── generateId.py             ← ID 生成
│
├── lib/                          ← 工具库层（原 common/）
│   ├── assertions.py             ← 断言工具箱
│   ├── connection.py             ← 数据库/Redis/SSH 连接管理
│   ├── debugtalk.py              ← 热加载函数（${...} 调用的函数）
│   ├── readyaml.py               ← YAML 读取 + pytest 参数化
│   ├── sendrequest.py            ← HTTP 请求封装
│   ├── recordlog.py              ← 日志
│   ├── excelutil.py              ← openpyxl（替换原 handleExcel.py）
│   └── dingRobot.py              ← 钉钉通知（可选）
│
├── test_data/                    ← 测试数据层（纯 YAML，与执行代码彻底分离）
│   └── ruoyi/
│       ├── login/
│       │   ├── captcha.yaml
│       │   └── login.yaml
│       └── system/
│           ├── user_add.yaml
│           ├── user_update.yaml
│           ├── user_delete.yaml
│           ├── user_list.yaml
│           ├── user_export.yaml
│           ├── user_import.yaml
│           ├── user_resetPwd.yaml
│           ├── user_changeStatus.yaml
│           └── ...
│
├── test_runner/                  ← 测试执行层（纯 pytest，执行器）
│   ├── __init__.py
│   ├── conftest.py               ← fixture：SSH 隧道、登录、数据准备
│   ├── test_login.py             ← 登录用例执行器
│   ├── test_user.py              ← 用户管理执行器
│   └── test_role.py              ← 角色管理执行器
│
├── data/                         ← 运行时数据
│   └── extract.yaml              ← 提取的变量（token 等）
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
| `common/` | `lib/` | 避免变成垃圾桶目录 |
| `testcase/` | `test_data/` + `test_runner/` | **数据与执行彻底分离** |

---

## 三、Phase 划分

### Phase 0 · 项目初始化
**目标：** GitHub 仓库就绪，项目骨架可跑空用例
```
□ 创建 GitHub 公开仓库 ruoyi-testing-frame
□ git clone 到本地
□ 搭建目录结构（conf/core/lib/test_data/test_runner/data/logs/report）
□ 从原框架复制核心代码（不改逻辑，只搬文件 + 修正 import 路径）
□ 配置 .gitignore / .env.example
□ 初始化依赖 uv add sshtunnel paramiko openpyxl pytest allure-pytest
□ pytest --collect-only 能跑通
□ git add + commit + push
```
**分支：** `feature/phase0-init`

### Phase 1 · 基础设施
**目标：** SSH 隧道打通，MySQL/Redis 可连接
```
□ config.ini 改造（若依环境信息，密码用占位符）
□ SSH 隧道 fixture（参考 manuTest/5-RedisLoginTest/conftest.py）
□ test_runner/conftest.py：ssh_tunnel + system_login fixture
□ connection.py 适配（不改核心逻辑，只配合新 config）
□ 数据库连接验证（执行一条 SELECT）
□ Redis 连接验证（执行一条 GET/PING）
```
**分支：** `feature/phase1-infra`

### Phase 2 · 核心适配
**目标：** 框架引擎能正确理解若依的响应模型
```
□ sendrequest.py 审查 + 精简（删不用的 get()/post()）
□ apiutil.py 适配若依响应（HTTP 200 + body.code 才是业务状态）
□ assertions.py 扩展（新增 Redis 键值断言 + 二进制文件断言）
□ debugtalk.py 改造（删业务随机值方法，新增 get_captcha_code(uuid)）
□ handleExcel.py → excelutil.py（xlrd → openpyxl，独立改造）
□ 单接口 debug 模式验证
```
**分支：** `feature/phase2-adapt`

### Phase 3 · 登录模块
**目标：** 第一个完整测试链路跑通
```
□ 编写 test_data/ruoyi/login/captcha.yaml
□ 编写 test_data/ruoyi/login/login.yaml
□ 编写 test_runner/test_login.py
□ 验证码获取 → Redis 取值 → 登录 → token 提取 → 写入 extract.yaml
□ 登录失败用例（错误密码、空用户名、不存在的用户）
□ 全链路跑通，token 正确提取
```
**分支：** `feature/phase3-login`

### Phase 4 · 系统管理模块
**目标：** 系统管理全部 API 有测试覆盖
```
□ 用户 CRUD（增/删/改/查/导出/导入/重置密码/状态修改）
□ 角色管理（CRUD + 权限分配）
□ 菜单管理（树形结构增删改查）
□ 部门管理 + 岗位管理
□ 字典管理（dictType + dictData）
□ 参数配置 + 通知管理
□ 账户锁定测试（5 次失败 → Redis 验证 pwd_err_cnt key）
```
**分支：** 可拆多个：`feature/phase4-user` / `feature/phase4-role` / ...

### Phase 5 · CI/CD
**目标：** push 代码 → Jenkins 自动构建 → 收到报告
```
□ 安装/配置 Jenkins
□ 编写 Jenkinsfile（Pipeline）
□ GitHub Webhook 触发自动构建
□ Allure 报告集成
□ 邮件/钉钉通知
```
**分支：** `feature/phase5-jenkins`

### Phase 6 · 收尾与展示
**目标：** 面试可展示的完整项目
```
□ README.md 完善（架构图 + 技术栈 + 运行说明）
□ 代码注释 + docstring 补充
□ Git 操作练习（merge 冲突解决、rebase、tag）
□ 打版本 tag（v1.0）
```
**分支：** 直接在 main（改动较琐碎）

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
3. **手敲为主** — 默认不生成代码，用户说"可以直接生成"时才写
4. **登录优先** — 先跑通验证码→登录→token，再铺开面
5. **Jenkins 收尾** — 大部分用例完成后再接入 CI/CD
6. **GitHub 公开仓库** — 跨机器开发 + 面试展示
7. **测试范围** — 系统管理模块（约 10 个控制器），不含代码生成/定时任务

---

## 六、注意事项

- SSH/数据库/Redis 密码由用户后续填入，config.ini 用占位符
- `.env.example` 提供模板，真实 `.env` 在 `.gitignore` 中
- 若依响应模型：HTTP 永远 200，业务状态码在 `body.code` 字段
- 验证码是 `math` 类型，答案存在 Redis：`captcha_codes:{uuid}`
- 账户锁定 Redis key：`pwd_err_cnt:{username}`

---

## 七、对话记录

### 对话 1（2026-07-29）
- 阅读 ruoyi-migration-summary.md，完成框架分析
- 讨论并确认了整体规划、目录结构、Git 策略
- 确认：数据/执行分离、Phase 划分、branch 工作流
- 准备进入 Phase 0
