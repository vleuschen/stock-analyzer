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
4. **宽度分两档**（改宽度只改这两个常数）：

   · `PHONE_EM = 24`：表格行、对齐行、标题行的硬上限。超了就会折行，
     折行会把表格打散，所以这些行一律 `_fit()` 截断 —— 宁可截，不让它折。
   · `PROSE_EM = 32`：说明性文字（理由、观点、备注）的上限。这些行在手机上
     折成两行也读得通，放宽是为了在宽屏（微信 PC / 浏览器）上不显得半屏空。

   为什么不是「手机一行到底几字」：同一份正文在微信 PC 上约 42 字/行，
   在 390dp 手机上约 22-24 字/行 —— 静态文本没法自适应，所以结构行按手机锁死，
   纯文字行给宽屏留空间。

由此定下两条取舍：
  · 长句先按标点断（`_brief`），截也只截到标点/括号处，不把词和数字拦腰切断；
  · 备注类信息（资金连续天数、数据滞后提示）一律「放得下才加，放不下整条丢掉」——
    硬塞会把「超大单+1735万」截成「超大单+1735…」，数字残了比不写更误导。

版式（越靠上越是「今天必须知道」）：
    ▎一句话 → ▎大盘 → ▎自选表现 → ▎今日变化 → ▎值得关注 → ▎自选全览 → ▎老龙反抽
