#!/usr/bin/env python3
"""
yyPZ (游资盘子) 选股策略模块
包含：老龙反抽策略 + 强势股追踪
零外部依赖，使用 Python 内置模块
"""

from __future__ import annotations

import math
import time
from datetime import datetime

from data_fetcher import fetch_stock_data


# ============================================================
# 老龙反抽候选池（约20只前强势股/赛道龙头）
# 这些票是历史上多次充当过"龙头"的标的，有辨识度、有流动性
# 策略逻辑：回踩关键均线 + 缩量企稳 + RSI超卖 = 反抽信号
# ============================================================
OLD_DRAGON_POOL = [
    # === AI / 算力 / 光通信 ===
    {"code": "300308", "name": "中际旭创", "market": "sz", "theme": "AI算力·光模块龙头"},
    {"code": "300502", "name": "新易盛",   "market": "sz", "theme": "AI算力·光模块"},
    {"code": "688041", "name": "海光信息", "market": "sh", "theme": "AI算力·国产CPU"},
    {"code": "603019", "name": "中科曙光", "market": "sh", "theme": "AI算力·服务器"},
    {"code": "000977", "name": "浪潮信息", "market": "sz", "theme": "AI算力·服务器"},
    {"code": "300624", "name": "万兴科技", "market": "sz", "theme": "AI应用"},
    {"code": "688256", "name": "寒武纪",   "market": "sh", "theme": "AI芯片"},

    # === 半导体 ===
    {"code": "002371", "name": "北方华创", "market": "sz", "theme": "半导体设备龙头"},
    {"code": "688981", "name": "中芯国际", "market": "sh", "theme": "半导体制造龙头"},
    {"code": "603501", "name": "韦尔股份", "market": "sh", "theme": "半导体设计龙头"},
    {"code": "300661", "name": "圣邦股份", "market": "sz", "theme": "模拟芯片"},

    # === 新能源 ===
    {"code": "300750", "name": "宁德时代", "market": "sz", "theme": "新能源电池龙头"},
    {"code": "002594", "name": "比亚迪",   "market": "sz", "theme": "新能源汽车龙头"},
    {"code": "605117", "name": "德业股份", "market": "sh", "theme": "逆变器·储能"},
    {"code": "300274", "name": "阳光电源", "market": "sz", "theme": "逆变器·储能龙头"},

    # === 机器人 / 智能制造 ===
    {"code": "300124", "name": "汇川技术", "market": "sz", "theme": "工控自动化龙头"},
    {"code": "688160", "name": "步科股份", "market": "sh", "theme": "机器人·伺服系统"},
    {"code": "002896", "name": "中大力德", "market": "sz", "theme": "机器人·减速器"},

    # === 低空经济 / 飞行汽车 ===
    {"code": "002085", "name": "万丰奥威", "market": "sz", "theme": "低空经济·飞行汽车"},
    {"code": "688631", "name": "莱斯信息", "market": "sh", "theme": "低空经济·空管系统"},

    # === 消费电子 ===
    {"code": "002475", "name": "立讯精密", "market": "sz", "theme": "消费电子精密制造"},
    {"code": "601138", "name": "工业富联", "market": "sh", "theme": "AI服务器·消费电子"},
]


