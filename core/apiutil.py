import json
import re
import configparser
from json.decoder import JSONDecodeError

import allure
import jsonpath
import requests

from conf.setting import FILE_PATH, TOKEN_PREFIX
from utils.assertions import run_validations
from utils.debugtalk import DebugTalk
from utils.readyaml import get_runtime, write_runtime, clear_runtime
from utils.recordlog import logs
from utils.sendrequest import SendRequest


def login_for_yaml(base_url, username, redis_client, password="123456"):
    """
    登录指定用户，返回 token。每次调用都是新登录，不缓存。
    供 specification_yaml 的 auth_user 字段使用。
    """
    # 1. 获取验证码
    captcha_resp = requests.get(
        f"{base_url}/captchaImage",
        headers={"Accept": "application/json"},
        timeout=10,
    ).json()
    uuid = captcha_resp["uuid"]

    # 2. Redis 取验证码答案
    code = DebugTalk().get_captcha_code(uuid)
    assert code is not None, f"[{username}] 验证码已过期，uuid={uuid}"

    # 3. 登录
    login_resp = requests.post(
        f"{base_url}/login",
        json={
            "username": username,
            "password": password,
            "uuid": uuid,
            "code": code,
        },
        headers={"Content-Type": "application/json;charset=UTF-8"},
        timeout=10,
    )
    token = login_resp.json().get("token", "")
    assert token, (
        f"[{username}] 登录失败，未返回 token\n"
        f"  响应: {login_resp.text}"
    )
    return token


