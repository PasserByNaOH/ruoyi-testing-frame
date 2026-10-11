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
# 四、对着**本机真实环境**验证（不造数据）
# ═══════════════════════════════════════════════════════════
#
# ⚠️ 这一段**不能写死任何路径**。之前这里硬编码了 `E:\Env\jdk*`（开发机的目录），
#    换一台机器跑必红。现在一律通过 run.py 自己的入口去问。
#
# ⚠️ 而且**判断标准必须和实现共用同一个函数**（run_module._looks_like_jdk）。
#    曾经这里自己写了"只按目录名收候选"，结果把空壳目录也算进来，
#    与 _find_java（会过滤掉没有 java 的目录）算出的"最高版本"不一致 —— 一遇到
#    名字像 JDK 但不是 JDK 的目录就红。
#
#    2026-10-11 两边各自修了这个问题（Gitee 上 d2d02f5 在本文件里加了
#    `_has_java_executable`；本地把判据抽到 run.py 的 `_looks_like_jdk`）。
#    最终取**共用 run.py 函数**这一版 —— 判据写在实现里，测试复用它，
#    才能真正做到"两边用同一把尺子"，而不是各写一份会长歪的逻辑。


def _real_jdk_candidates():
    """
    真实存在的 JDK 候选目录（与 run.py 的候选集合保持完全一致）。

    判断标准直接用 `run_module._looks_like_jdk` —— 即"目录里确实有 java 可执行文件"。
    自己另写一套判断是错的源头（如 `jdk-21_windows-x64_bin` 这种解压包装目录，
    真 JDK 在下一层，只按目录名会被误判成版本 21），别再这么做。
    """
    found = []
    for search_dir in run_module._configured_java_search_dirs():
        if os.path.isdir(search_dir):
            found.extend(
                p for p in glob.glob(os.path.join(search_dir, "jdk*"))
                if run_module._looks_like_jdk(p)
            )
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if run_module._looks_like_jdk(java_home):
        found.append(java_home)
    return found


def test_configured_search_dirs_is_a_list():
    """[JAVA] search_dirs 必须能被解析成列表（缺失/为空都不应报错）。"""
    dirs = run_module._configured_java_search_dirs()
    assert isinstance(dirs, list)
    assert all(isinstance(d, str) for d in dirs)


# ── 4.1 "像 JDK 但不是 JDK"的目录必须被排除（本次修的缺陷）──

@pytest.mark.parametrize("case, expect_looks_like", [
    ("有 bin/java.exe",                     True),
    ("只有目录没有 java",                    False),
    ("有 release 文件但没 java",             False),
    ("整个是个文件（压缩包）",                False),
    ("路径根本不存在",                       False),
])
def test_looks_like_jdk(tmp_path, case, expect_looks_like):
    """
    ★ _looks_like_jdk 是"这个目录到底是不是 JDK"的唯一判据。

    覆盖实测踩过的两类脏数据：
      · `jdk8.7z` —— 是**文件**不是目录
      · 名字像 JDK 但是**空壳**目录（解压失败残留）—— 只看 isdir 会误收
    """
    if case == "路径根本不存在":
        path = os.path.join(str(tmp_path), "jdk-does-not-exist")
    elif case == "整个是个文件（压缩包）":
        path = os.path.join(str(tmp_path), "jdk8.7z")
        open(path, "w").close()
    elif case == "有 release 文件但没 java":
        path = make_jdk(str(tmp_path), "jdk22", release_version="22.0.1",
                        with_java=False)
    else:
        path = make_jdk(str(tmp_path), "jdk21",
                        release_version="21.0.7",
                        with_java=(case == "有 bin/java.exe"))

    assert run_module._looks_like_jdk(path) is expect_looks_like


