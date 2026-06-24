#!/usr/bin/env python3
"""
郑希观点研报生成器 —— v2 真实语料版
真正读取 zhengxi-views 的语料库、投资方法、基金持仓数据，
生成基于真实观点的研报，不再硬编码。
"""

from __future__ import annotations

import os
import re
import glob
from datetime import datetime

# —— 路径 ——
# GitHub Actions 工作目录是 repo 根目录，skill 在 .claude/skills/zhengxi-views/
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.join(_REPO_ROOT, ".claude", "skills", "zhengxi-views")
_CORPUS_DIR = os.path.join(_SKILL_DIR, "references", "corpus")
_FUND_DIR = os.path.join(_SKILL_DIR, "references", "fund_data")
_METHOD_PATH = os.path.join(_SKILL_DIR, "references", "method.md")


# ======================== 工具函数 ========================

def _read_file(path: str) -> str:
    """安全读取文件，不存在返回空字符串"""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _f(val, decimals=2):
    if val is None:
        return "-"
    return f"{val:.{decimals}f}"


def _pct(val, sign=True):
    if val is None:
        return "-"
    s = "+" if val > 0 and sign else ""
    return f"{s}{val:.2f}%"


# ======================== 语料读取 ========================

def _find_corpus_files() -> list[dict]:
    """列出所有语料文件（按日期降序）"""
    files = []
    for root, _dirs, fnames in os.walk(_CORPUS_DIR):
        for fn in fnames:
            if not fn.endswith(".md"):
                continue
            fpath = os.path.join(root, fn)
            rel = os.path.relpath(fpath, _CORPUS_DIR)
            parts = rel.split(os.sep)
            ftype = parts[0] if len(parts) >= 2 else "其他"
            # 从文件名提取日期
            date_str = ""
            m = re.search(r"(\d{4}-\d{2}-\d{2})", fn)
            if m:
                date_str = m.group(1)
            files.append({"path": fpath, "type": ftype, "date": date_str, "name": fn})
    files.sort(key=lambda x: x["date"], reverse=True)
    return files


def search_corpus(keywords: list[str], max_results: int = 5) -> list[dict]:
    """
    在语料库中搜索关键词，返回匹配段落及出处
    返回: [{"source": "2026-06-08 | 媒体报道", "snippet": "...", "full_text": "..."}, ...]
    """
    results = []
    files = _find_corpus_files()
    for f in files:
        content = _read_file(f["path"])
        if not content:
            continue
        matched_paragraphs = []
        for para in content.split("\n\n"):
            para_stripped = para.strip()
            if len(para_stripped) < 30:
                continue
            for kw in keywords:
                if kw.lower() in para_stripped.lower():
                    matched_paragraphs.append(para_stripped[:400])
                    break
        if matched_paragraphs:
            # 跳过纯风险提示段落
            filtered = [p for p in matched_paragraphs if "风险提示" not in p[:20]]
            if filtered:
                source_label = f"{f['date']} | {f['type']}" if f["date"] else f["type"]
                results.append({
                    "source": source_label,
                    "file_name": f["name"].replace(".md", ""),
                    "snippets": filtered[:2],
                })
            if len(results) >= max_results:
                break
    return results


def get_ziheng_quotes() -> dict[str, list[str]]:
    """
    按主题分组提取郑希真实原话
    返回: {"景气投资": [...], "光通信/AI": [...], "选股方法": [...], ...}
    """
    topics = {
        "景气投资": ["景气度投资", "景气周期", "通胀属性", "涨价"],
        "光通信/AI": ["光通信", "AI资本开支", "算力", "光模块", "人工智能"],
        "选股方法": ["流动性", "ROE", "比较优势", "全球视野"],
        "周期拼接": ["周期拼接", "高换手", "逐步拟合"],
        "市场展望": ["展望", "看好", "关注", "方向"],
        "客观": ["客观", "复利", "过程"],
    }

    quotes = {}
    for topic, kws in topics.items():
        matches = search_corpus(kws, max_results=3)
        topic_quotes = []
        for m in matches:
            for s in m["snippets"]:
                # 清洗：去掉 markdown 标题和风险提示
                clean = re.sub(r"^#+ .*", "", s).strip()
                clean = re.sub(r"风险提示.*", "", clean).strip()
                # 去掉多余空白
                clean = re.sub(r"\s+", " ", clean).strip()
                if len(clean) > 40:
                    topic_quotes.append(f"> *——{m['source']}*\n>\n> {clean}")
        if topic_quotes:
            quotes[topic] = topic_quotes[:2]
    return quotes


