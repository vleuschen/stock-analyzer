"""
Server酱 / 微信推送正文排版模块

设计原则（针对「微信里可读性差」的问题）：
1. 不用 Markdown 表格、标题(#)、加粗(**)——微信卡片里不渲染，会露出原始符号
2. 信息分层：一句话结论 → 今天的变化 → 值得关注 → 全量一览 → 策略池 → 观点
3. 关键数字给出具体价位（支撑/压力/止损），而不是只说「观望」
4. 「今天的变化」优先于「今天的状态」，避免每天推送内容雷同
5. 单条控制在 1200 字以内，手机一屏能扫完重点

输出为纯文本（保留 emoji 和【】分节符），Markdown 与纯文本两种渲染下都不会显示错乱。
"""

SIGNAL_EMOJI = {
    "strong_buy": "🟢",
    "buy": "🟢",
    "neutral": "🟡",
    "sell": "🔴",
    "strong_sell": "⚠️",
}

SIGNAL_TEXT = {
    "strong_buy": "买入",
    "buy": "偏多",
    "neutral": "观望",
    "sell": "偏空",
    "strong_sell": "回避",
}

SIGNAL_RANK = {"strong_buy": 0, "buy": 1, "neutral": 2, "sell": 3, "strong_sell": 4}


def _pct(v, digits=2):
    if v is None:
        return "-"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.{digits}f}%"


def _num(v, digits=2):
    if v is None:
        return "-"
    return f"{v:.{digits}f}"


def _amount(v):
    """元 → 亿/万，带正负号"""
    if not v:
        return "-"
    sign = "+" if v > 0 else "-"
    a = abs(v)
    if a >= 1e8:
        return f"{sign}{a / 1e8:.2f}亿"
    if a >= 1e4:
        return f"{sign}{a / 1e4:.0f}万"
    return f"{sign}{a:.0f}"


def _label(signal):
    return f"{SIGNAL_EMOJI.get(signal, '❔')}{SIGNAL_TEXT.get(signal, '未知')}"


def _fmt_date_label(data_date: str) -> str:
    """2026-09-18 → 9月18日"""
    try:
        y, m, d = data_date.split("-")
        return f"{int(m)}月{int(d)}日"
    except (ValueError, AttributeError):
        return data_date or ""


def build_push_title(data_date: str, n_stocks: int, signal_counts: dict = None) -> str:
    """推送标题，控制在 32 字以内"""
    date_label = _fmt_date_label(data_date)
    counts = signal_counts or {}
    bullish = counts.get("strong_buy", 0) + counts.get("buy", 0)
    bearish = counts.get("sell", 0) + counts.get("strong_sell", 0)

    if bullish and not bearish:
        tag = f"偏多{bullish}只"
    elif bearish and not bullish:
        tag = f"偏空{bearish}只"
    elif bullish or bearish:
        tag = f"多{bullish}空{bearish}"
    else:
        tag = "全线观望"
    return f"📊 {date_label}复盘｜{n_stocks}只·{tag}"


def _section_index(indices: list) -> list:
    if not indices:
        return []
    lines = ["【大盘】"]
    for label, price, pct in indices:
        lines.append(f"{label} {_num(price)} {_pct(pct)}")
    return lines


def _section_summary(valid: list, signal_counts: dict) -> list:
    pcts = [r.get("quote", {}).get("pct_change", 0) or 0 for r in valid]
    up = sum(1 for p in pcts if p > 0)
    down = sum(1 for p in pcts if p < 0)
    flat = len(pcts) - up - down
    avg = sum(pcts) / len(pcts) if pcts else 0

    best = max(valid, key=lambda r: r.get("quote", {}).get("pct_change", 0) or 0)
    worst = min(valid, key=lambda r: r.get("quote", {}).get("pct_change", 0) or 0)

    lines = ["", "【自选表现】"]
    lines.append(f"涨{up} 平{flat} 跌{down}｜均幅 {_pct(avg)}")
    lines.append(
        f"最强 {best.get('config', {}).get('name', '')} "
        f"{_pct(best.get('quote', {}).get('pct_change', 0))}｜"
        f"最弱 {worst.get('config', {}).get('name', '')} "
        f"{_pct(worst.get('quote', {}).get('pct_change', 0))}"
    )
    lines.append(
        f"信号：偏多{signal_counts.get('strong_buy', 0) + signal_counts.get('buy', 0)}"
        f" 观望{signal_counts.get('neutral', 0)}"
        f" 偏空{signal_counts.get('sell', 0) + signal_counts.get('strong_sell', 0)}"
    )
    return lines


