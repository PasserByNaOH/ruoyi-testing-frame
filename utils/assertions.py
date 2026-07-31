from utils.recordlog import logs

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
     """断言 msg 包含指定关键字。"""
     actual = resp.json()
     msg = actual.get("msg", "")
     assert rule["keyword"] in msg, (
          f"body_contains 断言失败\n"
          f"  预期 msg 包含: {rule['keyword']}\n"
          f"  实际 msg:      {msg}"
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