# Phase 2 踩坑记录

## 1. YAML `data:` vs `json:`

**现象**：登录请求返回 HTTP 200，但 jsonpath `$.token` 未匹配。

**原因**：YAML 用了 `data:` 关键字。requests 库中 `data=dict` 将请求体编码为 `application/x-www-form-urlencoded`
（`username=admin&password=123`），而非 JSON。若依后端用 `@RequestBody` 接收，解析表单格式失败，登录未成功，响应中自然没有 token。

**修复**：所有 JSON API 的 YAML 用例改用 `json:` 关键字。
```yaml
# 错误
data:
  username: admin

# 正确
json:
  username: admin
```

---

## 2. `replace_load` 不还原 list 类型

**现象**：
```
TypeError: string indices must be integers, not 'str'
```
发生在 `utils/assertions.py:64` → `run_validations` 中 `rule["type"]`。

**原因**：`replace_load` 的出口判断只还原 dict，遗漏了 list：
```python
# 原代码
if data and isinstance(data, dict):   # list 不匹配 → 跳过
    return json.loads(str_data)
return str_data                        # 返回 JSON 字符串，不是 list
```

YAML 的 `validations` 是 list → `json.dumps` 转字符串处理 `${}` → 出口未还原 → `run_validations` 收到字符串 → `for rule in "字符串"` 遍历字符 → `"["["type"]` 报 TypeError。

**修复**：出口判断加上 list：
```python
if data and isinstance(data, (dict, list)):
    return json.loads(str_data)
```

---

## 3. `specification_yaml` 的 `pop` 掏空 case

**现象**：引擎调用后，case 字典只剩未被 pop 的字段（如 `captcha_mode`）。

**原因**：`test_login.py` 将原 case 直接传入 `specification_yaml()`，引擎内部大量 `test_case.pop()`（case_name、json、validations、extract 等）直接破坏了原数据。

**修复**：传入前浅拷贝：
```python
engine.specification_yaml(dict(base_info), dict(case))
```

---

## 4. `captcha_mode` 的设计

**问题**：为什么需要在 YAML 中标注 `captcha_mode`？

**原因**：验证码获取逻辑不在 YAML 中，也不在引擎中。它发生在 `test_login.py` 里——先调 `/captchaImage` 获取 uuid，再从 Redis 取验证码答案，最后拼入 data。YAML 用 `captcha_mode` 告诉 test 函数本条用例需要哪种策略：

| mode | test 函数行为 |
|------|-------------|
| `valid` | GET /captchaImage → Redis 取正确 code → 填入 |
| `wrong` | GET /captchaImage 拿 uuid，code 用 YAML 的假值 |
| `fake_uuid` | 不调 /captchaImage，YAML 直接提供假 uuid + code |
| `missing` | 不调 /captchaImage，YAML 只提供 uuid，不传 code |
| `skip` | 什么都不做（LOGIN-02 getInfo 不需要验证码） |

---

## 5. conftest autouse fixture 的执行顺序

**设计**：`test_login/conftest.py` 两个 autouse fixture：
- `clean_runtime_on_start`（session 级）：测试前清空 runtime.yaml
- `clean_pwd_error_count`（function 级）：每条测试后删除 `pwd_err_cnt:LoginTestUser`

**执行时序**：
```
session 启动
  → clean_runtime_on_start：清空 runtime.yaml（yield 之前的代码）

每条测试：
  → clean_pwd_error_count：yield（暂停，测试执行）
  → 测试运行
  → clean_pwd_error_count：删除 Redis 计数（yield 之后的代码）
```

---

# Phase 3 踩坑记录

## 6. `run_db_verify` — 引擎调用后 DB 验证不生效

**现象**：`feature/phase3-db-verify` 分支上，U-04（编辑）/U-05（删除）/U-06（重置密码）的 DB 验证全部失败。HTTP 断言全过（API 返回 code=200），但 MySQL 查询显示：
- U-04：用户存在，但 nick_name 未更新（仍是 create_user 时的初始值 `at_edit_04`）
- U-05/06：用户在 DB 中不存在（查询结果 0 行）

