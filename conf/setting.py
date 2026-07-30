import logging
import os

# 项目根目录
DIR_BASE= os.path.dirname(os.path.dirname(__file__))

# 调试日志相关
LOG_LEVEL = logging.DEBUG          # 输出到文件的级别
STREAM_LOG_LEVEL = logging.INFO    # 输出到控制台的级别

# HTTP 请求超时时间（秒）
API_TIMEOUT = 60

# 各个模块的路径
FILE_PATH= {
     # 若依框架配置文件
     'CONFIG' : os.path.join(DIR_BASE, 'conf', 'config.ini'),
     # 日志输出目录
     'LOG': os.path.join(DIR_BASE, 'logs'),
     # 测试案例目录
     'YAML': os.path.join(DIR_BASE, 'test_data'),
     # 运行时变量（token 等）
     'RUNTIME': os.path.join(DIR_BASE, 'data', 'runtime.yaml'),
}

# ---- 请求头模板 ----

# 普通 JSON 接口（负责crud和登录）
JSON_HEADER = {
     'Content-Type': 'application/json;charset=UTF-8',
     'Accept': 'application/json, text/plain, */*',
}

# EXCEL文件相关
EXCEL_FILE_HEADER = {
     'Accept': 'application/json, text/plain, */*',
}

# Token 前缀，运行时拼接：Authorization: Bearer <token>
TOKEN_PREFIX = 'Bearer '