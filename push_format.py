"""
Server酱 / 微信推送正文排版模块

排版规则来自对历史推送截图的复盘（服务器方渲染只有四条硬约束）：

1. **单个换行会被吞掉**：正文里用 "\\n" 分行的内容，在微信卡片里会被拼成一整段，
   只有**空行**才真的换段。所以任何「一行一件事」的地方，段与段之间必须留空行
   （本模块统一用 PARA 拼接）。
2. **Markdown 不保证渲染**：`**加粗**`、`#` 标题、表格、`- ` 列表在卡片端会露出原始
   符号（详情页才会渲染）。全篇走纯文本 + emoji + 【】分节，两种渲染下都不出错。
3. **一行约 22 个汉字**：单条超过就会折行，折行越多越难扫，所以每个段落尽量
   控制在 1~2 行以内，宁可多分段，不要长句。
4. **数字要能竖着比**：价格统一 2 位小数、涨跌幅带 +/-、金额走 亿/万，
   同一类信息用同一个分隔符（｜）分列。

信息层级（越靠前越是「今天必须知道」）：
    大盘 → 自选表现 → 今日变化 → 值得关注 → 自选全览 → 老龙反抽 → 郑希观点
"""

from signals import BEARISH, BULLISH, CARD as SIGNAL_EMOJI, RANK as SIGNAL_RANK, TEXT as SIGNAL_TEXT

# 段落分隔符：微信卡片里唯一真的能换行的东西
PARA = "\n\n"


# ============================================================
# 基础格式化
# ============================================================

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


def _abs_amount(v):
    """元 → 亿/万，不带符号（用来说明「净流出 x 万」这类方向已由文字表达的场景）"""
    a = abs(v or 0)
    if a >= 1e8:
        return f"{a / 1e8:.2f}亿"
    if a >= 1e4:
        return f"{a / 1e4:.0f}万"
    return f"{a:.0f}"


def _label(signal):
    return f"{SIGNAL_EMOJI.get(signal, '❔')} {SIGNAL_TEXT.get(signal, '未知')}"


def _fmt_date_label(data_date: str) -> str:
    """2026-09-18 → 9月18日"""
    try:
        y, m, d = data_date.split("-")
        return f"{int(m)}月{int(d)}日"
    except (ValueError, AttributeError):
        return data_date or ""


def _flow_net(flow: dict):
    """资金口径金额：东财「主力净额」优先，退化到新浪「超大单净额」"""
    if not flow:
        return None
    net = flow.get("main_net")
    if net is None:
        net = flow.get("super_net")
    return net


def _flow_line(flow: dict, data_date: str = "") -> str:
    """资金那一列：口径 + 金额 + 持续性，数据日期滞后时如实标注"""
    net = _flow_net(flow)
    if not net:
        return ""
    label = flow.get("label", "主力")
    tail = ""
    if net > 0:
        consec = flow.get("consec_in") or 1
        tail = f"（连{consec}日）" if consec >= 2 else ""
    else:
        consec = flow.get("consec_out") or 1
        tail = f"（连{consec}日）" if consec >= 2 else ""
    line = f"{label}净{'流入' if net > 0 else '流出'}{_abs_amount(net)}{tail}"
    flow_date = flow.get("date", "")
    if data_date and flow_date and flow_date != data_date:
        line += f"〔截至{flow_date[5:]}〕"
    return line


def _volume_ratio(quote: dict, ind: dict) -> str:
    """
    量比：优先用行情里的真实量比（当日每分钟均量 / 过去5日同口径）。
    指标里的量比是「近5日均量 / 近20日均量」，口径不同，只在真实量比缺失时兜底，
    且明确写成「量能」以免和真量比混为一谈。
    """
    vr = quote.get("volume_ratio")
    if vr:
        return f"量比 {_num(vr, 1)}"
    vr = ind.get("volume_ratio")
    if vr:
        return f"量能 {_num(vr, 1)}"
    return ""


# ============================================================
# 标题
# ============================================================

