#!/usr/bin/env python3
"""
🚀 A股全自动分析系统 —— 每日运行入口
整合：基础分析 → yyPZ老龙反抽策略 → 股票推送

运行顺序：
  1. analyzer              → 自选股技术面分析
  2. yypz_strategy         → 老龙反抽选股
  3. push_format           → 组装一条适合微信阅读的推送正文并发送

定时：北京时间每个工作日 18:00（见 .github/workflows/daily-analysis.yml）运行，
以当天收盘行情数据日期生成报告和推送。

环境变量：
  SERVERCHAN_SENDKEY  方糖 SendKey，缺省则只生成不发送
  PUSH_DRY_RUN=1      只生成推送正文并打印预览，不发送（本地调排版用）
  GITHUB_OUTPUT       Actions 专用：把数据日期透给归档步骤，本机运行时不设置
"""

import os
import re
import sys
import time
import glob
from datetime import datetime

# 确保能导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analyzer
import signals
import yypz_strategy
import push_format
from data_fetcher import fetch_realtime_quote

# 报告文件里的信号 emoji → 内部信号名（词表见 signals.py，勿在别处复制）
SIGNAL_BY_EMOJI = signals.SIGNAL_BY_MARK

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


# ============================================================
# 辅助函数
# ============================================================

def fetch_indices() -> list:
    """抓取三大指数（腾讯行情，指数代码同样适用）"""
    indices = []
    for symbol, label in [("sh000001", "上证"), ("sz399001", "深成"), ("sz399006", "创业板")]:
        try:
            code, market = symbol[2:], symbol[:2]
            quote = fetch_realtime_quote(code, market)
            if quote.get("error"):
                continue
            indices.append((label, quote.get("price", 0), quote.get("pct_change", 0)))
        except Exception:
            continue
    return indices


def load_previous_signals(before_date: str) -> dict:
    """
    读取上一个交易日的信号，用于生成「今日变化」。
    返回 {股票名: 信号名}
    """
    candidates = (glob.glob(os.path.join("reports", "daily", "*", "*", "report_*.md"))
                  + glob.glob(os.path.join("reports", "report_*.md")))

    dated = []
    for path in candidates:
        match = DATE_RE.search(os.path.basename(path))
        if match and match.group(1) < before_date:
            dated.append((match.group(1), path))
    if not dated:
        return {}

    dated.sort(reverse=True)
    signals = {}
    for line in open(dated[0][1], encoding="utf-8"):
        if not line.startswith("### "):
            continue
        name = line.replace("### ", "").split("（")[0].strip()
        for emoji, sig in SIGNAL_BY_EMOJI.items():
            if emoji in line:
                signals[name] = sig
                break
    print(f"  📚 对比基准: {dated[0][1]}（{len(signals)} 只）")
    return signals


def pick_data_date(stock_results: list, fallback: str) -> str:
    """取行情数据实际日期（K线最新一天），避免报告日期脱离行情数据"""
    dates = [r.get("data_date") for r in stock_results if r.get("data_date")]
    return max(dates) if dates else fallback


# 最后一次真正推出去的数据日期（一行文本，随仓库提交，Actions 每次都是干净检出）
PUSH_STATE = os.path.join("reports", ".last_push_date")


def push_requires_sendkey(trigger: str) -> bool:
    """CI 的真实推送入口没有密钥时必须失败，避免绿灯但手机无消息。"""
    return trigger in ("schedule", "workflow_dispatch")


def should_skip_duplicate(data_date: str, sent_before: str, trigger: str) -> bool:
    """
    只对真实 CI 推送入口做按行情日期去重。

    代码 push 是排版/回归运行，即使环境误传了非 dry-run，也不能消耗定时推送
    的资格；否则下一次 schedule 会把同一行情日期误判成“已经推过”。
    """
    return trigger in ("schedule", "workflow_dispatch") and bool(data_date) and data_date == sent_before


