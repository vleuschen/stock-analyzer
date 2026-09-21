"""
Server酱 / 微信推送正文排版模块 —— 手机优先的纯文本表格

渲染模型（对历史推送截图复盘得到，改版式前先读这四条）：

1. **一行 = 一个段落**。卡片端把正文按空行切段，段内的单个 "\\n" 会被折叠成一个
   空格，不会换行。所以要另起一行只能用空行（本模块统一用 PARA 拼段落）。
2. **ASCII 空格会被折叠**：连续空格只显示一个，行首空格直接消失。
   表格的列对齐因此只能用全角空格 U+3000 —— 它是普通字符，宽度正好 1 个汉字，
   既不折叠也不被吃掉（历史截图里 "　 华纬科技…" 的缩进能活下来就是证据）。
3. **Markdown 在卡片端不解析**：`**加粗**` / `#` / 表格 / `- ` 列表会露出原始符号
   （点进详情页才渲染）→ 正文一律纯文本 + emoji + 全角空格。
4. **一行约 20 个汉字**，超了就折行，折行会把表格打散。所有行都过一遍 `_fit()`
   做宽度截断 —— 宁可截断，也不让手机去折行。

由此定下两条取舍：
  · 长句先按标点断（`_brief`），截也只截到标点/括号处，不把词和数字拦腰切断；
  · 备注类信息（资金连续天数、数据滞后提示）一律「放得下才加，放不下整条丢掉」——
    硬塞会把「超大单+1735万」截成「超大单+1735…」，数字残了比不写更误导。

版式（越靠上越是「今天必须知道」）：
    ▎大盘 → ▎自选表现 → ▎今日变化 → ▎值得关注 → ▎自选全览 → ▎老龙反抽 → ▎郑希观点
"""

import re

from signals import BEARISH, BULLISH, CARD as SIGNAL_EMOJI, RANK as SIGNAL_RANK, TEXT as SIGNAL_TEXT

# 段落分隔符：卡片端唯一真的能换行的东西
PARA = "\n\n"

# 一行能放下的宽度（em，1 em = 1 个汉字）。
# 360dp 安卓屏减去卡片内边距后约 21 个汉字，375dp 的 iPhone 约 22 个，取 20 留余量。
PHONE_EM = 20.0

# 全角空格：微信里唯一撑得住列宽的空格
PAD = "\u3000"

# 表格 / 行内的列分隔符
SEP = "｜"

# 分节标记（方块元素，CJK 字体都有，比 【】 轻）
MARK = "▎"


# ============================================================
# 宽度：排版的地基
# ============================================================

# 半角字符宽度（em），微软雅黑 1000px 实测值。
# 估宽了会把本来放得下的行无谓截断（数字被腰斩最难受），估窄了会在手机上折行，
# 所以用实测值而不是拍脑袋的 0.5。
_HALF_EM = {
    " ": 0.30, ".": 0.25, ",": 0.25, ":": 0.25, ";": 0.30,
    "'": 0.20, '"': 0.40, "(": 0.35, ")": 0.35, "/": 0.43,
    "-": 0.44, "+": 0.75, "=": 0.75, "%": 0.89, "!": 0.35,
    "?": 0.55, "&": 0.75, "*": 0.45, "_": 0.50, "|": 0.40,
}

# 大写字母单独列：M/W 比 A/I 宽一倍多，用平均值会把 "MA5 / MA10" 这类估窄，
# 本来放得下的行就会被挤成两行
_UPPER_EM = {
    "A": 0.70, "B": 0.63, "C": 0.67, "D": 0.76, "E": 0.55, "F": 0.53,
    "G": 0.74, "H": 0.77, "I": 0.29, "J": 0.40, "K": 0.64, "L": 0.51,
    "M": 0.98, "N": 0.81, "O": 0.82, "P": 0.61, "Q": 0.82, "R": 0.65,
    "S": 0.58, "T": 0.57, "U": 0.75, "V": 0.68, "W": 1.02, "X": 0.65,
    "Y": 0.60, "Z": 0.62,
}


