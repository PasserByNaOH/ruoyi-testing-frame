import os
import yaml
import traceback

from conf.setting import FILE_PATH
from utils.recordlog import logs


def get_testcase_yaml(yaml_path):
     """
     读取测试用例 YAML 文件，解析为 pytest parametrize 所需的参数列表。
     格式要求：base_info + test_cases（与 manuTest 的 captcha_login.yaml 一致）
     返回：[(base_info, test_case), ...]
     """
     testcase_list = []
     try:
          with open(yaml_path, "r", encoding="utf-8") as f:
               data = yaml.safe_load(f)

          base_info = data["base_info"]
          test_cases = data["test_cases"]

          for case in test_cases:
               testcase_list.append([base_info, case])

          return testcase_list

     except FileNotFoundError:
          logs.error(f"YAML 文件未找到: {yaml_path}")
          raise
     except KeyError as e:
          logs.error(f"YAML 文件缺少必要字段 {e}，路径: {yaml_path}")
          raise
     except Exception as e:
          logs.error(f"读取 YAML 文件失败 [{yaml_path}]: {traceback.format_exc()}")
          raise


def write_runtime(data):
     """
     写入运行时变量到 runtime.yaml。
     先读旧数据 → 用新值覆盖同 key → 全量写回，保证文件始终干净。
     """
     file_path = FILE_PATH["RUNTIME"]
     os.makedirs(os.path.dirname(file_path), exist_ok=True)

     if not isinstance(data, dict):
          logs.error("写入 runtime.yaml 的数据必须为 dict")
          return

     # 读取旧数据
     old = {}
     if os.path.exists(file_path):
          try:
               with open(file_path, "r", encoding="utf-8") as f:
                    old = yaml.safe_load(f) or {}
          except Exception:
               logs.error(f"读取 runtime.yaml 失败: {traceback.format_exc()}")
               return

     # 合并新值
     old.update(data)

     # 全量写回
     try:
          with open(file_path, "w", encoding="utf-8") as f:
               yaml.dump(old, f, allow_unicode=True, sort_keys=False)
          logs.info(f"写入 runtime.yaml: {data}")
     except Exception:
          logs.error(f"写入 runtime.yaml 失败: {traceback.format_exc()}")



def get_runtime(key):
     """
     从 runtime.yaml 读取单个变量值。
     返回：变量值，不存在则返回 None。
     """
     file_path = FILE_PATH["RUNTIME"]
     if not os.path.exists(file_path):
          logs.warning(f"runtime.yaml 不存在: {file_path}")
          return None

     try:
          with open(file_path, "r", encoding="utf-8") as f:
               data = yaml.safe_load(f) or {}
          return data.get(key, None)
     except Exception:
          logs.error(f"读取 runtime.yaml 失败: {traceback.format_exc()}")
          return None


def clear_runtime():
     """清空 runtime.yaml 所有数据。"""
     file_path = FILE_PATH["RUNTIME"]
     try:
          with open(file_path, "w", encoding="utf-8") as f:
               f.truncate()
          logs.info("runtime.yaml 已清空")
     except Exception:
          logs.error(f"清空 runtime.yaml 失败: {traceback.format_exc()}")


# ═══════════════════════════════════════════════════════════
# 自测入口：验证 YAML 读取是否正常
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
     test_yaml = os.path.join(FILE_PATH["YAML"], "ruoyi", "login", "yamlRead_test.yaml")
     print(f"读取测试文件: {test_yaml}")

     try:
          cases = get_testcase_yaml(test_yaml)
          print(f"共解析到 {len(cases)} 条用例\n")

          for i, (base_info, case) in enumerate(cases, 1):
               print(f"--- 用例 {i}: {case['case_name']} ---")
               print(f"  接口: {base_info['api_name']}")
               print(f"  URL: {base_info.get('captcha_url', base_info.get('login_url', 'N/A'))}")
               print(f"  方法: {base_info['method']}")
               print(f"  data: {case.get('data', {})}")
               print(f"  validations: {len(case.get('validations', []))} 条断言")
               print()
     except Exception as e:
          print(f"测试失败: {e}")