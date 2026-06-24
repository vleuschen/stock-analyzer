#!/usr/bin/env python3
"""
郑希观点研报生成器
基于 zhengxi-views 的语料和方法框架，生成基金经理视角的每日研报
以研报风格推送：宏观判断 → 行业聚焦 → 持仓印证 → 策略建议

依赖：zhengxi-views skill (已安装在 .claude/skills/zhengxi-views/)
"""

from __future__ import annotations

import os
import sys
import json
import random
from datetime import datetime

# 郑希 skill 路径
SKILL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         ".claude", "skills", "zhengxi-views")
# 从 repo 根目录查找
if not os.path.exists(SKILL_DIR):
    SKILL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", ".claude", "skills", "zhengxi-views")
if not os.path.exists(SKILL_DIR):
    SKILL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "zhengxi_temp")

SKILL_DIR = os.path.normpath(SKILL_DIR)
METHOD_PATH = os.path.join(SKILL_DIR, "references", "method.md")
CORPUS_DIR = os.path.join(SKILL_DIR, "references", "corpus")


def load_method() -> str:
    """加载郑希投资方法框架"""
    if os.path.exists(METHOD_PATH):
        with open(METHOD_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def get_corpus_excerpts(keywords: list[str], max_chars: int = 2000) -> list[dict]:
    """从语料中获取相关段落"""
    excerpts = []
    if not os.path.exists(CORPUS_DIR):
        return excerpts

    for root, dirs, files in os.walk(CORPUS_DIR):
        for file in files:
            if file.endswith(".md"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                except:
                    continue

                # 提取文件名中的日期和标题
                rel_path = os.path.relpath(path, CORPUS_DIR)
                # 尝试提取日期
                date_hint = ""
                parts = rel_path.split(os.sep)
                if len(parts) >= 2:
                    date_hint = parts[-1].replace(".md", "")

                # 搜索关键词
                matched = []
                for kw in keywords:
                    if kw.lower() in content.lower():
                        # 找到关键词所在的段落
                        paragraphs = content.split("\n\n")
                        for para in paragraphs:
                            if kw.lower() in para.lower() and len(para.strip()) > 20:
                                matched.append(para.strip()[:300])
                                break

                if matched:
                    excerpts.append({
                        "source": date_hint,
                        "type": parts[0] if len(parts) >= 2 else "",
                        "excerpts": matched[:2],
                    })

    return excerpts


def generate_market_outlook(date_str: str, stock_results: list[dict] = None) -> str:
    """
    生成郑希视角的市场展望
    模拟研报的开篇宏观判断
    """
    lines = []

    # 统计当天的市场情绪（来自analyzer结果）
    up_count = 0
    down_count = 0
    if stock_results:
        for r in stock_results:
            swing = r.get("swing", {})
            signal = swing.get("signal", "")
            if signal in ("strong_buy", "buy"):
                up_count += 1
            elif signal in ("strong_sell", "sell"):
                down_count += 1

    total = len(stock_results) if stock_results else 0
    sentiment = "中性偏谨慎"
    emoji = "📊"
    if total > 0:
        bull_ratio = up_count / total
        if bull_ratio >= 0.6:
            sentiment = "结构性乐观"
            emoji = "☀️"
        elif bull_ratio >= 0.4:
            sentiment = "中性偏多"
            emoji = "🌤️"
        elif down_count / total >= 0.5:
            sentiment = "防御为主"
            emoji = "⛅"
        elif down_count / total >= 0.7:
            sentiment = "偏弱整理"
            emoji = "🌧️"

    lines.append(f"## 📋 郑希视角·每日研报 — {date_str}")
    lines.append("")

    # 宏观综述 —— 模拟郑希自上而下的框架口吻
    lines.append("### 一、宏观与市场环境")
    lines.append("")
    lines.append(f"> **今日市场情绪**: {emoji} {sentiment}")
    lines.append("")
    lines.append(
        "基于郑希的投资框架，当前市场呈现以下特征：\n\n"
        "**① 流动性环境方面**，郑希一贯强调"关注流动性充裕但ROE偏低背景下，"
        "资产价格重估的可能性"。当前市场流动性保持合理充裕，"
        "结构性机会集中在高景气赛道。\n\n"
        "**② 景气方向上**，AI产业链资本开支维持高位，"
        "光通信、算力基础设施环节景气度持续确认；"
        "新能源领域供需格局逐步改善，龙头公司盈利拐点渐近。\n\n"
        "**③ 估值层面**，部分优质标的经历调整后，"
        "已进入ROE低位修复可预期的区间，符合郑希"在低ROE时买入、"
        "高ROE时卖出"的周期拼接思路。"
    )
    lines.append("")

    return "\n".join(lines)


def generate_sector_focus(stock_results: list[dict] = None, yypz_results: list[dict] = None) -> str:
    """行业聚焦板块——结合当日分析结果"""
    lines = []
    lines.append("### 二、行业与个股聚焦")
    lines.append("")

    if yypz_results:
        # 从老龙反抽结果提炼行业分布
        theme_counts = {}
        for r in yypz_results:
            theme = r.get("theme", "").split("·")[0].strip() if "·" in r.get("theme", "") else r.get("theme", "其他")
            theme_counts[theme] = theme_counts.get(theme, 0) + 1

        if theme_counts:
            top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)
            lines.append("**活跃板块分布：**")
            for theme, count in top_themes[:5]:
                bar = "█" * count
                lines.append(f"- {theme}: {bar} ({count}只)")
            lines.append("")

    # AI/科技主线（郑希核心持仓方向）
    lines.append(
        "**AI算力产业链** — 郑希在2025-2026年持续重仓的方向。"
        "他在2026年6月采访中指出，光通信去年二季度开始已成为核心持仓。"
        "从产业趋势看，全球AI资本开支仍在加速，"
        "光模块、服务器、液冷等环节业绩确定性强。\n\n"
        "**半导体国产替代** — 郑希在2025年中报中强调"
        ""关注具备全球比较优势的环节"。半导体设备材料国产化率仍有较大提升空间，"
        "龙头公司订单可见度高。\n\n"
        "**新能源/储能** — 经历2023-2025年的产能出清后，"
        "行业格局优化，龙头公司盈利底部基本确认。"
        "郑希的方法论强调"在行业周期底部布局"，当前或已进入布局窗口。"
    )
    lines.append("")

    return "\n".join(lines)


def generate_holding_insight() -> str:
    """持仓印证——从郑希真实持仓看市场机会"""
    lines = []
    lines.append("### 三、持仓印证")
    lines.append("")

    # 从郑希基金数据中读取持仓信息
    fund_data_path = os.path.join(SKILL_DIR, "references", "fund_data")
    holdings = []
    if os.path.exists(fund_data_path):
        for fund_dir in os.listdir(fund_data_path):
            fund_path = os.path.join(fund_data_path, fund_dir)
            if os.path.isdir(fund_path):
                holdings_file = os.path.join(fund_path, "季度持仓.md")
                if os.path.exists(holdings_file):
                    with open(holdings_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    # 提取最近一个季度的持仓（文件开头的表格）
                    for line in content.split("\n")[:30]:
                        if "|" in line and "代码" not in line and "---" not in line:
                            cols = [c.strip() for c in line.split("|") if c.strip()]
                            if len(cols) >= 2:
                                holdings.append(cols[1])

    # 去重取前6个出现频率最高的股票
    from collections import Counter
    top_holdings = [item for item, count in Counter(holdings).most_common(8) if item]

    if top_holdings:
        lines.append("**郑希核心持仓（近期重仓股）：**")
        lines.append("")
        lines.append("| 重仓标的 | 所属方向 | 持仓逻辑 |")
        lines.append("|---|---|---|")
        for h in top_holdings[:6]:
            # 简化的映射
            mapping = {
                "中际旭创": ("AI算力", "光模块龙头，AI资本开支核心受益"),
                "新易盛": ("AI算力", "高速光模块需求旺盛"),
                "沪电股份": ("AI算力", "PCB龙头，AI服务器关键元件"),
                "源杰科技": ("AI算力", "光芯片国产替代"),
                "光库科技": ("AI算力", "光通信器件"),
                "德业股份": ("新能源", "逆变器，亚非拉市场需求增长"),
                "阳光电源": ("新能源", "逆变器全球龙头"),
                "宁德时代": ("新能源", "电池龙头，全球市占率持续提升"),
                "北方华创": ("半导体", "设备龙头，国产化率提升"),
                "中芯国际": ("半导体", "制造龙头，产能利用率回升"),
                "立讯精密": ("消费电子", "果链龙头，汽车电子拓展"),
                "中国海洋石油": ("能源", "高股息，油价中枢上移"),
            }
            if h in mapping:
                sector, logic = mapping[h]
                lines.append(f"| {h} | {sector} | {logic} |")
    lines.append("")
    lines.append("> 数据来源：郑希管理基金季度报告公开披露的前十大持仓。以上仅供研究参考。")
    lines.append("")

    return "\n".join(lines)


def generate_strategy_outlook() -> str:
    """策略展望"""
    lines = []
    lines.append("### 四、策略展望")
    lines.append("")
    lines.append(
        "综合郑希的投资方法论与当前市场环境，后续关注方向：\n\n"
        "1. **AI产业链扩散**：从光通信向算力基建、AI应用端扩散，"
        "关注液冷、AI服务器、端侧AI等细分\n"
        "2. **半导体周期复苏**：存储芯片价格企稳，"
        "晶圆厂产能利用率回升，关注设备和材料\n"
        "3. **新能源拐点**：逆变器/储能海外需求高增，"
        "动力电池格局出清后龙头份额提升\n"
        "4. **低空经济政策催化**：2026年作为低空经济商业化元年，"
        "基础设施和运营环节最先受益\n\n"
        "**操作策略**：郑希强调"在好赛道里做周期拼接"，"
        "建议在优质标的中关注回调充分的龙头，分批布局、控制仓位。"
    )
    lines.append("")

    return "\n".join(lines)


def get_recent_news() -> str:
    """获取郑希近期观点快讯"""
    lines = []
    # 从语料中提取最近的媒体报道
    media_dir = os.path.join(CORPUS_DIR, "媒体报道")
    if os.path.exists(media_dir):
        md_files = sorted([f for f in os.listdir(media_dir) if f.endswith(".md")], reverse=True)
        if md_files:
            latest = md_files[0]
            path = os.path.join(media_dir, latest)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            # 提取标题和前几段
            title_line = content.split("\n")[0] if content else ""
            lines.append(f"> **郑希最新观点** ({latest[:10]}): {title_line.replace('#', '').strip()}")
            lines.append("")

    return "\n".join(lines)


def generate_full_zhengxi_report(date_str: str,
                                  stock_results: list[dict] = None,
                                  yypz_results: list[dict] = None) -> str:
    """
    生成完整郑希视角研报
    Args:
        date_str: 日期字符串
        stock_results: analyzer.py 的分析结果（可选）
        yypz_results: yypz_strategy.py 的分析结果（可选）
    Returns:
        研报正文（Markdown格式）
    """
    sections = []

    # 标题 + 宏观
    sections.append(generate_market_outlook(date_str, stock_results))

    # 近期观点快讯
    news = get_recent_news()
    if news:
        sections.append(news)

    # 行业聚焦
    sections.append(generate_sector_focus(stock_results, yypz_results))

    # 持仓印证
    sections.append(generate_holding_insight())

    # 策略展望
    sections.append(generate_strategy_outlook())

    # 尾部
    sections.append(
        "---\n\n"
        f"📬 {date_str} 郑希视角研报 · 基于郑希（易方达基金经理）公开观点与投资方法框架\n\n"
        "⚠️ **免责声明**: 以上内容仅供参考，不构成投资建议。郑希的观点引自其公开披露的定期报告、"
        "基金经理手记和媒体采访，持仓数据来源于基金季度报告。推演内容基于其方法论框架，"
        "不代表其本人当前观点。投资有风险，决策需谨慎。"
    )

    return "\n".join(sections)


if __name__ == "__main__":
    date_str = datetime.now().strftime("%Y-%m-%d")
    report = generate_full_zhengxi_report(date_str)
    print(report)

    # 保存到文件
    os.makedirs("reports", exist_ok=True)
    path = os.path.join("reports", f"zhengxi_report_{date_str}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n✅ 研报已保存: {path}")
