"""
技术指标计算模块
纯 Python + math 实现，零外部依赖
"""

from __future__ import annotations

import math


def calc_ma(closes: list[float], period: int) -> float | None:
    """简单移动平均线"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calc_ma_series(closes: list[float], period: int) -> list[float | None]:
    """计算完整 MA 序列"""
    result = []
    for i in range(len(closes)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(closes[i - period + 1:i + 1]) / period)
    return result


def judge_ma_alignment(closes: list[float]) -> str:
    """
    判断均线排列
    返回: bullish(多头) / bearish(空头) / mixed(交织)
    """
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)

    values = [v for v in [ma5, ma10, ma20, ma60] if v is not None]
    if len(values) < 3:
        return "insufficient_data"

    # 多头排列: 短期均线 > 长期均线
    if all(values[i] >= values[i + 1] for i in range(len(values) - 1)):
        return "bullish"
    # 空头排列: 短期均线 < 长期均线
    if all(values[i] <= values[i + 1] for i in range(len(values) - 1)):
        return "bearish"
    return "mixed"


def calc_rsi(closes: list[float], period: int = 14) -> float | None:
    """相对强弱指标 RSI"""
    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calc_ema(data: list[float], period: int) -> float:
    """指数移动平均 EMA"""
    if not data:
        return 0
    k = 2.0 / (period + 1)
    ema = data[0]
    for price in data[1:]:
        ema = price * k + ema * (1 - k)
    return ema


def calc_macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """
    MACD 指标
    返回: {dif, dea, macd_hist, is_golden_cross, is_death_cross}
    """
    if len(closes) < slow + signal:
        return {"dif": 0, "dea": 0, "macd_hist": 0, "is_golden_cross": False, "is_death_cross": False}

    # 计算 DIF 序列
    ema_fast_series = []
    ema_slow_series = []

    k_fast = 2.0 / (fast + 1)
    k_slow = 2.0 / (slow + 1)

    ema_f = closes[0]
    ema_s = closes[0]

    dif_series = []
    for price in closes:
        ema_f = price * k_fast + ema_f * (1 - k_fast)
        ema_s = price * k_slow + ema_s * (1 - k_slow)
        dif_series.append(ema_f - ema_s)

    # 计算 DEA (DIF 的 signal 周期 EMA)
    k_signal = 2.0 / (signal + 1)
    dea = dif_series[0]
    dea_series = []
    for dif in dif_series:
        dea = dif * k_signal + dea * (1 - k_signal)
        dea_series.append(dea)

    dif = dif_series[-1]
    dea_val = dea_series[-1]
    macd_hist = 2 * (dif - dea_val)

    # 判断金叉/死叉（看最近两天）
    prev_dif = dif_series[-2]
    prev_dea = dea_series[-2]

    is_golden_cross = prev_dif <= prev_dea and dif > dea_val
    is_death_cross = prev_dif >= prev_dea and dif < dea_val

    return {
        "dif": dif,
        "dea": dea_val,
        "macd_hist": macd_hist,
        "is_golden_cross": is_golden_cross,
        "is_death_cross": is_death_cross,
    }


def calc_bollinger(closes: list[float], period: int = 20, num_std: float = 2.0) -> dict:
    """
    布林带
    返回: {upper, middle, lower, position(0-100), width}
    """
    if len(closes) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "position": 50, "width": 0}

    recent = closes[-period:]
    middle = sum(recent) / period
    variance = sum((x - middle) ** 2 for x in recent) / period
    std = math.sqrt(variance)

    upper = middle + num_std * std
    lower = middle - num_std * std
    width = upper - lower

    current = closes[-1]
    if width > 0:
        position = (current - lower) / width * 100
    else:
        position = 50

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "position": max(0, min(100, position)),
        "width": width,
    }


def calc_volume_ratio(volumes: list[int], short_period: int = 5, long_period: int = 20) -> float:
    """量比：短期均量 / 长期均量"""
    if len(volumes) < long_period:
        return 1.0
    short_avg = sum(volumes[-short_period:]) / short_period
    long_avg = sum(volumes[-long_period:]) / long_period
    if long_avg == 0:
        return 1.0
    return short_avg / long_avg


def calc_volatility(closes: list[float], period: int = 20) -> float:
    """年化波动率（基于日收益率标准差）"""
    if len(closes) < period + 1:
        return 0.0
    returns = []
    start = len(closes) - period
    for i in range(start, len(closes)):
        if closes[i - 1] != 0:
            ret = (closes[i] - closes[i - 1]) / closes[i - 1]
            returns.append(ret)
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    daily_std = math.sqrt(variance)
    return daily_std * math.sqrt(252) * 100  # 年化百分比


def calc_price_change(closes: list[float], period: int) -> float:
    """区间涨跌幅（%）"""
    if len(closes) < period + 1:
        return 0.0
    return (closes[-1] - closes[-period - 1]) / closes[-period - 1] * 100


def calc_all_indicators(klines: list[dict]) -> dict:
    """
    计算全部技术指标，返回完整指标字典
    """
    if not klines:
        return {}

    closes = [k["close"] for k in klines]
    volumes = [k["volume"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    current = closes[-1]

    # 均线
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)

    # 均线位置关系
    ma_positions = {}
    if ma5:
        ma_positions["ma5"] = "above" if current > ma5 else "below"
    if ma10:
        ma_positions["ma10"] = "above" if current > ma10 else "below"
    if ma20:
        ma_positions["ma20"] = "above" if current > ma20 else "below"
    if ma60:
        ma_positions["ma60"] = "above" if current > ma60 else "below"

    # RSI
    rsi6 = calc_rsi(closes, 6)
    rsi14 = calc_rsi(closes, 14)

    # MACD
    macd = calc_macd(closes)

    # 布林带
    boll = calc_bollinger(closes)

    # 量比
    vol_ratio = calc_volume_ratio(volumes)

    # 波动率
    volatility = calc_volatility(closes)

    # 区间涨跌幅
    chg_5d = calc_price_change(closes, 5)
    chg_10d = calc_price_change(closes, 10)
    chg_20d = calc_price_change(closes, 20)

    # 20日高低点
    recent_20_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
    recent_20_low = min(lows[-20:]) if len(lows) >= 20 else min(lows)
    price_position_20 = (
        (current - recent_20_low) / (recent_20_high - recent_20_low) * 100
        if recent_20_high != recent_20_low else 50
    )

    # 均线排列
    alignment = judge_ma_alignment(closes)

    return {
        "current": current,
        "ma": {"ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60},
        "ma_positions": ma_positions,
        "ma_alignment": alignment,
        "rsi": {"rsi6": rsi6, "rsi14": rsi14},
        "macd": macd,
        "bollinger": boll,
        "volume_ratio": vol_ratio,
        "volatility": volatility,
        "price_changes": {"5d": chg_5d, "10d": chg_10d, "20d": chg_20d},
        "range_20d": {"high": recent_20_high, "low": recent_20_low, "amplitude": (recent_20_high - recent_20_low) / recent_20_low * 100},
        "price_position_20": price_position_20,
    }