def build_push_title(data_date: str, n_stocks: int, signal_counts: dict = None) -> str:
    """推送标题，控制在 32 字以内（微信标题栏一行放得下）"""
    date_label = _fmt_date_label(data_date)
    counts = signal_counts or {}
    strong = counts.get("strong_buy", 0)
    bullish = strong + counts.get("buy", 0)
    bearish = counts.get("sell", 0) + counts.get("strong_sell", 0)

    # 「买入」是唯一可执行的多头档，有就报它；只有「偏多」时写「偏多」，
    # 不能笼统写成「多N」——偏多只代表强弱排序，不是买点。
    if strong and bearish:
        tag = f"买入{strong}·空{bearish}"
    elif strong:
        tag = f"买入{strong}只"
    elif bullish and bearish:
        tag = f"偏多{bullish}·空{bearish}"
    elif bullish:
        tag = f"偏多{bullish}只"
    elif bearish:
        tag = f"偏空{bearish}只"
    else:
        tag = "全线观望"
    return f"📊 {date_label}复盘｜{n_stocks}只·{tag}"


# ============================================================
# 各板块（每个元素 = 一个段落，段落之间由 build_push_body 补空行）
# ============================================================

def _section_index(indices: list) -> list:
    if not indices:
        return []
    parts = [f"{label} {_num(price)} {_pct(pct)}" for label, price, pct in indices]
    return [f"【大盘】{'｜'.join(parts)}"]


def _section_summary(valid: list, signal_counts: dict) -> list:
    pcts = [r.get("quote", {}).get("pct_change", 0) or 0 for r in valid]
    up = sum(1 for p in pcts if p > 0)
    down = sum(1 for p in pcts if p < 0)
    flat = len(pcts) - up - down
    avg = sum(pcts) / len(pcts) if pcts else 0

    best = max(valid, key=lambda r: r.get("quote", {}).get("pct_change", 0) or 0)
    worst = min(valid, key=lambda r: r.get("quote", {}).get("pct_change", 0) or 0)

    lines = [
        f"【自选】涨{up} 跌{down} 平{flat}，均幅 {_pct(avg)}｜"
        f"买入{signal_counts.get('strong_buy', 0)}"
        f" 偏多{signal_counts.get('buy', 0)}"
        f" 观望{signal_counts.get('neutral', 0)}"
        f" 偏空{signal_counts.get('sell', 0) + signal_counts.get('strong_sell', 0)}",
        f"最强 {best.get('config', {}).get('name', '')}{_pct(best.get('quote', {}).get('pct_change', 0))}｜"
        f"最弱 {worst.get('config', {}).get('name', '')}{_pct(worst.get('quote', {}).get('pct_change', 0))}",
    ]
    return lines


def _section_changes(valid: list, prev_signals: dict, max_items: int = 4) -> list:
    """今天相比上一个交易日发生信号切换的标的"""
    changes = []
    for r in valid:
        name = r.get("config", {}).get("name", "")
        sig = r.get("swing", {}).get("signal", "")
        prev = (prev_signals or {}).get(name)
        if not prev or prev == sig:
            continue
        # 箭头看的是「方向」而不是档位名次：回避→偏空 仍属空头，标 🔺 会读成看多。
        # 只有多头档才 🔺，空头档一律 🔽，观望档再按名次判升降。
        if sig in BULLISH:
            upgrading = True
        elif sig in BEARISH:
            upgrading = False
        else:
            upgrading = SIGNAL_RANK.get(sig, 9) < SIGNAL_RANK.get(prev, 9)
        mark = "🔺" if upgrading else "🔽"
        pct = r.get("quote", {}).get("pct_change", 0)
        why = _key_reason(r, upgrading=upgrading)
        changes.append(f"{mark} {name} {SIGNAL_TEXT.get(prev, prev)}→{SIGNAL_TEXT.get(sig, sig)}"
                       f" {_pct(pct, 1)}{why}")

    if not changes:
        return ["【今日变化】没有信号切换，维持上一交易日状态"]

    lines = [f"【今日变化】{len(changes)}只"]
    lines.extend(changes[:max_items])
    if len(changes) > max_items:
        lines.append(f"（另有 {len(changes) - max_items} 只切换，见归档报告）")
    return lines