**排查过程**：

1. **独立脚本验证 API** — 手写 `debug_edit.py`，绕过测试框架，用 `requests.put()` 直接调编辑 API，nick_name 正常更新。证明 API 本身没问题。

2. **测试框架内 raw requests 也失败** — 在 `test_user_edit` 函数内加诊断：引擎调用后立即用相同 `requests.put()` 再发一次，同样 code=200 但 nick_name 未变。说明问题不在引擎管道，而在 pytest 运行上下文。

3. **Token 隔离测试** — 把 `ensure_admin_login` 从 session 级改为 function 级（每用例独立登录），仍然失败。排除 token 共享/过期问题。

4. **排除因素**：不是 conftest 误删（`clean_at_users` 是 session 级）、不是 `replace_load` 篡改请求体、不是 MyBatis 动态 SQL 条件问题（所有 `<if>` 条件都能通过）。

**当前状态**：根因未定位。切回 master 分支（70ae7f4），移除 YAML 中的 `db_verify` 块，先推进 changeStatus。DB 验证作为独立议题后续处理。

**诊断关键代码**：见 `debug_edit.py`（临时文件，gitignore 排除）。步骤化执行创建→编辑→验证，每步可配合 DBeaver 观察。

---

**✅ 根因已定位（2026-08-04）**

**问题**：`ConnectMysql` 默认 `autocommit=False`，所有查询共享同一个隐式事务 + 同一个 cursor。MySQL REPEATABLE READ 在事务第一次 SELECT 时拍下快照，后续查询看不到 API 在另一个连接中提交的修改。

**传染链**：
1. `test_user_edit` 的诊断查询在 API 调用前执行了 SELECT → 开启隐式事务、拍下快照
2. 若依 API 在自己的数据库连接中 UPDATE + COMMIT
3. `test_user_edit` 的 `run_db_verify` 仍在同一事务中 → 读到旧快照 → ❌ 失败
4. `test_user_delete` 的 `run_db_verify` 用的是同一 cursor、同一事务 → 快照里 `at_del_05` 还没创建 → ❌ "用户不存在"
5. `test_user_resetPwd` 同理

**修复**：
- `ConnectMysql.__init__` 添加 `autocommit=True` — 每条 SQL 独立事务，每次 SELECT 都是最新快照
- `ConnectMysql.query()` 支持 `params` 参数 — 防止 SQL 注入
- `ConnectMysql.__init__` 支持可选连接参数 — conftest 通过 SSH 隧道端口指定连接
- `charset` 从 `"utf-8"` 修正为 `"utf8mb4"`

---

## 7. `cursor.execute(sql, ())` → `%` 被当作 Python 格式符

**现象**：`ConnectMysql` 加了 `params` 支持后，所有 `clean_at_users` 的 DELETE 语句全部报：

```
TypeError: not enough arguments for format string
```

SQL 中含有 `LIKE 'at\_%'` —— 这是 MySQL LIKE 通配符，不是 Python 占位符。

**原因**：`cursor.execute(sql, ())` —— 即使 params 是空 tuple `()`，pymysql 也会把整个 SQL 当作 Python 的 `%` 格式字符串处理。`LIKE 'at\_%'` 中的 `%` 被识别为格式符，但后面跟的是 `'`（单引号），不是合法的格式字符 → TypeError。

如果传的是 `cursor.execute(sql)`（无第二参数），pymysql 不会做格式化，`%` 作为字面量直接发给 MySQL → 正常。

**修复**：

```python
# 错误写法
self.cursor.execute(sql, params or ())

# 正确写法
if params:
    self.cursor.execute(sql, params)
else:
    self.cursor.execute(sql)
```

关键认知：pymysql 的 `cursor.execute(sql, params)` 本质上是 Python 的 `%` 字符串格式化 + SQL 转义——**不是**真正的参数化查询（prepared statement）。因此 SQL 里任何 `%` 都要加倍写成 `%%` 或者走无参数通道。


---

# Phase 4 踩坑记录

