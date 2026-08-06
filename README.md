# ruoyi-testing-frame

基于 **pytest + YAML 数据驱动**的若依（RuoYi）管理系统 API 自动化测试框架。

将通用 API 测试框架改造为适配若依管理系统的专用测试框架，核心思想是**测试数据（YAML）与执行代码（pytest）彻底分离**。覆盖登录、用户管理、角色权限（RBAC + DataScope）、Excel 导入导出等核心业务，总计 **83 条自动化用例**，直接打真实云服务器环境（非 Mock）。

## 技术栈

| 组件 | 用途 |
|------|------|
| Python 3.12 + pytest | 测试框架与执行器 |
| YAML | 测试数据声明（`test_data/`） |
| requests | HTTP 请求 |
| pymysql + redis | 数据库验证、验证码答案 / 登录失败计数读取 |
| sshtunnel | SSH 隧道，打通远程 MySQL / Redis |
| openpyxl | Excel 导入文件生成、导出结果解析 |

## 目录结构

```
ruoyi-testing-frame/
├── conf/                 # 配置层
│   ├── config.ini        # 真实配置（gitignore 排除，不提交）
│   ├── config.example.ini# 配置模板（占位符）
│   └── setting.py        # 全局设置常量
├── core/                 # 核心引擎层
│   └── apiutil.py        # 编排引擎：变量替换 → 请求 → 提取 → 断言
├── utils/                # 工具库层
│   ├── assertions.py     # 断言工具箱（VALIDATORS 字典模式）+ 声明式 DB 验证
│   ├── connection.py     # MySQL / Redis 连接池
│   ├── debugtalk.py      # ${...} 热加载函数（时间戳 / 随机串 / 验证码 / runtime）
│   ├── excel_utils.py    # 用户导入 Excel 生成
│   ├── readyaml.py       # YAML 读取 + runtime.yaml 运行时变量
│   ├── recordlog.py      # 日志（日期命名）
│   └── sendrequest.py    # HTTP 请求封装
├── test_data/            # 测试数据层（纯 YAML，与执行代码分离）
│   └── ruoyi/
│       ├── login/        # 登录用例（15 条）
│       └── system/       # 用户 / 角色 / Excel / 业务流用例（68 条）
├── test_runner/          # 测试执行层（pytest）
│   ├── test_login/       # 登录测试
│   ├── test_user/        # 用户管理测试
│   ├── test_role/        # 角色权限 + DataScope 测试
│   ├── test_user_excel/  # Excel 导入导出测试
│   └── test_business/    # 业务流程测试
├── data/                 # 运行时数据（runtime.yaml / excel 文件）
├── conftest.py           # 根级 fixtures（SSH 隧道 / base_url / redis_client）
├── pytest.ini
└── README.md
```

## 用例覆盖

| 模块 | 用例数 | 覆盖内容 |
|------|:------:|----------|
| 登录 | 15 | 正常登录 / token 验证 + 13 条无效等价类（验证码层 3 + 前置校验层 4 + 认证层 6） |
| 用户管理 | 24 | 新增 11 / 编辑 4 / 删除 3 / 重置密码 3 / 状态切换 3 |
| 角色管理 | 42 | 新增 8 / 编辑 8 / 删除 4 / 状态 3 / DataScope 3 / 用户授权 5 / 查询隔离 6 / 写隔离 + 边界 5 |
| Excel 导入导出 | 1 | 导入 → DB 验证 → 导出 → 内容比对（端到端） |
| 业务流程 | 1 | 创建角色 → 创建用户 → 删除用户 → 删除角色（6 步链路） |
| **合计** | **83** | |

### 覆盖说明

- **登录验证流程**：覆盖验证码（错误 / 过期 / 缺失）、loginPreCheck 前置校验（空用户名 / 空密码 / 长度边界）、authenticate 认证（密码错误 / 不存在 / 5 次锁定 / 停用 / 删除）三道处理环节
- **前后端校验差异**：通过代码分析发现前端与后端 Bean 校验规则不一致，补充了接口层对边界输入（如空昵称）的实际处理行为验证
- **RBAC 权限模型**：覆盖菜单权限（`@PreAuthorize`）和数据权限（DataScopeAspect），验证 5 种数据范围下用户查询的隔离结果以及写操作的拦截行为
- **安全审查**：在编写角色授权测试时发现 `cancelAuthUser` 接口缺少 `checkRoleDataScope` 调用，记录了漏洞触发条件
- **数据库验证**：YAML 中通过 `db_verify` 块声明 `exists / count / eq / not_empty` 等验证类型，SQL 参数化防注入

## 快速开始

### 1. 创建 conda 环境

```bash
conda create -n testframe python=3.12 -y
```

### 2. 安装依赖

```bash
conda run -n testframe python -m pip install pytest requests pyyaml pymysql redis sshtunnel "paramiko<3.0" jsonpath openpyxl
```

> ⚠️ **paramiko 必须 `<3.0`**：paramiko 3.x 移除了 DSSKey，与 sshtunnel 不兼容。

### 3. 配置 config.ini

`conf/config.ini` 含真实凭据，已被 gitignore 排除。首次使用先复制模板再填入真实值：

```bash
cp conf/config.example.ini conf/config.ini
```

```ini
[api_envi]
host = http://<服务器IP>:8080

[SSH]
host = <服务器IP>
port = 22
username = root
password = <SSH密码>

[MYSQL]
host = 127.0.0.1        ; 走 SSH 隧道后连本地映射端口
port = 3306
username = root
password = <数据库密码>
database = <数据库名>

[REDIS]
host = 127.0.0.1
port = 6379
password = <Redis密码>
db = 0

[admin]
username = admin
password = admin123
```

### 4. 运行测试

```bash
cd ruoyi-testing-frame

# 全量运行
conda run -n testframe python -m pytest -q

# 按模块运行
conda run -n testframe python -m pytest test_runner/test_login -q
conda run -n testframe python -m pytest test_runner/test_user -q
conda run -n testframe python -m pytest test_runner/test_role -q
```

> 依赖服务器连通性（SSH 隧道打通 MySQL/Redis），需先确保若依环境在线。

## 设计思路

- **数据与执行彻底分离** — YAML 只声明测试数据（`test_data/`），`test_*.py` 负责执行，加用例只需写 YAML
- **真环境测试** — 直接打云服务器，不 Mock，验证码通过 `/captchaImage` + Redis 真实走通
- **运行时变量** — 步骤间通过 `extract` → `runtime.yaml` → `${get_runtime(key)}` 串联，仿 Postman 环境变量
- **VALIDATORS 字典模式** — 新增断言只需写一个函数 + 注册一行映射，替代 if/elif 链
- **声明式 DB 验证** — `run_db_verify` 支持 `exists / count / eq / not_empty`，在 YAML 声明、不写裸 SQL
- **多身份登录** — `login_for_yaml()` 每次新登录（不缓存），消除角色重建后的 stale token 问题
- **自动数据清理** — session 结束物理删除 `at_%` 前缀测试数据，保证可重复运行
