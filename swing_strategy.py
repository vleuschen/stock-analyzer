"""
波段策略信号判断模块
综合技术指标给出操作建议
"""


def analyze_swing_signals(indicators: dict, money_flow: list[dict] = None) -> dict:
    """
    综合多指标判断波段信号
    返回: {signal, confidence, support_levels, resistance_levels, action, reasons}
    """
    if not indicators:
        return {"signal": "unknown", "confidence": "low", "action": "无法分析", "reasons": []}

    score = 0  # -100 ~ +100，正=看多，负=看空
    reasons = []

    current = indicators["current"]
    ma = indicators["ma"]
    ma_pos = indicators["ma_positions"]
    alignment = indicators["ma_alignment"]
    rsi = indicators["rsi"]
    macd = indicators["macd"]
    boll = indicators["bollinger"]
    vol_ratio = indicators["volume_ratio"]
    volatility = indicators["volatility"]

    # ========== 1. 均线系统（权重 30）==========
    if alignment == "bullish":
        score += 25
        reasons.append("✅ 均线多头排列，趋势向上")
    elif alignment == "bearish":
        score -= 25
        reasons.append("❌ 均线空头排列，趋势向下")
    else:
        reasons.append("⚠️ 均线交织，方向不明")

    # MA5/MA10 位置
    if ma_pos.get("ma5") == "above" and ma_pos.get("ma10") == "above":
        score += 5
        reasons.append("✅ 股价站上MA5和MA10")
    elif ma_pos.get("ma5") == "below" and ma_pos.get("ma10") == "below":
        score -= 5
        reasons.append("❌ 股价跌破MA5和MA10")

    # ========== 2. RSI（权重 20）==========
    rsi14 = rsi.get("rsi14")
    rsi6 = rsi.get("rsi6")

    if rsi14 is not None:
        if rsi14 < 30:
            score += 20
            reasons.append(f"✅ RSI(14)={rsi14:.1f} 超卖区域，反弹概率大")
        elif rsi14 < 40:
            score += 8
            reasons.append(f"🟡 RSI(14)={rsi14:.1f} 偏低，接近超卖")
        elif rsi14 > 70:
            score -= 20
            reasons.append(f"❌ RSI(14)={rsi14:.1f} 超买区域，回调风险大")
        elif rsi14 > 60:
            score -= 5
            reasons.append(f"🟡 RSI(14)={rsi14:.1f} 偏高")
        else:
            reasons.append(f"⚪ RSI(14)={rsi14:.1f} 中性")

    # RSI 金叉（RSI6 上穿 RSI14）
    if rsi6 is not None and rsi14 is not None:
        if rsi6 > rsi14 and rsi6 < 50:
            score += 5
            reasons.append("✅ RSI6上穿RSI14，短期动能好转")

    # ========== 3. MACD（权重 25）==========
    dif = macd.get("dif", 0)
    dea = macd.get("dea", 0)
    hist = macd.get("macd_hist", 0)

    if macd.get("is_golden_cross"):
        score += 25
        reasons.append("✅ MACD金叉！强烈买入信号")
    elif macd.get("is_death_cross"):
        score -= 25
        reasons.append("❌ MACD死叉！卖出信号")
    elif dif > dea and dif > 0:
        score += 10
        reasons.append("✅ MACD多头区域运行")
    elif dif < dea and dif < 0:
        score -= 10
        reasons.append("❌ MACD空头区域运行")
    else:
        reasons.append(f"⚪ MACD DIF={dif:.3f}，等待方向选择")

    # MACD 柱状线变化
    if hist > 0:
        score += 3
    else:
        score -= 3

    # ========== 4. 布林带（权重 15）==========
    boll_pos = boll.get("position", 50)

    if boll_pos < 10:
        score += 15
        reasons.append(f"✅ 触及布林下轨（位置{boll_pos:.0f}%），强支撑")
    elif boll_pos < 30:
        score += 8
        reasons.append(f"🟡 布林带下方区域（位置{boll_pos:.0f}%），接近支撑")
    elif boll_pos > 90:
        score -= 15
        reasons.append(f"❌ 触及布林上轨（位置{boll_pos:.0f}%），强压力")
    elif boll_pos > 70:
        score -= 5
        reasons.append(f"🟡 布林带上方区域（位置{boll_pos:.0f}%），接近压力")
    else:
        reasons.append(f"⚪ 布林带中间区域（位置{boll_pos:.0f}%）")

    # ========== 5. 量价配合（权重 10）==========
    if vol_ratio > 1.5:
        if score > 0:
            score += 10
            reasons.append(f"✅ 放量（量比{vol_ratio:.1f}），配合上涨动能强")
        else:
            score -= 10
            reasons.append(f"❌ 放量（量比{vol_ratio:.1f}），配合下跌抛压重")
    elif vol_ratio < 0.6:
        reasons.append(f"⚠️ 缩量（量比{vol_ratio:.1f}），观望情绪浓")
    else:
        reasons.append(f"⚪ 量能平稳（量比{vol_ratio:.1f}）")

    # ========== 6. 资金流向（附加分）==========
    if money_flow:
        recent_flow = money_flow[-1] if money_flow else None
        if recent_flow:
            main_net = recent_flow.get("main_net", 0)
            if main_net > 0:
                score += 5
                reasons.append(f"✅ 主力资金净流入 {main_net / 10000:.0f}万")
            else:
                score -= 5
                reasons.append(f"❌ 主力资金净流出 {abs(main_net) / 10000:.0f}万")

    # ========== 综合信号判断 ==========
    if score >= 40:
        signal = "strong_buy"
        signal_emoji = "🟢"
        signal_text = "强烈买入"
        action = "建议加仓，突破关键压力位可加大仓位"
        confidence = "high" if score >= 60 else "medium"
    elif score >= 15:
        signal = "buy"
        signal_emoji = "🟢"
        signal_text = "偏多"
        action = "可轻仓试探，设置好止损位"
        confidence = "medium"
    elif score >= -15:
        signal = "neutral"
        signal_emoji = "🟡"
        signal_text = "观望"
        action = "信号不明确，建议等待方向明朗"
        confidence = "low"
    elif score >= -40:
        signal = "sell"
        signal_emoji = "🔴"
        signal_text = "偏空"
        action = "建议减仓，跌破支撑位应果断止损"
        confidence = "medium"
    else:
        signal = "strong_sell"
        signal_emoji = "🔴"
        signal_text = "强烈回避"
        action = "建议清仓离场，等待企稳信号"
        confidence = "high" if score <= -60 else "medium"

    # ========== 支撑位 & 压力位 ==========
    support_levels = []
    resistance_levels = []

    # 布林带支撑/压力
    if boll.get("lower"):
        support_levels.append(("布林下轨", boll["lower"]))
    if boll.get("upper"):
        resistance_levels.append(("布林上轨", boll["upper"]))

    # 均线支撑/压力
    for name, val in [("MA5", ma.get("ma5")), ("MA10", ma.get("ma10")),
                       ("MA20", ma.get("ma20")), ("MA60", ma.get("ma60"))]:
        if val is not None:
            if val < current:
                support_levels.append((name, val))
            else:
                resistance_levels.append((name, val))

    # 20日高低点
    range_20d = indicators.get("range_20d", {})
    if range_20d.get("low"):
        support_levels.append(("20日低点", range_20d["low"]))
    if range_20d.get("high"):
        resistance_levels.append(("20日高点", range_20d["high"]))

    # 排序：支撑位从高到低，压力位从低到高
    support_levels.sort(key=lambda x: x[1], reverse=True)
    resistance_levels.sort(key=lambda x: x[1])

    return {
        "signal": signal,
        "signal_emoji": signal_emoji,
        "signal_text": signal_text,
        "score": score,
        "confidence": confidence,
        "action": action,
        "reasons": reasons,
        "support_levels": support_levels[:3],   # 最多3个支撑
        "resistance_levels": resistance_levels[:3],  # 最多3个压力
    }