class ApiEngine:
    """编排引擎：调用链入口，串联变量替换 → HTTP 请求 → 数据提取 → 断言。"""

    def __init__(self):
        self.send = SendRequest()
        cf = configparser.ConfigParser()
        cf.read(FILE_PATH["CONFIG"], encoding="utf-8")
        self.host = cf.get("api_envi", "host")

    # ═══════════════════════════════════════════════════════════
    # ${} 变量替换
    # replace_load 只管"把 YAML 里的 ${xxx} 替换成活的值"
    # ═══════════════════════════════════════════════════════════

    def replace_load(self, data):
        """
        扫描 ${func(args)} 模式，从内到外逐层替换（支持嵌套）。
        支持字符串和字典（先转 JSON 字符串处理再还原）。
        """
        str_data = data
        if not isinstance(data, str):
            str_data = json.dumps(data, ensure_ascii=False)

        while "${" in str_data:
            start = str_data.rfind("${")              # 最内层的 ${
            end = str_data.index("}", start)          # 它对应的 }
            ref_all = str_data[start:end + 1]         # 整段 ${...}

            func_name = ref_all[2:ref_all.index("(")]
            func_params = ref_all[ref_all.index("(") + 1:ref_all.index(")")]

            result = getattr(DebugTalk(), func_name)(
                *func_params.split(",") if func_params else ""
            )

            if result and isinstance(result, list):
                result = ",".join(str(e) for e in result)
            str_data = str_data.replace(ref_all, str(result))

        # 还原数据类型
        if data and isinstance(data, (dict, list)):
            return json.loads(str_data)
        return str_data

    # ═══════════════════════════════════════════════════════════
    # 引擎主循环
    # ═══════════════════════════════════════════════════════════

    def specification_yaml(self, base_info, test_case, db=None):
        """
        执行一条 YAML 用例：
        拼 URL → 替换变量 → 调 sendrequest → 提取数据 → 断言。

        db:  ConnectMysql 实例，传给 rows_in_scope 等断言
        """
        # 1. 基本信息（用例可选覆盖 url / method / headers）
        case_url = test_case.pop("url", None)
        url = self.host + (case_url or base_info["url"])
        method = test_case.pop("method", None) or base_info["method"]
        case_headers = test_case.pop("headers", None)
        headers = self.replace_load(case_headers if case_headers else base_info["headers"])
        headers = self.inject_token(headers)
        case_name = test_case.pop("case_name")
        allure.dynamic.title(case_name)
        logs.info(f"用例: {case_name}")

        # 2. 拼请求体（data / json / params 三选一）
        request_body = {}
        for key in ("data", "json", "params"):
            if key in test_case:
                request_body[key] = self.replace_load(test_case.pop(key))

        # 3. 文件上传
        files = test_case.pop("files", None)

        # 4. 提取规则（可选）
        extract_rules = test_case.pop("extract", None)

        # 5. 断言规则
        validations = self.replace_load(test_case.pop("validations"))

        # ── Allure: 附着请求信息 ──
        rel_url = case_url or base_info.get("url", "")
        with allure.step(f"{method.upper()} {rel_url}"):
            allure.attach(
                json.dumps({
                    "url": url,
                    "method": method.upper(),
                }, ensure_ascii=False, indent=2),
                "请求摘要",
                allure.attachment_type.JSON,
            )
            for k, v in request_body.items():
                allure.attach(
                    json.dumps(v, ensure_ascii=False, indent=2),
                    f"请求体({k})",
                    allure.attachment_type.JSON,
                )
            if files:
                allure.attach(
                    json.dumps({k: v[0] for k, v in files.items()},
                               ensure_ascii=False),
                    "上传文件",
                    allure.attachment_type.JSON,
                )

        # 6. 发请求
        resp = self.send.run_main(
            method=method, url=url, headers=headers,
            files=files, **request_body
        )

        # ── Allure: 附着响应 ──
        content_type = resp.headers.get("Content-Type", "")

        if "json" in content_type:
            try:
                resp_body = resp.json()
                allure.attach(
                    json.dumps(resp_body, ensure_ascii=False, indent=2),
                    f"响应 (HTTP {resp.status_code})",
                    allure.attachment_type.JSON,
                )
                # 提取数据
                if extract_rules:
                    self.extract_data(extract_rules, resp.text)
                # 执行断言
                run_validations(resp, validations, db=db)
            except JSONDecodeError:
                logs.error("响应 JSON 解析失败")
                raise

        elif "octet-stream" in content_type:
            allure.attach(
                f"HTTP {resp.status_code}\nContent-Type: {content_type}\n"
                f"文件大小: {len(resp.content)} bytes",
                "响应 (二进制)",
                allure.attachment_type.TEXT,
            )

        else:
            allure.attach(
                resp.text,
                f"响应 (HTTP {resp.status_code})",
                allure.attachment_type.TEXT,
            )
            run_validations(resp, validations, db=db)

        return resp

    # ═══════════════════════════════════════════════════════════
    # 数据提取
    # ═══════════════════════════════════════════════════════════

    def extract_data(self, extract_rules, response_text):
        """
        从响应中提取变量，写入 runtime.yaml。
        支持 jsonpath（用 $ 开头）和正则（用 ( 开头）。
        """
        for key, expression in extract_rules.items():
            try:
                if expression.startswith("$"):
                    # jsonpath 提取：$.data.token
                    result_list = jsonpath.jsonpath(
                        json.loads(response_text), expression
                    )
                    if result_list:
                        write_runtime({key: result_list[0]})
                        logs.info(f"提取变量: {key} = {result_list[0]}")
                    else:
                        logs.warning(f"jsonpath 未匹配: {expression}")

                elif "(" in expression:
                    # 正则提取：(.*?)
                    match = re.search(expression, response_text)
                    if match:
                        write_runtime({key: match.group(1)})
                        logs.info(f"提取变量: {key} = {match.group(1)}")
                    else:
                        logs.warning(f"正则未匹配: {expression}")

                else:
                    logs.error(f"无法识别的提取表达式: {key}={expression}")

            except Exception as e:
                logs.error(f"提取变量失败 [{key}]: {e}")

    # ═══════════════════════════════════════════════════════════
    # 二进制导出（Excel 等）
    # ═══════════════════════════════════════════════════════════

    def specification_export(self, base_info, test_case, db=None):
        """
        执行二进制导出用例（Excel 下载等）：
        拼 URL + 查询参数 → 发请求 → 拿二进制 content → 断言。

        不处理 json/data/extract/files，只处理 params 和二进制响应。
        """
        # 1. 拼 URL / method / headers
        case_url = test_case.pop("url", None)
        url = self.host + (case_url or base_info["url"])
        method = test_case.pop("method", None) or base_info["method"]
        case_headers = test_case.pop("headers", None)
        headers = self.replace_load(case_headers if case_headers else base_info["headers"])
        headers = self.inject_token(headers)
        case_name = test_case.pop("case_name")
        allure.dynamic.title(case_name)
        logs.info(f"用例: {case_name}")

        # 2. 查询参数（导出过滤条件）
        params = None
        if "params" in test_case:
            params = self.replace_load(test_case.pop("params"))

        # 3. 断言规则
        validations = self.replace_load(test_case.pop("validations"))

        # ── Allure: 附着请求信息 ──
        rel_url = case_url or base_info.get("url", "")
        with allure.step(f"{method.upper()} {rel_url}"):
            allure.attach(
                json.dumps({"url": url, "method": method.upper()},
                           ensure_ascii=False, indent=2),
                "请求摘要",
                allure.attachment_type.JSON,
            )
            if params:
                allure.attach(
                    json.dumps(params, ensure_ascii=False, indent=2),
                    "请求参数(params)",
                    allure.attachment_type.JSON,
                )

        # 4. 发请求
        resp = self.send.run_main(
            method=method, url=url, headers=headers, params=params,
        )

        # ── Allure: 附着二进制响应 ──
        content_type = resp.headers.get("Content-Type", "")
        if "spreadsheet" in content_type or "octet-stream" in content_type:
            allure.attach(
                f"HTTP {resp.status_code}\nContent-Type: {content_type}\n"
                f"文件大小: {len(resp.content)} bytes",
                "响应 (二进制)",
                allure.attachment_type.TEXT,
            )
            run_validations(resp, validations, db=db)
        else:
            logs.warning(f"预期二进制响应，实际 Content-Type: {content_type}")

        return resp

    # ═══════════════════════════════════════════════════════════
    # 占位符
    # ═══════════════════════════════════════════════════════════

    def extract_data_list(self, extract_rules, response_text):
        """PHASE 2: 批量提取多个值，以列表形式存入 runtime.yaml。"""
        raise NotImplementedError("extract_data_list 将在 Phase 2 实现")

    def inject_token(self, headers):
        """
        自动从 runtime.yaml 读取 token，注入 Authorization header。
        如果 headers 中已有 Authorization，则跳过（用户已显式指定）。
        """
        if "Authorization" in headers or "authorization" in headers:
            return headers

        token = get_runtime("token")
        if token:
            headers["Authorization"] = TOKEN_PREFIX + token
            logs.info("已自动注入 Authorization header")
        return headers

    def handle_file_upload(self, files):
        """PHASE 4: 文件上传预处理。"""
        raise NotImplementedError("handle_file_upload 将在 Phase 4 实现")

    def attach_allure(self, name, content):
        """PHASE 5: Allure 报告附件。"""
        raise NotImplementedError("attach_allure 将在 Phase 5 实现")


