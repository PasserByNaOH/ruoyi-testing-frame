"""
test_run_java.py —— run.py 里 Java 自动探测的单元测试（不依赖服务器／数据库）

覆盖 run.py 的 _jdk_major_version / _find_java（Phase 1 / 1.7）：

    - 版本号**以 release 文件为准**（Java 8 是 `1.8.0_151` 这种 `1.x` 写法，
      光看目录名会猜错）
    - 目录名解析不出来时**返回 0，绝不抛异常**
      （旧实现在 `jdk-17` / `jdkabc` 上会 AttributeError 崩掉）
    - 混合搜索根（多个 JDK + Program Files）时选版本最高的
    - 非目录条目（实测 E:\\Env 下有 `jdk8.7z`）不参与、不干扰

为什么必须自造目录：本机 JAVA_HOME 已设置，_get_env() 直接返回，
_find_java() **根本不会被调用**，跑全量回归测不到这一项。

不请求任何 fixture，秒级完成：
    pytest test_runner/test_00_engine -q
"""

import glob
import importlib.util
import os
import shutil
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUN_PY = os.path.join(PROJECT_ROOT, "run.py")

# 注意：不用 pytest 的 tmp_path —— 它落在系统临时目录，本机沙箱不允许写入。
# 改用工作区内的临时目录（测试结束后自动清掉）。


