"""
波段策略信号判断模块

评分框架（v2）：
    趋势 ±36  +  动能 ±30  +  位置 ±25  +  量价 ±10  +  资金 ±12

v1 的问题：所有因子简单相加、互相抵消，且「超买就扣分、超卖就加分」不看趋势，
导致上涨的票被自己的 RSI/布林扣回去，最终 60% 的结论是「观望」、27% 是「偏空」，
几乎从不给多头信号。v2 改为分维度评分 + 趋势自适应：
    - 趋势向上时，超买视为强势（小幅加分），超卖视为回调机会
    - 趋势向下时，超卖不再鼓励抄底（避免接飞刀），超买视为反弹结束

v3 用回测结果建立确认门槛（样本 1885、回溯 150 个交易日、前瞻 5 日），v4 在不放弃
风险边界的前提下改成偏进攻：
    - 「强烈买入」使用评分≥45、多头排列、RSI<75、资金不流出；允许参与强势股早段加速，
      但 RSI≥75、趋势未确认或资金流出时仍不追高。
    - 评分≥35 且站上 MA20、动能不弱、资金不流出时，偏多档提示“激进者小仓试错”；
      这不是确定性买点，只有强买档给完整买点/止损/目标。
    - 单笔风险按买点 -6% 封顶，并给出盈亏比，盈亏比不足 1.5 时明确标注。
    注意：样本只有 8 只自选票、7 个月，属于小样本，结论会随行情与票池变化，别当铁律。

另一个回测里很显眼、但**故意没有动手改**的现象：低分区（尤其均线空头排列）的 5 日
超额反而是正的（回避档 +0.44%，空头排列 +0.85%）—— 这批票在回撤后容易反抽。没有据此
加「抄底信号」的原因：一是 7 个月单一 regime 的反转特征，换个行情就会反过来咬人；
二是这套「低买」逻辑项目里已经有了，就是 yypz_strategy 的老龙反抽（超跌 + 缩量 + RSI 超卖），
用两套口径同时表达同一个赌注没有意义。要动这块先重新回测再说。
"""


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _consecutive_days(money_flow: list) -> tuple:
    """返回 (连续净流入天数, 连续净流出天数)，列表为日期倒序"""
    consec_in = consec_out = 0
    for row in money_flow:
        v = _flow_value(row)
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
    return consec_in, consec_out


def _flow_value(row: dict) -> float:
    """
    取资金流金额：优先东财「主力净额」，退化到新浪「超大单净额」。
    数据源不同口径不同，返回值仅用于方向判断与量级展示。
    """
    if not row:
        return 0.0
    main = row.get("main_net")
    if main is not None:
        return main
    return row.get("super_net") or 0.0


def _flow_label(row: dict) -> str:
    return "主力" if (row or {}).get("main_net") is not None else "超大单"


def _fmt_amount(val) -> str:
    """金额格式化（元 → 亿/万）"""
    if val is None:
        return "-"
    sign = "-" if val < 0 else ""
    v = abs(val)
    if v >= 1e8:
        return f"{sign}{v / 1e8:.2f}亿"
    if v >= 1e4:
        return f"{sign}{v / 1e4:.0f}万"
    return f"{sign}{v:.0f}"


def _dedupe_levels(levels: list, current: float, tol: float = 0.012) -> list:
    """去掉彼此过于接近的支撑/压力位（相差 1.2% 以内视为同一位置）"""
    out = []
    for name, price in levels:
        if price is None or price <= 0:
            continue
        # 距离现价超过 20% 的位置没有参考意义
        if current and abs(price - current) / current > 0.20:
            continue
        if any(abs(price - p) / p < tol for _, p in out):
            continue
        out.append((name, price))
    return out


