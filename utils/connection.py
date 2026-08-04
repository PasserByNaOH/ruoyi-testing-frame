import traceback
import configparser
import pymysql
import redis


from conf.setting import FILE_PATH
from utils.recordlog import logs

def _read_config():
     """读取 config.ini，返回 ConfigParser 对象。"""
     cf = configparser.ConfigParser()
     cf.read(FILE_PATH["CONFIG"], encoding="utf-8")
     return cf


class ConnectMysql:
     def __init__(self, host=None, port=None, user=None, password=None, database=None):
          cf = _read_config()
          mysql_conf = {
               "host" : host or cf.get("MYSQL", "host"),
               "port" : port or cf.getint("MYSQL", "port"),
               "user": user or cf.get("MYSQL", "username"),
               "password": password or cf.get("MYSQL", "password"),
               "database": database or cf.get("MYSQL", "database"),
          }

          try:
               # autocommit=True：每条 SELECT 都是独立事务，
               # 避免 REPEATABLE READ 导致 DB 验证读到旧快照
               self.conn = pymysql.connect(**mysql_conf, charset="utf8mb4", autocommit=True)
               self.cursor = self.conn.cursor(cursor=pymysql.cursors.DictCursor)
               logs.info(f"MySQL 连接成功: {mysql_conf['host']}:{mysql_conf['port']}/{mysql_conf['database']}")
          except Exception as e:
               logs.error(f"MySQL 连接失败: {e}")
               raise

     # 查询，返回 dict 列表
     def query(self, sql, params=None):
          try:
               if params:
                    self.cursor.execute(sql, params)
               else:
                    self.cursor.execute(sql)
               return self.cursor.fetchall()
          except Exception as e:
               logs.error(f"Mysql 查询失败：{sql} ------ {e}")
               raise

     # 执行——增删改
     def execute(self, sql, params=None):
          try:
               if params:
                    self.cursor.execute(sql, params)
               else:
                    self.cursor.execute(sql)
               self.conn.commit()
               logs.info(f"SQL 执行成功: {sql}")
          except Exception as e:
               self.conn.rollback()
               logs.error(f"SQL 执行失败: {sql} —— {e}")
               raise

     # 关闭链接
     def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logs.info("MySQL 连接已关闭")

# redis操作
class ConnectRedis:
     """Redis 操作：读写验证码、错误计数。"""
     def __init__(self):
          cf = _read_config()
          self.host = cf.get("REDIS", "host")
          self.port = cf.getint("REDIS", "port")
          self.password = cf.get("REDIS", "password") or None
          self.db = cf.getint("REDIS", "db")

          try:
               pool = redis.ConnectionPool(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                    db=self.db,
                    decode_responses=True,
               )
               self.client = redis.Redis(connection_pool=pool)
               self.client.ping()
               logs.info(f"Redis 连接成功: {self.host}:{self.port}")
          except Exception as e:
               logs.error(f"Redis 连接失败: {traceback.format_exc()}")
               raise

     def get(self, key):
        """读取 key 的值，不存在返回 None。"""
        try:
            return self.client.get(key)
        except Exception:
            logs.error(f"Redis GET 失败: {key}")
            return None

     def set(self, key, value, ex=None):
          """
          设置 key 的值。
          ex: 过期时间（秒），不填则永不过期。
          返回 True 表示成功。
          """
          try:
               return self.client.set(key, value, ex=ex)
          except Exception:
               logs.error(f"Redis SET 失败: {key}")
               return False    

     def delete(self, key):
          """删除指定 key。返回删除的数量。"""
          try:
               return self.client.delete(key)
          except Exception:
               logs.error(f"Redis DELETE 失败: {key}")
               return 0

     def close(self):
          """关闭连接。"""
          if self.client:
               self.client.close()
          logs.info("Redis 连接已关闭")     