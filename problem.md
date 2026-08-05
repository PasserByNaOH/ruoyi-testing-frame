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
