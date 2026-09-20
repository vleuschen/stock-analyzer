#!/usr/bin/env python3
"""
信号回测脚本 —— 用历史数据检验 swing_strategy 的评分分布与有效性

用途：
  1. 检查信号分布是否退化（v1 版本 60% 观望 + 27% 偏空，几乎不给多头信号）
  2. 统计每种信号之后 5 个交易日的平均涨跌，验证信号方向是否有效

用法：
    python scripts/backtest_signals.py [回溯天数]
"""

import os
import sys
import json
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_fetcher import fetch_kline, fetch_money_flow  # noqa: E402
from indicators import calc_all_indicators  # noqa: E402
from swing_strategy import analyze_swing_signals  # noqa: E402


def load_watchlist() -> list:
    with open("config.json", encoding="utf-8") as f:
        return json.load(f).get("stocks", [])


def build_flow_window(flow_rows: list, date: str, window: int = 10) -> list:
    """取 date（含）之前最近 window 天的资金流，日期倒序"""
    return [row for row in flow_rows if row["date"] <= date][:window]


def main():
    back_days = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    stocks = load_watchlist()

    signal_count = Counter()
    signal_scores = defaultdict(list)
    forward_returns = defaultdict(list)
    samples = []

    for stock in stocks:
        code, market = stock["code"], stock.get("market", "sz")
        name = stock.get("name", code)

        klines = fetch_kline(code, market, days=260)
        if len(klines) < 80:
            print(f"  ⚠️ {name} K线不足，跳过")
            continue

        flows = fetch_money_flow(code, market, days=back_days + 20)

        start = max(60, len(klines) - back_days)
        for i in range(start, len(klines) - 5):
            window = klines[:i + 1]
            indicators = calc_all_indicators(window)
            if not indicators:
                continue
            flow = build_flow_window(flows, klines[i]["date"])
            swing = analyze_swing_signals(indicators, flow)

            signal = swing["signal"]
            signal_count[signal] += 1
            signal_scores[signal].append(swing["score"])

            fwd = (klines[i + 5]["close"] - klines[i]["close"]) / klines[i]["close"] * 100
            forward_returns[signal].append(fwd)
            samples.append((klines[i]["date"], name, signal, swing["score"], fwd))

        print(f"  ✅ {name} 回测完成（{len(klines)} 根K线）")

    total = sum(signal_count.values())
    if not total:
        print("没有可用样本")
        return

    order = ["strong_buy", "buy", "neutral", "sell", "strong_sell"]
    label = {"strong_buy": "🟢强烈买入", "buy": "🟢偏多", "neutral": "🟡观望",
             "sell": "🔴偏空", "strong_sell": "⚠️回避"}

    # 全样本基准：用来分辨「信号有效」和「这段行情本来就涨」
    baseline = [fwd for rets in forward_returns.values() for fwd in rets]
    base_avg = sum(baseline) / len(baseline)

    def _median(values: list) -> float:
        s = sorted(values)
        mid = len(s) // 2
        return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

    print(f"\n{'='*74}")
    print(f"信号分布与 5 日前瞻收益（样本 {total} 个，回溯 {back_days} 个交易日）")
    print(f"基准：全样本 5 日平均 {base_avg:+.2f}%（超额 = 该信号 - 基准）")
    print(f"{'='*74}")
    print(f"{'信号':<12}{'次数':>6}{'占比':>8}{'平均分':>8}{'5日平均':>10}"
          f"{'超额':>9}{'中位数':>9}{'胜率':>8}")
    for sig in order:
        n = signal_count.get(sig, 0)
        if not n:
            continue
        rets = forward_returns[sig]
        avg_score = sum(signal_scores[sig]) / n
        avg_ret = sum(rets) / len(rets)
        win = sum(1 for r in rets if r > 0) / len(rets) * 100
        print(f"{label[sig]:<12}{n:>6}{n / total * 100:>7.1f}%{avg_score:>8.1f}"
              f"{avg_ret:>9.2f}%{avg_ret - base_avg:>8.2f}%{_median(rets):>8.2f}%{win:>7.1f}%")

    print("\n最看好的 10 个样本（按评分）:")
    for date, name, sig, score, fwd in sorted(samples, key=lambda x: -x[3])[:10]:
        print(f"  {date} {name:<8} {label[sig]:<10} {score:>6.1f}分  5日后 {fwd:+.2f}%")


if __name__ == "__main__":
    main()
