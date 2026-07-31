import json
import random
import string
import time

from utils.readyaml import get_runtime as read_runtime
from utils.recordlog import logs

class DebugTalk:
     """
     热加载函数工具箱。
     YAML 中 ${函数名(参数)} 的调用通过 apiutil.py 的 getattr(DebugTalk(), func_name)
     反射到这里的实例方法。

     Redis 连接作为类属性，由 test_runner/conftest.py 的 fixture 注入。
     """

     # 类属性：所有实例共享同一 Redis 连接
     _redis_client = None

     @classmethod
     def set_redis_client(cls, client):
          """由 conftest.py 的 redis_client fixture 调用，注入 Redis 连接。"""
          cls._redis_client = client
          logs.info("DebugTalk: Redis 客户端已注入")



    # ═══════════════════════════════════════════════════════════
    # 验证码 / 账户锁定
    # ═══════════════════════════════════════════════════════════
     CAPTCHA_KEY_PREFIX = "captcha_codes:"   # + uuid → 验证码答案
     PWD_ERR_KEY_PREFIX = "pwd_err_cnt:"     # + username → 错误次数


     def _load_fastjson_value(self, raw):
          """
          若依后端用 FastJson 序列化 Redis 值。
          Java String "8" → Redis 存为 JSON "8" → json.loads 还原。
          """
          if raw is None:
               return None
          return str(json.loads(raw))

     def get_captcha_code(self, uuid):
          """从 Redis 读取验证码答案。返回 None 表示已过期。"""
          if self._redis_client is None:
               raise RuntimeError("Redis 客户端未注入，请检查 conftest.py")
          raw = self._redis_client.get(self.CAPTCHA_KEY_PREFIX + uuid)
          return self._load_fastjson_value(raw) 
     
     def get_pwd_error_count(self, username):
          """获取密码错误次数。返回 None 表示无记录。"""
          if self._redis_client is None:
               raise RuntimeError("Redis 客户端未注入")
          raw = self._redis_client.get(self.PWD_ERR_KEY_PREFIX + username)
          return self._load_fastjson_value(raw)

     # ═══════════════════════════════════════════════════════════
     # 运行时变量：从 runtime.yaml 读取
     # ═══════════════════════════════════════════════════════════

     def get_runtime(self, key):
          """
          读取 runtime.yaml 中的变量。
          YAML 用法：${get_runtime(token)}
          """
          value = read_runtime(key)
          if value is None:
               logs.warning(f"runtime.yaml 中未找到 key: {key}")
          return value

     # ═══════════════════════════════════════════════════════════
     # 通用工具
     # ═══════════════════════════════════════════════════════════

     def timestamp(self):
          """当前 10 位时间戳。"""
          return int(time.time())

     def timestamp_thirteen(self):
          """当前 13 位时间戳。"""
          return int(time.time()) * 1000

     def random_str(self, length=8):
          """生成指定长度的随机字符串（字母 + 数字）。"""
          chars = string.ascii_letters + string.digits
          return "".join(random.choice(chars) for _ in range(int(length)))


# ═══════════════════════════════════════════════════════════
# 自测入口：测试纯函数（Redis 依赖的跳过）
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    dt = DebugTalk()

    # 1. 时间戳
    t10 = dt.timestamp()
    t13 = dt.timestamp_thirteen()
    print(f"10 位时间戳: {t10} (长度: {len(str(t10))})")
    print(f"13 位时间戳: {t13} (长度: {len(str(t13))})")

    # 2. 随机字符串
    s = dt.random_str(8)
    s16 = dt.random_str(16)
    print(f"随机 8 位: {s}")
    print(f"随机 16 位: {s16}")
    print(f"两次生成不同: {s != s16}")

    # 3. FastJson 值解析
    none_val = dt._load_fastjson_value(None)
    str_val = dt._load_fastjson_value('"8"')
    int_val = dt._load_fastjson_value("4")
    print(f"_load_fastjson(None) → {none_val}")
    print(f"_load_fastjson('\"8\"') → {str_val}")
    print(f"_load_fastjson('4') → {int_val}")

    # 4. get_runtime（先写再读）
    from utils.readyaml import write_runtime, clear_runtime
    write_runtime({"test_key": "test_value"})
    val = dt.get_runtime("test_key")
    print(f"get_runtime('test_key') → {val}")

    missing = dt.get_runtime("not_exist")
    print(f"get_runtime('not_exist') → {missing}")

    clear_runtime()
    print("\n所有纯函数测试完毕！（Redis 依赖函数需 Phase 1 隧道打通后测试）")