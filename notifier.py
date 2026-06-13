"""
方糖 ServerChan 微信推送模块
API: https://sct.ftqq.com/
零外部依赖，使用 Python 内置 http.client
"""

import os
import time
import json
import http.client
import ssl
import urllib.parse

# 强制清除代理
for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
            "ALL_PROXY", "all_proxy"]:
    os.environ.pop(key, None)


def push_serverchan(sendkey: str, title: str, desp: str, max_retries: int = 3) -> dict:
    """
    推送消息到微信（通过方糖 ServerChan）
    """
    if not sendkey:
        return {"code": -1, "message": "未配置 SERVERCHAN_SENDKEY"}

    # 截断标题（方糖限制100字）
    if len(title) > 100:
        title = title[:97] + "..."

    payload = urllib.parse.urlencode({
        "title": title,
        "desp": desp,
    }).encode("utf-8")

    path = f"/{sendkey}.send"

    for attempt in range(max_retries):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            conn = http.client.HTTPSConnection("sctapi.ftqq.com", 443, timeout=30, context=ctx)
            conn.request(
                "POST", path, body=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp = conn.getresponse()
            result = json.loads(resp.read().decode("utf-8"))
            conn.close()

            if result.get("code") == 0:
                print(f"✅ 推送成功: {title}")
                return result
            else:
                print(f"⚠️ 推送返回异常 (attempt {attempt + 1}/{max_retries}): {result}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        except Exception as e:
            print(f"❌ 推送失败 (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return {"code": -1, "message": f"推送失败，已重试{max_retries}次"}


def push_test(sendkey: str) -> dict:
    """发送测试消息"""
    return push_serverchan(
        sendkey=sendkey,
        title="🎉 stock-analyzer 测试推送",
        desp="## 测试成功\n\n如果你看到这条消息，说明方糖推送配置正确！\n\n"
             f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
    )