def _char_em(ch: str) -> float:
    """单个字符的显示宽度（em）。全角按 1 个汉字，半角查实测表。"""
    cp = ord(ch)
    if cp in (0xFE0F, 0x200D):          # 变体选择符 / 零宽连接符
        return 0.0
    if 0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF:
        return 1.2                       # emoji（微信里比汉字略宽）
    if cp == 0x00B7 or cp == 0x2022:     # · （中文连接号常被当半角用）
        return 0.25
    if ch.isascii():
        if ch in _HALF_EM:
            return _HALF_EM[ch]
        if ch.isdigit():
            return 0.59
        if ch in _UPPER_EM:
            return _UPPER_EM[ch]
        return 0.58                      # 小写字母
    return 1.0                           # 汉字与全角符号（→ ｜ — 等按汉字宽算）


def _w(text: str) -> float:
    """一段文字的显示宽度（em）"""
    return sum(_char_em(ch) for ch in text or "")


def _fit(text: str, budget: float = PHONE_EM, tail: str = "…") -> str:
    """把一行裁进 budget（em）。折行会把表格打散，所以宁可截断。"""
    if _w(text) <= budget:
        return text
    keep = budget - _w(tail)
    out, used = "", 0.0
    for ch in text:
        width = _char_em(ch)
        if used + width > keep:
            break
        out += ch
        used += width
    return out.rstrip() + tail


def _brief(text: str, budget: float) -> str:
    """取一句话里最靠前、又塞得进 budget 的那一段（优先按标点断句，别把词切断）"""
    # 「MA5 / MA10」里的半角空格在微信里会被折叠掉，留着只是白占宽度
    text = re.sub(r"\s*/\s*", "/", (text or "").strip())
    if _w(text) <= budget:
        return text
    for sep in ("，", "；", "。", "、", "|"):
        head = text.split(sep)[0].strip()
        if head and _w(head) <= budget:
            return head
    # 还是放不下，就先把括号里的补充说明去掉：「RSI 44.6 偏弱（下跌趋势中）」→「RSI 44.6 偏弱」
    bare = re.sub(r"[（(][^）)]*[）)]", "", text).strip()
    if bare and _w(bare) <= budget:
        return bare
    return _fit(text, budget)


def _pad_name(text: str, width: int = 4) -> str:
    """用全角空格把名称补齐到 width 个汉字宽（ASCII 空格撑不起列宽）"""
    return text + PAD * max(0, width - len(text))


def _pad_left(text: str, width: int) -> str:
    """左侧补空格到 width 个半角字符。微信会把连续空格折叠成一个，所以最多补 1 个。"""
    return (" " + text) if width - len(text) == 1 else text


# ============================================================
# 基础格式化
# ============================================================

def _pct(v, digits=2):
    # 平坦（0.00%）也带 + 号：表格里涨跌是一列，缺了符号这一列就长短不齐
    if v is None:
        return "-"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{digits}f}%"


def _num(v, digits=2):
    if v is None:
        return "-"
    return f"{v:.{digits}f}"


def _mark(signal: str) -> str:
    return SIGNAL_EMOJI.get(signal, "❔")


def _label(signal: str) -> str:
    return f"{_mark(signal)} {SIGNAL_TEXT.get(signal, '未知')}"


def _fmt_date_label(data_date: str) -> str:
    """2026-09-18 → 9月18日"""
    try:
        y, m, d = data_date.split("-")
        return f"{int(m)}月{int(d)}日"
    except (ValueError, AttributeError):
        return data_date or ""


def _section(title: str) -> str:
    """分节标记。方块符不需要额外空格，裸写更干净"""
    return f"{MARK}{title}"


def _flow_net(flow: dict):
    """资金口径金额：东财「主力净额」优先，退化到新浪「超大单净额」"""
    if not flow:
        return None
    net = flow.get("main_net")
    if net is None:
        net = flow.get("super_net")
    return net


