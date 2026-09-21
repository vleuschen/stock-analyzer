#!/usr/bin/env python3
"""
🚀 A股全自动分析系统 —— 每日运行入口
整合：基础分析 → yyPZ老龙反抽策略 → 郑希视角研报 → 推送

运行顺序：
  1. analyzer              → 自选股技术面分析
  2. yypz_strategy         → 老龙反抽选股
  3. zhengxi_report        → 郑希视角研报（归档用）
  4. push_format           → 组装一条适合微信阅读的推送正文并发送

定时：北京时间每天 6:00（见 .github/workflows/daily-analysis.yml）跑的是「昨天收盘」，
所以归档文件名一律用行情数据日期而不是运行日期，报告和推送里标的日期也是数据日期。

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
import zhengxi_report
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


def pick_zhengxi_quotes(max_age_days: int = 60, limit: int = 2) -> list:
    """
    提取郑希观点句。
    语料超过 max_age_days 天没有更新时返回空列表（避免每天推送同一段陈旧内容）。
    """
    try:
        files = zhengxi_report._find_corpus_files()
        newest = next((f["date"] for f in files if f.get("date")), "")
        if not newest:
            return []
        age = (datetime.now() - datetime.strptime(newest, "%Y-%m-%d")).days
        if age > max_age_days:
            print(f"  ⏭️ 郑希语料最新 {newest}（{age} 天前），已跳过该板块")
            return []

        substance = ("看好", "关注", "景气", "ROE", "流动性", "资本开支", "光通信",
                     "算力", "新能源", "电力", "估值", "周期", "复利", "机会")
        noise = ("采访", "记者", "现场", "问他", "他说", "笑道", "回忆", "风险提示",
                 "免责", "转载", "来源：", "|")

        matches = zhengxi_report.search_corpus(
            ["展望", "看好", "光通信", "AI资本开支", "景气", "通胀"], max_results=3
        )
        quotes, seen = [], set()
        for match in matches:
            for snippet in match.get("snippets", []):
                clean = zhengxi_report._clean_snippet(snippet)
                for sentence in clean.split("。"):
                    sentence = sentence.strip().lstrip("#•-*> ").strip()
                    if not (15 <= len(sentence) <= 70):
                        continue
                    if any(word in sentence for word in noise):
                        continue
                    if not any(word in sentence for word in substance):
                        continue
                    key = sentence[:12]
                    if key in seen:
                        continue
                    seen.add(key)
                    quotes.append(sentence + "。")
                    if len(quotes) >= limit:
                        return quotes
        return quotes
    except Exception as e:
        print(f"  ⚠️ 郑希观点提取失败: {e}")
        return []


def pick_data_date(stock_results: list, fallback: str) -> str:
    """取行情数据实际日期（K线最新一天），周末/节假日运行时避免标成当天"""
    dates = [r.get("data_date") for r in stock_results if r.get("data_date")]
    return max(dates) if dates else fallback


# 最后一次真正推出去的数据日期（一行文本，随仓库提交，Actions 每次都是干净检出）
PUSH_STATE = os.path.join("reports", ".last_push_date")


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

    # ====== 阶段 3: 郑希视角研报 ======
    phase3_start = time.time()
    print(f"{'='*50}")
    print(f"📋 阶段 3/4: 郑希视角研报")
    print(f"{'='*50}")

    zhengxi_body = ""
    try:
        zhengxi_body = zhengxi_report.generate_full_zhengxi_report(
            date_str=data_date,
            stock_results=stock_results,
            yypz_results=yypz_results,
        )
        with open(os.path.join("reports", f"zhengxi_{data_date}.md"), "w", encoding="utf-8") as f:
            f.write(zhengxi_body)
        print(f"\n✅ 郑希研报已保存")
    except Exception as e:
        print(f"❌ 郑希研报生成失败: {e}")
        import traceback
        traceback.print_exc()

    elapsed3 = time.time() - phase3_start
    print(f"\n⏱️ 阶段 3 耗时: {elapsed3:.1f}s\n")

    # ====== 阶段 4: 合并报告 + 推送 ======
    phase4_start = time.time()
    print(f"{'='*50}")
    print(f"📝 阶段 4/4: 生成完整合编报告 + 推送")
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
        full_lines.append("\n\n---\n\n")
        full_lines.append(zhengxi_body)

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
        zhengxi_quotes = pick_zhengxi_quotes()

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
            zhengxi_quotes=zhengxi_quotes,
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
            sent_before = last_pushed_date()
            if not sendkey:
                print("⚠️ 未配置 SERVERCHAN_SENDKEY，跳过发送（正文已存档）")
            elif sent_before == data_date:
                # 6 点跑的是「上一个交易日」的收盘：周一和周六早上取到的都是周五的数据，
                # 法定节假日更是天天一样。同一个交易日重复推一遍纯粹是打扰。
                print(f"⏭️ {data_date} 的复盘已经推过了，跳过发送（正文已归档）")
            else:
                from notifier import push_serverchan
                result = push_serverchan(sendkey, title, body)
                if result.get("code") == 0:
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
    print(f"   阶段3(郑希研报): {elapsed3:.1f}s")
    print(f"   阶段4(合并+推送): {elapsed4:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