@pytest.fixture
def tmp_path():
    """工作区内的临时目录，替代 pytest 内置 tmp_path（内置的落在受限的系统临时目录）。"""
    path = os.path.join(PROJECT_ROOT, "_tmp_jdk_test")
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _load_run_module():
    """按路径加载根目录的 run.py（它不是包，不能直接 import）。"""
    spec = importlib.util.spec_from_file_location("_run_under_test", RUN_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_run_under_test"] = module
    spec.loader.exec_module(module)
    return module


run_module = _load_run_module()


def make_jdk(root, name, release_version=None, with_java=True):
    """造一个假的 JDK 目录；release_version=None 表示不生成 release 文件。"""
    jdk = os.path.join(root, name)
    os.makedirs(os.path.join(jdk, "bin"), exist_ok=True)
    if with_java:
        open(os.path.join(jdk, "bin", "java.exe"), "w").close()
    if release_version is not None:
        with open(os.path.join(jdk, "release"), "w", encoding="utf-8") as f:
            f.write('JAVA_VERSION="%s"\n' % release_version)
            f.write('OS_NAME="Windows"\n')
    return jdk


# ═══════════════════════════════════════════════════════════
# 一、_jdk_major_version：以 release 文件为准
# ═══════════════════════════════════════════════════════════

def test_reads_modern_version_from_release(tmp_path):
    jdk = make_jdk(str(tmp_path), "whatever-name", "21.0.7")
    assert run_module._jdk_major_version(jdk) == 21


def test_reads_java8_style_version_from_release(tmp_path):
    """★ Java 8 写的是 `1.8.0_151`，主版本应是 8 而不是 1。"""
    jdk = make_jdk(str(tmp_path), "jdk8", "1.8.0_151")
    assert run_module._jdk_major_version(jdk) == 8


def test_release_wins_over_misleading_directory_name(tmp_path):
    """目录名叫 jdk17，实际装的是 21 → 必须信 release 文件。"""
    jdk = make_jdk(str(tmp_path), "jdk17", "21.0.7")
    assert run_module._jdk_major_version(jdk) == 21


# ═══════════════════════════════════════════════════════════
# 二、绝不抛异常（旧实现的崩溃点）
# ═══════════════════════════════════════════════════════════

@pytest.mark.parametrize("name", [
    "jdkabc",      # ★ 旧实现：re.search(r"jdk(\d+)") → None → AttributeError
    "jdk",         # 连数字都没有
    "jdk.bak17",   # 中间夹了字符，数字不紧跟 jdk
])
def test_no_release_and_unparsable_name_returns_zero(tmp_path, name):
    """解析不出来就返回 0 —— 排到最后跳过，绝不崩。"""
    jdk = os.path.join(str(tmp_path), name)
    os.makedirs(os.path.join(jdk, "bin"), exist_ok=True)
    assert run_module._jdk_major_version(jdk) == 0


def test_hyphenated_name_is_parsed(tmp_path):
    """★ 旧实现在 `jdk-17` 上会崩；新正则 `jdk-?(\\d+)` 刻意容忍这种写法。"""
    jdk = os.path.join(str(tmp_path), "jdk-17")
    os.makedirs(os.path.join(jdk, "bin"), exist_ok=True)
    assert run_module._jdk_major_version(jdk) == 17


def test_prefix_before_jdk_still_matches(tmp_path):
    """
    记录一处**新旧共有的宽松行为**：正则没有前置边界，
    所以 `notjdk21` / `myjdk17` 也会被解析成 21 / 17。

    不是本次引入的问题（旧实现同样如此），留此用例把行为固定下来，
    以免以后误以为是回归。
    """
    jdk = os.path.join(str(tmp_path), "notjdk21")
    os.makedirs(os.path.join(jdk, "bin"), exist_ok=True)
    assert run_module._jdk_major_version(jdk) == 21


# ═══════════════════════════════════════════════════════════
# 四、对着真实本机环境验证（不造数据）
# ═══════════════════════════════════════════════════════════

def test_real_env_jdk_dirs_all_parse():
    """本机 E:\\Env 下每个真实 JDK 目录都应能解析出版本号（非 0）。"""
    real = [p for p in glob.glob("E:\\Env\\jdk*") if os.path.isdir(p)]
    if not real:
        pytest.skip("本机 E:\\Env 下没有 jdk* 目录")
    for path in real:
        version = run_module._jdk_major_version(path)
        assert version > 0, f"{path} 解析出版本号 {version}"


def test_real_find_java_picks_highest_version():
    """
    真的调用 _find_java()：本机装了 jdk8/jdk17/jdk21，
    应选中版本最高的 jdk21（且它确实有 bin/java.exe）。
    """
    java_home, java_bin = run_module._find_java()
    if java_home is None:
        pytest.skip("本机未探测到 JDK")
    assert os.path.isfile(os.path.join(java_bin, "java.exe"))
    assert run_module._jdk_major_version(java_home) == max(
        run_module._jdk_major_version(p)
        for p in glob.glob("E:\\Env\\jdk*")
        if os.path.isdir(p)
    ), f"探测到的是 {java_home}，但它不是候选里版本最高的"


def test_real_find_java_does_not_crash_on_archive_file():
    """
    ★ 本机 E:\\Env 下确实存在 `jdk8.7z`（压缩包，不是目录）。
    _find_java 必须不受它影响、也不崩。
    """
    archives = [p for p in glob.glob("E:\\Env\\jdk*") if not os.path.isdir(p)]
    java_home, _ = run_module._find_java()   # 不抛异常即通过
    if archives:
        assert java_home is not None


def test_missing_release_falls_back_to_directory_name(tmp_path):
    """jlink 精简版可能没有 release 文件 → 退回目录名解析。"""
    jdk = make_jdk(str(tmp_path), "jdk-17", release_version=None)
    assert run_module._jdk_major_version(jdk) == 17


def test_unreadable_release_does_not_raise(tmp_path):
    """release 是个目录（异常情况）时也不能抛。"""
    jdk = make_jdk(str(tmp_path), "jdk21", release_version=None)
    os.makedirs(os.path.join(jdk, "release"), exist_ok=True)
    assert run_module._jdk_major_version(jdk) == 21


# ═══════════════════════════════════════════════════════════
# 三、遍历候选：目录名解析不出也不能挡住排序
# ═══════════════════════════════════════════════════════════

def test_sort_survives_mixed_names(tmp_path):
    """
    ★ 复现旧实现的崩溃场景：候选里混着 `jdkabc` / `jdk-17` 这类名字，
    且没有 release 文件可读。新实现必须能正常排序，而不是 AttributeError。
    """
    names = ["jdkabc", "jdk-17", "jdk17", "jdk21"]
    for name in names:
        make_jdk(str(tmp_path), name, release_version=None)

    candidates = [os.path.join(str(tmp_path), n) for n in names]
    ordered = sorted(
        candidates,
        key=lambda p: (-run_module._jdk_major_version(p), p),
    )

    assert [os.path.basename(p) for p in ordered] == [
        "jdk21",    # 21
        "jdk-17",   # 17（旧实现在这里崩）
        "jdk17",    # 17
        "jdkabc",   # 0，排最后且不干扰
    ]