## 8. 角色删除是逻辑删除（非物理删除）

**现象**：`test_role_delete[删除角色-正常]` → API 返回 200 "操作成功"，但 DB 验证 `SELECT COUNT(*) FROM sys_role WHERE role_id = ?` 返回 1（预期 0）。

**原因**：`SysRoleMapper.xml` 的 `<delete id="deleteRoleById">` 标签内写的 SQL 是 `UPDATE sys_role SET del_flag = '2' WHERE role_id = ?`——和用户删除一样，是**逻辑删除**不是物理删除。role 记录还在，只是 `del_flag` 标记为 `'2'`。

**修复**：DB 验证改用 `expect: eq` 验证 `del_flag = '2'`，和 `user_delete.yaml` 一致。

---

## 9. `login_as_user` 缓存 stale token

**现象**：隔离测试第一次跑全过（11/11），第二次跑查询全挂（6 条全部 403 "没有权限"）。

**原因**：`login_as_user()` 把用户 token 缓存到 `runtime.yaml["{username}_token"]`。第二次运行时 `clean_at_test_data` 清理旧角色 → `isolation_users` 重建（新 role_id），但 `login_as_user` 复用旧 token → 旧 role_id 的 `sys_role_menu` 已被删 → 权限为空 → 403。

**修复**：放弃缓存。新增 `login_for_yaml()`——每次完整走 `/captchaImage` → Redis → `/login` 流程。

---

## 10. `cancelAuthUser` 没有 `checkRoleDataScope`

**发现**：和 `selectAuthUserAll`（有 checkRoleDataScope）不同，`cancelAuthUser` 和 `cancelAuthUserAll` Controller 层未调 `checkRoleDataScope`。但 `@PreAuthorize("system:role:edit")` 在 Layer 1 拦截了大部分攻击——**漏洞仅在"用户有角色编辑菜单权限但 DataScope 受限"时暴露**。

---

## 11. YAML `auth_user` + `rows_in_scope` 集成

**背景**：隔离测试需要切换用户身份。原有 `inject_token` 只读 `runtime.yaml["token"]`。

**方案**：`specification_yaml` 新增 `auth_user` 字段 + `login_for_yaml`；`run_validations` 加 `**kwargs` 透传 `db` 给 `rows_in_scope` 断言。

**变更**：
- `assertions.py`：所有 validator 加 `**kwargs` + 新增 `assert_rows_in_scope`
- `apiutil.py`：`specification_yaml` 新增 `db` + `redis_client` 参数 + `auth_user` 处理
- 6 条查询隔离从 Python 转为 YAML（`role_scope_query.yaml`）


---

# Phase 4 Goal B 踩坑记录

## 12. `{}` 空 dict 在 Python 中是 falsy

**现象**：导入测试中 `import_case["headers"] = {}` 企图覆盖 base_info 的 JSON Content-Type，但请求头仍然是 `Content-Type: application/json`。file 参数虽然传了，requests 却以 JSON 而非 multipart 发送。

**原因**：`specification_yaml` 的回退逻辑：
```python
case_headers = test_case.pop("headers", None)
headers = self.replace_load(case_headers if case_headers else base_info["headers"])
```
`{}` 是 falsy → 回退到 `base_info["headers"]`（含 `Content-Type: application/json`）。

**修复**：传入不含 Content-Type 的非空 headers：
```python
"headers": {"Accept": "application/json, text/plain, */*"}
```

关键认知：Python 中 `bool({}) == False`，回退逻辑应使用 `is None` 检测而非 falsy 检测。

---

## 13. `specification_export` 方法被 IDE 覆盖丢失

**现象**：测试运行时报 `AttributeError: 'ApiEngine' object has no attribute 'specification_export'`，但之前已成功写入。

**原因**：IDE 对 `apiutil.py` 的自动保存/格式化操作可能覆盖了新增方法。EAFP 原则——检测到缺失后重新写入即可。

---

## 14. conda 环境 openpyxl 依赖

**现象**：`ModuleNotFoundError: No module named 'openpyxl'`。

