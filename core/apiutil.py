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


class PlaceholderError(Exception):
    """${} 占位符的解析错误：语法不合法、函数不存在、替换结果不是合法 JSON。"""


# 变量替换的最大轮数，防止"替换结果里又含占位符"导致死循环
_MAX_REPLACE_ROUNDS = 1000


def _find_innermost_placeholder(text):
    """
    从 text 里找出「当前最内层」的一个 ${func(args)}。

    返回 (start, end, func_name, func_params)：
        start / end  — 占位符在 text 中的起止下标（含 ${ 和 }）
        func_name    — 函数名，已 strip
        func_params  — 参数列表（list[str]，已 strip）

    找不到可解析的占位符返回 None；${ 没有配对的 } 抛 PlaceholderError。

    为什么不用"花括号深度配对 + 字符串字面量跟踪"：
        入参非 str 时是 json.dumps 出来的文本，JSON 自身的 {} 和转义引号 \\"
        会污染深度与引号状态，那种算法会误判（实测 5 种真实用例全部报错）。
        这里改用更笨但正确的办法 —— 对每个 ${ 向后找「第一个使括号归零的 }」：
        占位符自身的 {} 总是平衡的，所以第一个归零处一定是它的结尾；
        内层还有 ${ 时深度不会归零，扫描自然会把整个嵌套区间包进来。
    """
    at = text.find("${")
    while at != -1:
        # ① 向后扫描，找这个 ${ 的配对 }
        depth = 0
        close = -1
        for i in range(at + 1, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    close = i
                    break
        if close == -1:
            raise PlaceholderError(
                f"占位符缺少配对的 '}}'：{text[at:at + 120]!r}"
            )

        # ② 在区间内解析 func(args)
        body = text[at + 2:close]
        if "(" in body:
            paren = body.index("(")
            func_name = body[:paren].strip()
            rest = body[paren:]

            # 找配对的 )，必须正好落在区间末尾
            depth = 0
            arg_end = -1
            for i, ch in enumerate(rest):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        arg_end = i
                        break

            if (arg_end != -1
                    and rest[arg_end + 1:].strip() == ""
                    and "${" not in body):
                # 参数段内不再含 ${ → 这就是最内层
                return (at, close, func_name, _split_func_params(rest[1:arg_end]))

        # ③ 区间内还有更内层的 ${ → 跳到下一个继续找
        nxt = text.find("${", at + 2)
        if nxt == -1 or nxt > close:
            raise PlaceholderError(
                f"占位符格式应为 ${{函数名(参数)}}，实际是："
                f"{text[at:close + 1]!r}"
            )
        at = nxt

    return None


def _split_func_params(raw):
    """
    按「顶层逗号」切分参数，返回 list[str]（每段已 strip）。

    只有深度为 0 的逗号才是参数分隔符；() [] {} 内部的逗号、以及引号内的
    逗号都不切。空参数段 → 返回 []，这样 ${func()} 就是真正的零参数调用
    （旧实现会传一个空字符串进去，靠函数默认值侥幸没炸）。
    """
    raw = _unescape_json_text(raw)
    if raw.strip() == "":
        return []

    params = []
    current = []
    depth = 0
    in_quote = False
    escaped = False

    for ch in raw:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\":
            current.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_quote = not in_quote
            current.append(ch)
            continue
        if not in_quote:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == "," and depth == 0:
                params.append("".join(current).strip())
                current = []
                continue
        current.append(ch)

    params.append("".join(current).strip())
    return [_unescape_json_text(p) for p in params]


def _unescape_json_text(text):
    r"""把 json.dumps 产生的转义还原：\" → "，\\ → \。"""
    return text.replace('\\"', '"').replace("\\\\", "\\")


def _escape_json_text(text):
    r"""把值转义成能安全嵌进 JSON 字符串的文本：\ → \\，`"` → \"。"""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _stringify_for_splice(value):
    """
    把一个替换结果转成可嵌入 JSON 文本的字符串。

    文本拼接语义（"/user/${a()}" → "/user/501"）要求字符串不加引号，
    所以这里用「转义」而不是 json.dumps —— 与改造前的行为保持一致。
    """
    if isinstance(value, str):
        return _escape_json_text(value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    # list / dict 等其余类型：整体序列化成 JSON
    return _escape_json_text(json.dumps(value, ensure_ascii=False))


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
        把 YAML 里的 ${func(args)} 替换成活的值。

        算法：每次取「当前最内层」的一个占位符就地展开，直到没有为止。
        - 多占位符：字符串里有多少个就展开多少个（如 /user/${a()},${b()}）
        - 嵌套：靠"参数段内还含 ${ 就跳过、去看下一个 ${ "实现内层优先
        - 整串恰为一个占位符：直接返回原始类型（int / list / None 原样透传）
        - 其余情况：按字符串拼接语义替换，结果仍是字符串

        注意：入参非 str 时会被 json.dumps 转义，所以取的参数要先反转义、
        回填的值要先转义，否则含 " 或 \\ 的内容会把 JSON 拼坏。
        """
        str_data = data
        if not isinstance(data, str):
            str_data = json.dumps(data, ensure_ascii=False)

        result = None
        for _ in range(_MAX_REPLACE_ROUNDS):
            if "${" not in str_data:
                break

            found = _find_innermost_placeholder(str_data)
            if found is None:
                raise PlaceholderError(
                    f"占位符缺少配对的 '}}'：{str_data[:120]!r}"
                )

            start, end, func_name, func_params = found
            func = getattr(DebugTalk(), func_name, None)
            if func is None:
                raise PlaceholderError(
                    f"DebugTalk 里没有这个方法：{func_name}()\n"
                    f"  占位符: {str_data[start:end + 1]}"
                )

            result = func(*func_params)

            # 整串恰为这一个占位符 → 保留原始类型，不做字符串化
            if start == 0 and str_data[end + 1:].strip() == "":
                return result

            str_data = (
                str_data[:start]
                + _stringify_for_splice(result)
                + str_data[end + 1:]
            )
        else:
            raise PlaceholderError(
                f"变量替换超过 {_MAX_REPLACE_ROUNDS} 轮，疑似替换结果自引用："
                f"{str_data[:120]!r}"
            )

        # 还原数据类型（仅 dict / list 入参需要）
        if isinstance(data, (dict, list)):
            try:
                return json.loads(str_data)
            except json.JSONDecodeError as e:
                raise PlaceholderError(
                    f"变量替换后已不是合法 JSON：{e}\n"
                    f"  替换结果: {str_data[:200]!r}"
                ) from e
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