# ═══════════════════════════════════════════════════════════
# 自测入口
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    engine = ApiEngine()

    # ── 测试 1: replace_load ──
    print("--- 测试 1: replace_load 变量替换 ---")

    result = engine.replace_load("time_${timestamp()}")
    print(f"时间戳替换: {result[:20]}... (长度: {len(result)})")

    result = engine.replace_load("user_${random_str(6)}")
    print(f"随机串替换: {result}")

    # 字典带入
    data = {"username": "user_${random_str(4)}", "timestamp": "${timestamp()}"}
    result = engine.replace_load(data)
    print(f"字典替换: {result}")

    # 嵌套
    write_runtime({"greeting": "hello"})
    result = engine.replace_load("${get_runtime(greeting)}_world")
    print(f"get_runtime 替换: {result}")
    clear_runtime()

    # ── 测试 2: extract_data ──
    print("\n--- 测试 2: extract_data 数据提取 ---")

    login_response = '{"code": 200, "msg": "操作成功", "token": "fake_token_123"}'
    extract_rules = {"token": "$.token", "code": "$.code"}
    engine.extract_data(extract_rules, login_response)

    print(f"runtime 中的 token: {get_runtime('token')}")
    print(f"runtime 中的 code: {get_runtime('code')}")
    clear_runtime()

    # ── 测试 3: specification_yaml（仅 JSON 用例） ──
    print("\n--- 测试 3: specification_yaml（打 captchaImage） ---")
    base_info = {
        "api_name": "captcha",
        "url": "/captchaImage",
        "method": "get",
        "headers": {"Accept": "application/json"}
    }
    test_case = {
        "case_name": "获取验证码",
        "validations": [
            {"type": "status_code", "expected": 200},
            {"type": "body_code", "expected": 200}
        ]
    }

    try:
        resp = engine.specification_yaml(base_info, dict(test_case))
        print(f"captchaImage 响应: code={resp.json().get('code')}, uuid={resp.json().get('uuid')}")
        print("apiutil 引擎验证通过！")
    except Exception as e:
        print(f"执行失败: {e}")
