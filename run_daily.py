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

        # 保存报告
        os.makedirs("reports", exist_ok=True)
        base_report_path = os.path.join("reports", f"report_{date_str}.md")
        with open(base_report_path, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"\n✅ 基础报告已保存: {base_report_path}")

        # 推送微信
        sendkey = os.getenv("SERVERCHAN_SENDKEY", "")
        if sendkey:
            print("\n📤 推送到微信...")
            push_result = analyzer.push_serverchan(sendkey, title, body)
            if push_result.get("code") == 0:
                print("✅ 微信推送成功！")
            else:
                print(f"❌ 微信推送失败: {push_result}")
        else:
            print("\n⚠️ 未配置 SERVERCHAN_SENDKEY，跳过微信推送")

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

    # ====== 阶段 4: 合并完整报告 ======
    phase4_start = time.time()
    print(f"{'='*50}")
    print(f"📝 阶段 4/4: 生成完整合编报告")
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

        # 也推送到微信（如果配置了）
        sendkey = os.getenv("SERVERCHAN_SENDKEY", "")
        if sendkey:
            # 微信推送用精简版（基础分析 + yyPZ总览）
            summary_lines = []
            # 基础报告的摘要部分
            base_report_path = os.path.join("reports", f"report_{date_str}.md")
            if os.path.exists(base_report_path):
                with open(base_report_path, "r", encoding="utf-8") as f:
                    base_content = f.read()
                # 提取亮点部分
                for line in base_content.split("\n"):
                    if "值得看看" in line or "跟踪" in line:
                        summary_lines.append(line)
                    if line.startswith("- 🟢") or line.startswith("- 🔴") or line.startswith("- 📊") or line.startswith("- 💥"):
                        summary_lines.append(line)

            # 加上老龙反抽简表
            if yypz_results:
                summary_lines.append("\n**🐉 老龙反抽机会:**")
                for r in yypz_results[:5]:  # 最多列5只
                    summary_lines.append(f"  {r['stock']} {r['theme']} 评分{r['score']}")

            push_title = f"📊 全分析 {date_str}"
            push_body = "\n".join(summary_lines) if summary_lines else full_body

            from notifier import push_serverchan
            push_result = push_serverchan(sendkey, push_title, push_body)
            if push_result.get("code") == 0:
                print("✅ 完整报告微信推送成功！")
            else:
                print(f"⚠️ 微信推送结果: {push_result}")

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
    print(f"   阶段4(合并):     {elapsed4:.1f}s")
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