def _key_reason(r: dict, upgrading: bool = True) -> str:
    """
    从 swing 的理由里挑一条与信号变化方向一致的说明。
    只认方向一致的：降级却引一条「均线多头排列」，比不说还糟，所以宁可留空。
    """
    reasons = r.get("swing", {}).get("reasons", []) or []
    prefixes = ("✅", "📈") if upgrading else ("❌", "⚠️")
    for reason in reasons:
        if not reason.startswith(prefixes):
            continue
        text = reason.lstrip("✅❌⚠️📈📉🟡⚪ ").strip()
        if text:
            return f"｜{text[:20]}"
    return ""


def _focus_picks(valid: list, max_items: int = 3) -> list:
    """值得关注的标的：强烈买入优先，其次偏多，最后才是明确的风险对象"""
    ups = [r for r in valid if r.get("swing", {}).get("signal") in BULLISH]
    # 先按信号档位（买入 > 偏多）再按分数，避免「偏多 49 分」压过「买入 51 分」
    ups.sort(key=lambda r: (SIGNAL_RANK.get(r.get("swing", {}).get("signal"), 9),
                            -r.get("swing", {}).get("score", 0)))

    risks = [r for r in valid if r.get("swing", {}).get("signal") in BEARISH]
    risks.sort(key=lambda r: r.get("swing", {}).get("score", 0))

    picks = ups[:max_items]
    if len(picks) < max_items:
        picks += risks[:max_items - len(picks)]
    return picks


def _focus_card(r: dict, data_date: str = "") -> list:
    """单只标的的详情卡：3 个段落（标题 / 位置与动能 / 操作）"""
    cfg = r.get("config", {})
    quote = r.get("quote", {})
    ind = r.get("indicators", {})
    swing = r.get("swing", {})
    flow = swing.get("flow", {}) or {}
    signal = swing.get("signal", "")

    name = cfg.get("name", "")
    code = cfg.get("code", "")
    head = (f"{_label(signal)} {name}（{code}）"
            f" {swing.get('score', 0):+.0f}分")

    facts = [f"{_num(quote.get('price'))} {_pct(quote.get('pct_change'))}"]
    rsi = ind.get("rsi", {}).get("rsi14")
    if rsi is not None:
        facts.append(f"RSI {_num(rsi, 0)}")
    vr = _volume_ratio(quote, ind)
    if vr:
        facts.append(vr)
    flow_text = _flow_line(flow, data_date)
    if flow_text:
        facts.append(flow_text)
    body = "｜".join(facts)

    plan = swing.get("trade_plan") or {}
    if signal == "strong_buy" and plan:
        # 只有强买档才给可执行价位：偏多档在回测里没有正向期望，给买点等于误导
        rr = plan.get("rr") or 0
        tail = f"｜盈亏比 {_num(rr, 1)}" if rr else ""
        if rr and not plan.get("rr_ok", True):
            tail += "（偏低，仓位减半）"
        action = f"买点 {_num(plan.get('entry'))}｜止损 {_num(plan.get('stop'))}｜" \
                 f"目标 {_num(plan.get('target'))}{tail}"
    elif signal in BEARISH:
        supports = swing.get("support_levels") or []
        resists = swing.get("resistance_levels") or []
        level_bits = []
        if resists:
            level_bits.append(f"反弹压力 {_num(resists[0][1])}")
        if supports:
            level_bits.append(f"跌破 {_num(supports[0][1])} 加速下行")
        action = "｜".join(level_bits) if level_bits else swing.get("action", "")
    else:
        # 偏多 / 观望：没有可执行价位就别硬给，只留一句人话
        action = swing.get("action", "")

    lines = [head, body]
    if action:
        lines.append(action)
    return lines


def _section_focus(valid: list, data_date: str = "", max_items: int = 3) -> list:
    lines = ["【值得关注】"]
    picks = _focus_picks(valid, max_items)
    if not picks:
        lines.append("今天没有达到出手标准的标的，继续等")
        return lines
    for r in picks:
        lines.extend(_focus_card(r, data_date))
    return lines


