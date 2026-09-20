"""
分析结果格式化模块
风格：像朋友分享，带点 emoji，少 AI 味儿，看着不累
"""

import signals


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
    """信号标签（词表见 signals.py）"""
    return signals.text(signal)


def _signal_mark(signal):
    """信号标记（emoji 版，run_daily 会反解析它，改词表请去 signals.py）"""
    return signals.mark(signal)


def _flow_net(flow_list):
    """
    取最新一天的资金净额。
    东财口径为「主力净额」，新浪兜底口径为「超大单净额」；
    无数据或字段缺失时返回 0，避免 None 参与比较报错。
    """
    if not flow_list:
        return 0.0
    row = flow_list[0]
    value = row.get("main_net")
    if value is None:
        value = row.get("super_net")
    return value or 0.0


def _flow_label(flow_list) -> str:
    """资金口径名称：东财为「主力」，新浪备用口径为「超大单」"""
    if not flow_list:
        return "主力"
    return "主力" if flow_list[0].get("main_net") is not None else "超大单"


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
            main_net = _flow_net(money_flow)
            flow_label = _flow_label(money_flow)
            if main_net > 1e8:  # 超过1亿
                highlights.append(f"💰 {name} {flow_label}净流入 {_amt(main_net)}")
            elif main_net < -1e8:
                highlights.append(f"💸 {name} {flow_label}净流出 {_amt(abs(main_net))}")

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
        main_net = _flow_net(money_flow)
        small_net = mf.get("small_net") or 0
        flow_label = _flow_label(money_flow)

        if main_net > 0:
            mf_emoji = "🟢"
            mf_dir = "净流入"
        else:
            mf_emoji = "🔴"
            mf_dir = "净流出"

        mf_parts = [f"{mf_emoji}{flow_label}{mf_dir} {_amt(abs(main_net))}"]
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


_SCREENING_TEMPLATE = """## 🔍 每日选股筛选

{summary}

### 📌 满足条件的标的

| 标的 | 触发条件 | 今日涨跌 | 信号 |
|---|---|---|---|
{table}

### 📊 多条件综合评分 Top

{top_picks}

---

"""


def _get_screening_conditions(r: dict) -> tuple[list[str], int]:
    """
    检查单只股票触发了哪些选股条件
    返回: (conditions_list, score)
    """
    ind = r.get("indicators", {})
    swing = r.get("swing", {})
    quote = r.get("quote", {})
    name = r.get("config", {}).get("name", "")
    conditions = []
    score = 0

    macd = ind.get("macd", {})
    rsi14 = ind.get("rsi", {}).get("rsi14")
    ma_align = ind.get("ma_alignment", "")
    vol_ratio = ind.get("volume_ratio", 1)
    boll_pos = ind.get("bollinger", {}).get("position", 50)
    chg_5d = ind.get("price_changes", {}).get("5d", 0)
    signal = swing.get("signal", "")

    # MACD 金叉 (权重最高)
    if macd.get("is_golden_cross"):
        conditions.append("🟢 MACD金叉")
        score += 5

    # MACD 多头运行
    if macd.get("dif", 0) > macd.get("dea", 0) and signal in ("strong_buy", "buy"):
        conditions.append("📈 MACD多头+偏多信号")
        score += 3

    # RSI 超卖 (RSI < 30)
    if rsi14 is not None and rsi14 < 30:
        conditions.append(f"📉 RSI超卖({rsi14:.0f})")
        score += 3

    # RSI 超买 (RSI > 70)
    if rsi14 is not None and rsi14 > 70:
        conditions.append(f"📈 RSI超买({rsi14:.0f})")
        score += 2

    # 放量突破 (量比 > 1.5 + 站上MA10)
    if vol_ratio > 1.5:
        ma_pos = ind.get("ma_positions", {})
        if ma_pos.get("ma10") == "above":
            conditions.append(f"💥 放量突破MA10(量比{vol_ratio:.1f})")
            score += 4

    # 均线多头排列
    if ma_align == "bullish":
        conditions.append("🌱 均线多头排列")
        score += 4

    # 布林带超跌 (触及下轨)
    if boll_pos < 15:
        conditions.append(f"🛡️ 布林超跌(位置{boll_pos:.0f}%)")
        score += 2

    # 布林带强势 (触及上轨)
    if boll_pos > 85:
        conditions.append(f"🔥 布林强势(位置{boll_pos:.0f}%)")
        score += 2

    # 近5日急跌超10% (潜在反弹)
    if chg_5d < -10:
        conditions.append(f"🎢 近5日急跌{chg_5d:.0f}%")
        score += 2

    # 主力资金大幅流入
    money_flow = r.get("money_flow", [])
    if money_flow:
        main_net = _flow_net(money_flow)
        if main_net > 50000000:  # >5000万
            conditions.append("💰 主力大幅流入")
            score += 3
        elif main_net < -50000000:
            conditions.append("💸 主力大幅流出")
            score -= 2

    return conditions, score