def test_empty_shell_dir_is_not_a_candidate(tmp_path):
    """
    ★ 回归保护：一个"名字像 JDK 但没有 java"的空壳目录，
    不应进入候选，也不应影响最高版本的判断。
    """
    # 造一个版本号看起来最高、却没有 java 的空壳
    make_jdk(str(tmp_path), "jdk99", release_version="99.0.1", with_java=False)
    # 再造一个真实可用的低版本
    real = make_jdk(str(tmp_path), "jdk17", release_version="17.0.8")

    candidates = [
        p for p in glob.glob(os.path.join(str(tmp_path), "jdk*"))
        if run_module._looks_like_jdk(p)
    ]
    assert [os.path.basename(p) for p in candidates] == ["jdk17"]
    assert _real_jdk_version(candidates) == 17, "空壳不应把最高版本抬到 99"


def _real_jdk_version(candidates):
    return max(run_module._jdk_major_version(p) for p in candidates)


def test_find_java_returns_none_when_nothing_available(monkeypatch):
    """
    ★ 换一台**完全没装 JDK** 的机器：_find_java() 必须返回 (None, None) 且不抛异常。

    这条就是为"面试用的笔记本拉下代码跑测试"那种场景准备的 ——
    探测不到 Java 不该让测试变红，只该让 JDK 相关用例跳过。
    """
    monkeypatch.setattr(run_module, "_configured_java_search_dirs", lambda: [])
    monkeypatch.delenv("JAVA_HOME", raising=False)
    # 屏蔽 Windows 常见安装位置，模拟"整机没有 JDK"
    monkeypatch.setenv("ProgramFiles", r"Z:\no-such-program-files")

    java_home, java_bin = run_module._find_java()

    assert java_home is None and java_bin is None, (
        f"没有任何 JDK 时应返回 (None, None)，实际 ({java_home}, {java_bin})"
    )


def test_real_jdk_candidates_empty_is_safe(monkeypatch):
    """候选为空时，辅助函数要返回空列表（测试据此 skip，而不是报错）。"""
    monkeypatch.setattr(run_module, "_configured_java_search_dirs", lambda: [])
    monkeypatch.delenv("JAVA_HOME", raising=False)
    assert _real_jdk_candidates() == []


def test_real_env_jdk_dirs_all_parse():
    """配置里每个真实 JDK 目录都应能解析出版本号（非 0）。"""
    real = _real_jdk_candidates()
    if not real:
        pytest.skip("本机未找到 JDK 目录（配置 [JAVA] search_dirs / JAVA_HOME 都为空）")
    for path in real:
        version = run_module._jdk_major_version(path)
        assert version > 0, f"{path} 解析出版本号 {version}"


def test_real_find_java_picks_highest_version():
    """
    真的调用 _find_java()：应选中候选里版本最高的那个（且它确实有 bin/java.exe）。

    这一段全部靠"实际候选"来算，不预设版本号 —— 因为不同机器装的 JDK 不同。
    """
    java_home, java_bin = run_module._find_java()
    if java_home is None:
        pytest.skip("本机未探测到 JDK")

    java_exe = os.path.join(java_bin, "java.exe")
    if not os.path.isfile(java_exe):
        # 非 Windows（比如 Linux 上叫 java）时只校验探测结果非空
        java_exe = os.path.join(java_bin, "java")
    assert os.path.isfile(java_exe), f"探测到 {java_bin}，但里面没有 java 可执行文件"

    candidates = _real_jdk_candidates()
    if candidates:
        expected = max(run_module._jdk_major_version(p) for p in candidates)
        assert run_module._jdk_major_version(java_home) == expected, (
            f"探测到 {java_home}（版本 {run_module._jdk_major_version(java_home)}），"
            f"但候选里最高版本是 {expected}"
        )


def test_real_find_java_does_not_crash_on_archive_file():
    """
    search_dirs 下可能混着 `jdk8.7z` 这类**压缩包**（不是目录）。
    _find_java 必须不受它影响、也不崩。
    """
    java_home, _ = run_module._find_java()   # 不抛异常即通过
    for search_dir in run_module._configured_java_search_dirs():
        if not os.path.isdir(search_dir):
            continue
        archives = [p for p in glob.glob(os.path.join(search_dir, "jdk*"))
                    if not os.path.isdir(p)]
        if archives:
            assert java_home is not None, (
                f"{search_dir} 下有压缩包 {archives}，但 _find_java 没探测到任何 JDK"
            )


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
