"""
test_business_flow.py —— 系统管理核心链路业务流程测试

流程：创建角色 → 查角色ID → 创建用户 → 验证 → 删用户 → 删角色
步骤间通过 extract → runtime.yaml → ${get_runtime(key)} 串联数据
"""

import os
import pytest

from core.apiutil import ApiEngine
from utils.readyaml import get_testcase_yaml, FILE_PATH
from utils.recordlog import logs


_cases = get_testcase_yaml(
    os.path.join(FILE_PATH["YAML"], "ruoyi", "system", "business_flow.yaml")
)


@pytest.mark.parametrize(
    "base_info, case",
    _cases,
    ids=[c[1]["case_name"] for c in _cases],
)
def test_business_flow(base_url, db_connection, redis_client, base_info, case):
    engine = ApiEngine()
    steps = case["steps"]

    for step in steps:
        # 构建 spec case：step 中所有字段先过 replace_load 解析 ${} 引用
        spec_case = {
            "case_name": step["case_name"],
            "url": engine.replace_load(step.get("url", "")),
            "method": step.get("method"),
            "validations": step.get("validations", []),
        }

        # 请求体（json / params 二选一）
        if "json" in step:
            spec_case["json"] = engine.replace_load(step["json"])
        if "params" in step:
            spec_case["params"] = engine.replace_load(step["params"])

        # 执行
        resp = engine.specification_yaml(dict(base_info), spec_case)

        # 提取数据到 runtime.yaml 供后续步骤引用
        if "extract" in step:
            engine.extract_data(step["extract"], resp.text)

    logs.info(f"业务流程 [{case['case_name']}] 全部 {len(steps)} 步执行完毕")
