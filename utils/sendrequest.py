import json
import requests
import urllib3

from conf.setting import API_TIMEOUT
from utils.recordlog import logs

class SendRequest:
     """HTTP 请求封装，只管发请求 + 打日志，不做业务判断。"""
     def send_request(self, method, url, headers, **kwargs):
          session = requests.session()
          urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

          try:
               response = session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=API_TIMEOUT,
                    verify=False,
                    **kwargs
               )
               logs.info(f"响应状态码: {response.status_code}")
               return response

          except requests.exceptions.ConnectionError:
               logs.error("ConnectionError —— 连接失败，请检查网络或服务器地址")
               raise
          except requests.exceptions.Timeout:
               logs.error(f"请求超时（{API_TIMEOUT}s）: {method} {url}")
               raise
          except requests.exceptions.RequestException as e:
               logs.error(f"请求异常: {e}")
               raise


     def run_main(self, method, url, headers, **kwargs):
          """
          外层包装：打请求日志，然后调 send_request()。
          返回：requests.Response 对象（apiutil 拿到后自行 json.loads()）
          """
          logs.info(f"请求方式: {method}")
          logs.info(f"请求地址: {url}")
          logs.info(f"请求头: {json.dumps(headers, ensure_ascii=False)}")

          # 打印请求参数（data/json/params 只出现一种）
          for key in ("json", "data", "params"):
               if key in kwargs and kwargs[key] is not None:
                    logs.info(f"请求参数({key}): {json.dumps(kwargs[key], ensure_ascii=False)}")
                    break

          # 文件上传单独处理（不 json.dumps 二进制内容）
          if "files" in kwargs and kwargs["files"] is not None:
               logs.info(f"文件上传: {list(kwargs['files'].keys())}")

          return self.send_request(method=method, url=url, headers=headers, **kwargs)


# ═══════════════════════════════════════════════════════════
# 自测入口：验证 HTTP 请求层（打若依验证码接口，不需要 token）
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import configparser
    from conf.setting import FILE_PATH
    cf = configparser.ConfigParser()
    cf.read(FILE_PATH["CONFIG"], encoding="utf-8")
    host = cf.get("api_envi", "host")

    s = SendRequest()
    resp = s.run_main(
        method="get",
        url=f"{host}/captchaImage",
        headers={"Accept": "application/json"}
    )
    print(f"HTTP 状态码: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        print(f"uuid: {data.get('uuid')}")
        print(f"img 长度: {len(data.get('img', ''))} 字符")
        print("请求层验证通过！")
    else:
        print(f"服务器返回非 200，响应内容: {resp.text[:200]}")