def _section_changes(valid: list, prev_signals: dict) -> list:
    """今天相比上一个交易日发生信号切换的标的"""
    lines = ["", "【今日变化】"]
    changes = []
    for r in valid:
        name = r.get("config", {}).get("name", "")
        sig = r.get("swing", {}).get("signal", "")
        prev = (prev_signals or {}).get(name)
        if not prev or prev == sig:
            continue
        direction_up = SIGNAL_RANK.get(sig, 9) < SIGNAL_RANK.get(prev, 9)
        mark = "🔺" if direction_up else "🔻"
        pct = r.get("quote", {}).get("pct_change", 0)
        why = _key_reason(r, upgrading=direction_up)
        changes.append(f"{mark} {name} {SIGNAL_TEXT.get(prev, prev)}→{SIGNAL_TEXT.get(sig, sig)}"
                       f"（{_pct(pct, 1)}）{why}")

    if changes:
        lines.extend(changes[:6])
    else:
        lines.append("今天没有信号切换，维持昨日状态")
    return lines


def _key_reason(r: dict, upgrading: bool = True) -> str:
    """从 swing 的理由里挑一条与信号变化方向一致的说明"""
    reasons = r.get("swing", {}).get("reasons", []) or []
    prefixes = ("✅",) if upgrading else ("❌", "⚠️")
    hits = [x for x in reasons if x.startswith(prefixes)] or reasons
    for reason in hits:
        text = reason.lstrip("✅❌⚠️📈📉🟡⚪ ").strip()
        if text:
            return f"· {text[:22]}"
    return ""


def _section_focus(valid: list, max_items: int = 3) -> list:
    """值得关注的标的：偏多/买入优先，其次是明确的风险"""
    lines = ["", "【值得关注】"]

    ups = [r for r in valid if r.get("swing", {}).get("signal") in ("strong_buy", "buy")]
    ups.sort(key=lambda r: r.get("swing", {}).get("score", 0), reverse=True)

    risks = [r for r in valid
             if r.get("swing", {}).get("signal") in ("sell", "strong_sell")
             and abs(r.get("swing", {}).get("score", 0)) >= 30]
    risks.sort(key=lambda r: r.get("swing", {}).get("score", 0))

    picks = ups[:max_items]
    if len(picks) < max_items:
        picks += risks[:max_items - len(picks)]

    if not picks:
        lines.append("今天没有达到出手标准的标的，继续等待")
        return lines

    for i, r in enumerate(picks, 1):
        cfg = r.get("config", {})
        quote = r.get("quote", {})
        ind = r.get("indicators", {})
        swing = r.get("swing", {})
        flow = swing.get("flow", {}) or {}

        lines.append(
            f"{i}. {cfg.get('name', '')}（{cfg.get('code', '')}）"
            f"{_label(swing.get('signal', ''))} {swing.get('score', 0):+.0f}分"
        )
        lines.append(
            f"   {_num(quote.get('price'))} {_pct(quote.get('pct_change'))}｜"
            f"RSI {_num(ind.get('rsi', {}).get('rsi14'), 0)}｜"
            f"量比 {_num(ind.get('volume_ratio'), 1)}"
        )
        if flow:
            label = flow.get("label", "主力")
            net = flow.get("main_net")
            if net is None:
                net = flow.get("super_net")
            if net and net > 0:
                consec = f"连续流入{flow.get('consec_in', 1)}天"
            elif net:
                consec = f"连续流出{flow.get('consec_out', 1)}天"
            else:
                consec = "资金持平"
            lines.append(
                f"   {label}资金 {_amount(net)}"
                f"｜近5日 {_amount(flow.get('sum5'))}"
                f"｜{consec}"
            )

        plan = swing.get("trade_plan") or {}
        if plan:
            lines.append(
                f"   买点 {_num(plan.get('entry'))}｜止损 {_num(plan.get('stop'))}｜"
                f"目标 {_num(plan.get('target'))}（盈亏比 {_num(plan.get('rr'), 1)}）"
            )
        lines.append(f"   操作：{swing.get('action', '')}")
    return lines