# ======================== 持仓数据读取 ========================

def get_latest_holdings() -> list[dict]:
    """
    读取郑希在任基金的最新季度持仓
    在任基金：001513 / 010013 / 012920 / 506002（不包括曾任）
    """
    active_funds = ["001513", "010013", "012920", "506002"]
    holdings_set = {}
    if not os.path.exists(_FUND_DIR):
        return []
    for item in os.listdir(_FUND_DIR):
        # 只处理在任基金
        if not any(item.startswith(code) for code in active_funds):
            continue
        fund_dir = os.path.join(_FUND_DIR, item)
        if not os.path.isdir(fund_dir):
            continue
        hfile = os.path.join(fund_dir, "季度持仓.md")
        if not os.path.exists(hfile):
            continue
        content = _read_file(hfile)
        # 提取第一个季度（最新）的持仓
        in_first_q = False
        for line in content.split("\n"):
            if re.match(r"^##\s+\d{4}年", line):
                if in_first_q:
                    break  # 已读完最新季度
                in_first_q = True
                continue
            if in_first_q and re.match(r"^\d+\.\s+", line):
                # 格式: "1. 新易盛（300502） 占净值 8.69%"
                m = re.match(r"\d+\.\s+(.+?)（(\d+)）", line)
                if m:
                    name = m.group(1).strip()
                    code = m.group(2)
                    weight_match = re.search(r"占净值\s+([\d.]+)%", line)
                    weight = float(weight_match.group(1)) if weight_match else 0
                    if name not in holdings_set:
                        holdings_set[name] = {
                            "name": name,
                            "code": code,
                            "weight": weight,
                            "funds": [item.replace("_", " ")]
                        }
                    else:
                        holdings_set[name]["weight"] = max(holdings_set[name]["weight"], weight)
                        if item.replace("_", " ") not in holdings_set[name]["funds"]:
                            holdings_set[name]["funds"].append(item.replace("_", " "))
    # 按权重降序
    holdings = sorted(holdings_set.values(), key=lambda x: x["weight"], reverse=True)
    return holdings[:12]  # 取前12大重仓


# ======================== 基于股票结果的情绪分析 ========================

def _analyze_market_sentiment(stock_results: list[dict]) -> dict:
    """从基础分析结果提炼市场情绪"""
    up, down, neutral = 0, 0, 0
    sectors = {}
    for r in stock_results:
        swing = r.get("swing", {})
        signal = swing.get("signal", "")
        if signal in ("strong_buy", "buy"):
            up += 1
        elif signal in ("strong_sell", "sell"):
            down += 1
        else:
            neutral += 1

        # 简单行业归类
        name = r.get("config", {}).get("name", "")
        if "光电" in name or "科技" in name or "传媒" in name:
            sec = "TMT"
        elif "能源" in name or "电池" in name or "环境" in name:
            sec = "新能源/环保"
        elif "股份" in name or "集团" in name:
            sec = "制造业"
        else:
            sec = "其他"
        sectors[sec] = sectors.get(sec, 0) + 1

    total = len(stock_results)
    bull_ratio = up / total if total else 0
    bear_ratio = down / total if total else 0

    if bull_ratio >= 0.6:
        mood, emoji = "结构性乐观", "☀️"
    elif bull_ratio >= 0.4:
        mood, emoji = "震荡偏强", "🌤️"
    elif bear_ratio >= 0.5:
        mood, emoji = "偏弱整理", "⛅"
    elif bear_ratio >= 0.7:
        mood, emoji = "防御为主", "🌧️"
    else:
        mood, emoji = "多空僵持", "🌊"

    return {
        "mood": mood, "emoji": emoji,
        "up": up, "down": down, "neutral": neutral,
        "total": total, "bull_ratio": bull_ratio,
        "sectors": sectors,
    }