def analyze_swing_signals(indicators: dict, money_flow: list = None) -> dict:
    """
    综合多指标判断波段信号
    返回: {signal, score, confidence, action, reasons, support_levels,
           resistance_levels, trade_plan, flow, dimensions}
    """
    if not indicators:
        return {"signal": "unknown", "confidence": "low", "action": "无法分析",
                "reasons": [], "score": 0, "support_levels": [], "resistance_levels": [],
                "trade_plan": {}, "flow": {}, "dimensions": {}}

    current = indicators["current"]
    ma = indicators.get("ma", {})
    ma_pos = indicators.get("ma_positions", {})
    alignment = indicators.get("ma_alignment", "mixed")
    rsi = indicators.get("rsi", {})
    macd = indicators.get("macd", {})
    boll = indicators.get("bollinger", {})
    vol_ratio = indicators.get("volume_ratio", 1.0)

    ma5, ma10, ma20 = ma.get("ma5"), ma.get("ma10"), ma.get("ma20")
    trend_up = bool(ma20 and current > ma20)
    trend_down = bool(ma20 and current < ma20)

    reasons = []

    # ================= 1. 趋势（±36） =================
    trend_score = 0
    if alignment == "bullish":
        trend_score += 28
        reasons.append("✅ 均线多头排列，趋势向上")
    elif alignment == "bearish":
        trend_score -= 28
        reasons.append("❌ 均线空头排列，趋势向下")
    else:
        if trend_up:
            trend_score += 8
            reasons.append("⚖️ 均线交织，但股价站在 MA20 上方")
        elif trend_down:
            trend_score -= 8
            reasons.append("⚖️ 均线交织，股价位于 MA20 下方")
        else:
            reasons.append("⚖️ 均线交织，方向不明")

    if ma5 and ma10:
        if current > ma5 and current > ma10:
            trend_score += 8
            reasons.append("✅ 站上 MA5 / MA10")
        elif current < ma5 and current < ma10:
            trend_score -= 8
            reasons.append("❌ 跌破 MA5 / MA10")
    trend_score = _clamp(trend_score, -36, 36)

    # ================= 2. 动能（±30） =================
    mom_score = 0
    dif = macd.get("dif", 0)
    dea = macd.get("dea", 0)
    if macd.get("is_golden_cross"):
        mom_score += 20
        reasons.append("✅ MACD 金叉，动能转强")
    elif macd.get("is_death_cross"):
        mom_score -= 20
        reasons.append("❌ MACD 死叉，动能转弱")
    elif dif > dea:
        mom_score += 10 if dif > 0 else 5
        reasons.append("✅ MACD 多头区域运行" if dif > 0 else "🟡 MACD 零轴下方金叉待确认")
    else:
        mom_score -= 10 if dif < 0 else 5
        reasons.append("❌ MACD 空头区域运行" if dif < 0 else "🟡 MACD 零轴上方死叉待确认")

    hist = macd.get("macd_hist", 0)
    hist_prev = macd.get("macd_hist_prev", 0)
    if hist > 0 and hist > hist_prev:
        mom_score += 10
        reasons.append("✅ 红柱放大")
    elif hist > 0:
        mom_score += 3
    elif hist < 0 and hist < hist_prev:
        mom_score -= 10
        reasons.append("❌ 绿柱放大")
    elif hist < 0:
        mom_score -= 3
    mom_score = _clamp(mom_score, -30, 30)

    # ================= 3. 位置：RSI + 布林（±25） =================
    pos_score = 0
    rsi14 = rsi.get("rsi14")
    if rsi14 is not None:
        if rsi14 >= 80:
            pos_score -= 15
            reasons.append(f"⚠️ RSI {rsi14:.1f} 极度超买")
        elif rsi14 >= 70:
            if trend_up:
                pos_score += 4
                reasons.append(f"📈 RSI {rsi14:.1f} 超买（趋势向上，暂不视为卖点）")
            else:
                pos_score -= 12
                reasons.append(f"⚠️ RSI {rsi14:.1f} 超买且趋势不强")
        elif rsi14 >= 55:
            if trend_up:
                pos_score += 10
                reasons.append(f"✅ RSI {rsi14:.1f} 强势区")
            else:
                pos_score += 3
                reasons.append(f"🟡 RSI {rsi14:.1f} 中性偏强")
        elif rsi14 >= 45:
            reasons.append(f"⚪ RSI {rsi14:.1f} 中性")
        elif rsi14 >= 30:
            if trend_down:
                pos_score -= 6
                reasons.append(f"⚠️ RSI {rsi14:.1f} 偏弱（下跌趋势中）")
            else:
                pos_score += 4
                reasons.append(f"🟡 RSI {rsi14:.1f} 偏低，有修复空间")
        else:
            if trend_up:
                pos_score += 10
                reasons.append(f"✅ RSI {rsi14:.1f} 超卖回调，趋势未破")
            else:
                pos_score -= 10
                reasons.append(f"⚠️ RSI {rsi14:.1f} 超卖且趋势向下，不宜抄底")

    boll_pos = boll.get("position", 50)
    if boll_pos < 10:
        if trend_up:
            pos_score += 8
            reasons.append("✅ 回踩布林下轨（趋势向上）")
        else:
            pos_score -= 4
            reasons.append("⚠️ 跌破布林下轨，弱势")
    elif boll_pos < 30:
        pos_score += 4 if trend_up else -2
    elif boll_pos > 90:
        pos_score -= 12
        reasons.append("⚠️ 触及布林上轨，短线过热")
    elif boll_pos > 70:
        if trend_up:
            pos_score += 4
            reasons.append("✅ 运行于布林上轨区（强势）")
        else:
            pos_score -= 5
            reasons.append("⚠️ 布林上轨附近但趋势不强")
    pos_score = _clamp(pos_score, -25, 25)

    # ================= 4. 量价（±10） =================
    vol_score = 0
    if vol_ratio > 1.5:
        if trend_up:
            vol_score += 8
            reasons.append(f"✅ 放量（量比 {vol_ratio:.1f}）配合上行")
        else:
            vol_score -= 8
            reasons.append(f"❌ 放量（量比 {vol_ratio:.1f}）但趋势偏弱，抛压重")
    elif vol_ratio < 0.6:
        vol_score += 2 if trend_up else -2
        reasons.append(f"⚪ 缩量（量比 {vol_ratio:.1f}）")
    vol_score = _clamp(vol_score, -10, 10)

    # ================= 5. 资金（±12，真实主力净额） =================
    flow_score = 0
    flow_detail = {}
    if money_flow:
        latest = money_flow[0]
        main_net = _flow_value(latest)
        label = _flow_label(latest)
        consec_in, consec_out = _consecutive_days(money_flow)
        sum5 = sum(_flow_value(r) for r in money_flow[:5])

        if main_net > 0:
            flow_score += 5
            reasons.append(f"✅ {label}净流入 {_fmt_amount(main_net)}")
            if consec_in >= 3:
                flow_score += 4
                reasons.append(f"✅ {label}连续 {consec_in} 日净流入")
        elif main_net < 0:
            flow_score -= 5
            reasons.append(f"❌ {label}净流出 {_fmt_amount(abs(main_net))}")
            if consec_out >= 3:
                flow_score -= 4
                reasons.append(f"❌ {label}连续 {consec_out} 日净流出")

        if sum5 > 0:
            flow_score += 3
        elif sum5 < 0:
            flow_score -= 3

        flow_detail = {
            "date": latest.get("date", ""),
            "main_net": main_net,
            "label": label,
            "source": latest.get("source", ""),
            "sum5": sum5,
            "consec_in": consec_in,
            "consec_out": consec_out,
        }
    flow_score = _clamp(flow_score, -12, 12)

    # ================= 综合 =================
    score = _clamp(trend_score + mom_score + pos_score + vol_score + flow_score, -100, 100)

    # 「强烈买入」的确认门槛。本自选池 150 个交易日 / 1885 个样本的 5 日前瞻回测：
    #   score>=50 单独用            → 超额 +1.01%，胜率 51%
    #   score>=50 + 多头排列 + RSI<70 + 资金不流出 → 超额 +2.80%，胜率 70%
    #     （去极值后 +2.28%；逐股留一超额均为正；前后半段 +1.30% / +3.01%）
    # 反过来，score>=50 但 RSI>=70 的样本 5 日中位数 -1.10% —— 高分不等于能买，
    # 均线未走多头 / 已经过热 / 资金在流出，都属于「看着强但没人接」，故降级。
    # 进攻口径：仍要求趋势、资金方向一致，但把 RSI 的容忍度从 70 放宽到 75，
    # 允许参与强势股的早段加速；极度过热（>=75）仍不追。
    strong_confirm = (
        alignment == "bullish"
        and rsi14 is not None and rsi14 < 75
        and flow_score >= 0
    )

    if score >= 45 and strong_confirm:
        signal, emoji, text = "strong_buy", "🟢", "强烈买入"
        action = "趋势共振，激进者可分批建仓，跌破支撑止损"
        confidence = "high"
    elif score >= 35 and trend_up and mom_score >= 0 and flow_score >= 0:
        # 偏多不是无脑买点，但给出小仓试错路径，满足偏激进用户的执行需要；
        # 只有强买档才给完整买点/止损/目标，避免把试仓写成确定性买入。
        signal, emoji, text = "buy", "🟢", "偏多"
        action = "趋势/动能占优，激进者可小仓试仓；站稳关键位再加仓"
        confidence = "medium"
    elif score >= 50:
        # 缺什么写什么：泛泛写「等资金回流」，可资金明明在流入，就自相矛盾了
        lacks = []
        if alignment != "bullish":
            lacks.append("均线未多头排列")
        if rsi14 is not None and rsi14 >= 70:
            lacks.append(f"RSI {rsi14:.0f} 偏热")
        if flow_score < 0:
            lacks.append("资金净流出")
        lack_text = "、".join(lacks) or "确认条件不足"
        reasons.append(f"🟡 高分但确认不足（{lack_text}），降级观察")
        signal, emoji, text = "buy", "🟢", "偏多"
        action = f"评分达标但缺确认（{lack_text}），激进者仅小仓试错，不追高"
        confidence = "low"
    elif score >= 25:
        # 回测中这一档（25~50）的 5 日超额为 -0.77%，三段行情全为负，
        # 即「偏多」不是买点，只作为强弱排序用，不给出手建议。
        signal, emoji, text = "buy", "🟢", "偏多"
        action = "偏强整理，尚未形成买点，等信号切换到强烈买入再动手"
        confidence = "low"
    elif score > -25:
        signal, emoji, text = "neutral", "🟡", "观望"
        action = "多空力量接近，等方向明确再动手"
        confidence = "low"
    elif score > -50:
        signal, emoji, text = "sell", "🔴", "偏空"
        action = "动能偏弱，建议减仓，跌破支撑先离场"
        confidence = "medium"
    else:
        signal, emoji, text = "strong_sell", "🔴", "回避"
        action = "趋势与动能同步走坏，规避为主，等企稳信号"
        confidence = "high" if score <= -75 else "medium"

    # ================= 支撑 / 压力 =================
    support_levels = []
    resistance_levels = []

    for lname, val in [("MA5", ma5), ("MA10", ma10), ("MA20", ma20),
                       ("MA60", ma.get("ma60"))]:
        if val is None:
            continue
        (support_levels if val < current else resistance_levels).append((lname, val))

    if boll.get("lower"):
        support_levels.append(("布林下轨", boll["lower"]))
    if boll.get("upper"):
        resistance_levels.append(("布林上轨", boll["upper"]))

    range_20d = indicators.get("range_20d", {})
    if range_20d.get("low"):
        support_levels.append(("20日低点", range_20d["low"]))
    if range_20d.get("high"):
        resistance_levels.append(("20日高点", range_20d["high"]))

    support_levels.sort(key=lambda x: x[1], reverse=True)
    resistance_levels.sort(key=lambda x: x[1])
    support_levels = _dedupe_levels(support_levels, current)[:3]
    resistance_levels = _dedupe_levels(resistance_levels, current)[:3]

    # ================= 操作计划（给出具体价位） =================
    trade_plan = {}
    if support_levels and resistance_levels:
        entry = support_levels[0][1]
        target = resistance_levels[0][1]
        stop = support_levels[1][1] * 0.99 if len(support_levels) > 1 else entry * 0.96
        if stop >= entry:
            stop = entry * 0.96
        # 单笔风险上限 6%：第二支撑位太远时按「买点 -6%」收口，
        # 否则会出现「买点 10 元、止损 8 元」这种一次亏掉两成、实际没人执行的计划。
        stop = max(stop, entry * 0.94)
        if target > entry > stop:
            rr = (target - entry) / (entry - stop)
            trade_plan = {
                "entry": entry,
                "stop": stop,
                "target": target,
                "rr": rr,
                # 盈亏比 1.5 以下：赢面不够覆盖试错成本，推送里标注「偏低」
                "rr_ok": rr >= 1.5,
            }

    return {
        "signal": signal,
        "signal_emoji": emoji,
        "signal_text": text,
        "score": score,
        "confidence": confidence,
        "action": action,
        "reasons": reasons,
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "trade_plan": trade_plan,
        "flow": flow_detail,
        "dimensions": {
            "trend": trend_score,
            "momentum": mom_score,
            "position": pos_score,
            "volume": vol_score,
            "flow": flow_score,
        },
    }