def _section_all(valid: list) -> list:
    lines = ["", "【自选一览】"]
    ordered = sorted(
        valid,
        key=lambda r: (SIGNAL_RANK.get(r.get("swing", {}).get("signal", ""), 9),
                       -r.get("swing", {}).get("score", 0)),
    )
    for r in ordered:
        cfg = r.get("config", {})
        quote = r.get("quote", {})
        swing = r.get("swing", {})
        ind = r.get("indicators", {})
        flow = swing.get("flow", {}) or {}

        extra = ""
        if ind.get("macd", {}).get("is_golden_cross"):
            extra = " 金叉"
        elif ind.get("macd", {}).get("is_death_cross"):
            extra = " 死叉"

        # 观望的标的省略资金列，保持列表紧凑
        show_flow = flow and swing.get("signal") != "neutral"
        net = (flow.get("main_net") if flow.get("main_net") is not None
               else flow.get("super_net")) if flow else None
        flow_str = (f" {flow.get('label', '主力')}{_amount(net)}"
                    if show_flow and net else "")
        lines.append(
            f"{SIGNAL_EMOJI.get(swing.get('signal', ''), '❔')} {cfg.get('name', '')} "
            f"{_num(quote.get('price'))} {_pct(quote.get('pct_change'), 1)}｜"
            f"{SIGNAL_TEXT.get(swing.get('signal', ''), '')} {swing.get('score', 0):+.0f}"
            f"{extra}{flow_str}"
        )
    return lines


def _section_dragon(yypz_results: list, pool_size: int = 22, max_items: int = 4) -> list:
    lines = ["", "【老龙反抽】"]
    if not yypz_results:
        lines.append(f"扫描{pool_size}只赛道龙头，今天没有符合条件的机会")
        return lines

    lines.append(f"扫描{pool_size}只 → 入选{len(yypz_results)}只（{yypz_results[0].get('confidence', '')}为最高评分）")
    for r in yypz_results[:max_items]:
        star = "🚀" if r.get("signal") == "strong_rebound" else "🔄"
        lines.append(
            f"{star} {r.get('stock', '')} {r.get('score', 0)}分｜"
            f"{r.get('theme', '')}｜{_pct(r.get('pct_change'), 1)}"
        )
        top_reason = (r.get("reasons") or [""])[0]
        if top_reason:
            lines.append(f"   {top_reason[:40]}")
    return lines


def _section_zhengxi(quotes: list) -> list:
    """郑希观点，仅在语料新鲜时输出（由调用方判断）"""
    quotes = [q for q in (quotes or []) if q and q.strip()]
    if not quotes:
        return []
    lines = ["", "【郑希观点】"]
    for i, q in enumerate(quotes[:2], 1):
        lines.append(f"{i}. {q.strip()}")
    return lines


def build_push_body(data_date: str,
                    stock_results: list,
                    yypz_results: list = None,
                    indices: list = None,
                    prev_signals: dict = None,
                    zhengxi_quotes: list = None,
                    dragon_pool_size: int = 22) -> str:
    """
    组装推送正文（纯文本）

    Args:
        data_date: 行情数据日期（YYYY-MM-DD），注意不是运行日期
        stock_results: analyzer 的分析结果列表
        indices: [(名称, 点位, 涨跌幅%), ...]
        prev_signals: {股票名: 上一交易日信号}，用于展示「今日变化」
        zhengxi_quotes: 已清洗的郑希观点句（可为空）
    """
    valid = [r for r in stock_results if not r.get("error")]
    signal_counts = {}
    for r in valid:
        sig = r.get("swing", {}).get("signal", "unknown")
        signal_counts[sig] = signal_counts.get(sig, 0) + 1

    lines = [f"📊 {_fmt_date_label(data_date)} 盘后复盘"]

    lines += _section_index(indices or [])
    if valid:
        lines += _section_summary(valid, signal_counts)
        lines += _section_changes(valid, prev_signals or {})
        lines += _section_focus(valid)
        lines += _section_all(valid)

    lines += _section_dragon(yypz_results or [], pool_size=dragon_pool_size)
    lines += _section_zhengxi(zhengxi_quotes)

    lines += ["", "——————", "仅供复盘参考，不构成投资建议"]
    return "\n".join(lines)
