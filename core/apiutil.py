import json
import re
import configparser

import allure
import jsonpath
import requests

from conf.setting import FILE_PATH, TOKEN_PREFIX
from utils.assertions import run_validations, try_parse_json
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
    """${} 占位符的解析错误：语法不合法、函数不存在、参数个数不对。"""


# 单个字符串内变量替换的最大轮数，防止"替换结果里又含占位符"导致死循环
_MAX_REPLACE_ROUNDS = 1000


def _find_innermost_placeholder(text):
    """
    从 text 里找出「当前最内层」的一个 ${func(args)}。

    返回 (start, end, func_name, func_params)：
        start / end  — 占位符在 text 中的起止下标（含 ${ 和 }）
        func_name    — 函数名，已 strip
        func_params  — 参数列表（list[str]，已 strip）

    找不到可解析的占位符返回 None；${ 没有配对的 } 抛 PlaceholderError。

    入参永远是**真实字符串**（结构化替换后不再有 json.dumps 文本），所以
    只需按花括号配平判断结尾，不必跟踪 JSON 转义引号。
    算法：对每个 ${ 向后找「第一个使括号归零的 }」——占位符自身的 {} 总是
    平衡的，所以第一个归零处一定是它的结尾；内层还有 ${ 时深度不会归零，
    扫描自然会把整个嵌套区间包进来。
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
    return params


def _call_debugtalk(func_name, func_params):
    """
    调用 DebugTalk 里以 func_name 命名的零参/多参方法。

    只允许公开方法（不要 dunder，避免 ${__init__()} 之类的意外调用）；
    函数不存在或参数个数不对时，抛出能定位问题的 PlaceholderError。
    """
    if func_name.startswith("__") and func_name.endswith("__"):
        raise PlaceholderError(
            f"不允许调用 DebugTalk 的内部方法：{func_name}()"
        )

    func = getattr(DebugTalk(), func_name, None)
    if func is None or not callable(func):
        raise PlaceholderError(
            f"DebugTalk 里没有这个方法：{func_name}()"
        )

    try:
        return func(*func_params)
    except TypeError as e:
        raise PlaceholderError(
            f"调用 {func_name}({', '.join(func_params)}) 失败：{e}"
        ) from e


def _replace_in_string(text):
    """
    对**一个真实字符串**做 ${} 替换，返回原始类型或拼接后的字符串。

    三种出口：
      - 没有占位符         → 原字符串原样返回（不再 dump→loads 绕一圈）
      - 恰好一个且独占整串 → 返回**原始类型**（int / list / None 原样透传）
      - 占位符只占其中一段 → 逐段拼接成字符串（非 str 结果按 str 语义转换）

    每轮取「当前最内层」的占位符展开，展开后重扫整串 —— 嵌套
    （${f(${g()})}：内层先成文本，外层才成形）依赖这一点。

    已知边界：替换**结果**里若含 ${，会被当作下一个占位符继续展开
    （与改造前一致）。_MAX_REPLACE_ROUNDS 是这类自引用的保险丝。
    """
    if not isinstance(text, str) or "${" not in text:
        return text

    for _ in range(_MAX_REPLACE_ROUNDS):
        found = _find_innermost_placeholder(text)
        if found is None:
            return text

        start, end, func_name, func_params = found
        value = _call_debugtalk(func_name, func_params)

        # 整串恰为这一个占位符 → 直接返回原始类型（类型保真的关键）
        if start == 0 and end == len(text) - 1:
            return value

        text = (
            text[:start]
            + _stringify_for_splice(value)
            + text[end + 1:]
        )

    raise PlaceholderError(
        f"变量替换超过 {_MAX_REPLACE_ROUNDS} 轮，疑似替换结果自引用："
        f"{text[:120]!r}"
    )


def _walk(data):
    """递归走到每个叶子值：容器重建，字符串交给 _replace_in_string。"""
    if isinstance(data, dict):
        return {key: _walk(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_walk(item) for item in data]
    if isinstance(data, str):
        return _replace_in_string(data)
    # int / float / bool / None 等标量：本来就保真，原样返回
    return data


def _stringify_for_splice(value):
    """
    把一个替换结果转成可拼进字符串的文本（占位符**只占字符串一段**时用）。

    这是纯文本拼接语义（"/user/${a()}" → "/user/501"），不是 JSON 序列化：
    现在值直接拼进真实字符串，不再经过 JSON 文本，所以**不做任何转义**。
    """
    if isinstance(value, str):
        return value
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return repr(value)
    # bool 用 Python 写法（True/False），与 str() 一致
    if isinstance(value, bool):
        return str(value)
    # list / dict 等其余类型：整体序列化成 JSON
    return json.dumps(value, ensure_ascii=False)


def _resolve_extract(key, expression, response_text):
    """
    按一条 extract 规则求值，返回提取到的值（不写 runtime、不发请求）。

    纯函数：同样的入参永远得到同样的结果，所以能被单元测试直接覆盖，
    包括 jsonpath / 正则 / null / 未匹配 这些真实服务器上很难稳定复现的分支。

    提取不到"可用的值"时抛 RuntimeError；详细规则见 extract_data 的文档。
    """
    def fail(reason):
        snippet = response_text or ""
        if len(snippet) > 200:
            snippet = snippet[:200] + "..."
        return RuntimeError(
            f"提取变量失败 [{key}]：{reason}\n"
            f"  表达式: {expression}\n"
            f"  响应片段: {snippet}"
        )

    if expression.startswith("$"):
        try:
            document = json.loads(response_text)
        except (TypeError, ValueError) as e:
            raise fail(f"响应不是合法 JSON，无法做 jsonpath 提取（{e}）") from e

        result = jsonpath.jsonpath(document, expression)
        # 该库没有匹配时返回 False（不是空列表），匹配到则返回列表
        if not result:
            raise fail("jsonpath 未匹配")
        value = result[0]
        if value is None:
            raise fail("jsonpath 匹配到了字段，但值是 null")
        return value

    if "(" in expression:
        try:
            match = re.search(expression, response_text or "")
        except re.error as e:
            raise fail(f"正则表达式不合法（{e}）") from e
        if match is None:
            raise fail("正则未匹配")
        return match.group(1)

    raise fail("无法识别的提取表达式（应以 $ 开头走 jsonpath，或含 ( 走正则）")


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

        算法：**递归遍历结构**，只在叶子字符串上做占位符替换。
        - dict → 逐值递归重建；list → 逐元素递归重建
        - 标量（int / float / bool / None）原样返回，类型天然保真
        - 叶子字符串的处理见 _replace_in_string：
            · 恰好一个占位符独占整串 → 返回原始类型
            · 占位符只占一段（含多个占位符）→ 拼接成字符串
            · 没有占位符 → 原样返回

        为什么不再走"json.dumps → 文本替换 → json.loads"：
            值一旦被摊平成 JSON 文本，替换进去的数字就会沾上 JSON 的引号
            变成字符串（例：{"user_id": "${...}"} 里的 701 变成 "701"），
            而且含 " 或 \\ 的值会把 JSON 拼坏、需要转义往返。
            递归到叶子则不存在这些问题：类型不经过文本，也不需任何转义。
        """
        return _walk(data)

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
        # 分成两步，互不牵连：
        #   ① 贴响应到报告（能解析成 JSON 就贴 JSON，否则贴原始文本／二进制摘要）
        #   ② 提取 + 断言 —— **无论响应是什么格式都要执行**
        # 旧实现把这两步捆在一起、且按 Content-Type 分支：解析一失败就被异常
        # 带走，断言一行都没跑（报错变成 JSONDecodeError，真实断言从没运行过）。
        self._attach_response(resp)

        # 提取数据（1.3 起：提取失败会抛错，不再静默）
        if extract_rules:
            self.extract_data(extract_rules, resp.text)

        # 执行断言 —— 无条件执行
        run_validations(resp, validations, db=db)

        return resp

    # ── 响应附着（只负责把响应放进报告，不做任何判断）──

    def _attach_response(self, resp):
        """
        把响应附着到 Allure 报告。

        只做"展示"这一件事，**不参与控制流**：解析不出 JSON 就退化成贴原始
        文本，而不是抛异常——是否合法 JSON 该由断言去判断，不该在这里决定
        后面的检查跑不跑。
        """
        content_type = resp.headers.get("Content-Type", "")
        title = f"响应 (HTTP {resp.status_code})"

        if "octet-stream" in content_type or "spreadsheet" in content_type:
            allure.attach(
                f"HTTP {resp.status_code}\nContent-Type: {content_type}\n"
                f"文件大小: {len(resp.content)} bytes",
                "响应 (二进制)",
                allure.attachment_type.TEXT,
            )
            return

        body = try_parse_json(resp)
        if body is not None:
            allure.attach(
                json.dumps(body, ensure_ascii=False, indent=2),
                title,
                allure.attachment_type.JSON,
            )
        else:
            allure.attach(resp.text, title, allure.attachment_type.TEXT)

    # ═══════════════════════════════════════════════════════════
    # 数据提取
    # ═══════════════════════════════════════════════════════════

    def extract_data(self, extract_rules, response_text):
        """
        从响应中提取变量并写入 runtime.yaml。

        支持两种表达式：
            $ 开头   —— jsonpath，如 $.token、$.rows[0].userId
            含 (     —— 正则，如 r'"token":"(.*?)"'

        **提取失败一律抛异常，不再只打日志。** 理由：runtime.yaml 里的值
        是后续用例的输入（token、实体 ID），拿不到就必须当场停下，否则错误
        会以"一片 401""DB 查不到行"的面目出现在离原因很远的地方。
        这与本项目"前置函数失败即 raise"的风格保持一致。

        失败（抛异常）的情形：
            - jsonpath 未匹配（库返回 False）
            - 匹配到了但值是 null（[None]）
            - 正则未匹配
            - 表达式既不以 $ 开头、也不含 (

        成功的情形：只要值不是 None 就算成功，包括 0 / '' / False / [] /
        {} 这些合法的"空值"。判空必须用 `value is None`，不能写 `if not value`。

        注意：jsonpath 匹配到**多条**时取第一条，这是既有行为，不做改动。
        """
        for key, expression in extract_rules.items():
            value = _resolve_extract(key, expression, response_text)
            write_runtime({key: value})
            logs.info(f"提取变量: {key} = {value!r}")

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

        # ── Allure: 附着响应 ──
        # 与 specification_yaml 同理：附着只负责展示，断言**无条件执行**。
        # 旧实现在"实际不是二进制"时只打一行 warning，一条断言都不跑 ——
        # 而"导出失败返回了错误 JSON/HTML"正是最该让断言出场的时候。
        self._attach_response(resp)

        # 执行断言 —— 无条件执行
        # 二进制导出用例的断言类型是 excel_content，它本来就判二进制，
        # 不会因为响应不是二进制而无从判断（会直接报"不是有效的 xlsx"）。
        run_validations(resp, validations, db=db)

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

