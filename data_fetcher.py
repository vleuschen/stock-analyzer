"""
东方财富 API 数据抓取模块
支持 SH/SZ/BJ 全部交易所，免费无需 API Key
零外部依赖，使用 Python 内置 urllib
"""

from __future__ import annotations

import time
import json
import urllib.request
import urllib.parse


# 市场代码映射
MARKET_MAP = {
    "sh": "1",  # 上海
    "sz": "0",  # 深圳
    "bj": "0",  # 北京
}


def _get_secid(code: str, market: str) -> str:
    """构造东方财富 secid: 市场编号.股票代码"""
    market_id = MARKET_MAP.get(market.lower(), "0")
    return f"{market_id}.{code}"


def _headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }


def _http_get(url: str, params: dict = None, timeout: int = 15) -> dict:
    """发送 HTTP GET 请求并返回 JSON（绕过系统代理）"""
    if params:
        query = urllib.parse.urlencode(params)
        url = f"{url}?{query}"

    req = urllib.request.Request(url, headers=_headers())

    # 绕过系统代理，直连
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    resp = opener.open(req, timeout=timeout)
    return json.loads(resp.read().decode("utf-8"))


def fetch_realtime_quote(code: str, market: str) -> dict:
    """
    获取实时行情快照
    返回: {code, name, price, open, high, low, pre_close, change, pct_change,
           volume, amount, turnover, pe_ttm, pb, total_mv, circ_mv, amplitude}
    """
    secid = _get_secid(code, market)
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "secid": secid,
        "fields": "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,"
                  "f116,f117,f162,f167,f168,f169,f170,f171",
        "ut": "fa5fd1943c7b386f172d6893dbbd1",
    }
    data = _http_get(url, params).get("data", {})

    if not data:
        return {"error": f"无法获取 {code} 实时行情"}

    # 东方财富的价格/金额字段以分为单位（整数），需要 /100
    return {
        "code": data.get("f57", code),
        "name": data.get("f58", ""),
        "price": data.get("f43", 0) / 100,
        "open": data.get("f46", 0) / 100,
        "high": data.get("f44", 0) / 100,
        "low": data.get("f45", 0) / 100,
        "pre_close": data.get("f60", 0) / 100,
        "change": data.get("f169", 0) / 100,
        "pct_change": data.get("f170", 0) / 100,
        "volume": data.get("f47", 0),          # 手
        "amount": data.get("f48", 0),           # 元
        "turnover": data.get("f168", 0) / 100,  # %
        "pe_ttm": data.get("f167", 0) / 100,
        "pb": data.get("f162", 0) / 100,
        "total_mv": data.get("f116", 0),        # 元
        "circ_mv": data.get("f117", 0),         # 元
        "amplitude": data.get("f171", 0) / 100, # %
        "volume_ratio": data.get("f50", 0) / 100,
    }


def fetch_kline(code: str, market: str, days: int = 120, frequency: str = "daily") -> list:
    """
    获取历史K线数据（前复权）
    frequency: daily / weekly / monthly
    返回: [{date, open, close, high, low, volume, amount, amplitude, pct_change, change, turnover}]
    """
    secid = _get_secid(code, market)
    klt_map = {"daily": 101, "weekly": 102, "monthly": 103}
    klt = klt_map.get(frequency, 101)

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": klt,
        "fqt": "1",
        "beg": "0",
        "end": "20500101",
        "lmt": str(days),
        "ut": "fa5fd1943c7b386f172d6893dbbd1",
    }

    data = _http_get(url, params).get("data", {})

    if not data or not data.get("klines"):
        return []

    klines = []
    for line in data["klines"]:
        parts = line.split(",")
        klines.append({
            "date": parts[0],
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": int(parts[5]),
            "amount": float(parts[6]),
            "amplitude": float(parts[7]),
            "pct_change": float(parts[8]),
            "change": float(parts[9]),
            "turnover": float(parts[10]),
        })
    return klines


def fetch_money_flow(code: str, market: str, days: int = 10) -> list:
    """
    获取资金流向（最近N日）
    返回: [{date, main_net, small_net, mid_net, big_net, super_large_net}]
    """
    secid = _get_secid(code, market)
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": str(days),
        "klt": "101",
        "ut": "fa5fd1943c7b386f172d6893dbbd1",
    }

    try:
        data = _http_get(url, params).get("data", {})
        if not data or not data.get("klines"):
            return []

        flows = []
        for line in data["klines"]:
            parts = line.split(",")
            flows.append({
                "date": parts[0],
                "main_net": float(parts[1]),
                "small_net": float(parts[2]),
                "mid_net": float(parts[3]),
                "big_net": float(parts[4]),
                "super_large_net": float(parts[5]),
            })
        return flows
    except Exception:
        return []


def fetch_stock_data(code: str, market: str, kline_days: int = 120) -> dict:
    """
    一站式获取股票全部数据（行情 + K线 + 资金流）
    自动处理请求间隔，避免触发限频
    """
    quote = fetch_realtime_quote(code, market)
    time.sleep(0.5)

    klines = fetch_kline(code, market, days=kline_days)
    time.sleep(0.5)

    money_flow = fetch_money_flow(code, market, days=10)

    return {
        "quote": quote,
        "klines": klines,
        "money_flow": money_flow,
    }
