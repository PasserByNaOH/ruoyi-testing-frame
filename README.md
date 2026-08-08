# ruoyi-testing-frame

若依（RuoYi）管理系统 API 自动化测试框架。

基于 **pytest + YAML 数据驱动 + Allure 报告 + Jenkins 流水线**构建，核心思想是**测试数据（YAML）与执行代码（pytest）彻底分离**。覆盖登录、用户管理、角色权限（RBAC + DataScope）、Excel 导入导出等核心业务，总计 **83 条自动化用例**。

## 环境设置

### 1. 本机代码运行环境

测试代码在本机运行，使用 conda 管理 Python 环境：

```bash
conda create -n testframe python=3.12 -y

conda run -n testframe python -m pip install pytest requests pyyaml pymysql redis sshtunnel "paramiko<3.0" jsonpath openpyxl allure-pytest
```

> ⚠️ **paramiko 必须 `<3.0`**：paramiko 3.x 移除了 DSSKey，与 sshtunnel 不兼容。

### 2. 被测系统（若依）环境

若依系统部署在 **2 核 2G 的阿里云服务器**上：

- RuoYi 后端运行在 `8080` 端口
- MySQL、Redis 用 Docker 部署，仅绑定 `127.0.0.1`，不对外暴露
- 测试代码通过 **SSH 隧道**打通远程 MySQL / Redis（验证码答案、登录失败计数、DB 验证都依赖它）

### 3. CI/CD（Jenkins）环境

Jenkins 部署在 **本机 VMware 的 2 核 4G Ubuntu 虚拟机**上（非云服务器）：

- Jenkins 运行在 `9090` 端口
- 使用 **uv 管理 Python 依赖**（替代 conda），流水线通过 `uv run pytest` 执行测试
- 测试完成后自动生成 Allure 报告，并推送钉钉通知到群
- 工作流：Windows 开发机写用例 → git push GitHub → VM git pull → Jenkins 一键回归

## 技术栈

| 组件 | 用途 |
|------|------|
| Python 3.12 + pytest | 测试框架与执行器 |
| YAML | 测试数据声明（`test_data/`） |
| requests | HTTP 请求 |
| pymysql + redis | 数据库验证、验证码答案 / 登录失败计数读取 |
| sshtunnel | SSH 隧道，打通远程 MySQL / Redis |
| openpyxl | Excel 导入文件生成、导出结果解析 |
| Allure | 测试报告（epic/feature/story 分层 + 请求/响应/断言附件） |
| Jenkins | CI/CD 流水线（Declarative Pipeline + Allure 报告归档） |
| 钉钉机器人 | 构建结果推送（成功/失败即时通知到群） |

## 目录结构

```
ruoyi-testing-frame/
├── conf/                     # 配置层
│   ├── config.ini            # 真实配置（gitignore 排除，不提交）
│   ├── config.example.ini    # 配置模板（占位符）
│   └── setting.py            # 全局设置常量
├── core/                     # 核心引擎层
│   └── apiutil.py            # 编排引擎：变量替换 → 请求 → 提取 → 断言
├── utils/                    # 工具库层
│   ├── assertions.py         # 断言工具箱（VALIDATORS 字典模式）+ 声明式 DB 验证
│   ├── connection.py         # MySQL / Redis 连接池
│   ├── debugtalk.py          # ${...} 热加载函数（时间戳 / 随机串 / 验证码 / runtime）
│   ├── excel_utils.py        # 用户导入 Excel 生成
│   ├── jenkins.py            # Jenkins API + 钉钉封装（本地手动查询用，流水线未使用）
│   ├── readyaml.py           # YAML 读取 + runtime.yaml 运行时变量
│   ├── recordlog.py          # 日志（日期命名）
│   └── sendrequest.py        # HTTP 请求封装
├── test_data/                # 测试数据层（纯 YAML，与执行代码分离）
│   └── ruoyi/
│       ├── login/            # 登录用例（15 条）
│       └── system/           # 用户 / 角色 / Excel / 业务流用例（68 条）
├── test_runner/              # 测试执行层（pytest）
│   ├── test_01_login/        # 登录（15 条）
│   │   ├── conftest.py       # 模块 fixtures（session 清 runtime / 清密码错误计数）
│   │   ├── helpers.py        # 复用工具：prepare_captcha / apply_setup
│   │   ├── test_login_success.py   # 登录成功执行器（2 条）
│   │   └── test_login_fail.py      # 登录失败执行器（13 条）
│   ├── test_02_user/         # 用户管理（24 条）
│   │   ├── conftest.py       # fixtures + admin 登录 + at_% 残留清理
│   │   ├── helpers.py        # 复用工具：create_user / get_user_id
│   │   └── test_user.py      # 5 端点参数化执行器
│   ├── test_03_role/         # 角色权限 + DataScope（42 条）
│   │   ├── conftest.py       # fixtures + admin 登录 + isolation_users 预置（5 角色 + 7 用户）
│   │   ├── helpers.py        # 复用工具：角色 CRUD / 多身份登录 / scope 计算
│   │   ├── test_role_crud.py # 角色 CRUD 执行器（31 条）
│   │   └── test_role_scope.py# DataScope 隔离（11 条）
│   ├── test_04_user_excel/   # Excel 导入导出（1 条）
│   │   ├── conftest.py       # fixtures + admin 登录 + 残留清理
│   │   └── test_user_import_export.py  # 导入 → DB 验证 → 导出 → 内容比对
│   └── test_05_business/     # 业务流程（1 条）
│       ├── conftest.py       # fixtures + admin 登录 + 用户/角色双清理
│       └── test_business_flow.py     # 创建角色 → 查角色ID → 创建用户 → 验证 → 删除用户 → 删除角色（6 步链路）
├── data/                     # 运行时数据（runtime.yaml / 导入导出 Excel）
├── conftest.py               # 根级 fixtures（SSH 隧道 / base_url / redis_client）
├── Jenkinsfile               # CI/CD 流水线：动态发现用例模块 → pytest → Allure 归档 → 钉钉推送
├── run.py                    # 一键全量回归 + 生成 / 打开 Allure 报告
├── environment.xml.example   # Allure 环境信息模板（测试环境参数）
├── setup-vm.sh               # 虚拟机一键部署脚本（Java + Jenkins + uv + Allure）
├── LICENSE                   # MIT 开源许可
├── pytest.ini                # pytest 配置
└── README.md
```

