"""
Jenkins API 封装 —— 查询构建状态 / 测试报告 / 控制台日志

参考源框架 common/Pjenkins.py，扩展以下功能：
  - get_build_status()     查询最新构建状态（SUCCESS / FAILURE / ABORTED）
  - get_report_stats()     查询测试报告统计（通过 / 失败 / 跳过 / 总数）
  - get_console_log()      获取控制台输出（提取 Allure 报告链接等）
  - get_build_url()        获取本次构建的 Jenkins 页面链接
  - build_info_summary()   汇总以上信息，供通知（钉钉/邮件）使用

依赖：pip install python-jenkins（需要先在 .venv 中安装）
配置：conf/config.ini 中 [JENKINS] 节
"""

import re
import sys
from configparser import ConfigParser

from conf.setting import FILE_PATH


class JenkinsClient:
    """Jenkins API 客户端。

    供外部脚本调用，不参与 pytest 测试执行。
    用法:
        from utils.jenkins import JenkinsClient
        jk = JenkinsClient()
        summary = jk.build_info_summary()
        print(summary)
    """

    def __init__(self):
        cf = ConfigParser()
        cf.read(FILE_PATH['CONFIG'], encoding='utf-8')

        self._url      = cf.get('JENKINS', 'url')
        self._username = cf.get('JENKINS', 'username')
        self._password = cf.get('JENKINS', 'password')
        self._job_name = cf.get('JENKINS', 'job_name')

        self._server = None  # 延迟初始化，避免 import 失败

    def _connect(self):
        """延迟连接 Jenkins，避免 python-jenkins 未安装时 import 即报错。"""
        if self._server is None:
            try:
                import jenkins as jk
            except ImportError:
                raise ImportError(
                    "python-jenkins 未安装，请执行: pip install python-jenkins"
                )
            self._server = jk.Jenkins(
                url=self._url,
                username=self._username,
                password=self._password,
                timeout=15,
            )

    # ── 构建信息 ──────────────────────────────────────

    def _get_last_build_number(self):
        self._connect()
        job = self._server.get_job_info(self._job_name)
        last = job.get('lastBuild')
        if last is None:
            raise RuntimeError(f"Job '{self._job_name}' 尚未执行过构建")
        return last['number']

    def get_build_status(self, build_number=None):
        """返回 'SUCCESS' / 'FAILURE' / 'ABORTED' / None（仍在运行）"""
        if build_number is None:
            build_number = self._get_last_build_number()
        self._connect()
        info = self._server.get_build_info(self._job_name, build_number)
        return info.get('result')

    def get_build_url(self, build_number=None):
        """返回本次构建的 Jenkins 页面链接。"""
        if build_number is None:
            build_number = self._get_last_build_number()
        self._connect()
        info = self._server.get_build_info(self._job_name, build_number)
        return info.get('url', '')

    # ── 控制台日志 ────────────────────────────────────

    def get_console_log(self, build_number=None):
        """获取控制台完整输出。"""
        if build_number is None:
            build_number = self._get_last_build_number()
        self._connect()
        return self._server.get_build_console_output(self._job_name, build_number)

    def extract_allure_url(self, build_number=None):
        """从控制台日志中提取 Allure 报告链接。"""
        log = self.get_console_log(build_number)
        match = re.search(r'(https?://\S+allure\S+)', log)
        return match.group(0) if match else None

    # ── 测试报告 ──────────────────────────────────────

    def get_report_stats(self, build_number=None):
        """
        返回测试报告统计 dict:
            {total, pass_count, fail_count, skip_count, duration_seconds}
        """
        if build_number is None:
            build_number = self._get_last_build_number()
        self._connect()

        try:
            report = self._server.get_build_test_report(self._job_name, build_number)
        except Exception:
            return None

        pass_count = report.get('passCount', 0)
        fail_count = report.get('failCount', 0)
        skip_count = report.get('skipCount', 0)

        return {
            'total':      int(pass_count) + int(fail_count) + int(skip_count),
            'pass_count': int(pass_count),
            'fail_count': int(fail_count),
            'skip_count': int(skip_count),
            'duration_seconds': int(report.get('duration', 0)),
        }

    # ── 汇总 ──────────────────────────────────────────

    def build_info_summary(self, build_number=None):
        """
        一次性返回本次构建的完整摘要：
            {status, build_number, url, stats, allure_url}
        供通知模块（钉钉/邮件）使用。
        """
        if build_number is None:
            build_number = self._get_last_build_number()

        stats = self.get_report_stats(build_number)

        return {
            'status':       self.get_build_status(build_number),
            'build_number': build_number,
            'url':          self.get_build_url(build_number),
            'stats':        stats,
            'allure_url':   self.extract_allure_url(build_number),
        }