def last_pushed_date() -> str:
    try:
        with open(PUSH_STATE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def mark_pushed(data_date: str):
    try:
        with open(PUSH_STATE, "w", encoding="utf-8") as f:
            f.write(data_date)
    except OSError as e:
        print(f"  ⚠️ 记录推送日期失败: {e}")


# ============================================================
# 主流程
# ============================================================

def main():
    start_time = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"🚀 A股全自动分析系统 | {date_str}")
    print(f"{'='*60}\n")

    os.makedirs("reports", exist_ok=True)

    # ====== 阶段 1: 基础分析 ======
    phase1_start = time.time()
    print(f"{'='*50}")
    print(f"📊 阶段 1/4: 基础技术面分析")
    print(f"{'='*50}")

    stock_results = []
    # 归档文件名一律用「行情数据日期」，不用运行日期：
    # 早上 6 点跑的时候，运行日期是今天，复盘的却是昨天 —— 按运行日期命名的话，
    # 周一那个文件里装的会是周五的数据，周六的周复盘读到的整周信号就整体错位一天。
    data_date = date_str
    try:
        config = analyzer.load_config()
        stocks = config.get("stocks", [])
        kline_days = config.get("analysis", {}).get("kline_days", 120)
        print(f"📋 跟踪标的: {len(stocks)} 只\n")

        for stock_config in stocks:
            stock_results.append(analyzer.analyze_stock(stock_config, kline_days))
            time.sleep(0.8)

        data_date = pick_data_date(stock_results, date_str)
        print(f"\n📅 行情数据日期 {data_date}（运行日期 {date_str}）")

        _, body = analyzer.format_full_report(stock_results, data_date)
        base_report_path = os.path.join("reports", f"report_{data_date}.md")
        with open(base_report_path, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"\n✅ 基础报告已保存: {base_report_path}")
    except Exception as e:
        print(f"❌ 基础分析失败: {e}")
        import traceback
        traceback.print_exc()

    elapsed1 = time.time() - phase1_start
    print(f"⏱️ 阶段 1 耗时: {elapsed1:.1f}s\n")

    # ====== 阶段 2: yyPZ 老龙反抽 ======
    phase2_start = time.time()
    print(f"{'='*50}")
    print(f"🐉 阶段 2/4: yyPZ·老龙反抽策略")
    print(f"{'='*50}")

    yypz_results = []
    try:
        yypz_results = yypz_strategy.run_old_dragon_rebound()
        yypz_report = yypz_strategy.format_dragon_report(yypz_results, data_date)
        with open(os.path.join("reports", f"yypz_{data_date}.md"), "w", encoding="utf-8") as f:
            f.write(yypz_report)
        print(f"\n✅ yyPZ报告已保存")
    except Exception as e:
        print(f"❌ yyPZ策略失败: {e}")
        import traceback
        traceback.print_exc()

    elapsed2 = time.time() - phase2_start
    print(f"\n⏱️ 阶段 2 耗时: {elapsed2:.1f}s\n")

    # ====== 阶段 3: 合并报告 + 推送 ======
    phase4_start = time.time()
    print(f"{'='*50}")
    print(f"📝 阶段 3/3: 生成完整合编报告 + 推送")
    print(f"{'='*50}")

    try:
        # ---- 完整合编报告（归档用）----
        full_lines = [f"# 📊 A股全分析报告 | {data_date}", "", "---", ""]
        base_report_path = os.path.join("reports", f"report_{data_date}.md")
        if os.path.exists(base_report_path):
            with open(base_report_path, "r", encoding="utf-8") as f:
                full_lines.append(f.read())
        full_lines.append("\n\n---\n\n")
        full_lines.append(yypz_strategy.format_dragon_report(yypz_results, data_date))
        full_path = os.path.join("reports", f"full_{data_date}.md")
        with open(full_path, "w", encoding="utf-8") as f:
            f.write("\n".join(full_lines))
        print(f"✅ 完整报告已保存: {full_path}")

        # ---- 推送内容 ----
        # 正文无论是否发送都要生成：一是本地预览排版（PUSH_DRY_RUN=1），
        # 二是把真正推出去的文案一起归档，事后能核对「微信里看到的」和「报告里的」是否一致。
        print(f"\n📤 组装推送（数据日期 {data_date}）...")

        indices = fetch_indices()
        prev_signals = load_previous_signals(data_date)
        valid = [r for r in stock_results if not r.get("error")]
        signal_counts = {}
        for r in valid:
            sig = r.get("swing", {}).get("signal", "unknown")
            signal_counts[sig] = signal_counts.get(sig, 0) + 1

        title = push_format.build_push_title(data_date, len(valid), signal_counts)
        body = push_format.build_push_body(
            data_date,
            stock_results,
            yypz_results=yypz_results,
            indices=indices,
            prev_signals=prev_signals,
            dragon_pool_size=len(yypz_strategy.OLD_DRAGON_POOL),
        )

        push_path = os.path.join("reports", f"push_{data_date}.md")
        with open(push_path, "w", encoding="utf-8") as f:
            f.write(f"{title}\n\n{body}\n")
        print(f"   标题: {title}")
        print(f"   正文: {len(body)} 字 → {push_path}")

        # 归档步骤要按数据日期去找文件，把日期透出去（Actions 之外是空操作）
        github_output = os.getenv("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a", encoding="utf-8") as f:
                f.write(f"data_date={data_date}\n")

        if os.getenv("PUSH_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on"):
            print("\n🧪 PUSH_DRY_RUN 已开启，只生成不发送。推送正文预览：\n")
            print("-" * 60)
            print(body)
            print("-" * 60)
        else:
            sendkey = os.getenv("SERVERCHAN_SENDKEY", "")
            trigger = os.getenv("PUSH_TRIGGER", "local").strip().lower()
            sent_before = last_pushed_date()
            if not sendkey:
                message = "❌ 未配置 SERVERCHAN_SENDKEY，真实推送无法完成"
                print(message)
                if push_requires_sendkey(trigger):
                    sys.exit(1)
                print("   本地运行已跳过发送（正文已存档）")
            elif should_skip_duplicate(data_date, sent_before, trigger):
                # 同一个行情日期不重复推送，避免手动运行或节假日重复打扰。
                print(f"⏭️ {data_date} 的复盘已经推过了，跳过发送（正文已归档）")
            else:
                from notifier import push_serverchan
                result = push_serverchan(sendkey, title, body)
                if result.get("code") == 0:
                    # 代码 push 只用于生成/验版，哪怕外部误把 dry-run 关掉，
                    # 也不能污染定时任务的去重状态。
                    if trigger != "push":
                        mark_pushed(data_date)
                    print("✅ 推送成功！")
                else:
                    print(f"❌ 推送失败: {result}")
                    sys.exit(1)
    except Exception as e:
        print(f"❌ 合编报告/推送失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    elapsed4 = time.time() - phase4_start
    total_elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"✅ 全部分析完成！总耗时 {total_elapsed:.1f} 秒")
    print(f"   阶段1(基础分析): {elapsed1:.1f}s")
    print(f"   阶段2(yyPZ):     {elapsed2:.1f}s")
    print(f"   阶段3(合并+推送): {elapsed4:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
