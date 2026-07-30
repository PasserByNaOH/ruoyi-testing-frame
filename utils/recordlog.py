import logging
import os
import time
from logging.handlers import RotatingFileHandler

from conf.setting import FILE_PATH, LOG_LEVEL, STREAM_LOG_LEVEL

# 确保保存日志的目录存在
LOG_DIR = FILE_PATH['LOG']
if not os.path.exists(LOG_DIR):
     os.mkdir(LOG_DIR)

# 日志文件名按日期区分，如 test.20260730.log
logfile_name = os.path.join(LOG_DIR, "test.{}.log".format(time.strftime("%Y%m%d")))

def setup_logger():
     """配置日志：文件（按大小滚动）+ 控制台输出，返回全局共用的 logger。"""
     logger = logging.getLogger("ruoyi_test")
     if not logger.handlers:

          # 设置日志级别
          logger.setLevel(LOG_LEVEL)

          # 定义日志的格式：级别 - 时间 - 文件名:行号 - [模块名:函数名] - 消息内容
          formatter = logging.Formatter(
               "%(levelname)s - %(asctime)s - %(filename)s:%(lineno)d - "
               "[%(module)s:%(funcName)s] - %(message)s"
          )

          # 文件输出：5MB 一个文件，保留最近 7 个
          fh = RotatingFileHandler(
               logfile_name, # 日志名称设置
               mode="a", # 设置为追加输入模式，w是写入，同时清空之前的内容
               maxBytes=5242880, # 设置日志最大大小，这里设置为5MB
               backupCount=7, # 满了就轮转，旧文件最多 7 个
               encoding="utf-8" # 设置编码格式
          )
          fh.setLevel(LOG_LEVEL)
          fh.setFormatter(formatter)
          logger.addHandler(fh)

          # 控制台输出
          sh = logging.StreamHandler()
          sh.setLevel(STREAM_LOG_LEVEL)
          sh.setFormatter(formatter)
          logger.addHandler(sh)

     return logger


logs = setup_logger()