**原因**：之前检查的 Python 环境和 conda `testframe` 环境不同。openpyxl 3.1.0 在 base 环境，但 tests 在 `testframe` 中运行。

**修复**：`conda run -n testframe pip install openpyxl`（v3.1.5）。


---

# Phase 6 CI/CD 踩坑记录

## 15. Jenkins 最新稳定版要求 Java 21

**现象**：Jenkins 启动报错：
```
Running with Java 17 from /usr/lib/jvm/java-17-openjdk-amd64,
which is older than the minimum required version (Java 21).
```

**原因**：Jenkins 2.479+ 已将最低 Java 版本从 17 提升到 21。project-startup.md 和 setup-vm.sh 中的计划基于 Java 17，已过时。

**修复**：`sudo apt install -y openjdk-21-jdk`，然后 `sudo update-alternatives --config java` 切换默认版本。

---

## 16. Jenkins 官方 apt 源在国内网络不可达 + 清华镜像不支持 apt 仓库格式

**现象**：`pkg.jenkins.io` 的 GPG key 下载失败，清华 Jenkins 镜像 `mirrors.tuna.tsinghua.edu.cn/jenkins/debian-stable` 的 Release 文件 404。

**原因**：
- `pkg.jenkins.io` 被墙，GPG key 和 apt 源均不可达
- 清华 Jenkins 镜像只提供 war 包直接下载，不提供 apt 仓库格式（无 Release 文件）

**修复**：放弃 apt 安装。从清华镜像直接下载 war 包 + 手动创建 systemd 服务：
```bash
wget https://mirrors.tuna.tsinghua.edu.cn/jenkins/war-stable/latest/jenkins.war
sudo mkdir -p /var/lib/jenkins
sudo useradd -r -s /bin/false jenkins
sudo chown -R jenkins:jenkins /var/lib/jenkins
sudo mv jenkins.war /var/lib/jenkins/

sudo tee /etc/systemd/system/jenkins.service > /dev/null << 'EOF'
[Unit]
Description=Jenkins CI
After=network.target

[Service]
User=jenkins
WorkingDirectory=/var/lib/jenkins
Environment="JENKINS_HOME=/var/lib/jenkins"
ExecStart=/usr/bin/java -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true -Xmx256m -jar /var/lib/jenkins/jenkins.war --httpPort=9090
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now jenkins
```

关键：`ExecStart` 中 war 包必须放在 `jenkins` 用户有权访问的路径（`/var/lib/jenkins/`），不要放 `/home/aaa/`。

---

## 17. `jenkins` 用户没有家目录 → git config 报错

**现象**：
```
error: could not lock config file /home/jenkins/.gitconfig: No such file or directory
```

**原因**：`useradd -r` 创建的系统用户没有家目录，`git config --global` 尝试写 `~/.gitconfig` 失败。

**修复**：
```bash
sudo mkdir -p /home/jenkins
sudo chown jenkins:jenkins /home/jenkins
```

---

## 18. Jenkins `dir()` 步骤创建 `@tmp` → AccessDenied

**现象**：
```
java.nio.file.AccessDeniedException: /home/aaa/ruoyi-testing-frame@tmp
```

**原因**：Jenkins Pipeline 的 `sh` 步骤由 Durable Task Plugin 实现，会在 `dir()` 指定的目录下创建 `@tmp` 子目录存放临时代码。`jenkins` 用户对 `/home/aaa/ruoyi-testing-frame` 无写权限 → 创建失败，整个 `sh` 步骤在脚本执行前就挂了。

**修复**：不用 `dir()`，改为直接在 `sh` 中用 `cd` 切换目录。`@tmp` 将在 Jenkins workspace（`/var/lib/jenkins/workspace/`）下创建，`jenkins` 用户有写权限。

---

## 19. Git 所有权检测（dubious ownership）

**现象**：
```
fatal: detected dubious ownership in repository at '/home/aaa/ruoyi-testing-frame'
```

**原因**：Git 2.35.2+ 安全特性——如果仓库所有者不是当前用户，拒绝操作。仓库属主是 `aaa`，Jenkins 以 `jenkins` 用户执行 `git pull`。