"""

import math
import re

from signals import BEARISH, BULLISH, CARD as SIGNAL_EMOJI, RANK as SIGNAL_RANK, TEXT as SIGNAL_TEXT

# 段落分隔符：卡片端唯一真的能换行的东西
PARA = "\n\n"

# 一行的宽度上限（em，1 em = 1 个汉字），两个档次见模块说明
PHONE_EM = 24.0
PROSE_EM = 32.0

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
    # 逗号通常只是证据串里的短停顿（例如「小仓试仓，确认后加仓」），
    # 说明行应尽量保留后半句；先在完整句号/分号处断，放不下再按宽度收口。
    for sep in ("；", "。", "、", "|"):
        head = text.split(sep)[0].strip()
        if head and _w(head) <= budget:
            return head
    # 还是放不下，就先把括号里的补充说明去掉：「RSI 44.6 偏弱（下跌趋势中）」→「RSI 44.6 偏弱」
    bare = re.sub(r"[（(][^）)]*[）)]", "", text).strip()
    if bare and _w(bare) <= budget:
        return bare
    return _fit(text, budget)


# ============================================================
# 表格：真的一列一列对得齐
# ============================================================

def _pad_name(text: str, width: int = 4) -> str:
    """用全角空格把名称补齐到 width 个汉字宽（ASCII 空格撑不起列宽）"""
    return text + PAD * max(0, width - len(text))


def _cell(text: str, width: int, align: str = "left") -> str:
    """
    把单元格补到 width 个汉字宽。

    列宽只能是整数字符（全角空格 1 em 一格），所以先把列宽向上取整，
    再按四舍五入补空格 —— 同一列每行都这么补，列起点就不会漂。
    """
    gap = int(round(width - _w(text)))
    if gap <= 0:
        return text
    return (PAD * gap + text) if align == "right" else (text + PAD * gap)


def _columns(headers: dict, rows: list, aligns: dict = None, gap: int = 1,
             tight_first: bool = False) -> tuple:
    """
    拼一张表：headers / cells 都是 {列名: 文本}，列宽取「表头与所有单元格」的最宽值。

    列之间一律空 1 个全角空格（gap）：补到整列宽之后常常正好不留空，
    「13.51+3.42%」这样两列贴在一起，数字列再对齐也读不出来。

    `tight_first=True` 时第一列后面不再空这一格 —— 首列是 emoji + 名称，
    emoji 宽 1.2 em，向上取整后本来就会多出 0.8-1.2 em，再空一格就白占 1 个字
    （5 列的表，1 个字就是能不能塞进手机的区别）。首列是纯汉字的表别开这个开关：
    中文名宽度是整数，取整后不留空，会直接贴到下一列上。

    列宽由数据自己撑出来，所以表头、数据行、分隔线三者的列位置必然一致 ——
    手写空格对齐那种做法，改一个字段就会错位。

    返回 (行列表, 表格总宽 em)，总宽给表头分隔线用。
    """
    aligns = aligns or {}
    names = list(headers)
    widths = {}
    for name in names:
        widths[name] = int(math.ceil(max([_w(headers[name])] + [_w(r.get(name, "")) for r in rows])))
    # step[i] = 第 i 列前面空几格（第 0 列前面不空格）
    step = [0] + [0 if (i == 1 and tight_first) else gap for i in range(1, len(names))]

    def render(cells: dict) -> str:
        parts = []
        for i, name in enumerate(names):
            if i:
                parts.append(PAD * step[i])
            parts.append(_cell(cells.get(name, ""), widths[name], aligns.get(name, "left")))
        return "".join(parts).rstrip()

    rules = [render(headers)] + [render(r) for r in rows]
    total = sum(widths.values()) + sum(step)
    return rules, total


def _rule(width: int, char: str = "—") -> str:
    """表头下的分隔线：破折号在微信里按汉字宽渲染，连起来就是一条线"""
    return char * width


def _box_table(headers: list, rows: list, widths: list, aligns: list = None) -> list:
    """生成 Unicode 画线表格；固定列宽，确保边框不会因数据长度漂移。"""
    aligns = aligns or ["left"] * len(headers)

    def cell(value: str, width: int, align: str) -> str:
        value = _fit(str(value), width, tail="")
        gap = max(0, int(round(width - _w(value))))
        return (PAD * gap + value) if align == "right" else (value + PAD * gap)

    def render(values: list) -> str:
        cells = [cell(value, width, aligns[i])
                 for i, (value, width) in enumerate(zip(values, widths))]
        return "│" + "│".join(cells) + "│"

    top = "┌" + "┬".join("─" * width for width in widths) + "┐"
    separator = "├" + "┼".join("─" * width for width in widths) + "┤"
    bottom = "└" + "┴".join("─" * width for width in widths) + "┘"
    return [top, render(headers), separator] + [render(values) for values in rows] + [bottom]


def _score_table(swing: dict) -> list:
    """重点标的的五维评分表：总分不是涨跌幅，而是五项加总。"""
    dimensions = swing.get("dimensions", {}) or {}
    values = [
        f"{dimensions.get('trend', 0):+g}",
        f"{dimensions.get('momentum', 0):+g}",
        f"{dimensions.get('position', 0):+g}",
        f"{dimensions.get('volume', 0):+g}",
        f"{dimensions.get('flow', 0):+g}",
    ]
    return _box_table(["趋势", "动能", "位置", "量价", "资金"], [values],
                      [3, 3, 3, 3, 3], ["right"] * 5)


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


def _flow_is_super(flow: dict) -> bool:
    """这一格用的是不是「超大单」口径（表格里要用 ＊ 标出来，不能含糊）"""
    return bool(flow) and flow.get("main_net") is None and flow.get("super_net") is not None


def _amount(v, digits: int = 2) -> str:
    """金额简写：+1.13亿 / +1735万"""
    sign = "+" if v > 0 else "-"
    a = abs(v)
    if a >= 1e8:
        return f"{sign}{a / 1e8:.{digits}f}亿"
    if a >= 1e4:
        return f"{sign}{a / 1e4:.0f}万"
    return f"{sign}{a:.0f}"


def _flow_short(flow: dict) -> str:
    """带口径的资金证据：超大单+1.72亿（详情行用，口径写全）"""
    net = _flow_net(flow)
    if not net:
        return ""
    return f"{flow.get('label', '主力')}{_amount(net)}"


def _flow_compact(flow: dict) -> str:
    """表格里的一格：+1735万（列头已经写了「资金」，口径用 ＊ 区分）"""
    net = _flow_net(flow)
    if not net:
        return "—"
    return _amount(net) + ("＊" if _flow_is_super(flow) else "")


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


def _volume_ratio(r: dict) -> str:
    """
    量比：优先用行情里的真实量比（当日每分钟均量 / 过去5日同口径）。
    指标里的量比是「近5日均量 / 近20日均量」，口径不同，只在真实量比缺失时兜底，
    且明确写成「量能」以免和真量比混为一谈。
    """
    vr = r.get("quote", {}).get("volume_ratio")
    if vr:
        return f"量比{_num(vr, 1)}"
    vr = (r.get("indicators", {}) or {}).get("volume_ratio")
    if vr:
        return f"量能{_num(vr, 1)}"
    return ""


def _rsi_note(r: dict) -> str:
    """RSI 极值才值得占一行字：50 附近没有信息量"""
    rsi = ((r.get("indicators", {}) or {}).get("rsi", {}) or {}).get("rsi14")
    if not rsi:
        return ""
    if rsi >= 75:
        return f"RSI{_num(rsi, 0)}过热"
    if rsi <= 30:
        return f"RSI{_num(rsi, 0)}超卖"
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
    三大指数：点位右对齐成列，竖着能直接比。

    点位取整到个位（指数报价没人看小数点），涨跌幅右对齐 ——
    两列都右对齐，一眼能看出哪天的创业板跌得更狠。
    """
    if not indices:
        return []
    rows = [{"指数": label, "点位": f"{price:.0f}", "涨跌": _pct(pct)}
            for label, price, pct in indices]
    # 名称列左对齐，两个数字列右对齐 —— 列宽由数据自己撑，表头和数据行必然对齐
    lines, _ = _columns({"指数": "指数", "点位": "点位", "涨跌": "涨跌"}, rows,
                        aligns={"点位": "right", "涨跌": "right"})
    return [_section("大盘")] + lines


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

    return [
        _section("自选表现"),
        _fit(f"涨{up} · 跌{down} · 平{flat} · 均幅 {_pct(avg)}"),
        _fit(dist),
    ]


