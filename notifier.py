"""
方糖 ServerChan 微信推送模块
API: https://sct.ftqq.com/
零外部依赖，使用 Python 内置 urllib
"""

import time
import json
import urllib.request
import urllib.parse


SERVERCHAN_URL = "https://sctapi.ftqq.com/{sendkey}.send"


def push_serverchan(sendkey: str, title: str, desp: str, max_retries: int = 3) -> dict:
    """
    推送消息到微信（通过方糖 ServerChan）

    Args:
        sendkey: 方糖 SendKey
        title: 消息标题（最长100字）
        desp: 消息正文（Markdown 格式）
        max_retries: 最大重试次数

    Returns:
        API 响应 JSON
    """
    if not sendkey:
        return {"code": -1, "message": "未配置 SERVERCHAN_SENDKEY"}

    url = SERVERCHAN_URL.format(sendkey=sendkey)

    # 截断标题（方糖限制100字）
    if len(title) > 100:
        title = title[:97] + "..."

    payload = urllib.parse.urlencode({
        "title": title,
        "desp": desp,
    }).encode("utf-8")

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            # 绕过系统代理
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)
            resp = opener.open(req, timeout=30)
            result = json.loads(resp.read().decode("utf-8"))

            if result.get("code") == 0:
                print(f"✅ 推送成功: {title}")
                return result
            else:
                print(f"⚠️ 推送返回异常 (attempt {attempt + 1}/{max_retries}): {result}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        except urllib.error.URLError as e:
            print(f"⚠️ 推送失败 (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"❌ 推送异常: {e}")
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