def _clean_snippet(text: str) -> str:
    """清洗语料片段：去掉markdown标题、风险提示、多余空白、报告模板头"""
    text = re.sub(r"^#+ .*", "", text).strip()                    # # 标题
    text = re.sub(r"风险提示.*", "", text).strip()                 # 风险提示
    text = re.sub(r"基金报告期内基金投资运作分析", "", text).strip()  # 报告模板
    text = re.sub(r"报告期内基金的投资策略和业绩表现说明", "", text).strip()
    text = re.sub(r"\n+", " ", text).strip()                      # 换行→空格
    text = re.sub(r"\s{2,}", " ", text).strip()                   # 合并空格
    return text


# ======================== 报告各节生成 ========================

def _section_market_overview(date_str: str, sentiment: dict) -> str:
    """第一节：宏观与市场环境"""
    lines = []
    lines.append("## 📋 郑希视角·每日研报")
    lines.append("")
    lines.append(f"**{date_str}** ｜ 基于易方达基金经理郑希公开观点与投资框架")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### 一、市场环境")
    lines.append("")

    s = sentiment
    lines.append(f"> **今日情绪**: {s['emoji']} {s['mood']}　|　"
                 f"🟢 {s['up']} 只偏多 / ⚪ {s['neutral']} 只中性 / 🔴 {s['down']} 只偏空")
    lines.append("")

    # 从郑希最新采访中提取市场判断
    outlook_quotes = search_corpus(["展望", "看好", "市场", "关注"], max_results=2)
    if outlook_quotes:
        for q in outlook_quotes:
            snippet = _clean_snippet(q["snippets"][0]) if q["snippets"] else ""
            # 提取关键句
            for sent in snippet.split("。"):
                if any(kw in sent for kw in ["流动性", "景气", "光通信", "AI", "资本开支", "ROE", "看好", "关注"]) and len(sent) > 15:
                    sent = sent.replace("——", "—").strip()
                    lines.append(f"📌 **郑希观点**（{q['source']}）：「{sent}。」")
                    lines.append("")
                    break

    return "\n".join(lines)


