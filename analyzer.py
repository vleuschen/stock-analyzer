#!/usr/bin/env python3
"""
A股自动分析 & 微信推送 —— 主程序
读取配置 → 抓取数据 → 计算指标 → 波段策略 → 格式化 → 方糖推送

零外部依赖，全部使用 Python 内置模块
"""

import os
import sys
import json
import time
from datetime import datetime

from data_fetcher import fetch_stock_data
from indicators import calc_all_indicators
from swing_strategy import analyze_swing_signals
from formatter import format_full_report
from notifier import push_serverchan


def load_config(config_path: str = None) -> dict:
    """
    加载配置文件
    优先 JSON，如果 PyYAML 可用也支持 YAML
    """
    # 查找配置文件（优先 json，其次 yaml）
    if config_path and os.path.exists(config_path):
        paths = [config_path]
    else:
        paths = ["config.json", "config.yaml", "config.yml"]

    for path in paths:
        if not os.path.exists(path):
            continue

        if path.endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        elif path.endswith((".yaml", ".yml")):
            try:
                import yaml
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
            except ImportError:
                print(f"⚠️ PyYAML 未安装，跳过 YAML 配置: {path}")
                continue

    print("❌ 未找到配置文件（config.json 或 config.yaml）")
    sys.exit(1)


def is_trading_day() -> bool:
    """简单判断是否为交易日（工作日）"""
    today = datetime.now()
    return today.weekday() < 5  # 0=周一 ... 4=周五


def analyze_stock(stock_config: dict, kline_days: int = 120) -> dict:
    """分析单只股票"""
    code = stock_config["code"]
    market = stock_config.get("market", "sz")
    name = stock_config.get("name", code)

    print(f"\n{'='*50}")
    print(f"📊 正在分析: {name} ({code})")
    print(f"{'='*50}")

    # 1. 抓取数据
    print("  [1/3] 抓取行情数据...")
    stock_data = fetch_stock_data(code, market, kline_days=kline_days)

    if stock_data.get("quote", {}).get("error"):
        print(f"  ❌ 数据获取失败: {stock_data['quote']['error']}")
        return {"config": stock_config, "error": stock_data["quote"]["error"]}

    quote = stock_data["quote"]
    klines = stock_data["klines"]
    money_flow = stock_data["money_flow"]

    print(f"  ✅ 最新价: {quote['price']}  涨跌: {quote['pct_change']}%")
    print(f"  ✅ K线数据: {len(klines)} 条")

    # 2. 计算技术指标
    print("  [2/3] 计算技术指标...")
    indicators = calc_all_indicators(klines)
    print(f"  ✅ 均线排列: {indicators.get('ma_alignment', 'unknown')}")
    print(f"  ✅ RSI(14): {indicators.get('rsi', {}).get('rsi14', 'N/A')}")

    # 3. 波段策略
    print("  [3/3] 分析波段信号...")
    swing = analyze_swing_signals(indicators, money_flow)
    print(f"  ✅ 信号: {swing.get('signal_emoji', '')} {swing.get('signal_text', '')}")
    print(f"  ✅ 建议: {swing.get('action', '')}")

    return {
        "config": stock_config,
        "quote": quote,
        "klines": klines,
        "indicators": indicators,
        "swing": swing,
    }


def main():
    """主流程"""
    start_time = time.time()

    # 获取当前日期
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"🚀 A股自动分析系统启动 | {date_str}")
    print(f"   运行环境: {'GitHub Actions' if os.getenv('GITHUB_ACTIONS') else '本地'}")

    # 加载配置
    config = load_config()
    stocks = config.get("stocks", [])
    analysis_config = config.get("analysis", {})
    kline_days = analysis_config.get("kline_days", 120)

    if not stocks:
        print("❌ 配置文件中没有股票列表")
        sys.exit(1)

    print(f"📋 跟踪标的: {len(stocks)} 只")
    for s in stocks:
        print(f"   - {s.get('name', '')} ({s.get('code', '')})")

    # 交易日检查
    if not is_trading_day():
        print("\n⚠️ 今天不是工作日，数据可能为上一交易日")

    # 逐只分析
    results = []
    for stock_config in stocks:
        result = analyze_stock(stock_config, kline_days)
        results.append(result)
        time.sleep(1)  # API 限频

    # 格式化报告
    print(f"\n{'='*50}")
    print("📝 生成分析报告...")
    title, body = format_full_report(results, date_str)

    # 保存到文件
    report_path = os.path.join("reports", f"report_{date_str}.md")
    os.makedirs("reports", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"✅ 报告已保存: {report_path}")

    # 推送到微信
    sendkey = os.getenv("SERVERCHAN_SENDKEY", "")
    if sendkey:
        print("\n📤 推送到微信...")
        push_result = push_serverchan(sendkey, title, body)
        if push_result.get("code") == 0:
            print("✅ 微信推送成功！")
        else:
            print(f"❌ 微信推送失败: {push_result}")
    else:
        print("\n⚠️ 未配置 SERVERCHAN_SENDKEY，跳过微信推送")
        print("   报告仅保存到本地文件")

    # 统计
    elapsed = time.time() - start_time
    print(f"\n{'='*50}")
    print(f"✅ 分析完成！耗时 {elapsed:.1f} 秒")
    print(f"{'='*50}")

    # 非 GitHub Actions 环境输出报告到控制台
    if not os.getenv("GITHUB_ACTIONS"):
        print("\n" + body)


if __name__ == "__main__":
    main()