**修复**：最终方案——不依赖 `/home/aaa/`。将项目复制到 `/var/lib/jenkins/ruoyi-testing-frame/`，`chown -R jenkins:jenkins`，Jenkins 用自己拥有的仓库。

---

## 20. `.venv` 复制后路径绑定失效 + 漏装 `jsonpath`

**现象**：
```
ModuleNotFoundError: No module named 'jsonpath'
```

**原因**：
- 原项目 `.venv` 在 `/home/aaa/ruoyi-testing-frame/.venv`，部分 Python 二进制硬编码了原路径
- 依赖列表不全——`jsonpath` 在前期手工装过但从未写入任何 `requirements` 文件

**修复**：删除旧 `.venv`，在 `/var/lib/jenkins/ruoyi-testing-frame/` 重建：
```bash
sudo -u jenkins uv venv --python 3.12
sudo -u jenkins uv pip install \
    -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple \
    --trusted-host mirrors.tuna.tsinghua.edu.cn \
    pytest allure-pytest "paramiko<3.0" pymysql redis sshtunnel pyyaml requests openpyxl jsonpath
```

---

## 21. 项目缺少 `data/` 目录

**现象**：`test_login.py` 首条用例 FAILED，日志报 `clear_runtime` → `FileNotFoundError: data/runtime.yaml`。

**原因**：`data/runtime.yaml` 在 `.gitignore` 中排除，git clone 不创建 `data/` 空目录。首次运行时自动创建逻辑也不覆盖这种场景。

**修复**：
```bash
sudo mkdir -p /var/lib/jenkins/ruoyi-testing-frame/data
sudo chown jenkins:jenkins /var/lib/jenkins/ruoyi-testing-frame/data
```

---

## 22. `config.ini` 复制时 IP 笔误

**现象**：虚拟机 Jenkins 构建中 HTTP 请求打到了 `http://47.10.149.194:8080`（少了一个 `9`），ConnectionError。

**原因**：config.ini 从 Windows 手工拷贝到虚拟机时键盘输入错误。云服务器真实 IP 是 `47.109.149.194`。

**修复**：`sed -i 's/47\.10\.149\.194/47.109.149.194/g' config.ini`。

**教训**：IP/密码等敏感信息要么用 Jenkins Credentials 注入，要么用 `diff` 对比 Windows 和 Linux 两端配置确认一致。

---

## 23. Jenkins Git Plugin 拒绝本地目录 checkout

**现象**：
```
ERROR: Checkout of Git remote '/var/lib/jenkins/ruoyi-testing-frame/.git' aborted
because it references a local directory, which may be insecure.
```

**原因**：Jenkins Git Plugin 默认禁止本地文件系统路径作为 remote URL，避免安全风险。

**修复**：在 `jenkins.service` 的 `ExecStart` 添加 JVM 参数（注意是 `java` 启动参数，不是 `JAVA_OPTS` 环境变量）：
```
-Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true
```
坑：写到 `Environment="JAVA_OPTS=..."` 不生效——因为 systemd 服务用的是 `ExecStart=/usr/bin/java -jar ...`，`JAVA_OPTS` 环境变量不会被 java 命令自动读取。必须把参数直接加在 `-jar` 前面。

---

## 24. Allure 未在虚拟机上安装

**现象**：`sh: allure: not found`。

**原因**：前期 Jenkins 安装问题频出，Allure 安装步骤被跳过。后因 GitHub 被墙，下载也受阻。

**修复**：
- 方案 A（代理）：`export https_proxy=http://宿主机IP:7897 && wget https://github.com/...`
- 方案 B（手动）：Windows 下载 `allure-2.32.0.tgz` → Xftp 传到虚拟机 → `sudo tar -xzf ~/allure-2.32.0.tgz -C /opt/ && sudo ln -sf /opt/allure-2.32.0/bin/allure /usr/local/bin/allure`

npm 的 `allure-commandline` 包内部 dist/ 解压也需要同样处理，无实质区别。