def _flow_short(flow: dict) -> str:
    """紧凑资金证据：超大单+1.72亿 —— 手机上一行字字千金，「净流入」用 + 号代替"""
    net = _flow_net(flow)
    if not net:
        return ""
    label = flow.get("label", "主力")
    sign = "+" if net > 0 else "-"
    a = abs(net)
    size = f"{a / 1e8:.2f}亿" if a >= 1e8 else (f"{a / 1e4:.0f}万" if a >= 1e4 else f"{a:.0f}")
    return f"{label}{sign}{size}"


def _flow_consec(flow: dict) -> str:
    """资金连续流入/流出天数：连3日 —— 加分项，不是结论，放不下就该丢"""
    net = _flow_net(flow)
    if not net:
        return ""
    consec = (flow.get("consec_in") if net > 0 else flow.get("consec_out")) or 1
    return f"连{consec}日" if consec >= 2 else ""


def _flow_lag_note(flow: dict, data_date: str) -> str:
    """资金数据日期和行情对不上时如实标注 —— 否则会把昨天的资金当成今天的"""
    if not flow:
        return ""
    flow_date = flow.get("date", "")
    if data_date and flow_date and flow_date != data_date:
        return f"〔{flow_date[5:]}〕"
    return ""


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
# 各板块 —— 每个元素 = 一个段落（= 卡片里的一行）
# ============================================================

def _section_index(indices: list) -> list:
    """
    三大指数：一行一个，点位取整到个位（指数报价没人看小数点），
    名称与点位用全角空格对齐，竖着能直接比。
    """
    if not indices:
        return []
    lines = [_section("大盘")]
    for label, price, pct in indices:
        lines.append(_fit(f"{_pad_name(label, 3)}{PAD}{price:.0f}{PAD}{_pct(pct)}"))
    return lines


def _section_summary(valid: list, signal_counts: dict) -> list:
    """自选表现：涨跌统计 + 信号分布（同时充当表格里 emoji 的图例）"""
    pcts = [r.get("quote", {}).get("pct_change", 0) or 0 for r in valid]
    up = sum(1 for p in pcts if p > 0)
    down = sum(1 for p in pcts if p < 0)
    flat = len(pcts) - up - down
    avg = sum(pcts) / len(pcts) if pcts else 0

    dist = " · ".join([
        f"{_mark('strong_buy')}买入{signal_counts.get('strong_buy', 0)}",
        f"{_mark('buy')}偏多{signal_counts.get('buy', 0)}",
        f"{_mark('neutral')}观望{signal_counts.get('neutral', 0)}",
        f"{_mark('sell')}偏空{signal_counts.get('sell', 0)}",
    ])
    strong_sell = signal_counts.get("strong_sell", 0)
    if strong_sell:
        dist += f" · {_mark('strong_sell')}回避{strong_sell}"

    # 「最强 / 最弱」不再单开一行：全览表里 13 只的涨跌都排在那里，扫一眼就有，
    # 而这一行永远差几个字放不下（两只股票名 + 两个幅度 = 21 个汉字宽），
    # 截断后剩个「-0…」，比不放还难看。
    return [
        _section("自选表现"),
        _fit(f"涨{up} · 跌{down} · 平{flat} · 均幅 {_pct(avg)}"),
        _fit(dist),
    ]


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
            return text
    return ""


def _section_changes(valid: list, prev_signals: dict, max_items: int = 4) -> list:
    """
    相比上一个交易日发生信号切换的标的 —— 一行一条。

    最多列 4 条：全列出来就是 13 行，把「值得关注」挤到屏幕外面去了；
    理由按「箭头 + 名称 + 转向」之后剩下的宽度截，优先切在标点处。
    """
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
        arrow = f"{SIGNAL_TEXT.get(prev, prev)}→{SIGNAL_TEXT.get(sig, sig)}"
        head = f"{mark} {name} {arrow}"
        reason = _key_reason(r, upgrading=upgrading)
        changes.append((head, reason))

    if not changes:
        return [_section("今日变化"), "没有信号切换，维持上一交易日状态"]

    lines = [_section(f"今日变化 {len(changes)}只")]
    for head, reason in changes[:max_items]:
        budget = PHONE_EM - _w(head) - _w(SEP)
        lines.append(_fit(f"{head}{SEP}{_brief(reason, budget)}" if reason else head))
    if len(changes) > max_items:
        lines.append(f"（另 {len(changes) - max_items} 只见归档报告）")
    return lines


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