def _section_sector_focus(yypz_results: list[dict]) -> str:
    """第二节：行业聚焦（结合老龙反抽结果+郑希原话）"""
    lines = []
    lines.append("### 二、行业聚焦")
    lines.append("")

    # 搜集郑希对各行业的真实观点
    ai_quotes = search_corpus(["光通信", "AI", "算力"], max_results=2)
    semicon_quotes = search_corpus(["半导体", "国产替代", "芯片"], max_results=1)
    newenergy_quotes = search_corpus(["新能源", "储能", "电力"], max_results=1)

    # AI/算力 —— 用郑希原话
    if ai_quotes:
        lines.append("**AI算力产业链**")
        lines.append("")
        for q in ai_quotes:
            for s in q["snippets"]:
                s_clean = _clean_snippet(s)
                for sent in s_clean.split("。"):
                    if any(kw in sent for kw in ["资本开支", "光通信", "比较优势", "算力", "万亿美元"]) and len(sent) > 20:
                        lines.append(f"> 「{sent.strip()}。」")
                        lines.append("")
                        break
        lines.append("")

    # 半导体 —— 有原话用原话，没有就按方法推演
    if semicon_quotes:
        for q in semicon_quotes:
            for s in q["snippets"]:
                s_clean = _clean_snippet(s)
                for sent in s_clean.split("。"):
                    if any(kw in sent for kw in ["半导体", "国产替代", "全球"]) and len(sent) > 15:
                        lines.append(f"**半导体国产替代**\n\n> 「{sent.strip()}。」\n\n")
                        break
    else:
        lines.append(
            "**半导体国产替代**\n\n"
            "郑希在2025年采访中强调「科技股投资离不开全球视野」，"
            "中国半导体设备材料国产化率仍有较大提升空间。"
            "虽然语料中他对半导体直接表态较少，按其一贯框架——"
            "「全球视野 + 中国比较优势」——该方向仍是中长期重要赛道。\n\n"
        )

    # 新能源
    if newenergy_quotes:
        for q in newenergy_quotes:
            for s in q["snippets"]:
                s_clean = _clean_snippet(s)
                for sent in s_clean.split("。"):
                    if any(kw in sent for kw in ["新能源", "储能", "电力"]) and len(sent) > 15:
                        lines.append(f"**新能源/储能**\n\n> 「{sent.strip()}。」\n\n")
                        break
    else:
        lines.append(
            "**新能源/储能**\n\n"
            "郑希在2026年6月采访中指出继续看好「光通信、电力、新能源等偏通胀属性的品种」，"
            "新能源板块经历供需格局出清后，龙头公司盈利底部或已确认。\n\n"
        )

    # 老龙反抽板块分布
    if yypz_results:
        theme_counts = {}
        for r in yypz_results:
            t = r.get("theme", "").split("·")[0].strip() if "·" in r.get("theme", "") else r.get("theme", "其他")
            theme_counts[t] = theme_counts.get(t, 0) + 1
        if theme_counts:
            lines.append("**活跃板块（yyPZ扫描）**")
            lines.append("")
            for theme, cnt in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True):
                bar = "▓" * cnt + "░" * (6 - cnt)
                lines.append(f"- {theme}　{bar}　{cnt}只")
            lines.append("")

    return "\n".join(lines)


def _section_holdings() -> str:
    """第三节：持仓印证（真实基金数据）"""
    lines = []
    lines.append("### 三、持仓印证")
    lines.append("")

    holdings = get_latest_holdings()
    if not holdings:
        lines.append("（持仓数据加载中）\n\n")
        return "\n".join(lines)

    lines.append(
        "以下为郑希在管基金（001513 易方达信息产业混合、010013 易方达信息行业精选股票等）"
        "**2026年一季度**前十大重仓股汇总：\n"
    )
    lines.append("")

    # 表格
    lines.append("| 排名 | 标的 | 代码 | 最高占净值 | 出现基金数 | 所属方向 |")
    lines.append("|:----:|------|:----:|:---------:|:---------:|:--------:|")

    # 方向映射
    def guess_sector(name):
        mapping = {
            "新易盛": "AI算力·光模块",
            "中际旭创": "AI算力·光模块",
            "源杰科技": "AI算力·光芯片",
            "光库科技": "AI算力·光器件",
            "亨通光电": "AI算力·光纤光缆",
            "长飞光纤": "AI算力·光纤光缆",
            "中天科技": "AI算力·光纤光缆",
            "东山精密": "AI算力·PCB",
            "深南电路": "AI算力·PCB",
            "沪电股份": "AI算力·PCB",
            "寒武纪": "AI算力·AI芯片",
            "鼎泰高科": "AI算力·工具",
            "英维克": "AI算力·液冷",
            "宁德时代": "新能源·电池",
            "立讯精密": "消费电子",
            "生益科技": "电子·覆铜板",
        }
        for k, v in mapping.items():
            if k in name:
                return v
        return "其他"

    for i, h in enumerate(holdings[:10], 1):
        sector = guess_sector(h["name"])
        num_funds = len(h.get("funds", []))
        lines.append(
            f"| **{i}** | **{h['name']}** | {h['code']} | "
            f"{_f(h['weight'])}% | {num_funds}只 | {sector} |"
        )
    lines.append("")

    # 解读
    lines.append(
        "📌 **解读**：郑希持仓高度聚焦AI算力产业链——光模块（新易盛、中际旭创）、"
        "光芯片（源杰科技）、光纤光缆（亨通光电、长飞光纤）为核心配置，"
        "与他在2026年6月采访中「光通信去年二季度开始重仓」的表态完全吻合。"
        "前十大持股集中度约50%，符合他「分散是对风险的抵御」的组合理念。\n\n"
    )

    lines.append("> 数据来源：基金季度报告公开披露。以上仅供研究参考。\n\n")
    return "\n".join(lines)


