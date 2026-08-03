# DB 验证专项排查 · 启动提示词

> 用途：台式机（或任意新会话）继续解决 problem.md §6 的 DB 验证问题。
> 环境就绪后，直接粘贴下方"提示词"开始。

---

## 一、启动提示词（粘贴到新会话）

```text
阅读 project-startup.md、problem.md、ruoyi-migration-summary.md，先阅读整个项目代码，再开始。

当前唯一任务：解决 problem.md 第 6 节的 DB 验证问题（run_db_verify 在 pytest 引擎调用后 DB 查询不到预期数据，但独立脚本 debug_edit.py 分步执行却能成功）。

处理步骤：
1. 先 checkout 分支 feature/phase3-db-verify（该分支包含 run_db_verify 和 db_verify YAML 块的全部诊断代码，master 上是干净基线）
2. 对比该分支与 master 的差异，理解 DB 验证的实现方式
3. 结合 problem.md §6 的排查记录（已排除：API 本身问题 / token 隔离 / conftest 误删 / replace_load 篡改 / MyBatis 动态 SQL）
4. 用 debug_edit.py 的分步思路，定位 pytest 上下文中 DB 验证失效的根因
5. 修复后合回 master，更新 problem.md 与 project-startup.md

注意：config.ini 已在台式机本地配置好真实值；测试手动执行，不要自动跑。
```

---

## 二、台式机环境准备（一次性）

### Python 版本

- Python **3.12**（conda 环境名 `testframe`）

### 依赖清单

| 包 | 版本 | 用途 |
|---|---|---|
| requests | 2.34.2 | HTTP 请求 |
| pytest | 9.1.1 | 测试框架 |
| PyMySQL | 1.2.0 | MySQL 连接 |
| redis | 8.0.1 | Redis 连接 |
| sshtunnel | 0.4.0 | SSH 隧道 |
| **paramiko** | **<3.0（实测 2.12.0）** | sshtunnel 依赖，3.x 移除了 DSSKey |
| PyYAML | 6.0.3 | YAML 解析 |
| jsonpath | 0.82.2 | 响应提取 |
| allure-pytest | 2.16.0 | 报告（可选） |
| openpyxl | — | Phase 4 Excel 才需要 |

```bash
conda create -n testframe python=3.12 -y
conda activate testframe
pip install requests pytest pymysql redis sshtunnel "paramiko<3.0" pyyaml jsonpath
```

### ⚠️ 必做：创建 conf/config.ini

`config.ini` 含真实密码，被 gitignore，不会随 clone 带过去。从 `conf/config.example.ini` 复制并填入真实值：
- `[api_envi] host`——注意 example 里带引号 `http://"ip":8080`（格式有误），填真实 IP 时去掉引号
- `[SSH]` 密码
- `[MYSQL]` 密码
- `[REDIS]` 密码
- `[admin]` 账号（example 默认 admin/admin123）

`data/runtime.yaml` 也是 gitignored，运行时自动重建，不用管。

---

## 三、Git 拉取

```bash
# 代理不通时先设代理
git config --global https.proxy http://127.0.0.1:7897
git pull
```
