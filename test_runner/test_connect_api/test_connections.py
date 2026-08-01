"""
test_connect_api 冒烟测试
验证 SSH 隧道打通后 Redis / MySQL 能否连通
"""
import redis
import pymysql
from configparser import ConfigParser

from conf.setting import FILE_PATH
from utils.recordlog import logs


def _read_config():
    cf = ConfigParser()
    cf.read(FILE_PATH['CONFIG'], encoding="utf-8")
    return cf


def test_redis_connection(ssh_tunnel):
    """通过 SSH 隧道连接 Redis，验证 ping 通"""
    cf = _read_config()
    r = None

    try:
        r = redis.Redis(
            host="127.0.0.1",
            port=ssh_tunnel["redis_port"],
            password=cf.get("REDIS", "password"),
            db=cf.getint("REDIS", "db"),
            decode_responses=True,
        )
        r.ping()
        logs.info("Redis 连接成功")
    except Exception as e:
        logs.error(f"Redis 连接失败: {e}")
        raise AssertionError(f"Redis 连接失败: {e}")
    finally:
        if r:
            r.close()


def test_mysql_connection(ssh_tunnel):
    """通过 SSH 隧道连接 MySQL，执行 SELECT 1"""
    cf = _read_config()
    conn = None
    cursor = None

    try:
        conn = pymysql.connect(
            host="127.0.0.1",
            port=ssh_tunnel["mysql_port"],
            user=cf.get("MYSQL", "username"),
            password=cf.get("MYSQL", "password"),
            database=cf.get("MYSQL", "database"),
            charset="utf8mb4",
        )
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        logs.info("MySQL 连接成功")
    except Exception as e:
        logs.error(f"MySQL 连接失败: {e}")
        raise AssertionError(f"MySQL 连接失败: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
