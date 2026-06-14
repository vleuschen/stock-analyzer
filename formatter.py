"""
分析结果格式化模块
风格：像朋友分享，带点 emoji，少 AI 味儿，看着不累
"""


def _f(val, decimals=2):
    """格式化数字"""
    if val is None:
        return "-"
    return f"{val:.{decimals}f}"


def _amt(val):
    """格式化金额"""
    if val is None or val == 0:
        return "-"
    if abs(val) >= 1e8:
        return f"{val / 1e8:.2f}亿"
    elif abs(val) >= 1e4:
        return f"{val / 1e4:.0f}万"
    return f"{val:.0f}"


def _pct(val, sign=True):
    """格式化百分比"""
    if val is None:
        return "-"
    s = "+" if val > 0 and sign else ""
    return f"{s}{val:.2f}%"


def _signal_tag(signal):
    """信号标签"""
    tags = {
        "strong_buy": "买入",
        "buy": "偏多",
        "neutral": "观望",
        "sell": "偏空",
        "strong_sell": "回避",
    }
    return tags.get(signal, "未知")


def _signal_mark(signal):
    """信号标记（emoji版）"""
    marks = {
        "strong_buy": "🚀",    # 火箭，冲！
        "buy": "📈",           # 向上
        "neutral": "⏳",       # 等一等
        "sell": "📉",          # 向下
        "strong_sell": "⚠️",   # 小心
    }
    return marks.get(signal, "❓")


def _collect_highlights(results: list) -> list:
    """从所有股票中收集值得关注的亮点，带 emoji"""
    highlights = []

    for r in results:
        name = r.get("config", {}).get("name", "")
        ind = r.get("indicators", {})
        swing = r.get("swing", {})
        macd = ind.get("macd", {})
        rsi = ind.get("rsi", {})
        boll = ind.get("bollinger", {})
        ma_pos = ind.get("ma_positions", {})
        chg = ind.get("price_changes", {})
        vol_ratio = ind.get("volume_ratio", 1)

        # MACD 金叉
        if macd.get("is_golden_cross"):
            highlights.append(f"🟢 {name} MACD 金叉，短期动能转强")

        # MACD 死叉
        if macd.get("is_death_cross"):
            highlights.append(f"🔴 {name} MACD 死叉，注意短期风险")

        # RSI 超卖
        rsi14 = rsi.get("rsi14")
        if rsi14 is not None:
            if rsi14 < 20:
                highlights.append(f"📉 {name} RSI={_f(rsi14, 1)}，极度超卖，关注反弹机会")
            elif rsi14 < 30:
                highlights.append(f"📊 {name} RSI={_f(rsi14, 1)}，进入超卖区间")
            elif rsi14 > 80:
                highlights.append(f"📈 {name} RSI={_f(rsi14, 1)}，极度超买，警惕回调")
            elif rsi14 > 70:
                highlights.append(f"📊 {name} RSI={_f(rsi14, 1)}，进入超买区间")

        # 布林带极端位置
        boll_pos = boll.get("position", 50)
        if boll_pos < 10:
            highlights.append(f"🛡️ {name} 触及布林下轨，短线超跌")
        elif boll_pos > 90:
            highlights.append(f"🔥 {name} 触及布林上轨，短线强势")

        # 放量突破均线
        if vol_ratio > 1.5 and ma_pos.get("ma10") == "above" and ma_pos.get("ma20") == "below":
            highlights.append(f"💥 {name} 放量突破 MA10，关注能否站稳 MA20")

        # 均线多头/空头排列
        alignment = ind.get("ma_alignment", "")
        if alignment == "bullish":
            highlights.append(f"🌱 {name} 均线转为多头排列，趋势向好")

        # 大幅波动
        chg5 = chg.get("5d", 0)
        if abs(chg5) > 10:
            direction = "急涨" if chg5 > 0 else "急跌"
            highlights.append(f"🎢 {name} 近5日{direction} {_pct(chg5)}")

        # 主力资金大幅流入/流出
        money_flow = r.get("money_flow", [])
        if money_flow:
            main_net = money_flow[0].get("main_net", 0)
            if main_net > 1e8:  # 超过1亿
                highlights.append(f"💰 {name} 主力净流入 {_amt(main_net)}")
            elif main_net < -1e8:
                highlights.append(f"💸 {name} 主力净流出 {_amt(abs(main_net))}")

    return highlights