def format_daily_screening(results: list) -> str:
    """
    每日选股筛选 —— 从跟踪标的中选出满足条件的个股
    支持筛选条件: MACD金叉/RSI超卖/放量突破/均线多头/布林极端
    """
    # 收集所有触发条件的股票
    triggered = []
    for r in results:
        if r.get("error"):
            continue
        conds, score = _get_screening_conditions(r)
        if conds:  # 至少触发一个条件
            triggered.append((r, conds, score))

    # 按分数降序
    triggered.sort(key=lambda x: x[2], reverse=True)

    total = len([r for r in results if not r.get("error")])
    hit = len(triggered)

    if hit == 0:
        return (
            "## 🔍 每日选股筛选\n\n"
            f"📭 今日跟踪 {total} 只标的，**无标的触发筛选条件**。\n\n"
            "所有标的均处于中性或无序状态，建议继续观望。\n\n---\n\n"
        )

    # 摘要
    cond_summary = {}
    for _r, conds, _s in triggered:
        for c in conds:
            key = c.split("(")[0]  # 去掉括号内细节
            cond_summary[key] = cond_summary.get(key, 0) + 1

    summary_parts = []
    summary_parts.append(f"> 📊 今日跟踪 {total} 只标的，**{hit} 只**触发筛选条件。\n")
    if cond_summary:
        summary_parts.append("> 触发分布：")
        for c, cnt in sorted(cond_summary.items(), key=lambda x: x[1], reverse=True):
            summary_parts.append(f">   - {c}：{cnt} 只")
    summary = "\n".join(summary_parts)

    # 表格
    def _pct_display(val):
        if val is None:
            return "-"
        s = "+" if val > 0 else ""
        return f"{s}{val:.2f}%"

    def _signal_display(signal):
        return f"{signals.mark(signal)} {signals.text(signal)}"

    table_rows = []
    for r, conds, score in triggered:
        name = r.get("config", {}).get("name", "")
        pct = r.get("quote", {}).get("pct_change", 0)
        signal = r.get("swing", {}).get("signal", "")
        cond_str = " · ".join(conds[:3])  # 最多3个条件
        table_rows.append(
            f"| **{name}** | {cond_str} | {_pct_display(pct)} | {_signal_display(signal)} |"
        )
    table = "\n".join(table_rows)

    # Top picks (综合评分最高)
    top = triggered[:5]
    top_lines = []
    for i, (r, conds, score) in enumerate(top, 1):
        name = r.get("config", {}).get("name", "")
        price = r.get("quote", {}).get("price", 0)
        pct = r.get("quote", {}).get("pct_change", 0)
        cond_str = " · ".join(conds[:3])
        top_lines.append(f"  **{i}. {name}** ({_pct_display(pct)}) — {cond_str}")

    top_picks = "\n".join(top_lines) if top_lines else "（无）"

    return _SCREENING_TEMPLATE.format(
        summary=summary,
        table=table,
        top_picks=top_picks,
    )


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
    lines.append("| 📊 标的 | 💰 价格 | 📈 涨跌 | 🎯 信号 | 📐 均线 | 📡 RSI | 🔄 MACD | 💰 资金净额 |")
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
            main_net = _flow_net(money_flow)
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
