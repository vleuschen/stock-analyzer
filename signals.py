"""
信号词表 —— 全项目唯一来源。

三个消费方，各取所需：
    formatter.py    归档 md 报告，用 MARK（run_daily 会反解析这个 emoji 反推信号名）
    push_format.py  微信卡片，用 CARD（卡片里 emoji 比文字更抓眼）
    run_daily.py    读上一份报告做「今日变化」，用 SIGNAL_BY_MARK

改信号名/emoji 只改这里。别在别处再抄一份 —— 一旦 emoji 和信号名对不上，
run_daily 反解析不到就当「没有变化」，推送会静默失准，且不报错。
"""

# 档位顺序：从强到弱，也用作「升级/降级」的排序（数值越小越强）
ORDER = ("strong_buy", "buy", "neutral", "sell", "strong_sell")

# 信号名（人话）
TEXT = {
    "strong_buy": "强烈买入",
    "buy": "偏多",
    "neutral": "观望",
    "sell": "偏空",
    "strong_sell": "回避",
}

# 归档报告用标记（会被 run_daily 反解析，勿随意改动）
MARK = {
    "strong_buy": "🚀",
    "buy": "📈",
    "neutral": "⏳",
    "sell": "📉",
    "strong_sell": "⚠️",
}

# 推送卡片用标记
CARD = {
    "strong_buy": "🟢",
    "buy": "🔹",
    "neutral": "🟡",
    "sell": "🔴",
    "strong_sell": "⚠️",
}

RANK = {sig: i for i, sig in enumerate(ORDER)}
SIGNAL_BY_MARK = {mark: sig for sig, mark in MARK.items()}

BULLISH = ("strong_buy", "buy")
BEARISH = ("sell", "strong_sell")


def text(signal: str) -> str:
    return TEXT.get(signal, "未知")


def mark(signal: str) -> str:
    return MARK.get(signal, "❓")