def format_daily_summary(results: list, date_str: str) -> str:
    """生成每日市场总结——像人话"""
    lines = []

    # 统计信号分布
    signals = {}
    for r in results:
        s = r.get("swing", {}).get("signal", "unknown")
        signals[s] = signals.get(s, 0) + 1

    buy_count = signals.get("strong_buy", 0) + signals.get("buy", 0)
    neutral_count = signals.get("neutral", 0)
    sell_count = signals.get("sell", 0) + signals.get("strong_sell", 0)
    total = len(results)

    # 市场情绪——说得像人话
    if buy_count > sell_count * 2:
        mood_emoji = "☀️"
        mood = "今天整体偏暖，多数标的有积极信号"
    elif sell_count > buy_count * 2:
        mood_emoji = "🌧️"
        mood = "今天比较疲软，大部分标的还在往下走"
    elif sell_count > buy_count:
        mood_emoji = "⛅"
        mood = "偏弱震荡，空头占优，不过也不算太极端"
    elif buy_count > sell_count:
        mood_emoji = "🌤️"
        mood = "震荡偏强，部分标的有企稳的苗头"
    else:
        mood_emoji = "🌊"
        mood = "多空僵持，信号比较乱"

    # 开头——简洁自然
    lines.append(f"{mood_emoji} 跟踪 {total} 只标的，{mood}")
    lines.append("")

    # 信号分布（一行带过）
    parts = []
    if buy_count:
        parts.append(f"看好 {buy_count} 只")
    if neutral_count:
        parts.append(f"观望 {neutral_count} 只")
    if sell_count:
        parts.append(f"看空 {sell_count} 只")
    lines.append(f"{' · '.join(parts)}")
    lines.append("")

    # 亮点——有情况才列
    highlights = _collect_highlights(results)
    if highlights:
        lines.append("**👀 值得看看：**")
        lines.append("")
        for h in highlights:
            lines.append(f"- {h}")
        lines.append("")

    return "\n".join(lines)


def format_stock_brief(r: dict) -> str:
    """格式化单只股票简报——笔记风格"""
    config = r.get("config", {})
    quote = r.get("quote", {})
    ind = r.get("indicators", {})
    swing = r.get("swing", {})

    name = config.get("name", "")
    code = config.get("code", "")
    price = quote.get("price", 0)
    pct = quote.get("pct_change", 0)
    signal = swing.get("signal", "")
    action = swing.get("action", "")
    score = swing.get("score", 0)
    ma_align = ind.get("ma_alignment", "")
    rsi14 = ind.get("rsi", {}).get("rsi14")
    macd = ind.get("macd", {})
    boll = ind.get("bollinger", {})
    vol_ratio = ind.get("volume_ratio", 1)
    chg = ind.get("price_changes", {})

    lines = []
    # 标题行：股票名 + emoji信号
    lines.append(f"### {name}（{code}）{_signal_mark(signal)} {_signal_tag(signal)}")
    lines.append("")

    # 价格 + 涨跌 + 成交
    arrow = " 🔺" if pct > 0 else " 🔻" if pct < 0 else ""
    lines.append(f"**{_f(price)}** {arrow}（{_pct(pct)}）  💰 {_amt(quote.get('amount'))}  换手{_f(quote.get('turnover'), 1)}%")
    lines.append("")

    # 技术面——紧凑但不枯燥
    tech_parts = []

    # 均线
    align_text = {"bullish": "多头📈", "bearish": "空头📉", "mixed": "交织⚖️"}.get(ma_align, "")
    if align_text:
        tech_parts.append(f"均线{align_text}")

    # RSI
    if rsi14 is not None:
        if rsi14 > 70:
            tech_parts.append(f"RSI {_f(rsi14, 1)} ⚠️超买")
        elif rsi14 < 30:
            tech_parts.append(f"RSI {_f(rsi14, 1)} 💫超卖")
        else:
            tech_parts.append(f"RSI {_f(rsi14, 1)}")

    # MACD
    if macd.get("is_golden_cross"):
        tech_parts.append("MACD 🟢金叉")
    elif macd.get("is_death_cross"):
        tech_parts.append("MACD 🔴死叉")
    elif macd.get("dif", 0) > macd.get("dea", 0):
        tech_parts.append("MACD 多头")
    else:
        tech_parts.append("MACD 空头")

    # 量能
    if vol_ratio > 1.5:
        tech_parts.append(f"💥放量({_f(vol_ratio, 1)})")
    elif vol_ratio < 0.6:
        tech_parts.append(f"💤缩量({_f(vol_ratio, 1)})")

    lines.append(" · ".join(tech_parts))
    lines.append("")

    # 资金流向
    money_flow = r.get("money_flow", [])
    if money_flow:
        mf = money_flow[0]
        main_net = mf.get("main_net", 0)
        small_net = mf.get("small_net", 0)

        if main_net > 0:
            mf_emoji = "🟢"
            mf_dir = "净流入"
        else:
            mf_emoji = "🔴"
            mf_dir = "净流出"

        mf_parts = [f"{mf_emoji}主力{mf_dir} {_amt(abs(main_net))}"]
        if small_net > 0:
            mf_parts.append(f"小单+{_amt(small_net)}")
        elif small_net < 0:
            mf_parts.append(f"小单{_amt(small_net)}")
        lines.append(" · ".join(mf_parts))
        lines.append("")

    # 布林位置
    boll_pos = boll.get("position", 50)
    boll_emoji = "⬆️" if boll_pos > 60 else "⬇️" if boll_pos < 40 else "➡️"
    lines.append(f"📐 布林{boll_emoji}（{_f(boll_pos, 0)}%）")

    # 支撑 / 压力
    support = swing.get("support_levels", [])
    resist = swing.get("resistance_levels", [])
    info_parts = []
    if support:
        s_str = " · ".join(f"{n} {_f(p)}" for n, p in support[:2])
        info_parts.append(f"🛡️ {s_str}")
    if resist:
        r_str = " · ".join(f"{n} {_f(p)}" for n, p in resist[:2])
        info_parts.append(f"🧱 {r_str}")
    if info_parts:
        lines.append(" | ".join(info_parts))
    lines.append("")

    # 操作建议（核心结论）
    lines.append(f"> {action}")
    lines.append("")

    return "\n".join(lines)


