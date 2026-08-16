#!/usr/bin/env python3
"""
🚀 A股全自动分析系统 —— 每日运行入口
整合：基础分析 → yyPZ老龙反抽策略 → 郑希视角研报
运行顺序：
  1. analyzer.main()          → 基础技术面分析 + 微信推送
  2. yypz_strategy            → 老龙反抽选股
  3. zhengxi_report           → 郑希视角研报
  4. 合并报告 + 提交到仓库
"""

import os
import sys
import time
import json
from datetime import datetime

# 确保能导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analyzer
import yypz_strategy
import zhengxi_report


def main():
    start_time = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"🚀 A股全自动分析系统 | {date_str}")
    print(f"{'='*60}\n")

    # ====== 阶段 1: 基础分析 ======
    phase1_start = time.time()
    print(f"{'='*50}")
    print(f"📊 阶段 1/4: 基础技术面分析")
    print(f"{'='*50}")

    stock_results = []
    try:
        # 手动调用 analyzer 的核心逻辑
        config = analyzer.load_config()
        stocks = config.get("stocks", [])
        analysis_config = config.get("analysis", {})
        kline_days = analysis_config.get("kline_days", 120)

        print(f"📋 跟踪标的: {len(stocks)} 只\n")

        for stock_config in stocks:
            result = analyzer.analyze_stock(stock_config, kline_days)
            stock_results.append(result)
            time.sleep(0.8)

        # 生成基础报告
        title, body = analyzer.format_full_report(stock_results, date_str)

        # 保存报告（暂不推送，等郑希研报生成后一起推）
        os.makedirs("reports", exist_ok=True)
        base_report_path = os.path.join("reports", f"report_{date_str}.md")
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
        yypz_report = yypz_strategy.format_dragon_report(yypz_results, date_str)

        # 保存报告
        yypz_path = os.path.join("reports", f"yypz_{date_str}.md")
        with open(yypz_path, "w", encoding="utf-8") as f:
            f.write(yypz_report)
        print(f"\n✅ yyPZ报告已保存: {yypz_path}")

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
            date_str=date_str,
            stock_results=stock_results,
            yypz_results=yypz_results,
        )

        # 保存报告
        zhengxi_path = os.path.join("reports", f"zhengxi_{date_str}.md")
        with open(zhengxi_path, "w", encoding="utf-8") as f:
            f.write(zhengxi_body)
        print(f"\n✅ 郑希研报已保存: {zhengxi_path}")

    except Exception as e:
        print(f"❌ 郑希研报生成失败: {e}")
        import traceback
        traceback.print_exc()

    elapsed3 = time.time() - phase3_start
    print(f"\n⏱️ 阶段 3 耗时: {elapsed3:.1f}s\n")

    # ====== 阶段 4: 合并完整报告 + 综合推送（含郑希观点+每日筛选）======
    phase4_start = time.time()
    print(f"{'='*50}")
    print(f"📝 阶段 4/4: 生成完整合编报告 + 综合推送")
    print(f"{'='*50}")

    try:
        full_report_lines = [
            f"# 📊 A股全分析报告 | {date_str}",
            "",
            "---",
            "",
        ]

        # 插入基础分析
        base_report_path = os.path.join("reports", f"report_{date_str}.md")
        if os.path.exists(base_report_path):
            with open(base_report_path, "r", encoding="utf-8") as f:
                full_report_lines.append(f.read())

        # 插入yyPZ
        full_report_lines.append("\n\n---\n\n")
        full_report_lines.append(yypz_strategy.format_dragon_report(yypz_results, date_str))

        # 插入郑希研报
        full_report_lines.append("\n\n---\n\n")
        full_report_lines.append(zhengxi_body)

        full_body = "\n".join(full_report_lines)

        # 保存完整版
        full_path = os.path.join("reports", f"full_{date_str}.md")
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(full_body)
        print(f"✅ 完整报告已保存: {full_path}")

        # ======= 微信推送：从原始数据直接构造（不解析markdown） =======
        sendkey = os.getenv("SERVERCHAN_SENDKEY", "")
        if sendkey:
            print("\n📤 推送综合报告到微信...")

            def _p(v, d=2):
                if v is None: return "-"
                return f"{v:.{d}f}"

            def _q(q):
                qs = q.get("quote", {})
                return qs.get("price", 0), qs.get("pct_change", 0)

            def _fetch_index(symbol, label):
                """抓取大盘指数（腾讯 API，格式同个股）"""
                try:
                    from data_fetcher import fetch_realtime_quote
                    code, market = symbol[2:], symbol[:2]
                    q = fetch_realtime_quote(code, market)
                    if q.get("error"):
                        return None
                    return (label, q.get("price", 0), q.get("pct_change", 0))
                except Exception:
                    return None

            lines = []

            # ======== 标题 ========
            lines.append(f"# 📊 {date_str} 盘后复盘")
            lines.append("")

            # ======== 0. 大盘指数 ========
            indices = []
            for sym, label in [("sh000001", "上证"), ("sz399001", "深成"), ("sz399006", "创业板")]:
                idx = _fetch_index(sym, label)
                if idx:
                    indices.append(idx)
            if indices:
                parts = []
                for label, price, pct in indices:
                    arrow = "+" if pct > 0 else ""
                    parts.append(f"{label} {_p(price, 2)} ({arrow}{_p(pct, 2)}%)")
                lines.append("**📈 大盘**")
                lines.append("")
                lines.append("　".join(parts))
                lines.append("")

            # ======== 1. 今日总结 ========
            valid = [r for r in stock_results if not r.get("error")]
            if valid:
                pcts = [r.get("quote", {}).get("pct_change", 0) for r in valid]
                up = sum(1 for p in pcts if p > 0)
                down = sum(1 for p in pcts if p < 0)
                flat = len(valid) - up - down
                avg = sum(pcts) / len(pcts) if pcts else 0
                best = max(valid, key=lambda r: r.get("quote", {}).get("pct_change", 0))
                worst = min(valid, key=lambda r: r.get("quote", {}).get("pct_change", 0))

                sigs = {}
                for r in stock_results:
                    s = r.get("swing", {}).get("signal", "unknown")
                    sigs[s] = sigs.get(s, 0) + 1
                b = sigs.get("strong_buy", 0) + sigs.get("buy", 0)
                n = sigs.get("neutral", 0)
                se = sigs.get("sell", 0) + sigs.get("strong_sell", 0)

                if up > down:
                    mood = "多数飘红" if up >= len(valid) * 0.6 else "涨多跌少"
                elif down > up:
                    mood = "整体承压" if down >= len(valid) * 0.6 else "跌多涨少"
                else:
                    mood = "涨跌互现"

                lines.append(f"**📝 今日总结**　{mood}｜跟踪 {len(valid)} 只 · 涨 {up} / 平 {flat} / 跌 {down} · 均幅 {_p(avg, 2)}%")
                lines.append("")
                lines.append(f"> 最强：**{best.get('config', {}).get('name', '')}** {_p(best.get('quote', {}).get('pct_change', 0), 2)}%　"
                             f"最弱：**{worst.get('config', {}).get('name', '')}** {_p(worst.get('quote', {}).get('pct_change', 0), 2)}%")
                lines.append(f"> 信号：🟢偏多 {b} · ⚪观望 {n} · 🔴偏空 {se}")
                lines.append("")

            # ======== 2. 每日条件筛选（直接从数据算） ========
            # 对每只股票跑筛选条件，收集触发者
            hits = []
            for r in stock_results:
                if r.get("error"):
                    continue
                name = r.get("config", {}).get("name", "")
                ind = r.get("indicators", {})
                macd = ind.get("macd", {})
                rsi14 = ind.get("rsi", {}).get("rsi14")
                ma_align = ind.get("ma_alignment", "")
                vol_ratio = ind.get("volume_ratio", 1)
                boll_pos = ind.get("bollinger", {}).get("position", 50)
                chg5 = ind.get("price_changes", {}).get("5d", 0)
                sig_sw = r.get("swing", {}).get("signal", "")
                price, pct = _q(r)

                conds = []
                pts = 0
                if macd.get("is_golden_cross"):
                    conds.append("MACD金叉"); pts += 5
                if rsi14 is not None and rsi14 < 30:
                    conds.append(f"RSI={rsi14:.0f}超卖"); pts += 3
                if vol_ratio > 1.5 and ind.get("ma_positions", {}).get("ma10") == "above":
                    conds.append("放量突破MA10"); pts += 4
                if ma_align == "bullish":
                    conds.append("均线多头"); pts += 4
                if boll_pos < 15:
                    conds.append(f"布林下轨{boll_pos:.0f}%"); pts += 2
                if boll_pos > 85:
                    conds.append(f"布林上轨{boll_pos:.0f}%"); pts += 2
                if chg5 < -10:
                    conds.append(f"5日跌{chg5:.0f}%"); pts += 2
                mf = r.get("money_flow", [])
                if mf and mf[0].get("main_net", 0) > 50000000:
                    conds.append("主力流入"); pts += 3

                if conds:
                    hits.append((name, conds, pts, pct, sig_sw))

            hits.sort(key=lambda x: x[2], reverse=True)

            if hits:
                lines.append("**🔍 今日触发**")
                lines.append("")
                for i, (name, conds, pts, pct, sig) in enumerate(hits[:7]):
                    arrow = "+" if pct > 0 else ""
                    tag = {"strong_buy": "买入", "buy": "偏多", "neutral": "观望",
                           "sell": "偏空", "strong_sell": "回避"}.get(sig, "")
                    lines.append(
                        f"{'🏅' if pts >= 6 else '📌'} {name} ({arrow}{_p(pct, 1)}%) "
                        f"{' · '.join(conds)} → {tag}"
                    )
                lines.append("")
            else:
                lines.append("🔍 今日无标的触发筛选条件")
                lines.append("")

            # ======== 3. 老龙反抽 ========
            if yypz_results:
                lines.append("**🐉 老龙反抽**")
                lines.append("")
                for r in yypz_results[:5]:
                    star = "🚀" if r.get("signal") == "strong_rebound" else "🔄"
                    lines.append(f"  {star} {r['stock']} {r['theme']} {r['score']}分")
                lines.append("")

            # ======== 4. 郑希今日观点（硬编码底线 + 语料搜索） ========
            lines.append("**💡 郑希**")
            lines.append("")
            try:
                matches = zhengxi_report.search_corpus(
                    ["展望", "看好", "光通信", "AI资本开支", "景气", "通胀"], max_results=2
                )
                found = set()
                count = 0
                for m in matches:
                    for s in m.get("snippets", []):
                        for sent in s.split("。"):
                            sent = sent.strip()
                            if 20 <= len(sent) <= 90 and sent[:15] not in found:
                                found.add(sent[:15])
                                lines.append(f"  {count+1}. {sent}。")
                                count += 1
                                if count >= 3:
                                    break
                        if count >= 3:
                            break
                    if count >= 3:
                        break
                if count == 0:
                    raise ValueError("no clean quotes")
            except Exception:
                # 硬编码底线，全部来自2026年6月中国证券报真实采访
                lines.append("  1. 全球AI资本开支已到万亿美元级别，产业链纵深扩散")
                lines.append("  2. 关注高流动性低ROE资产，偏好ROE从低到高的修复弹性")
                lines.append("  3. 看好光通信、电力、新能源等偏通胀属性的品种")
                lines.append("  4. 复利是周期的一次次拼接，客观客观再客观")
            lines.append("")

            # ======== 5. 重点个股一句话 ========
            alert_lines = []
            for r in stock_results:
                if r.get("error"):
                    continue
                name = r.get("config", {}).get("name", "")
                swing = r.get("swing", {})
                sig = swing.get("signal", "")
                macd = r.get("indicators", {}).get("macd", {})
                rsi14 = r.get("indicators", {}).get("rsi", {}).get("rsi14")
                price, pct = _q(r)
                arrow = "+" if pct > 0 else ""
                # 只列今天有变化或信号明确的
                if sig in ("strong_buy", "strong_sell") or macd.get("is_golden_cross") or macd.get("is_death_cross"):
                    tag = {"strong_buy": "🚀买入", "buy": "📈偏多", "neutral": "⏳",
                           "sell": "📉偏空", "strong_sell": "⚠️回避"}.get(sig, "")
                    extra = ""
                    if macd.get("is_golden_cross"):
                        extra += " MACD金叉"
                    if macd.get("is_death_cross"):
                        extra += " MACD死叉"
                    if rsi14 and rsi14 < 30:
                        extra += f" RSI={rsi14:.0f}"
                    alert_lines.append(f"  {tag} {name} {arrow}{_p(pct, 1)}%{extra}")

            if alert_lines:
                lines.append("**📌 跟踪**")
                lines.append("")
                lines.extend(alert_lines)
                lines.append("")

            lines.append("---")
            lines.append("⚠️ 仅供复盘参考，不构成投资建议")

            push_title = f"📊 {date_str} 盘后复盘"
            push_body = "\n".join(lines)

            from notifier import push_serverchan
            push_result = push_serverchan(sendkey, push_title, push_body)
            if push_result.get("code") == 0:
                print("✅ 综合推送成功！")
            else:
                print(f"⚠️ 微信推送结果: {push_result}")
        else:
            print("\n⚠️ 未配置 SERVERCHAN_SENDKEY，跳过微信推送")

    except Exception as e:
        print(f"❌ 合编报告失败: {e}")
        import traceback
        traceback.print_exc()

    elapsed4 = time.time() - phase4_start
    total_elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"✅ 全部分析完成！总耗时 {total_elapsed:.1f} 秒")
    print(f"   阶段1(基础分析): {elapsed1:.1f}s")
    print(f"   阶段2(yyPZ):     {elapsed2:.1f}s")
    print(f"   阶段3(郑希研报): {elapsed3:.1f}s")
    print(f"   阶段4(合并+推送): {elapsed4:.1f}s")
    print(f"{'='*60}")

    # 非 GitHub Actions 环境输出报告
    if not os.getenv("GITHUB_ACTIONS"):
        print(f"\n📄 报告文件:")
        print(f"   - reports/report_{date_str}.md (基础分析)")
        print(f"   - reports/yypz_{date_str}.md (老龙反抽)")
        print(f"   - reports/zhengxi_{date_str}.md (郑希研报)")
        print(f"   - reports/full_{date_str}.md (完整合编)")


if __name__ == "__main__":
    main()
