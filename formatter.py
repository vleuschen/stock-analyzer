"""
分析结果格式化模块
将技术指标和策略信号格式化为 Markdown，适配方糖推送
"""


def _fmt_num(val, decimals=2):
    """格式化数字"""
    if val is None:
        return "-"
    return f"{val:.{decimals}f}"


def _fmt_amount(val):
    """格式化金额（元 → 亿/万）"""
    if val is None:
        return "-"
    if abs(val) >= 1e8:
        return f"{val / 1e8:.2f}亿"
    elif abs(val) >= 1e4:
        return f"{val / 1e4:.0f}万"
    else:
        return f"{val:.0f}"


def _fmt_pct(val):
    """格式化百分比"""
    if val is None:
        return "-"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.2f}%"


def format_stock_analysis(
    stock_config: dict,
    quote: dict,
    indicators: dict,
    swing: dict,
    date_str: str,
) -> str:
    """
    格式化单只股票的分析报告（Markdown）
    """
    name = stock_config.get("name", quote.get("name", "未知"))
    code = stock_config.get("code", quote.get("code", "------"))

    lines = []
    lines.append(f"## {name}（{code}）")
    lines.append("")

    # ===== 行情快照 =====
    pct = quote.get("pct_change", 0)
    pct_emoji = "📈" if pct > 0 else "📉" if pct < 0 else "➡️"
    lines.append(f"**行情快照** {pct_emoji}")
    lines.append("")
    lines.append(f"| 项目 | 数值 |")
    lines.append(f"|---|---|")
    lines.append(f"| 最新价 | **{_fmt_num(quote.get('price'))}** ({_fmt_pct(pct)}) |")
    lines.append(f"| 开盘 / 最高 / 最低 | {_fmt_num(quote.get('open'))} / {_fmt_num(quote.get('high'))} / {_fmt_num(quote.get('low'))} |")
    lines.append(f"| 成交额 | {_fmt_amount(quote.get('amount'))} |")
    lines.append(f"| 换手率 | {_fmt_pct(quote.get('turnover'))} |")
    lines.append(f"| 振幅 | {_fmt_pct(quote.get('amplitude'))} |")
    lines.append(f"| PE(TTM) | {_fmt_num(quote.get('pe_ttm'))}x |")
    lines.append(f"| PB | {_fmt_num(quote.get('pb'))}x |")
    lines.append(f"| 总市值 | {_fmt_amount(quote.get('total_mv'))} |")
    lines.append("")

    # ===== 技术信号 =====
    signal_emoji = swing.get("signal_emoji", "⚪")
    signal_text = swing.get("signal_text", "未知")
    confidence = swing.get("confidence", "低")
    lines.append(f"**技术信号: {signal_emoji} {signal_text}** （置信度: {confidence}）")
    lines.append("")

    # 均线
    ma = indicators.get("ma", {})
    ma_pos = indicators.get("ma_positions", {})
    alignment = indicators.get("ma_alignment", "")

    alignment_map = {"bullish": "多头排列 📈", "bearish": "空头排列 📉", "mixed": "交织 ⚠️"}
    alignment_text = alignment_map.get(alignment, alignment)

    lines.append(f"- **均线**: {alignment_text}")
    for name_ma, key in [("MA5", "ma5"), ("MA10", "ma10"), ("MA20", "ma20"), ("MA60", "ma60")]:
        val = ma.get(key)
        if val is not None:
            pos = "↑上" if ma_pos.get(key) == "above" else "↓下"
            lines.append(f"  - {name_ma}: {_fmt_num(val)} (股价在{pos})")

    # RSI
    rsi = indicators.get("rsi", {})
    rsi6 = rsi.get("rsi6")
    rsi14 = rsi.get("rsi14")
    if rsi14 is not None:
        rsi_status = "超买" if rsi14 > 70 else "超卖" if rsi14 < 30 else "中性"
        lines.append(f"- **RSI**: RSI6={_fmt_num(rsi6, 1)} / RSI14={_fmt_num(rsi14, 1)} ({rsi_status})")

    # MACD
    macd = indicators.get("macd", {})
    dif = macd.get("dif", 0)
    dea = macd.get("dea", 0)
    macd_hist = macd.get("macd_hist", 0)
    macd_status = ""
    if macd.get("is_golden_cross"):
        macd_status = "🟢 金叉！"
    elif macd.get("is_death_cross"):
        macd_status = "🔴 死叉！"
    elif dif > dea:
        macd_status = "多头"
    else:
        macd_status = "空头"
    lines.append(f"- **MACD**: DIF={_fmt_num(dif, 3)} / DEA={_fmt_num(dea, 3)} / 柱={_fmt_num(macd_hist, 3)} ({macd_status})")

    # 布林带
    boll = indicators.get("bollinger", {})
    lines.append(f"- **布林带**: 上轨{_fmt_num(boll.get('upper'))} / 中轨{_fmt_num(boll.get('middle'))} / 下轨{_fmt_num(boll.get('lower'))}")
    boll_pos = boll.get("position", 50)
    boll_desc = "上轨附近" if boll_pos > 70 else "下轨附近" if boll_pos < 30 else "中轨附近"
    lines.append(f"  - 当前位置: {boll_desc}（{boll_pos:.0f}%）")

    # 量价
    vol_ratio = indicators.get("volume_ratio", 1)
    vol_desc = "放量" if vol_ratio > 1.3 else "缩量" if vol_ratio < 0.7 else "平量"
    lines.append(f"- **量比**: {vol_ratio:.2f} ({vol_desc})")

    # 波动率
    vol = indicators.get("volatility", 0)
    lines.append(f"- **年化波动率**: {_fmt_num(vol, 1)}%")

    # 区间涨跌
    chg = indicators.get("price_changes", {})
    lines.append(f"- **区间涨跌**: 5日{_fmt_pct(chg.get('5d', 0))} / 10日{_fmt_pct(chg.get('10d', 0))} / 20日{_fmt_pct(chg.get('20d', 0))}")
    lines.append("")

    # ===== 波段建议 =====
    lines.append("**波段建议**")
    lines.append("")
    lines.append(f"> **操作**: {swing.get('action', '-')}")
    lines.append("")

    # 支撑位
    support = swing.get("support_levels", [])
    if support:
        support_str = " / ".join(f"{name}({_fmt_num(price)})" for name, price in support)
        lines.append(f"- 📗 支撑位: {support_str}")

    # 压力位
    resistance = swing.get("resistance_levels", [])
    if resistance:
        resist_str = " / ".join(f"{name}({_fmt_num(price)})" for name, price in resistance)
        lines.append(f"- 📕 压力位: {resist_str}")

    lines.append("")

    # ===== 信号明细 =====
    lines.append("<details>")
    lines.append("<summary>📋 信号明细（点击展开）</summary>")
    lines.append("")
    for reason in swing.get("reasons", []):
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def format_full_report(
    stock_results: list[dict],
    date_str: str,
) -> tuple[str, str]:
    """
    格式化完整报告（多只股票合并）
    返回: (title, markdown_body)
    """
    title = f"📊 A股波段分析 | {date_str}"

    lines = []
    lines.append(f"# 📊 A股波段分析报告")
    lines.append(f"")
    lines.append(f"**分析日期**: {date_str}")
    lines.append(f"**跟踪标的**: {len(stock_results)} 只")
    lines.append("")

    # 总览表
    lines.append("## 📋 信号总览")
    lines.append("")
    lines.append("| 股票 | 最新价 | 涨跌幅 | 信号 | 建议 |")
    lines.append("|---|---|---|---|---|")

    for result in stock_results:
        quote = result.get("quote", {})
        swing = result.get("swing", {})
        name = result.get("config", {}).get("name", quote.get("name", ""))
        price = _fmt_num(quote.get("price"))
        pct = _fmt_pct(quote.get("pct_change", 0))
        signal = f"{swing.get('signal_emoji', '')} {swing.get('signal_text', '-')}"
        action = swing.get("action", "-")
        # 截取 action 前 20 字
        if len(action) > 20:
            action = action[:20] + "..."
        lines.append(f"| {name} | {price} | {pct} | {signal} | {action} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 逐只股票详情
    for result in stock_results:
        config = result.get("config", {})
        quote = result.get("quote", {})
        indicators = result.get("indicators", {})
        swing = result.get("swing", {})

        report = format_stock_analysis(config, quote, indicators, swing, date_str)
        lines.append(report)

    # 免责声明
    lines.append("")
    lines.append("> ⚠️ **免责声明**: 以上分析基于技术指标自动生成，仅供参考，不构成投资建议。股市有风险，投资需谨慎。")
    lines.append("")
    lines.append(f"*由 stock-analyzer 自动生成 | {date_str}*")

    return title, "\n".join(lines)