def format_full_report(results: list, date_str: str) -> tuple:
    """
    格式化完整报告
    返回: (title, markdown_body)
    """
    title = f"📊 波段分析 {len(results)} 只 | {date_str}"

    lines = []

    # === 每日总结 ===
    lines.append(format_daily_summary(results, date_str))
    lines.append("---")
    lines.append("")

    # === 总览表 ===
    lines.append("| 📊 标的 | 💰 价格 | 📈 涨跌 | 🎯 信号 | 📐 均线 | 📡 RSI | 🔄 MACD | 💰 主力净流入 |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for r in results:
        config = r.get("config", {})
        quote = r.get("quote", {})
        ind = r.get("indicators", {})
        swing = r.get("swing", {})

        name = config.get("name", "")
        price = _f(quote.get("price"))
        pct = _pct(quote.get("pct_change", 0))
        tag = _signal_tag(swing.get("signal", ""))
        align = {"bullish": "多📈", "bearish": "空📉", "mixed": "混⚖️"}.get(ind.get("ma_alignment", ""), "-")

        rsi14 = ind.get("rsi", {}).get("rsi14")
        rsi_str = _f(rsi14, 0) if rsi14 else "-"
        # 极端值加标记
        if rsi14 and rsi14 < 30:
            rsi_str += "💫"
        elif rsi14 and rsi14 > 70:
            rsi_str += "⚠️"

        macd = ind.get("macd", {})
        if macd.get("is_golden_cross"):
            macd_str = "🟢金叉"
        elif macd.get("is_death_cross"):
            macd_str = "🔴死叉"
        elif macd.get("dif", 0) > macd.get("dea", 0):
            macd_str = "多"
        else:
            macd_str = "空"

        # 资金流向
        money_flow = r.get("money_flow", [])
        if money_flow:
            main_net = money_flow[0].get("main_net", 0)
            if main_net > 0:
                mf_str = f"🟢+{_amt(main_net)}"
            elif main_net < 0:
                mf_str = f"🔴{_amt(main_net)}"
            else:
                mf_str = "⚪0"
        else:
            mf_str = "-"

        lines.append(f"| {name} | {price} | {pct} | {tag} | {align} | {rsi_str} | {macd_str} | {mf_str} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # === 逐只详情 ===
    for r in results:
        lines.append(format_stock_brief(r))
        lines.append("---")
        lines.append("")

    # 底部——自然一点
    lines.append(f"📬 {date_str} 盘后笔记 · 仅供复盘参考，不构成投资建议")

    return title, "\n".join(lines)