def _lack_note(swing: dict) -> str:
    """偏多档差在哪一步 —— 这个问题比「多少分」更该讲清楚"""
    for reason in swing.get("reasons", []) or []:
        if "确认不足" in reason:
            match = re.search(r"[（(]([^）)]+)[）)]", reason)
            if match:
                return f"差{match.group(1)}"
    return ""


def _focus_card(r: dict, data_date: str = "") -> list:
    """
    单只标的 2 行：第 1 行「谁 + 多少钱 + 多少分」，第 2 行缩进写「怎么做 + 为什么」。
    价格和评分在表格里已经能竖着比了，这里只补表格给不出的结论。
    """
    cfg = r.get("config", {})
    quote = r.get("quote", {})
    swing = r.get("swing", {})
    flow = swing.get("flow", {}) or {}
    signal = swing.get("signal", "")
    indent = PAD + " "

    head = (f"{_mark(signal)} {cfg.get('name', '')}"
            f" {_num(quote.get('price'))} {_pct(quote.get('pct_change'))}"
            f" · {swing.get('score', 0):+.0f}分")

    plan = swing.get("trade_plan") or {}
    if signal == "strong_buy" and plan:
        # 只有强买档才给可执行价位：偏多档在回测里没有正向期望，给买点等于误导
        rr = plan.get("rr") or 0
        tail = f"{SEP}盈亏比{_num(rr, 1)}"
        if rr and not plan.get("rr_ok", True):
            tail += "偏低，仓位减半"
        body = (f"买点 {_num(plan.get('entry'))}{SEP}止损 {_num(plan.get('stop'))}"
                f"{SEP}目标 {_num(plan.get('target'))}{tail}")
    elif signal in BEARISH:
        supports = swing.get("support_levels") or []
        resists = swing.get("resistance_levels") or []
        bits = []
        if resists:
            bits.append(f"压力 {_num(resists[0][1])}")
        if supports:
            bits.append(f"跌破 {_num(supports[0][1])} 加速下行")
        body = SEP.join(bits) or swing.get("action", "")
    else:
        # 偏多 / 观望：先写差哪一步，再给资金证据，别硬凑一句「观望」
        bits = [x for x in (_lack_note(swing), _flow_short(flow)) if x]
        body = SEP.join(bits)
        if body:
            # 连续天数、资金数据滞后都属于备注：放得下才加，放不下整条丢掉。
            # 硬塞的后果是把「超大单+1735万」截成「超大单+1735…」—— 数字残了更误导。
            for note in (_flow_consec(flow), _flow_lag_note(flow, data_date)):
                if note and _w(indent + body + note) <= PHONE_EM:
                    body += note
        else:
            body = swing.get("action", "")

    out = [_fit(head)]
    if body:
        # 预算只扣缩进：_fit 自己会给省略号留位置，这里再扣一次等于白丢一个字的宽度
        out.append(_fit(indent + _brief(body, PHONE_EM - _w(indent))))
    return out


def _section_focus(valid: list, data_date: str = "", max_items: int = 3) -> list:
    lines = [_section("值得关注")]
    picks = _focus_picks(valid, max_items)
    if not picks:
        lines.append("今天没有达到出手标准的标的，继续等")
        return lines
    for r in picks:
        lines.extend(_focus_card(r, data_date))
    return lines


