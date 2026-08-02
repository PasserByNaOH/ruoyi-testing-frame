"""
test_login/conftest.py —— 登录测试专用 fixtures

提供：
  base_url       → session 级，服务器地址
  redis_client   → session 级，Redis 连接 + 注入 DebugTalk
                   （依赖根 conftest.py 的 ssh_tunnel）
"""

import pytest
import redis
from configparser import ConfigParser

from conf.setting import FILE_PATH
from utils.debugtalk import DebugTalk
from utils.readyaml import clear_runtime
from utils.recordlog import logs


def _read_config():
     cf = ConfigParser()
     cf.read(FILE_PATH['CONFIG'], encoding='utf-8')
     return cf

# 获取服务器ip
@pytest.fixture(scope="session")
def base_url():
     cf = _read_config()
     return cf.get("api_envi", "host")

@pytest.fixture(scope="session")
def redis_client(ssh_tunnel):
     cf = _read_config()

     r = redis.Redis(
          host="127.0.0.1",
          port=ssh_tunnel["redis_port"],
          password=cf.get("REDIS", "password") or None,
          db=cf.getint("REDIS", "db"),
          decode_responses=True,
     )
     r.ping()
     logs.info("Redis 连接成功，注入 DebugTalk")
     DebugTalk.set_redis_client(r)

     yield r

     r.close()
     logs.info("Redis 连接已关闭")


@pytest.fixture(scope="session", autouse=True)
def clean_runtime_on_start():
    """session 开始时清空 runtime.yaml，防止上次运行的旧 token 残留。"""
    clear_runtime()
    logs.info("runtime.yaml 已清空（session 开始）")
    yield


@pytest.fixture(autouse=True)
def clean_pwd_error_count(redis_client):
    """每个测试后删除 LoginTestUser 的密码错误计数，保证用例间独立。"""
    yield
    redis_client.delete("pwd_err_cnt:LoginTestUser")