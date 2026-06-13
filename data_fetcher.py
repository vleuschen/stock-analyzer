"""
股票数据抓取模块
主数据源: 腾讯财经 API (qt.gtimg.cn + web.ifzq.gtimg.cn)
备用数据源: 东方财富 API
零外部依赖，使用 Python 内置 http.client
"""

from __future__ import annotations

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

# SSL 上下文（跳过证书验证，兼容内网环境）
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# 市场代码映射（腾讯格式）
MARKET_MAP = {
    "sh": "sh",
    "sz": "sz",
    "bj": "bj",
}


def _get_symbol(code: str, market: str) -> str:
    """构造证券代码: sh600519 / sz002170"""
    m = MARKET_MAP.get(market.lower(), "sz")
    return f"{m}{code}"


def _https_get_json(host: str, path: str, timeout: int = 15, encoding: str = "utf-8") -> any:
    """通过 http.client 直连 HTTPS，返回解析后的 JSON"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://{host}/",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }
    conn = http.client.HTTPSConnection(host, 443, timeout=timeout, context=_SSL_CTX)
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode(encoding)
    conn.close()
    return json.loads(raw)


def _https_get_text(host: str, path: str, timeout: int = 15, encoding: str = "utf-8") -> str:
    """通过 http.client 直连 HTTPS，返回原始文本"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://{host}/",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }
    conn = http.client.HTTPSConnection(host, 443, timeout=timeout, context=_SSL_CTX)
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode(encoding)
    conn.close()
    return raw


def fetch_realtime_quote(code: str, market: str) -> dict:
    """
    获取实时行情快照（腾讯财经 API）
    """
    symbol = _get_symbol(code, market)
    path = f"/q={symbol}"

    try:
        text = _https_get_text("qt.gtimg.cn", path, encoding="gbk")
    except Exception as e:
        return {"error": f"无法获取 {code} 实时行情: {e}"}

    # 解析腾讯行情格式: v_sz002170="51~芭田股份~002170~11.35~..."
    try:
        content = text.split('"')[1]
        fields = content.split("~")
    except (IndexError, ValueError):
        return {"error": f"解析行情数据失败: {text[:100]}"}

    if len(fields) < 50:
        return {"error": f"行情数据字段不足: {len(fields)} fields"}

    def safe_float(s, default=0.0):
        try:
            return float(s) if s else default
        except ValueError:
            return default

    def safe_int(s, default=0):
        try:
            return int(s) if s else default
        except ValueError:
            return default

    price = safe_float(fields[3])
    pre_close = safe_float(fields[4])
    change = price - pre_close if pre_close else 0
    pct_change = (change / pre_close * 100) if pre_close else 0

    return {
        "code": fields[2],
        "name": fields[1],
        "price": price,
        "open": safe_float(fields[5]),
        "high": safe_float(fields[33]) if len(fields) > 33 else safe_float(fields[3]),
        "low": safe_float(fields[34]) if len(fields) > 34 else safe_float(fields[3]),
        "pre_close": pre_close,
        "change": round(change, 2),
        "pct_change": round(pct_change, 2),
        "volume": safe_int(fields[6]),           # 手
        "amount": safe_float(fields[37]) * 10000 if len(fields) > 37 else 0,  # 万元→元
        "turnover": safe_float(fields[38]),       # %
        "pe_ttm": safe_float(fields[39]),
        "pb": safe_float(fields[46]) if len(fields) > 46 else 0,
        "total_mv": safe_float(fields[45]) * 1e8 if len(fields) > 45 else 0,   # 亿→元
        "circ_mv": safe_float(fields[44]) * 1e8 if len(fields) > 44 else 0,   # 亿→元
        "amplitude": safe_float(fields[43]) if len(fields) > 43 else 0,  # %
        "volume_ratio": safe_float(fields[49]) if len(fields) > 49 else 0,
    }


def fetch_kline(code: str, market: str, days: int = 120, frequency: str = "daily") -> list:
    """
    获取历史K线数据（腾讯财经 API，前复权）
    """
    symbol = _get_symbol(code, market)
    freq_map = {"daily": "day", "weekly": "week", "monthly": "month"}
    freq = freq_map.get(frequency, "day")

    path = f"/appstock/app/fqkline/get?param={symbol},{freq},,,{days},qfq"

    try:
        data = _https_get_json("web.ifzq.gtimg.cn", path)
    except Exception as e:
        print(f"  ⚠️ K线获取失败: {e}")
        return []

    # 解析 JSON 数据
    stock_data = data.get("data", {}).get(symbol, {})
    kline_key = f"qfq{freq}"
    klines_raw = stock_data.get(kline_key, [])

    if not klines_raw:
        # 尝试不带前复权的 key
        klines_raw = stock_data.get(freq, [])

    klines = []
    prev_close = None
    for item in klines_raw:
        if len(item) < 6:
            continue

        date_str = item[0]
        open_p = float(item[1])
        close_p = float(item[2])
        high_p = float(item[3])
        low_p = float(item[4])
        volume = int(float(item[5]))

        pct_change = 0.0
        change = 0.0
        if prev_close and prev_close > 0:
            change = round(close_p - prev_close, 4)
            pct_change = round(change / prev_close * 100, 2)

        amplitude = round((high_p - low_p) / prev_close * 100, 2) if prev_close else 0

        klines.append({
            "date": date_str,
            "open": open_p,
            "close": close_p,
            "high": high_p,
            "low": low_p,
            "volume": volume,
            "amount": 0,  # 腾讯K线不含成交额
            "amplitude": amplitude,
            "pct_change": pct_change,
            "change": change,
            "turnover": 0,  # 腾讯K线不含换手率
        })
        prev_close = close_p

    return klines


def fetch_stock_data(code: str, market: str, kline_days: int = 120) -> dict:
    """
    一站式获取股票全部数据（行情 + K线）
    """
    quote = fetch_realtime_quote(code, market)
    time.sleep(0.3)

    klines = fetch_kline(code, market, days=kline_days)
    time.sleep(0.3)

    return {
        "quote": quote,
        "klines": klines,
        "money_flow": [],  # 腾讯API暂不支持资金流向
    }