def _section_all(valid: list) -> list:
    """
    自选全览：按信号分组，只留「名称 + 评分」。
    「买入」和「偏多」分开列 —— 偏多只表示强弱排序，回测里没有正向期望，
    混在一起会让人误以为都是买点。
    """
    groups = [
        (("strong_buy",), "🟢 强烈买入"),
        (("buy",), "🔹 偏多"),
        (("neutral",), "🟡 观望"),
        (("sell", "strong_sell"), "🔴 偏空"),
    ]
    lines = ["【自选全览】"]
    for signals, title in groups:
        members = [r for r in valid if r.get("swing", {}).get("signal") in signals]
        if not members:
            continue
        members.sort(key=lambda r: r.get("swing", {}).get("score", 0), reverse=True)
        items = [f"{r.get('config', {}).get('name', '')} "
                 f"{r.get('swing', {}).get('score', 0):+.0f}"
                 for r in members]
        for i in range(0, len(items), 4):
            prefix = f"{title} · " if i == 0 else "　 "
            lines.append(prefix + " · ".join(items[i:i + 4]))
    return lines


def _section_dragon(yypz_results: list, pool_size: int = 22, max_items: int = 3) -> list:
    if not yypz_results:
        return [f"【老龙反抽】扫描{pool_size}只，今天没符合条件的机会"]

    lines = [f"【老龙反抽】扫描{pool_size}只，入选{len(yypz_results)}只"]
    for r in yypz_results[:max_items]:
        star = "🚀" if r.get("signal") == "strong_rebound" else "🔄"
        lines.append(
            f"{star} {r.get('stock', '')} {r.get('score', 0)}分"
            f"｜{_pct(r.get('pct_change'), 1)}｜近20日 {_pct(r.get('chg_20d'), 1)}"
        )
        reason = _dragon_reason(r)
        if reason:
            lines.append(f"{r.get('theme', '')}｜{reason}")
    if len(yypz_results) > max_items:
        lines.append(f"（其余 {len(yypz_results) - max_items} 只见归档报告）")
    return lines


def _dragon_reason(r: dict) -> str:
    """挑一条最有信息量的入选理由（跌幅深度 / RSI 超卖优先）"""
    reasons = r.get("reasons") or []
    for prefix in ("📉", "💫", "🔄"):
        for reason in reasons:
            if reason.startswith(prefix):
                return reason.lstrip("📉💫🔄📊⚪✅💤🛡️📏⭐💰💸📈 ").strip()[:24]
    return reasons[0].lstrip("📉💫🔄📊⚪✅💤🛡️📏⭐💰💸📈 ").strip()[:24] if reasons else ""


def _section_zhengxi(quotes: list) -> list:
    """郑希观点，仅在语料新鲜时输出（由调用方判断）"""
    quotes = [q for q in (quotes or []) if q and q.strip()]
    if not quotes:
        return []
    lines = ["【郑希观点】"]
    for q in quotes[:2]:
        lines.append(q.strip())
    return lines


# ============================================================
# 正文组装
# ============================================================

def build_push_body(data_date: str,
                    stock_results: list,
                    yypz_results: list = None,
                    indices: list = None,
                    prev_signals: dict = None,
                    zhengxi_quotes: list = None,
                    dragon_pool_size: int = 22) -> str:
    """
    组装推送正文（纯文本，段落之间空行分隔）

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

    # 每个元素是一个段落，段落之间空行
    paragraphs = []
    paragraphs += _section_index(indices or [])
    if valid:
        paragraphs += _section_summary(valid, signal_counts)
        paragraphs += _section_changes(valid, prev_signals or {})
        paragraphs += _section_focus(valid, data_date)
        paragraphs += _section_all(valid)
    paragraphs += _section_dragon(yypz_results or [], pool_size=dragon_pool_size)
    paragraphs += _section_zhengxi(zhengxi_quotes)

    if not paragraphs:
        paragraphs.append(f"【{_fmt_date_label(data_date)}】今天没有取到有效数据")

    paragraphs.append("———— 仅供复盘参考，不构成投资建议")
    return PARA.join(paragraphs)
