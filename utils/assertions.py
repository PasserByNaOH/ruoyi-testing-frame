from utils.recordlog import logs

# ═══════════════════════════════════════════════════════════
# HTTP 断言
# ═══════════════════════════════════════════════════════════

def assert_status_code(resp, rule):
     """断言 HTTP 状态码。"""
     assert resp.status_code == rule["expected"], (
          f"HTTP 状态码断言失败\n"
          f"  预期: {rule['expected']}\n"
          f"  实际: {resp.status_code}"
     )

def assert_body_code(resp, rule):
     """断言若依业务状态码（body.code）。"""
     actual = resp.json()
     assert actual.get("code") == rule["expected"], (
          f"body_code 断言失败\n"
          f"  预期 code: {rule['expected']}\n"
          f"  实际响应:   {actual}"
     )


def assert_body_contains(resp, rule):
     """断言响应体包含指定关键字（查整个 JSON 字符串）。"""
     body_text = resp.text
     assert rule["keyword"] in body_text, (
          f"body_contains 断言失败\n"
          f"  预期响应包含: {rule['keyword']}\n"
          f"  实际响应:     {body_text}"
     )


def assert_body_not_contains(resp, rule):
     """断言响应体不包含指定关键字（查整个 JSON 字符串）。"""
     body_text = resp.text
     assert rule["keyword"] not in body_text, (
          f"body_not_contains 断言失败\n"
          f"  预期响应不包含: {rule['keyword']}\n"
          f"  实际响应:       {body_text}"
     )


def assert_token_not_empty(resp, rule):
     """断言响应中包含非空 token。"""
     token = resp.json().get("token", "")
     assert token != "", "登录成功但未返回 token"


def assert_token_absent(resp, rule):
     """断言响应中不包含 token（失败登录场景）。"""
     assert "token" not in resp.json(), (
          f"失败登录不应返回 token，实际返回: {resp.json().get('token')}"
     )

#   验证导出的二进制文件内容是否和数据库的数据相同
def assert_excel_content(resp, rule):
     pass

# type 字符串 → 断言函数的映射表
VALIDATORS = {
     "status_code":     assert_status_code,
     "body_code":       assert_body_code,
     "body_contains":   assert_body_contains,
     "body_not_contains": assert_body_not_contains,
     "token_not_empty": assert_token_not_empty,
     "token_absent":    assert_token_absent,
     "excel_content":    assert_excel_content,
}

def run_validations(resp, validations):
     """
     遍历验证规则列表，逐个执行断言。
     加新断言类型：写一个 assert_xxx 函数 → 在 VALIDATORS 里加一行即可。
     """
     for rule in validations:
          validate_type = rule["type"]
          validate_func = VALIDATORS.get(validate_type)
          if validate_func is None:
               raise ValueError(f"不支持的断言类型: {validate_type}")
          validate_func(resp, rule)
          logs.info(f"断言通过: {validate_type}")


# ═══════════════════════════════════════════════════════════
# DB 验证
# ═══════════════════════════════════════════════════════════

