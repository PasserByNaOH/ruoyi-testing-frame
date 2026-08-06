"""run.py —— 全量测试 + Allure 报告"""

import glob
import os
import re
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(__file__)
PYTHON = sys.executable
REPORT_TEMP = os.path.join(PROJECT_ROOT, "report", "temp")
REPORT_OUTPUT = os.path.join(PROJECT_ROOT, "report", "allure")


def _find_java():
    """自动探测本机 Java，返回 (java_home, bin_dir) 或 (None, None)。"""
    # 搜索 E:\Env\jdk*（按数字版号降序，高版本优先）
    jdk_dirs = glob.glob("E:\\Env\\jdk*")
    jdk_dirs.sort(key=lambda p: int(re.search(r"jdk(\d+)", p).group(1)), reverse=True)
    search_roots = jdk_dirs
    prog_java = os.path.join(
        os.environ.get("ProgramFiles", "C:\\Program Files"), "Java"
    )
    if os.path.isdir(prog_java):
        search_roots.extend(
            os.path.join(prog_java, d) for d in os.listdir(prog_java)
        )

    for jdk_root in search_roots:
        java_exe = os.path.join(jdk_root, "bin", "java.exe")
        if os.path.isfile(java_exe):
            return jdk_root, os.path.join(jdk_root, "bin")

    return None, None


def _get_env():
    """构建带 JAVA_HOME 的环境变量。"""
    env = os.environ.copy()

    # 已有 JAVA_HOME → 补 PATH
    if env.get("JAVA_HOME"):
        env["PATH"] = (
            os.path.join(env["JAVA_HOME"], "bin")
            + os.pathsep
            + env.get("PATH", "")
        )
        return env

    # PATH 里已有 java → 直接复用
    for p in env.get("PATH", "").split(os.pathsep):
        if os.path.isfile(os.path.join(p, "java.exe")):
            return env

    # 自动探测
    java_home, java_bin = _find_java()
    if java_home:
        env["JAVA_HOME"] = java_home
        env["PATH"] = java_bin + os.pathsep + env.get("PATH", "")
        print(f"已探测 JAVA_HOME = {java_home}")

    return env


def _run(cmd, desc):
    print(f"\n>>> {desc}")
    result = subprocess.run(
        cmd, cwd=PROJECT_ROOT, shell=True, env=_get_env(),
    )
    if result.returncode != 0:
        print(f"FAIL: {desc} (exit={result.returncode})")
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    print("=" * 50)
    print("若依测试框架 · 全量回归 + Allure 报告")
    print("=" * 50)

    # 1. 运行全量测试，收集 Allure 数据
    _run(
        f'{PYTHON} -m pytest -q '
        f'--alluredir="{REPORT_TEMP}" --clean-alluredir',
        "1/3  运行全量测试",
    )

    # 2. 复制环境信息到 Allure 数据目录
    env_xml = os.path.join(PROJECT_ROOT, "environment.xml")
    if os.path.exists(env_xml):
        shutil.copy(env_xml, REPORT_TEMP)
        print("     environment.xml 已复制")

    # 3. 生成 HTML 报告
    _run(
        f'allure generate "{REPORT_TEMP}" -o "{REPORT_OUTPUT}" --clean',
        "2/3  生成 Allure 报告",
    )

    # 4. 打开报告
    _run(
        f'allure open "{REPORT_OUTPUT}"',
        "3/3  打开报告",
    )