def _section_table(valid: list) -> list:
    """
    自选全览 —— 真正的表格：一票一行，标记 / 名称 / 涨跌 / 评分 四列竖着对得齐。

    按评分降序排，不分档位分组：档位本来就和评分同序（偏多 >25、偏空 <-25），
    排下来自然成组，而 emoji 列已经把档位标出来了 —— 分组标题纯属多余。
    """
    if not valid:
        return []
    rows = sorted(valid, key=lambda r: r.get("swing", {}).get("score", 0), reverse=True)

    lines = [_section(f"自选全览 {len(rows)}只")]
    # 表头用和数据行同一套拼法，列宽才对得上（全角空格是唯一撑得住列宽的空格）
    lines.append(f"{PAD} 名称{PAD * 2}{PAD}涨跌{PAD * 2}评分")
    for r in rows:
        sig = r.get("swing", {}).get("signal", "")
        name = _pad_name(r.get("config", {}).get("name", ""), 4)
        pct = _pad_left(_pct(r.get("quote", {}).get("pct_change", 0)), 7)
        score = _pad_left(f"{r.get('swing', {}).get('score', 0):+.0f}", 3)
        lines.append(_fit(f"{_mark(sig)} {name}{PAD}{pct}{PAD}{score}"))
    return lines


def _section_dragon(yypz_results: list, pool_size: int = 22, max_items: int = 3) -> list:
    """老龙反抽：一行「谁 + 多少分 + 近20日」，一行缩进写主题与入选理由"""
    if not yypz_results:
        return [_section(f"老龙反抽 {pool_size}只"), "今天没有符合条件的机会"]

    lines = [_section(f"老龙反抽 {len(yypz_results)}/{pool_size}只入选")]
    indent = PAD + " "
    for r in yypz_results[:max_items]:
        star = "🚀" if r.get("signal") == "strong_rebound" else "🔄"
        # r["stock"] 已经是「阳光电源(300274)」，别再拼一次代码
        lines.append(_fit(f"{star} {r.get('stock', '')} {r.get('score', 0)}分"))
        theme = (r.get("theme") or "").strip()
        detail = "，".join(x for x in (theme, f"近20日{_pct(r.get('chg_20d'), 1)}") if x)
        lines.append(_fit(indent + _brief(detail, PHONE_EM - _w(indent))))
    if len(yypz_results) > max_items:
        lines.append(f"（其余 {len(yypz_results) - max_items} 只见归档报告）")
    return lines


def _dragon_reason(r: dict) -> str:
    """挑一条最有信息量的入选理由（跌幅深度 / RSI 超卖优先）"""
    reasons = r.get("reasons") or []
    for prefix in ("📉", "💫", "🔄"):
        for reason in reasons:
            if reason.startswith(prefix):
                return reason.lstrip("📉💫🔄📊⚪✅💤🛡️📏⭐💰💸📈 ").strip()
    return reasons[0].lstrip("📉💫🔄📊⚪✅💤🛡️📏⭐💰💸📈 ").strip() if reasons else ""


def _section_zhengxi(quotes: list) -> list:
    """郑希观点，仅在语料新鲜时输出（由调用方判断）"""
    quotes = [q for q in (quotes or []) if q and q.strip()]
    if not quotes:
        return []
    lines = [_section("郑希观点")]
    for q in quotes[:2]:
        # 摘录按标点断，不要拦腰截断：观点句断在半句上，读起来像漏字
        lines.append(_brief(q, PHONE_EM))
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
        paragraphs += _section_table(valid)
    paragraphs += _section_dragon(yypz_results or [], pool_size=dragon_pool_size)
    paragraphs += _section_zhengxi(zhengxi_quotes)

    if not paragraphs:
        paragraphs.append(f"{_fmt_date_label(data_date)} 今天没有取到有效数据")

    paragraphs.append("—— 仅供复盘参考，不构成投资建议")
    return PARA.join(paragraphs)


# ============================================================
# 自检：本地改完排版跑一下，确认没有一行会在手机上折行
# ============================================================

def widest_lines(body: str, budget: float = PHONE_EM):
    """返回超过手机行宽的段落（供 scripts/check_push_layout.py 做体检）"""
    over = []
    for line in body.split(PARA):
        width = _w(line)
        if width > budget:
            over.append((round(width, 1), line))
    return over