def coerce_db_param(value):
    """将 replace_load 反序列化后的字符串还原为适合 SQL 参数的类型。

    问题背景：YAML 中的 `${get_runtime(created_user_id)}` 经过 replace_load 后，
    数字 191 变成了字符串 "191"（因为 str(result) 拼接）。
    MySQL 的 WHERE user_id = '191' 字符串与 bigint 列可能不匹配，
    需要转回 int。
    """
    if not isinstance(value, str):
        return value
    # int：纯数字或负号开头
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    # bool
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def run_db_verify(db, rules):
    """遍历 db_verify 规则列表，对 MySQL 做声明式断言。

    db 是 ConnectMysql 实例（autocommit=True，每次 query 都是最新快照）。

    支持 4 种 expect 类型：
      exists     — SELECT COUNT(*) >= 1
      count      — SELECT COUNT(*) == value
      eq         — SELECT column == value
      not_empty  — SELECT column IS NOT NULL AND != ''
    """
    for rule in rules:
        expect = rule["expect"]
        table = rule["table"]
        where = rule["where"]

        pairs = [f"{k} = %s" for k in where]
        clause = " AND ".join(pairs)
        params = [coerce_db_param(v) for v in where.values()]

        if expect == "exists":
            sql = f"SELECT COUNT(*) FROM {table} WHERE {clause}"
            actual = db.query(sql, params)[0]["COUNT(*)"]
            assert actual >= 1, (
                f"DB验证失败 [{rule['desc']}]\n"
                f"  SQL: {sql}\n  params: {params}\n"
                f"  COUNT(*): {actual} (预期 >=1)"
            )

        elif expect == "count":
            sql = f"SELECT COUNT(*) FROM {table} WHERE {clause}"
            actual = db.query(sql, params)[0]["COUNT(*)"]
            assert actual == rule["value"], (
                f"DB验证失败 [{rule['desc']}]\n"
                f"  SQL: {sql}\n  params: {params}\n"
                f"  COUNT(*): {actual} (预期 {rule['value']})"
            )

        elif expect == "eq":
            sql = f"SELECT {rule['column']} FROM {table} WHERE {clause}"
            rows = db.query(sql, params)
            assert rows, (
                f"DB验证失败 [{rule['desc']}]\n"
                f"  SQL: {sql}\n  params: {params}\n"
                f"  查询结果: 0 行，用户可能不存在"
            )
            actual = rows[0][rule["column"]]
            assert str(actual) == str(rule["value"]), (
                f"DB验证失败 [{rule['desc']}]\n"
                f"  SQL: {sql}\n  params: {params}\n"
                f"  实际: {actual!r}\n  预期: {rule['value']!r}"
            )

        elif expect == "not_empty":
            sql = f"SELECT {rule['column']} FROM {table} WHERE {clause}"
            rows = db.query(sql, params)
            assert rows, (
                f"DB验证失败 [{rule['desc']}]\n"
                f"  SQL: {sql}\n  params: {params}\n"
                f"  查询结果: 0 行，用户可能不存在"
            )
            actual = rows[0][rule["column"]]
            assert actual not in (None, ""), (
                f"DB验证失败 [{rule['desc']}]\n"
                f"  SQL: {sql}\n  params: {params}\n"
                f"  实际: {actual!r}（预期非空）"
            )

        else:
            raise ValueError(f"不支持的 DB 验证类型: {expect}")

        logs.info(f"DB验证通过: {rule['desc']}")


# ═══════════════════════════════════════════════════════════
# 自测入口：用假响应验证所有断言类型
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    class MockResponse:
        """模拟 requests.Response 对象。"""
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data

        def json(self):
            return self._json

    # 模拟登录成功响应
    success_resp = MockResponse(200, {
        "code": 200,
        "msg": "操作成功",
        "token": "eyJhbGciOi..."
    })

    # 模拟登录失败响应
    fail_resp = MockResponse(200, {
        "code": 500,
        "msg": "验证码错误"
    })

    print("--- 测试 1: status_code 断言（成功） ---")
    run_validations(success_resp, [{"type": "status_code", "expected": 200}])

    print("--- 测试 2: body_code 断言（成功 + 失败） ---")
    run_validations(success_resp, [{"type": "body_code", "expected": 200}])

    try:
        run_validations(fail_resp, [{"type": "body_code", "expected": 200}])
        print("  预期应失败但通过了！")
    except AssertionError as e:
        print(f"  正确捕获到失败: body_code 500 != 200")

    print("--- 测试 3: body_contains 断言 ---")
    run_validations(success_resp, [{"type": "body_contains", "keyword": "操作成功"}])

    print("--- 测试 4: token_not_empty 断言 ---")
    run_validations(success_resp, [{"type": "token_not_empty"}])

    print("--- 测试 5: token_absent 断言 ---")
    run_validations(fail_resp, [{"type": "token_absent"}])

    print("--- 测试 6: 不支持的 type 应报错 ---")
    try:
        run_validations(success_resp, [{"type": "unknown_type"}])
    except ValueError as e:
        print(f"  正确捕获: {e}")

    print("\n所有断言类型验证完毕！")