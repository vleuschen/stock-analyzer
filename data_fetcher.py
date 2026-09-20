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


def _https_get_json(host: str, path: str, timeout: int = 15, encoding: str = "utf-8",
                    extra_headers: dict = None) -> any:
    """通过 http.client 直连 HTTPS，返回解析后的 JSON"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://{host}/",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }
    if extra_headers:
        headers.update(extra_headers)
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

    # ⚠️ 注意：腾讯行情接口第 62/70/71 号字段是「年初至今/20日/60日涨跌幅(%)」，
    # 不是资金流向。历史版本曾把它们当资金流使用，导致数据完全错误（已修正）。
    # 这些区间涨跌幅这里顺手保留下来，字段名如实标注。
    chg_ytd = safe_float(fields[62]) if len(fields) > 62 else 0.0
    chg_20d = safe_float(fields[70]) if len(fields) > 70 else 0.0
    chg_60d = safe_float(fields[71]) if len(fields) > 71 else 0.0

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
        # 区间涨跌幅（腾讯行情内嵌，单位 %）
        "chg_ytd": chg_ytd,
        "chg_20d": chg_20d,
        "chg_60d": chg_60d,
    }


# 东方财富市场前缀：1=沪市, 0=深市/北交所
_EM_PREFIX = {"sh": "1", "sz": "0", "bj": "0"}

# 资金流接口的限流 / 熔断状态（避免被数据源封 IP）
_FLOW_STATE = {"last_call": 0.0, "em_fail": 0, "em_off": False,
               "sina_fail": 0, "sina_off": False}

# 东方财富资金流端点（按「能拿到多长历史」排序）
#   push2his + daykline = 真正的历史资金流接口，可返回 lmt 根日线
#   push2 / push2delay 的同名接口只返回最新一根，仅作兜底
_EM_FLOW_ENDPOINTS = [
    ("push2his.eastmoney.com", "/api/qt/stock/fflow/daykline/get"),
    ("push2.eastmoney.com", "/api/qt/stock/fflow/daykline/get"),
    ("push2delay.eastmoney.com", "/api/qt/stock/fflow/daykline/get"),
]

# 少于该行数就不算拿到了历史（连续流入天数 / 近5日累计会失真），改用备用源
_MIN_FLOW_ROWS = 3

# 端点级熔断：东财按 IP 限流，某个域名连续失败两次就不再撞它，避免拖慢整轮
_EM_HOST_FAIL = {host: 0 for host, _ in _EM_FLOW_ENDPOINTS}


def _throttle(min_interval: float = 0.4):
    """两次资金流请求之间至少间隔 min_interval 秒"""
    delta = time.time() - _FLOW_STATE["last_call"]
    if delta < min_interval:
        time.sleep(min_interval - delta)
    _FLOW_STATE["last_call"] = time.time()


def _to_float(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _fetch_flow_eastmoney(code: str, market: str, days: int) -> list:
    """东方财富资金流：主力/大单/超大单/中单/小单 全口径（单位：元）"""
    if _FLOW_STATE["em_off"]:
        return []

    prefix = _EM_PREFIX.get(market.lower(), "0")
    query = (
        f"?lmt={days}&klt=101&secid={prefix}.{code}"
        "&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    )

    klines = []
    for host, api in _EM_FLOW_ENDPOINTS:
        if _EM_HOST_FAIL[host] >= 2:
            continue
        _throttle()
        try:
            data = _https_get_json(
                host, api + query, timeout=12,
                extra_headers={"Referer": "https://data.eastmoney.com/"},
            )
        except Exception:
            _EM_HOST_FAIL[host] += 1
            continue
        rows = (data or {}).get("data", {}).get("klines") if isinstance(data, dict) else None
        _EM_HOST_FAIL[host] = 0
        if rows and len(rows) > len(klines):
            klines = rows
        if len(klines) >= days:
            break

    if len(klines) < _MIN_FLOW_ROWS:
        _FLOW_STATE["em_fail"] += 1
        if _FLOW_STATE["em_fail"] >= 3:
            _FLOW_STATE["em_off"] = True
            print("  ⚠️ 东方财富资金流连续失败，本次运行改用备用数据源")
        return []

    _FLOW_STATE["em_fail"] = 0
    rows = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 6:
            continue
        rows.append({
            "date": parts[0],
            # 东财口径：f52=主力净额, f53=小单, f54=中单, f55=大单, f56=超大单
            "main_net": _to_float(parts[1]),
            "small_net": _to_float(parts[2]),
            "medium_net": _to_float(parts[3]),
            "big_net": _to_float(parts[4]),
            "super_net": _to_float(parts[5]),
            "source": "eastmoney",
        })
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def _fetch_flow_sina(code: str, market: str, days: int) -> list:
    """
    新浪资金流（备用数据源）：提供超大单净额与净流入总额，单位：元
    注意：口径与东财不同，主力净额记为 None，只提供超大单 net。
    """
    if _FLOW_STATE["sina_off"]:
        return []

    symbol = f"{market.lower()}{code}"
    path = ("/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs"
            f"?page=1&num={days}&sort=opendate&asc=0&daima={symbol}")

    data = None
    for attempt in range(2):
        _throttle()
        try:
            data = _https_get_json(
                "vip.stock.finance.sina.com.cn", path, timeout=12,
                extra_headers={"Referer": "https://finance.sina.com.cn/"},
            )
            break
        except Exception:
            if attempt == 0:
                time.sleep(1.5)

    if not isinstance(data, list) or not data:
        _FLOW_STATE["sina_fail"] += 1
        if _FLOW_STATE["sina_fail"] >= 3:
            _FLOW_STATE["sina_off"] = True
            print("  ⚠️ 新浪资金流连续失败，本次运行不再尝试")
        return []

    _FLOW_STATE["sina_fail"] = 0
    rows = []
    for item in data:
        date = str(item.get("opendate", ""))
        if not date:
            continue
        rows.append({
            "date": date,
            "main_net": None,                       # 新浪不提供主力口径
            "super_net": _to_float(item.get("r0_net")),   # 超大单净额
            "net_amount": _to_float(item.get("netamount")),
            "source": "sina",
        })
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def fetch_money_flow(code: str, market: str, days: int = 10) -> list[dict]:
    """
    获取个股资金流向（单位：元），返回按日期倒序的列表，[0] 为最新交易日。

    数据源优先级：东方财富（全口径）→ 新浪（超大单口径）。
    "main_net" 仅在东方财富口径下存在；新浪口径使用 "super_net"。
    两个数据源都失败时返回空列表，调用方需能降级（推送里不显示资金行）。
    """
    rows = _fetch_flow_eastmoney(code, market, days)
    if rows:
        return rows
    return _fetch_flow_sina(code, market, days)


def flow_main(flow: dict) -> float:
    """取该条资金流记录可用的「主力口径」金额（东财 main_net，退化到新浪超大单）"""
    if not flow:
        return 0.0
    if flow.get("main_net") is not None:
        return flow["main_net"]
    return flow.get("super_net") or 0.0


def flow_label(flow: dict) -> str:
    """资金口径说明，用于推送里如实标注数据来源口径"""
    if not flow:
        return "资金"
    return "主力" if flow.get("main_net") is not None else "超大单"


def latest_flow(money_flow: list[dict]) -> dict:
    """取最新一天的资金流向记录（列表为倒序存储，[0] 即最新）"""
    if not money_flow:
        return {}
    return money_flow[0]


def summarize_money_flow(money_flow: list[dict]) -> dict:
    """
    汇总资金流向：最新一日、连续净流入/流出天数、近5日累计主力净额
    """
    if not money_flow:
        return {}

    latest = money_flow[0]
    consec_in = 0
    consec_out = 0
    for row in money_flow:
        v = flow_main(row)
        if v > 0:
            if consec_out:
                break
            consec_in += 1
        elif v < 0:
            if consec_in:
                break
            consec_out += 1
        else:
            break

    return {
        "latest": latest,
        "sum5": sum(flow_main(r) for r in money_flow[:5]),
        "consec_in": consec_in,
        "consec_out": consec_out,
        "label": flow_label(latest),
        "source": latest.get("source", ""),
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


def _fmt_money(val: float) -> str:
    """格式化金额显示"""
    if val is None or val == 0:
        return "0"
    if abs(val) >= 1e8:
        return f"{val / 1e8:.2f}亿"
    elif abs(val) >= 1e4:
        return f"{val / 1e4:.0f}万"
    return f"{val:.0f}"


def fetch_stock_data(code: str, market: str, kline_days: int = 120) -> dict:
    """
    一站式获取股票全部数据（行情 + K线 + 资金流向）
    资金流向来自东方财富 fflow 接口（真实主力/大单/中单/小单净额）
    """
    quote = fetch_realtime_quote(code, market)
    time.sleep(0.3)

    klines = fetch_kline(code, market, days=kline_days)
    time.sleep(0.3)

    money_flow = fetch_money_flow(code, market)
    latest = latest_flow(money_flow)
    main_net = flow_main(latest)
    if main_net:
        _dir = "净流入" if main_net > 0 else "净流出"
        print(f"  ✅ 资金流向({latest.get('date', '')}): "
              f"{flow_label(latest)}{_dir} {_fmt_money(abs(main_net))} [{latest.get('source', '')}]")

    # 数据日期以 K 线最新一根为准（周末/节假日运行时避免误标成当天）
    data_date = klines[-1]["date"] if klines else ""

    return {
        "quote": quote,
        "klines": klines,
        "money_flow": money_flow,
        "flow_summary": summarize_money_flow(money_flow),
        "data_date": data_date,
    }