## 用例覆盖

| 模块 | 用例数 | 测试设计方法 |
|------|:------:|------------|
| 登录 | 15 | 等价类 + 边界值 + 异常链 |
| 用户管理 | 24 | CRUD + 唯一性冲突 + Bean 校验 + 前后端缺口挖掘 |
| 角色管理 | 42 | RBAC 双层模型（菜单 + DataScope）+ 越权测试 |
| Excel 导入导出 | 1 | 端到端业务流 + 数据一致性 |
| 业务流程 | 1 | 跨模块数据串联 |
| **合计** | **83** | |

### 覆盖说明

- **登录验证流程**：覆盖验证码（错误 / 过期 / 缺失）、loginPreCheck 前置校验（空用户名 / 空密码 / 长度边界）、authenticate 认证（密码错误 / 不存在 / 5 次锁定 / 停用 / 删除）三道处理环节
- **前后端校验差异**：通过代码分析发现前端与后端 Bean 校验规则不一致，补充了接口层对边界输入（如空昵称）的实际处理行为验证
- **RBAC 权限模型**：覆盖菜单权限（`@PreAuthorize`）和数据权限（DataScopeAspect），验证 5 种数据范围下用户查询的隔离结果以及写操作的拦截行为
- **安全审查**：在编写角色授权测试时发现 `cancelAuthUser` 接口缺少 `checkRoleDataScope` 调用，记录了漏洞触发条件
- **数据库验证**：YAML 中通过 `db_verify` 块声明 `exists / count / eq / not_empty` 等验证类型，SQL 参数化防注入

## 设计思路

- **数据与执行彻底分离** — YAML 声明测试数据（`test_data/`），`test_*.py` 负责执行，新增用例只需在 YAML 中声明，无需修改执行代码
- **真环境测试** — 采用企业沙盒测试方式，测试环境部署在真实云服务器中（2核2G 阿里云），验证码通过 `/captchaImage` 获取、从 Redis 读取答案，全链路使用真实数据
- **运行时变量** — 步骤间通过 `extract` → `runtime.yaml` → `${get_runtime(key)}` 串联，实现跨步骤数据传递
- **VALIDATORS 字典模式** — 断言类型通过 VALIDATORS 字典注册，新增断言只需写一个断言函数并注册一行映射，替代 if/elif 分支链
- **声明式 DB 验证** — `run_db_verify` 支持 `exists / count / eq / not_empty` 四种验证类型，在 YAML 中声明验证规则、无需手写 SQL
- **多身份登录** — `login_for_yaml()` 每次完整执行验证码→登录流程、不缓存 token，避免角色重建后旧 token 权限失效
- **自动数据清理** — session 结束物理删除 `at_%` 前缀的测试数据，保证测试可重复执行