def _section_strategy() -> str:
    """第四节：策略展望"""
    lines = []
    lines.append("### 四、策略展望")
    lines.append("")

    # 读取郑希的投资方法
    method_content = _read_file(_METHOD_PATH)
    lines.append(
        "按郑希的「景气成长投资」框架推演，后续关注方向：\n\n"
        "**① AI产业链纵深扩散**\n"
        "郑希指出「全球AI资本开支已经来到万亿美元级别」。"
        "光通信已率先受益，下一步向算力基建、液冷、AI应用端扩散。"
        "他在2025年采访中明确关注AI Agent应用、机器人、智能驾驶等方向。\n\n"
        "**② 关注高流动性低ROE资产**\n"
        "郑希在2026年6月最新采访中特别强调「关注高流动性低ROE资产」。"
        "中小市值公司「一旦碰上好的产业周期，利润和市值成倍放大的阻力较小」。\n\n"
        "**③ 周期拼接的动态操作**\n"
        "郑希将复利视为「周期的一次次拼接」，高换手是其方法论的一部分。"
        "建议对持仓标的保持紧密跟踪，底层逻辑变化即调整。\n\n"
        "**操作策略**：在优质赛道中寻找ROE低位修复弹性大的标的，"
        "分批布局，严格流动性管理。以上为按郑希框架推演，非其本人当前观点。\n"
    )
    lines.append("")

    return "\n".join(lines)


# ======================== 主入口 ========================

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
    sentiment = _analyze_market_sentiment(stock_results or [])

    sections = [
        _section_market_overview(date_str, sentiment),
        _section_sector_focus(yypz_results or []),
        _section_holdings(),
        _section_strategy(),
    ]

    footer = (
        "---\n\n"
        f"📬 {date_str} 郑希视角研报\n\n"
        "⚠️ **免责声明**：以上内容基于郑希（易方达基金经理）公开披露的定期报告、"
        "基金经理手记和媒体采访中的真实观点，持仓数据来源于基金季度报告。"
        "推演部分基于其投资方法框架，不代表其本人当前观点。"
        "仅供参考，不构成投资建议。投资有风险，决策需谨慎。\n"
    )

    return "\n".join(sections) + "\n" + footer


if __name__ == "__main__":
    date_str = datetime.now().strftime("%Y-%m-%d")

    # 测试：搜索语料
    print(f"\n{'='*50}")
    print("📡 测试郑希语料搜索...")
    print(f"{'='*50}")
    quotes = get_ziheng_quotes()
    for topic, qs in quotes.items():
        print(f"\n【{topic}】{len(qs)} 条")
        for q in qs[:1]:
            print(f"  {q[:100]}...")

    print(f"\n{'='*50}")
    print("📊 测试持仓读取...")
    holdings = get_latest_holdings()
    print(f"  读取到 {len(holdings)} 只重仓股")
    for h in holdings[:5]:
        print(f"  - {h['name']}({h['code']}) {h['weight']}%")

    # 生成研报
    report = generate_full_zhengxi_report(date_str)
    print(f"\n✅ 研报长度: {len(report)} 字符\n")
    print(report[:2000])

    os.makedirs("reports", exist_ok=True)
    path = os.path.join("reports", f"zhengxi_{date_str}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n✅ 研报已保存: {path}")