def _section_headline(valid: list, signal_counts: dict) -> list:
    """先给结论，再让后面的数字解释结论，避免用户在长卡片里找重点。"""
    if not valid:
        return [_section("一句话"), "数据不足，今天不下结论"]
    pcts = [r.get("quote", {}).get("pct_change", 0) or 0 for r in valid]
    up = sum(1 for pct in pcts if pct > 0)
    strong = signal_counts.get("strong_buy", 0)
    buy = signal_counts.get("buy", 0)
    bearish = signal_counts.get("sell", 0) + signal_counts.get("strong_sell", 0)
    if strong:
        verdict = f"多头占优，{strong}只达到进攻标准"
    elif buy:
        verdict = f"偏强但未全面确认，{buy}只适合小仓试错"
    elif bearish:
        verdict = f"防守优先，{bearish}只处于弱势"
    else:
        verdict = "多空未决，等待方向确认"
    return [_section("一句话"), _fit(f"{verdict} · {up}/{len(valid)}只上涨")]


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


def _section_changes(valid: list, prev_signals: dict, max_items: int = 10) -> list:
    """
    相比上一个交易日发生信号切换的标的 —— 一行一条，全列出来。

    以前最多列 4 条、剩下的写「另 N 只见归档报告」，等于把当天最有信息量的
    内容裁掉了：信号切换本来就不多（通常 3-7 条），一行一条也压不到别的板块。
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

    第 2 行按 PROSE_EM 写：理由、资金、连续天数、量比、RSI 极值都是这里的信息，
    宽屏上一行放得下就不该截 —— 手机折成两行也读得通（这行本来就是句子）。
    """
    cfg = r.get("config", {})
    quote = r.get("quote", {})
    swing = r.get("swing", {})
    flow = swing.get("flow", {}) or {}
    signal = swing.get("signal", "")
    indent = PAD + " "
    budget = PROSE_EM - _w(indent)

    head = _fit(f"{_mark(signal)} {cfg.get('name', '')}"
                f" {_num(quote.get('price'))} {_pct(quote.get('pct_change'))}"
                f" · {swing.get('score', 0):+.0f}分")

    plan = swing.get("trade_plan") or {}
    if signal == "strong_buy" and plan:
        # 只有强买档才给可执行价位：偏多档在回测里没有正向期望，给买点等于误导
        rr = plan.get("rr") or 0
        tail = f" · 盈亏比{_num(rr, 1)}"
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
        # 偏多 / 观望：先写差哪一步，再给资金、连续天数、量比 —— 都是可核对的证据
        if signal == "buy":
            action_note = ("激进者仅小仓试错" if swing.get("confidence") == "low"
                           else "激进者可小仓试仓，确认后加仓")
        else:
            action_note = ""
        parts = [action_note, _lack_note(swing)]
        parts = [p for p in parts if p]
        body = SEP.join(parts)
        flow_note = _flow_short(flow) + _flow_lag_note(flow, data_date)
        # 资金数字不能被 _fit 截半：放不下时整条证据省略，避免「+173…」这种误导。
        if flow_note:
            candidate = f"{body}{SEP}{flow_note}" if body else flow_note
            if _w(candidate) <= budget:
                body = candidate
        notes = [x for x in (_flow_consec(flow), _volume_ratio(r), _rsi_note(r)) if x]
        for note in notes:
            candidate = f"{body} · {note}" if body else note
            if _w(candidate) <= budget:
                body = candidate
        if not body:
            body = swing.get("action", "")

    out = [head]
    if swing.get("dimensions"):
        out.extend(_score_table(swing))
    if body:
        # 这一行是句子，按 PROSE_EM 收口：body 本来就是照预算拼的，别在最后又按结构行截一次
        out.append(_fit(indent + _brief(body, budget), PROSE_EM))
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
    自选全览 —— Unicode 画线表格：信号 / 股票 / 涨跌 / 总分。

    按评分降序排，不分档位分组：档位本来就和评分同序（偏多 >25、偏空 <-25），
    排下来自然成组，而 emoji 列已经把档位标出来了 —— 分组标题纯属多余。

    资金列用 ＊ 标出「超大单」口径（东财主力净额缺失时的新浪兜底），
    表下给一行脚注说明 —— 两个口径混在一列里还不标，那是数据错误不是排版问题。
    """
    if not valid:
        return []
    rows = sorted(valid, key=lambda r: r.get("swing", {}).get("score", 0), reverse=True)

    cells = []
    for r in rows:
        sig = r.get("swing", {}).get("signal", "")
        flow = (r.get("swing", {}).get("flow", {}) or {})
        cells.append({
            "名称": f"{_mark(sig)}{_pad_name(r.get('config', {}).get('name', ''), 4)}",
            "现价": _num(r.get("quote", {}).get("price")),
            "涨跌": _pct(r.get("quote", {}).get("pct_change", 0)),
            "资金": _flow_compact(flow),
            "评分": f"{r.get('swing', {}).get('score', 0):+.0f}",
        })

    # 口径标记只在一列里混了两种口径时才逐行打 ＊：全表同一个口径的话，
    # 每行都挂一个 ＊ 是白占 1 个字，脚注写一次就够了。
    calibers = {_flow_is_super(r.get("swing", {}).get("flow", {}) or {})
                for r in rows if _flow_net(r.get("swing", {}).get("flow", {}) or {})}
    mark_per_row = len(calibers) > 1
    if not mark_per_row:
        for cell in cells:
            cell["资金"] = cell["资金"].rstrip("＊")
    # 这张表故意收窄为四列：画线表格在手机上必须完整显示，资金详情放到重点卡片。
    box_rows = []
    for r in rows:
        sig = r.get("swing", {}).get("signal", "")
        box_rows.append([
            _mark(sig),
            _fit(r.get("config", {}).get("name", ""), 4, tail=""),
            _pct(r.get("quote", {}).get("pct_change", 0)),
            f"{r.get('swing', {}).get('score', 0):+.0f}",
        ])
    box = _box_table(["信号", "股票", "涨跌", "总分"], box_rows, [2, 4, 7, 4],
                     ["left", "left", "right", "right"])
    out = [_section(f"自选全览 {len(rows)}只")]
    out.append("总分=五项相加；正强负弱；不是涨跌幅")
    out.extend(box)
    out.append("资金、RSI、量比见上方重点标的详情")
    if calibers == {True}:
        out.append("＊资金列为超大单净额（当日无主力数据）")
    elif mark_per_row:
        out.append("＊超大单净额口径（当日无主力数据）")
    return out


def _section_dragon(yypz_results: list, pool_size: int = 22, max_items: int = 3) -> list:
    """老龙反抽：一行「谁 + 多少分 + 近20日」，一行缩进写主题与入选理由"""
    if not yypz_results:
        return [_section(f"老龙反抽 {pool_size}只"), "今天没有符合条件的机会"]

    lines = [_section(f"老龙反抽 {len(yypz_results)}/{pool_size}只入选")]
    indent = PAD + " "
    budget = PROSE_EM - _w(indent)
    for r in yypz_results[:max_items]:
        star = "🚀" if r.get("signal") == "strong_rebound" else "🔄"
        # r["stock"] 已经是「阳光电源(300274)」，别再拼一次代码
        lines.append(_fit(f"{star} {r.get('stock', '')} {r.get('score', 0)}分"))
        theme = (r.get("theme") or "").strip()
        chg = f"近20日{_pct(r.get('chg_20d'), 1)}"
        detail = " · ".join(x for x in (theme, chg) if x)
        reason = _dragon_reason(r)
        # 理由本身若也是「近20日…」，和前面那截是同一件事，重复写只是占宽度
        if reason.startswith("近20日"):
            reason = ""
        if reason and _w(f"{detail}{SEP}{reason}") <= budget:
            detail = f"{detail}{SEP}{reason}"
        # 同样是句子，按 PROSE_EM 收口（默认的 PHONE_EM 会把数字拦腰截断）
        lines.append(_fit(indent + _brief(detail, budget), PROSE_EM))
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


# ============================================================
# 正文组装
# ============================================================

def build_push_body(data_date: str,
                    stock_results: list,
                    yypz_results: list = None,
                    indices: list = None,
                    prev_signals: dict = None,
                    dragon_pool_size: int = 22) -> str:
    """
    组装推送正文（纯文本，段落之间空行分隔）

    Args:
        data_date: 行情数据日期（YYYY-MM-DD），注意不是运行日期
        stock_results: analyzer 的分析结果列表
        indices: [(名称, 点位, 涨跌幅%), ...]
        prev_signals: {股票名: 上一交易日信号}，用于展示「今日变化」
    """
    valid = [r for r in stock_results if not r.get("error")]
    signal_counts = {}
    for r in valid:
        sig = r.get("swing", {}).get("signal", "unknown")
        signal_counts[sig] = signal_counts.get(sig, 0) + 1

    # 每个元素是一个段落，段落之间空行
    paragraphs = []
    if valid:
        paragraphs += _section_headline(valid, signal_counts)
    paragraphs += _section_index(indices or [])
    if valid:
        paragraphs += _section_summary(valid, signal_counts)
        paragraphs += _section_changes(valid, prev_signals or {})
        paragraphs += _section_focus(valid, data_date)
        paragraphs += _section_table(valid)
    paragraphs += _section_dragon(yypz_results or [], pool_size=dragon_pool_size)

    if not paragraphs:
        paragraphs.append(f"{_fmt_date_label(data_date)} 今天没有取到有效数据")

    paragraphs.append("—— 仅供复盘参考，不构成投资建议")
    return PARA.join(paragraphs)


# ============================================================
# 自检：本地改完排版跑一下，确认没有一行会在手机上折行
# ============================================================

def widest_lines(body: str, budget: float = PHONE_EM):
    """
    返回超过 budget 的段落（供 scripts/check_push_layout.py 做体检）。

    结构行按 PHONE_EM 卡；说明行按 PROSE_EM 卡 —— 想一次看全部，传 PROSE_EM。
    """
    over = []
    for line in body.split(PARA):
        width = _w(line)
        if width > budget:
            over.append((round(width, 1), line))
    return over