---

## 25. Pipeline `allure` 步骤不显示报告 → workspace 路径不匹配

**现象**：
- Allure Jenkins Plugin 已安装、Global Tool 已配 `/opt/allure-2.32.0`
- Pipeline `post` 中已写 `allure includeProperties: false, results: [[path: 'report/temp']]`
- Jenkins 构建日志显示 `allure` 步骤执行成功
- 但构建侧边栏始终没有 **Allure Report** 链接
- Freestyle 项目中 `Publish Allure Report` post-build action 同样无报告

**排查过程**：
1. 检查 `report/temp` 目录——数据存在（880 个 JSON 文件），排除 pytest 未生成数据
2. 尝试 Freestyle 的 `Publish Allure Report` ——仍然不显示，排除 Pipeline 语法问题
3. 手动 `allure generate report/temp` + `http.server` ——报告可正常查看，排除 Allure 工具本身问题
4. 检查 Jenkins workspace——`/var/lib/jenkins/workspace/ruoyi-testing-frame/` 下是空的，**没有 `report/temp`**

**根因**：Jenkins Pipeline 默认 workspace 和实际项目目录是**两个不同路径**：

```
默认 workspace：  /var/lib/jenkins/workspace/ruoyi-testing-frame/   ← 空的
项目实际路径：    /var/lib/jenkins/ruoyi-testing-frame/              ← 代码 + report/temp 在这里
```

`allure` 步骤中的 `results: [[path: 'report/temp']]` 是相对于 **workspace** 的路径，在默认 workspace 下找不到 → 无报告。

**修复**：让 workspace 指向项目目录。

Pipeline 方式（Jenkinsfile）：
```groovy
pipeline {
    agent {
        node {
            label 'built-in'
            customWorkspace '/var/lib/jenkins/ruoyi-testing-frame'
        }
    }
    ...
    post {
        always {
            allure includeProperties: false, results: [[path: 'report/temp']]
        }
    }
}
```

Freestyle 方式（UI 配置）：
```
General → 高级 → ✅ Use custom workspace → /var/lib/jenkins/ruoyi-testing-frame
Post-build Actions → Allure Report → Results: report/temp
```

修复后 Pipeline 和 Freestyle 两种模式均正常显示 Allure Report 链接。

**关键认知**：Jenkins 的几乎所有路径（`sh` 工作目录、`allure` results 路径、`archiveArtifacts` 路径）都相对于 workspace。如果项目不在标准 workspace 下，要么用 `customWorkspace`，要么所有路径写绝对路径。

---

## 26. `allure generate` 文件权限冲突

**现象**：`aaa` 用户执行 `allure generate` 时报 `AccessDeniedException: report/allure/history/retry-trend.json`。

**原因**：Jenkins 构建以 `jenkins` 用户运行，生成的 `report/allure/` 文件属主为 `jenkins:jenkins`。`aaa` 用户无写权限，无法覆盖 history 趋势文件。

**修复**：
```bash
sudo chown -R aaa:aaa /var/lib/jenkins/ruoyi-testing-frame/report
# 或
sudo chmod -R 777 /var/lib/jenkins/ruoyi-testing-frame/report
```

---

## Phase 6 环境总览（最终可用状态）

```
虚拟机 Ubuntu 22.04 (192.168.119.144)
├── Jenkins         /var/lib/jenkins/jenkins.war  :9090  (java 21)
├── 项目            /var/lib/jenkins/ruoyi-testing-frame/  (jenkins:jenkins)
├── Python 3.12     uv venv (.venv)
├── Allure          /opt/allure-2.32.0/
└── 防火墙          22/tcp, 9090/tcp, 8088/tcp

Jenkins Pipeline Job（Script 模式，手动粘贴 Jenkinsfile）
  Stage 1. 登录测试       → 15 条
  Stage 2. 用户管理       → 24 条
  Stage 3. 角色权限       → 42 条
  Stage 4. 文件与业务流    →  2 条
  总计                    83 条

Allure 报告          手动生成 + python3 -m http.server 8088
```