def _calc_rsi_single(closes: list[float], period: int = 14) -> float | None:
    """计算 RSI"""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def _calc_ma(closes: list[float], period: int) -> float | None:
    """简单移动平均"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _calc_volume_ratio(volumes: list[int]) -> float:
    """量比 = 近5日均量 / 近20日均量"""
    if len(volumes) < 20:
        return 1.0
    short_avg = sum(volumes[-5:]) / 5
    long_avg = sum(volumes[-20:]) / 20
    return short_avg / long_avg if long_avg > 0 else 1.0


def _f(val, decimals=2):
    """格式化数字"""
    if val is None:
        return "-"
    return f"{val:.{decimals}f}"


def _pct(val, sign=True):
    """格式化百分比"""
    if val is None:
        return "-"
    s = "+" if val > 0 and sign else ""
    return f"{s}{val:.2f}%"


def analyze_dragon_rebound(stock: dict) -> dict | None:
    """
    分析单只老龙的反抽潜力
    返回包含评分和推荐理由的字典，不符合条件返回 None
    """
    code = stock["code"]
    market = stock.get("market", "sz")
    name = stock.get("name", code)
    theme = stock.get("theme", "")

    # 抓取数据（60天的K线就够了）
    data = fetch_stock_data(code, market, kline_days=90)
    quote = data.get("quote", {})
    klines = data.get("klines", [])

    if quote.get("error") or len(klines) < 30:
        return None

    closes = [k["close"] for k in klines]
    volumes = [k["volume"] for k in klines]
    current_price = quote.get("price", 0)
    pct_change = quote.get("pct_change", 0)
    amount = quote.get("amount", 0)

    # 计算技术指标
    ma5 = _calc_ma(closes, 5)
    ma10 = _calc_ma(closes, 10)
    ma20 = _calc_ma(closes, 20)
    ma60 = _calc_ma(closes, 60)
    rsi14 = _calc_rsi_single(closes, 14)
    rsi6 = _calc_rsi_single(closes, 6)
    vol_ratio = _calc_volume_ratio(volumes)

    # === 反抽评分系统 (0-100) ===
    score = 0
    reasons = []

    # 1. 跌幅深度：近20日跌幅越大，反抽概率越高（但需有企稳迹象）
    chg_20d = ((closes[-1] - closes[-21]) / closes[-21] * 100) if len(closes) >= 21 else 0
    if chg_20d < -20:
        score += 25
        reasons.append(f"📉 近20日跌幅{_f(chg_20d)}%，深度回调提供反抽空间")
    elif chg_20d < -10:
        score += 15
        reasons.append(f"📉 近20日跌幅{_f(chg_20d)}%，回调较为充分")
    elif chg_20d < -5:
        score += 8
        reasons.append(f"📊 近20日跌{_f(chg_20d)}%，轻度回调")

    # 2. RSI超卖信号
    if rsi14 is not None:
        if rsi14 < 25:
            score += 20
            reasons.append(f"💫 RSI(14)={_f(rsi14, 1)}，深度超卖，反弹动能积聚")
        elif rsi14 < 35:
            score += 12
            reasons.append(f"🔄 RSI(14)={_f(rsi14, 1)}，接近超卖区域")
        elif rsi14 < 45:
            score += 5
            reasons.append(f"⚪ RSI(14)={_f(rsi14, 1)}，中性偏低")

    # RSI6上穿RSI14（短期动能转好）
    if rsi6 is not None and rsi14 is not None and rsi6 > rsi14:
        score += 8
        reasons.append("📈 RSI6上穿RSI14，短期动能改善")

    # 3. 缩量企稳（量比 < 0.8 且价格不再创新低）
    if vol_ratio < 0.8:
        score += 10
        reasons.append(f"💤 缩量（量比{_f(vol_ratio, 2)}），抛压衰减")
    elif vol_ratio < 1.0:
        score += 5
        reasons.append(f"⚪ 量能萎缩（量比{_f(vol_ratio, 2)}），杀跌动能减弱")

    # 4. 均线支撑
    support_ma = None
    if ma60 and current_price > ma60:
        support_ma = "MA60"
    elif ma20 and current_price > ma20:
        support_ma = "MA20"
    elif ma10 and current_price > ma10:
        support_ma = "MA10"

    if support_ma:
        score += 8
        value = locals()[f"ma{support_ma[2:]}"]
        reasons.append(f"🛡️ 站上{support_ma}={_f(value)}，获得均线支撑")
    else:
        # 远离均线 = 超跌
        if ma60 and current_price < ma60 * 0.85:
            score += 12
            reasons.append(f"📏 股价低于MA60超15%，严重超跌")

    # 5. 今日跌幅收窄或翻红（企稳迹象）
    if pct_change > 0:
        score += 10
        reasons.append(f"✅ 今日收涨{_pct(pct_change)}，有企稳迹象")
    elif pct_change > -2:
        score += 3
        reasons.append(f"⚪ 今日微跌{_pct(pct_change)}，跌幅收窄")

    # 6. 前两日K线形态（十字星/锤子线 = 止跌信号）
    if len(klines) >= 3:
        k1 = klines[-2]  # 昨日
        k2 = klines[-3]  # 前日
        # 十字星：开盘≈收盘且振幅较大
        k1_body = abs(k1["close"] - k1["open"])
        k1_range = k1["high"] - k1["low"]
        if k1_range > 0 and k1_body / k1_range < 0.15 and k1["close"] > k1["low"] * 0.99:
            score += 5
            reasons.append("⭐ 昨日出现十字星，止跌信号")

    # 7. 主力资金动向
    main_net = quote.get("main_net", 0)
    if main_net > 0:
        score += 5
        reasons.append(f"💰 主力资金净流入{_fmt_amt(main_net)}")

    # 标记是否为强势反抽机会
    if score >= 35:
        confidence = "⭐⭐⭐" if score >= 50 else "⭐⭐"
        signal = "strong_rebound" if score >= 50 else "rebound"
    else:
        return None  # 分数不够，不纳入推送

    return {
        "stock": f"{name}({code})",
        "theme": theme,
        "price": current_price,
        "pct_change": pct_change,
        "score": score,
        "confidence": confidence,
        "signal": signal,
        "rsi14": rsi14,
        "vol_ratio": vol_ratio,
        "chg_20d": chg_20d,
        "reasons": reasons[:4],  # 最多4条理由，保持精简
        "market": market,
        "amount": amount,
    }


def _fmt_amt(val):
    """格式化金额"""
    if val is None or val == 0:
        return "-"
    if abs(val) >= 1e8:
        return f"{val/1e8:.2f}亿"
    elif abs(val) >= 1e4:
        return f"{val/1e4:.0f}万"
    return f"{val:.0f}"


def run_old_dragon_rebound() -> list[dict]:
    """
    运行老龙反抽策略
    扫描候选池，筛选出符合条件的反抽标的，按分数排序
    """
    print(f"\n{'='*50}")
    print(f"🐉 老龙反抽策略扫描")
    print(f"{'='*50}")
    print(f"📋 候选池: {len(OLD_DRAGON_POOL)} 只前强股/龙头股")

    results = []
    for stock in OLD_DRAGON_POOL:
        print(f"  🔍 分析: {stock['name']}({stock['code']}) [{stock['theme']}]...")
        result = analyze_dragon_rebound(stock)
        if result:
            results.append(result)
            print(f"     ✅ 评分{result['score']}分 {result['confidence']} - {result['reasons'][0] if result['reasons'] else ''}")
        time.sleep(0.5)  # API限频

    # 按分数降序排列
    results.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n✅ 老龙反抽扫描完成: {len(results)} 只符合条件")
    return results


def format_dragon_report(results: list[dict], date_str: str) -> str:
    """
    格式化为精良可阅读的报告
    包含：总览统计 → 板块分布 → 逐只推荐卡
    """
    if not results:
        return (
            "## 🐉 yyPZ·老龙反抽策略\n\n"
            "---\n\n"
            "📭 **今日无符合条件标的**\n\n"
            "扫描 22 只赛道龙头，均未触发反抽信号。\n"
            "市场可能处于趋势行情中，或回调尚未充分。\n\n"
            "---\n"
        )

    # ========== 统计 ==========
    strong = sum(1 for r in results if r["signal"] == "strong_rebound")
    normal = sum(1 for r in results if r["signal"] == "rebound")

    # 按板块分组
    sectors_order = []
    sector_map = {}
    for r in results:
        theme = r.get("theme", "其他")
        sector = theme.split("·")[0].strip() if "·" in theme else "其他"
        if sector not in sector_map:
            sector_map[sector] = []
            sectors_order.append(sector)
        sector_map[sector].append(r)

    lines = []
    lines.append(f"## 🐉 yyPZ·老龙反抽策略")
    lines.append("")
    lines.append(
        f"> 📡 扫描 {len(OLD_DRAGON_POOL)} 只赛道龙头 · "
        f"筛选出 **{len(results)} 只** 反抽机会 "
        f"（🚀 强反抽 {strong} 只 / 🔄 一般 {normal} 只）"
    )
    lines.append("")

    # ========== 板块分布 ==========
    if sectors_order:
        lines.append("### 📂 板块分布")
        lines.append("")
        for sector in sectors_order:
            stocks_in_sector = sector_map[sector]
            names = "、".join(s["stock"].split("(")[0] for s in stocks_in_sector)
            count_info = f"{len(stocks_in_sector)}只"
            sc = sum(s["score"] for s in stocks_in_sector)
            avg = round(sc / len(stocks_in_sector))
            lines.append(f"- **{sector}** ({count_info}, 均分 {avg}) — {names}")
        lines.append("")

    # ========== 总览表 ==========
    lines.append("### 📊 评分总览")
    lines.append("")
    lines.append("| # | 标的 | 主题 | 现价 | 涨跌 | 评分 | RSI | 量比 | 信号 |")
    lines.append("|---|------|------|-----:|-----:|----:|----:|----:|:----:|")

    for i, r in enumerate(results, 1):
        name = r["stock"]
        theme = r["theme"]
        price = _f(r["price"])
        pct = _pct(r["pct_change"])
        score = r["score"]
        rsi_v = r.get("rsi14")
        rsi_str = _f(rsi_v, 1) if rsi_v is not None else "-"
        vr = r.get("vol_ratio", 1)
        vr_str = _f(vr, 2)

        # 信号标记
        if r["signal"] == "strong_rebound":
            sig = "🚀 强反抽"
        else:
            sig = "🔄 反抽"

        # 评分星级
        stars = "⭐" * min(3, max(1, score // 20))

        lines.append(
            f"| {i} | **{name}** | {theme} | {price} | {pct} | "
            f"**{score}**{stars} | {rsi_str} | {vr_str} | {sig} |"
        )
    lines.append("")

    # ========== 逐只推荐卡 ==========
    lines.append("### 🎯 个股推荐理由")
    lines.append("")

    for i, r in enumerate(results, 1):
        name = r["stock"]
        theme = r["theme"]
        score = r["score"]
        price = _f(r["price"])
        pct = _pct(r["pct_change"])
        rsi_v = _f(r["rsi14"], 1) if r.get("rsi14") is not None else "N/A"
        chg20 = _f(r.get("chg_20d", 0))

        signal_icon = "🚀" if r["signal"] == "strong_rebound" else "🔄"
        confidence_stars = r.get("confidence", "⭐")

        lines.append(f"**#{i} {signal_icon} {name}** — {theme}　|　评分 {score} {confidence_stars}")
        lines.append("")
        lines.append(f"> | 📊 现价 {price} | 📈 今日 {pct} | 📉 近20日 {chg20}% | 📡 RSI {rsi_v} |")
        lines.append(">")
        for reason in r["reasons"]:
            lines.append(f"> {reason}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ========== 策略说明 ==========
    lines.append("")
    lines.append("📌 **策略说明**")
    lines.append("")
    lines.append(
        "老龙反抽策略追踪前强股/赛道龙头的超跌反弹机会。"
        "评分基于跌幅深度(25%)、RSI超卖(20%)、缩量企稳(10%)、"
        "均线支撑(8%)、企稳信号(15%)、K线形态(5%)、资金流向(5%)等维度。"
        "**35分以上**纳入推送，50分以上标记强反抽。\n\n"
        "⚠️ *以上内容仅供研究参考，不构成投资建议。*"
    )
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    results = run_old_dragon_rebound()
    print(format_dragon_report(results, date_str))
