"""run.py —— 全量测试 + Allure 报告"""

import configparser
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

# JDK 的搜索目录从 conf/config.ini 的 [JAVA] search_dirs 读（多个用 ; 分隔）。
# 不写死在代码里 —— 换一台机器只改配置。
CONFIG_PATH = os.path.join(PROJECT_ROOT, "conf", "config.ini")


def _configured_java_search_dirs():
    """读 conf/config.ini 的 [JAVA] search_dirs，返回目录列表（不存在则空列表）。"""
    cf = configparser.ConfigParser()
    try:
        cf.read(CONFIG_PATH, encoding="utf-8")
        raw = cf.get("JAVA", "search_dirs", fallback="")
    except (configparser.Error, OSError):
        return []
    return [d.strip() for d in raw.split(";") if d.strip()]


def _jdk_major_version(jdk_root):
    """
    取 JDK 的主版本号：**优先读 release 文件（事实），读不到再退回目录名（猜测）**。

    为什么以 release 文件为准：Java 的版本号有两种写法，靠目录名猜会猜错 ——
        21.0.7     → 主版本 21
        17.0.8     → 主版本 17
        1.8.0_151  → 主版本 8    ← 目录常被命名为 "jdk8"，但它其实是 "1.x" 格式
    实测本机 `E:\\Env\\jdk8` 的 release 里就写着 `1.8.0_151`。

    返回 0 表示"认不出这是哪个版本"，调用方据此把它排到最后并跳过，
    **绝不抛异常**（旧实现在目录名不含 `jdk<数字>` 时会 AttributeError 崩掉，
    例如 `jdk-17`、`jdkabc`）。
    """
    release = os.path.join(jdk_root, "release")
    try:
        with open(release, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("JAVA_VERSION"):
                    version = line.split("=", 1)[1].strip().strip('"')
                    matched = re.match(r"1\.(\d+)", version)   # 1.8.0_151 → 8
                    if matched:
                        return int(matched.group(1))
                    matched = re.match(r"(\d+)", version)      # 21.0.7 → 21
                    return int(matched.group(1)) if matched else 0
    except OSError:
        pass   # release 不存在（如 jlink 精简版）或读不了 → 退回目录名

    # 兜底：目录名。`-?` 是为了容忍 jdk-17 这种写法
    matched = re.search(r"jdk-?(\d+)", jdk_root)
    return int(matched.group(1)) if matched else 0


def _java_executable(jdk_root):
    """
    返回该目录下的 java 可执行文件路径；不是 JDK 目录则返回 None。

    Windows 上是 `bin\\java.exe`，其它平台是 `bin/java`。
    """
    for name in ("java.exe", "java"):
        candidate = os.path.join(jdk_root, "bin", name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _looks_like_jdk(path):
    """
    判断一个路径是否**真的是 JDK 根目录**（即里面确实有 java 可执行文件）。

    为什么不能只看"是不是目录"：
        实测踩过两次 ——
          · 某些目录下混着 `jdk8.7z` 这种**压缩包**（不是目录）
          · 还有名字像 JDK、实际是**空壳**的目录（如解压失败残留的 `jdk-17`）
        只看 os.path.isdir 会把空壳也收进候选；它虽然会被后面的 isfile 过滤掉，
        但 `_jdk_major_version()` 会给它解出一个版本号参与排序，
        导致**候选集合是脏的**（测试与实现据此算出的"最高版本"也会不一致）。
    """
    return os.path.isdir(path) and _java_executable(path) is not None


def _find_java():
    """
    自动探测本机 Java，返回 (java_home, bin_dir) 或 (None, None)。

    候选来源（按优先级）：
        ① `JAVA_HOME` 环境变量 —— 最标准、也最该被尊重
        ② `conf/config.ini` 的 `[JAVA] search_dirs` 下每个**真的是 JDK** 的 `jdk*` 目录
        ③ `%ProgramFiles%\\Java\\*`（Windows 常见安装位置）

    只在 JAVA_HOME 未设置、且 PATH 里也没有 java 时才会被调用
    （见 _get_env），探测失败由调用方降级为"直接用 PATH 里的 java"。
    """
    candidates = []

    # ① JAVA_HOME 优先：它已经是"JDK 根目录"，不需要再猜
    java_home_env = os.environ.get("JAVA_HOME", "").strip()
    if _looks_like_jdk(java_home_env):
        candidates.append(java_home_env)

    # ② 配置里声明的搜索目录：扫每个目录下的 jdk*，只收"真的是 JDK"的
    for search_dir in _configured_java_search_dirs():
        if os.path.isdir(search_dir):
            candidates.extend(
                p for p in glob.glob(os.path.join(search_dir, "jdk*"))
                if _looks_like_jdk(p)
            )

    # ③ Windows 常见安装位置
    prog_java = os.path.join(
        os.environ.get("ProgramFiles", "C:\\Program Files"), "Java"
    )
    if os.path.isdir(prog_java):
        candidates.extend(
            os.path.join(prog_java, d) for d in os.listdir(prog_java)
            if _looks_like_jdk(os.path.join(prog_java, d))
        )

    def sort_key(path):
        # 版本降序；同版本时按路径排序，保证结果稳定可复现
        return (-_jdk_major_version(path), path)

    for jdk_root in sorted(candidates, key=sort_key):
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


def _run(cmd, desc, required=True):
    """
    执行一条命令，返回 returncode。

    required=True （默认）：失败即中断 —— 用于"没成功后面就没意义"的步骤。
    required=False        ：失败只记警告、继续往下走 —— 用于跑测试那一步。

    为什么测试那一步不能中断：
        有用例失败时 pytest 依然会把**已完成用例的结果**写进 alluredir。
        如果直接 SystemExit，后面的 allure generate / open 都不会执行，
        结果是"什么都不给你看"——比"报告里 70 绿 3 红"糟糕得多。
        所以把失败码先留着，等报告生成、打开之后再作为退出码抛出去。
    """
    print(f"\n>>> {desc}")
    result = subprocess.run(
        cmd, cwd=PROJECT_ROOT, shell=True, env=_get_env(),
    )
    if result.returncode != 0:
        if required:
            print(f"FAIL: {desc} (exit={result.returncode})")
            raise SystemExit(result.returncode)
        print(f"WARN: {desc} 未全部通过 (exit={result.returncode}) —— 继续生成报告")
    return result.returncode


if __name__ == "__main__":
    print("=" * 50)
    print("若依测试框架 · 全量回归 + Allure 报告")
    print("=" * 50)

    # 1. 运行全量测试，收集 Allure 数据
    #    required=False：即使有用例失败（甚至后端中途抖动导致部分报错），
    #    也继续往下生成报告，最后再用这个返回码退出。
    test_code = _run(
        f'{PYTHON} -m pytest -q '
        f'--alluredir="{REPORT_TEMP}" --clean-alluredir',
        "1/3  运行全量测试",
        required=False,
    )
    if test_code != 0:
        print(f"     [!] 本次未全部通过（exit={test_code}），"
              f"仍继续生成报告，最后以该返回码退出")

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

    # 5. 报告已经给到人看了，这时候再把测试的失败码抛出去
    if test_code != 0:
        print(f"\n>>> 全量测试未全部通过 (exit={test_code})")
        raise SystemExit(test_code)
    print("\n>>> 全量测试全部通过，报告已生成")