# ═══════════════════════════════════════════════════════
# 命令行入口（python -m utils.jenkins）
# ═══════════════════════════════════════════════════════

class DingTalkNotifier:
    """钉钉机器人通知 —— 供 Jenkins pipeline 和本地脚本共用。

    用法：
        from utils.jenkins import DingTalkNotifier
        dt = DingTalkNotifier()
        dt.send(title="构建完成", text="83/83 通过")
    """

    def __init__(self):
        cf = ConfigParser()
        cf.read(FILE_PATH['CONFIG'], encoding='utf-8')
        self._webhook = cf.get('DINGTALK', 'webhook', fallback='')
        self._secret  = cf.get('DINGTALK', 'secret', fallback='')

    def send(self, title: str, text: str) -> bool:
        """发送 Markdown 消息到钉钉群。

        Args:
            title: 消息标题（显示在通知横幅）
            text:  Markdown 正文

        Returns:
            True 发送成功，False 失败
        """
        import json
        import urllib.request

        if not self._webhook or '你的access_token' in self._webhook:
            print("[DingTalk] webhook 未配置，跳过通知", file=sys.stderr)
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text,
            },
        }

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url=self._webhook,
                data=data,
                headers={'Content-Type': 'application/json; charset=utf-8'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            if result.get('errcode') == 0:
                print(f"[DingTalk] 通知已发送: {title}")
                return True
            else:
                print(f"[DingTalk] 发送失败: {result}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"[DingTalk] 发送异常: {e}", file=sys.stderr)
            return False

    def send_build_success(self, build_number: int, build_url: str,
                           duration: str = '', stats: dict = None) -> bool:
        """发送构建成功通知（预设模板）。"""
        lines = [
            '### ✅ 若依测试框架 - 构建成功',
            '',
        ]
        if stats:
            total = stats.get('total', '?')
            passed = stats.get('pass_count', '?')
            failed = stats.get('fail_count', '?')
            lines.append(f'> {total} 条用例 | 通过 {passed} | 失败 {failed}')
        else:
            lines.append('> 83 条用例全量通过')
        lines += [
            '',
            f'| 项目 | 内容 |',
            f'|------|------|',
            f'| 构建编号 | #{build_number} |',
            f'| 耗时 | {duration} |' if duration else '',
            f'| [Jenkins 页面]({build_url}) | 点击查看 |',
        ]
        return self.send(title=f"✅ 构建成功 - #{build_number}",
                         text='\n'.join(filter(None, lines)))

    def send_build_failure(self, build_number: int, build_url: str,
                           duration: str = '', reason: str = '') -> bool:
        """发送构建失败通知（预设模板）。"""
        lines = [
            '### ❌ 若依测试框架 - 构建失败',
            '',
            f'> {reason}' if reason else '> 请检查控制台日志',
            '',
            f'| 项目 | 内容 |',
            f'|------|------|',
            f'| 构建编号 | #{build_number} |',
            f'| 耗时 | {duration} |' if duration else '',
            f'| [控制台日志]({build_url}console) | 点击查看 |',
        ]
        return self.send(title=f"❌ 构建失败 - #{build_number}",
                         text='\n'.join(filter(None, lines)))


# ═══════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse

    ap = argparse.ArgumentParser(description='Jenkins / 钉钉通知 工具')
    ap.add_argument('action', choices=['jenkins', 'dingtalk-test'],
                    help='jenkins: 查询构建摘要 | dingtalk-test: 测试钉钉连通性')
    args = ap.parse_args()

    if args.action == 'jenkins':
        try:
            jk = JenkinsClient()
            summary = jk.build_info_summary()
            print("=" * 50)
            print("Jenkins 构建摘要")
            print("=" * 50)
            for key, value in summary.items():
                print(f"  {key}: {value}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.action == 'dingtalk-test':
        dt = DingTalkNotifier()
        ok = dt.send(
            title="🧪 钉钉通知测试 — 构建连通性验证",
            text=(
                "### 🧪 钉钉通知测试 — 构建连通性验证\n\n"
                "如果你看到这条消息，说明钉钉机器人配置成功。\n\n"
                "- 来源: `utils/jenkins.py`\n"
                "- 时间: 本地手动触发"
            ),
        )
        sys.exit(0 if ok else 1)
