#!/usr/bin/env python3
"""
推送排版体检 + 手机预览

作用：把 push_format 生成的正文，按「微信卡片」的渲染规则在本地画出来，用来
（1）肉眼确认排版，（2）量出有没有哪一行会在手机上折行。

卡片渲染规则（与 push_format 顶部说明一致）：
  · 按空行分段，一个段落 = 一行
  · ASCII 空格折叠：连续多个算一个，行首的直接吃掉
  · 全角空格 U+3000 是普通字符，原样保留 —— 表格就靠它对齐

用法：
    python scripts/check_push_layout.py                    # 内置样例数据，渲染 + 体检
    python scripts/check_push_layout.py --strong-buy       # 样例里造一只「强烈买入」
    python scripts/check_push_layout.py reports/push_X.md  # 体检已有的推送正文
    python scripts/check_push_layout.py --png out.png      # 顺便导出手机预览图
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import push_format  # noqa: E402

# 手机参数：375dp 的屏、16px 正文、左右各 16px 内边距 —— 微信卡片常见取值
SCREEN_DP = 375
FONT_PX = 16
PADDING_DP = 16
CONTENT_PX = SCREEN_DP - PADDING_DP * 2
SCALE = 3                      # 预览图放大倍数，放大后数字才看得清

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"
EMOJI_FONT_PATH = r"C:\Windows\Fonts\seguiemj.ttf"


def collapse(line: str) -> str:
    """
    模拟卡片端的空格折叠：连续 ASCII 空格算一个，首尾的丢掉。

    注意只能 strip ASCII 空白：Python 的 str.strip() 把全角空格 U+3000 也算空白，
    用它会把表格首列的缩进一起削掉 —— 而微信（HTML 语义）只折叠 ASCII 空白，
    U+3000 是普通字符，该留下。
    """
    return re.sub(r"[ \t\n\r\f]+", " ", line).strip(" \t\n\r\f")


def _is_emoji(ch: str) -> bool:
    """emoji 在真机上走的是系统 emoji 字体，宽度和中文字体不是一套，得分开量"""
    cp = ord(ch)
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF
            or 0x2B00 <= cp <= 0x2BFF or cp in (0xFE0F, 0x200D))


def runs(text: str):
    """把一行切成 (是不是 emoji, 片段) 的序列，供分字体测量 / 绘制"""
    out = []
    for ch in text:
        flag = _is_emoji(ch)
        if out and out[-1][0] == flag:
            out[-1][1] += ch
        else:
            out.append([flag, ch])
    return [(f, s) for f, s in out]


class Measurer:
    """按字符类型分别用中文字体 / emoji 字体量宽，逼近手机上的真实排版"""

    def __init__(self, size: int):
        from PIL import ImageFont
        self.size = size
        self.cjk = ImageFont.truetype(FONT_PATH, size)
        self.emoji = (ImageFont.truetype(EMOJI_FONT_PATH, size)
                      if os.path.exists(EMOJI_FONT_PATH) else self.cjk)

    def font_for(self, flag: bool):
        return self.emoji if flag else self.cjk

    def width(self, text: str) -> float:
        return sum(self.font_for(f).getlength(s) for f, s in runs(text))


# ============================================================
# 样例数据：照抄 2026-09-18 那份日报，改排版时不用联网也能复现
# ============================================================

def _row(code, name, price, pct, signal, score, flow=None, rsil=55, consec=1,
         lack=None, reasons=(), label="超大单"):
    """
    照 analyzer + swing_strategy 的数据形状拼一条，字段名必须和生产代码一致。

    label 默认按新浪口径写「超大单」（三字），不按东财的「主力」（两字）——
    东财限频时线上走的就是新浪兜底，三字口径比两字宽 1 em，最容易把行挤爆。
    """
    flow = flow or {}
    net = flow.get("net")
    return {
        "config": {"code": code, "name": name, "market": "sz"},
        "quote": {"price": price, "pct_change": pct, "volume_ratio": flow.get("vr")},
        "indicators": {"rsi": {"rsi14": rsil}},
        "swing": {
            "signal": signal,
            "score": score,
            "action": f"评分达标但缺确认（{lack}），先观察不加仓" if lack else "偏强整理，尚未形成买点",
            "reasons": (([f"🟡 高分但确认不足（{lack}），降级观察"] if lack else []) + list(reasons)),
            "flow": {
                "main_net": None,               # 东财主口径取不到时才是这个形状
                "super_net": net,               # 此时退化到新浪的超大单口径
                "label": label,
                "consec_in": consec if (net or 0) > 0 else 0,
                "consec_out": consec if (net or 0) < 0 else 0,
                "date": "2026-09-18",
            },
        },
    }


def demo_body(with_strong_buy: bool = False) -> str:
    """样例数据 = 2026-09-18 那份日报的信号 + 2026-09-21 跑出来的理由措辞"""
    stocks = [
        _row("600637", "东方明珠", 8.84, 1.96, "buy", 56, {"net": 1735e4, "vr": 1.3}, 63,
             consec=3, lack="均线未多头排列"),
        _row("002741", "光华科技", 26.39, 3.98, "buy", 50, {"net": 1.13e8, "vr": 1.6}, 61,
             consec=2, lack="均线未多头排列"),
        _row("001380", "华纬科技", 18.93, 2.32, "buy", 50, {"net": 3082e4}, 80, lack="RSI 80 偏热"),
        _row("600977", "中国电影", 13.51, 4.64, "buy", 46, {"net": 6935e4, "vr": 2.1}, 64,
             lack="均线未多头排列"),
        _row("002264", "新华都", 7.66, 4.22, "buy", 42, {"net": 4471e4}, 66, lack="均线未多头排列"),
        _row("002074", "国轩高科", 26.98, 2.03, "buy", 39, {"net": 2205e4}, 58),
        _row("603928", "兴业股份", 12.24, 0.33, "buy", 33, {"net": -342e4}, 53),
        _row("002714", "牧原股份", 43.20, 2.49, "neutral", 20, {"net": 1.06e8}, 59),
        _row("002842", "翔鹭钨业", 14.15, -0.90, "neutral", -1, {"net": -1877e4}, 45),
        _row("001230", "劲旅环境", 17.31, 2.61, "neutral", -17, {"net": -933e4}, 47),
        _row("002170", "芭田股份", 9.14, 0.92, "sell", -27, {"net": -2519e4}, 42),
        _row("002027", "分众传媒", 7.03, 2.15, "sell", -31, {"net": -4166e4}, 44),
        _row("300785", "值得买", 21.54, 0.70, "sell", -37, {"net": -3948e4}, 41),
    ]
    if with_strong_buy:
        # 造一只够「强烈买入」的：均线多头 + RSI<70 + 资金不流出 + 有买卖计划
        strong = stocks[3]
        strong["quote"]["pct_change"] = 3.42
        strong["swing"].update({
            "signal": "strong_buy",
            "score": 68,
            "action": "多指标共振，可分批建仓，跌破支撑止损",
            "reasons": ["✅ 均线多头排列，趋势向上", "✅ 站上 MA5 / MA10"],
            "trade_plan": {"entry": 20.40, "stop": 19.25, "target": 24.10,
                           "rr": 2.3, "rr_ok": True},
        })

    yypz = [
        {"stock": "阳光电源(300274)", "theme": "逆变器·储能龙头", "score": 74,
         "signal": "strong_rebound", "pct_change": 3.8, "chg_20d": -22.3,
         "reasons": ["📉 近20日跌幅22.28%，深度回调提供反抽空间"]},
        {"stock": "浪潮信息(000977)", "theme": "AI算力·服务器", "score": 69,
         "signal": "strong_rebound", "pct_change": 3.0, "chg_20d": -5.9,
         "reasons": ["💫 RSI(14)=23.2，深度超卖，反弹动能积聚"]},
        {"stock": "德业股份(605117)", "theme": "逆变器·储能", "score": 64,
         "signal": "rebound", "pct_change": 2.1, "chg_20d": -12.0,
         "reasons": ["📉 近20日跌幅12.03%，回调较为充分"]},
        {"stock": "北方华创(002371)", "theme": "半导体设备龙头", "score": 58,
         "signal": "rebound", "pct_change": -0.4, "chg_20d": -9.4,
         "reasons": ["📉 近20日跌幅9.4%，深度回调提供反抽空间"]},
        {"stock": "中芯国际(688981)", "theme": "半导体制造龙头", "score": 55,
         "signal": "rebound", "pct_change": 1.2, "chg_20d": -8.1,
         "reasons": ["💫 RSI(14)=29.5，深度超卖，反弹动能积聚"]},
    ]

    # 让「今日变化」凑够 6 条（>4 条才能验证「另 N 只见归档」那行），
    # 理由按方向给：升级引 ✅/📈，降级引 ❌/⚠️ —— 方向反了宁可不引
    stocks[10]["swing"]["reasons"] += ["❌ MACD 空头区域运行"]
    stocks[11]["swing"]["reasons"] += ["❌ 均线空头排列，趋势向下"]
    stocks[7]["swing"]["reasons"] += ["✅ 站上 MA5 / MA10"]
    stocks[8]["swing"]["reasons"] += ["⚠️ RSI 44.6 偏弱（下跌趋势中）"]
    stocks[12]["swing"]["reasons"] += ["⚠️ RSI 41 偏弱（下跌趋势中）"]
    stocks[6]["swing"]["reasons"] += ["📈 MACD 金叉，动能转强"]
    prev = {"芭田股份": "strong_sell", "分众传媒": "strong_sell", "牧原股份": "sell",
            "翔鹭钨业": "buy", "值得买": "sell", "兴业股份": "neutral",
            "光华科技": "neutral", "东方明珠": "buy"}

    return push_format.build_push_body(
        "2026-09-18", stocks, yypz_results=yypz,
        indices=[("上证", 3911.87, 0.94), ("深成", 13640.87, 1.72),
                 ("创业板", 3372.68, 2.25)],
        prev_signals=prev,
        zhengxi_quotes=["流动性宽松叠加资本开支上行，光通信与算力仍是景气度最高的方向。"],
        dragon_pool_size=22,
    )


# ============================================================
# 体检
# ============================================================

def check(body: str) -> int:
    """按段落量宽度：先看排版模块自己的估算，再用真实字体实测（实测才是手机上看到的）"""
    measurer = Measurer(FONT_PX) if os.path.exists(FONT_PATH) else None

    print(f"手机参数: {SCREEN_DP}dp 屏 · {FONT_PX}px 正文 · 可用宽度 {CONTENT_PX}px")
    print(f"排版预算: {push_format.PHONE_EM} em\n")

    paragraphs = body.split(push_format.PARA)
    over, near = [], []
    print(f"{'估算':>5} {'实测':>5}  {'':2} 段落")
    print("-" * 72)
    for line in paragraphs:
        shown = collapse(line)
        em = push_format._w(line)
        px = measurer.width(shown) if measurer else em * FONT_PX
        if px > CONTENT_PX:
            over.append((px, em, shown))
            flag = "❌"
        elif px > CONTENT_PX - 20:
            near.append((px, shown))
            flag = "⚠️"
        else:
            flag = "  "
        print(f"{em:>5.1f} {px:>5.0f}  {flag} {shown}")

    print("-" * 72)
    if over:
        print(f"\n❌ {len(over)} 行会在手机上折行（折行会把表格打散）：")
        for px, em, line in over:
            print(f"   实测 {px:.0f}px / 可用 {CONTENT_PX}px  估算 {em:.1f}em  {line}")
        return 1
    if near:
        print(f"\n⚠️ {len(near)} 行贴着边（换台字体更宽的机器就可能折行）：")
        for px, line in near:
            print(f"   实测 {px:.0f}px / 可用 {CONTENT_PX}px  {line}")
    print(f"\n✅ {len(paragraphs)} 行全部放得下，手机上不会折行")
    return 0


# ============================================================
# 手机预览图
# ============================================================

def render(body: str, out_path: str) -> str:
    """把正文画成 375dp 手机里的样子（超出宽度的行会像真机一样折行，一眼能看出来）"""
    from PIL import Image, ImageDraw

    if not os.path.exists(FONT_PATH):
        raise SystemExit(f"找不到中文字体: {FONT_PATH}")

    m = Measurer(FONT_PX * SCALE)
    line_h = int(FONT_PX * 1.65 * SCALE)
    pad = PADDING_DP * SCALE
    limit = CONTENT_PX * SCALE

    # 先按渲染规则折行，算出总高
    rows = []
    for line in body.split(push_format.PARA):
        text = collapse(line)
        if not text:
            continue
        current, used = "", 0.0
        for ch in text:
            w = m.font_for(_is_emoji(ch)).getlength(ch)
            if used + w > limit and current:
                rows.append(current)
                current, used = ch, w
            else:
                current += ch
                used += w
        rows.append(current)

    height = pad * 2 + line_h * len(rows)
    img = Image.new("RGB", (width := SCREEN_DP * SCALE, height), "#ffffff")
    draw = ImageDraw.Draw(img)
    y = pad
    for row in rows:
        x = pad
        for flag, chunk in runs(row):
            font = m.font_for(flag)
            draw.text((x, y), chunk, font=font, fill="#1a1a1a",
                      embedded_color=flag)
            x += font.getlength(chunk)
        y += line_h

    img.save(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="推送排版体检 + 手机预览")
    parser.add_argument("path", nargs="?", help="已有的推送正文文件（不传则用内置样例）")
    parser.add_argument("--strong-buy", action="store_true",
                        help="样例里造一只「强烈买入」，检查买点那几行排版")
    parser.add_argument("--png", metavar="OUT", help="导出手机预览图")
    parser.add_argument("--body-only", action="store_true", help="只打印正文")
    args = parser.parse_args()

    if args.path:
        with open(args.path, encoding="utf-8") as f:
            body = f.read().strip()
    else:
        body = demo_body(with_strong_buy=args.strong_buy)

    if args.body_only:
        print(body)
        return 0

    code = check(body)

    if args.png:
        out = render(body, args.png)
        print(f"🖼️ 手机预览图: {out}")
    return code


if __name__ == "__main__":
    sys.exit(main())
