#!/usr/bin/env python3
"""
周末复盘生成脚本
读取本周所有日报 → 调用 DeepSeek 生成周评 → 写入 reports/weekly/
零外部依赖，使用 Python 标准库
"""

import os
import sys
import json
import time
import glob
import http.client
import ssl
import urllib.parse
from datetime import datetime, timedelta


def get_week_range() -> tuple:
    """计算本周一和本周五的日期"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def load_daily_reports(monday: datetime, friday: datetime) -> list:
    """读取周一至周五的所有日报（优先 daily 归档，回退到根目录）"""
    reports = []
    for i in range(5):
        day = monday + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        year = day.strftime("%Y")
        month = day.strftime("%m")

        # 优先从归档目录读取
        path = os.path.join("reports", "daily", year, month, f"report_{date_str}.md")
        if not os.path.exists(path):
            # 回退到根目录 reports/
            path = os.path.join("reports", f"report_{date_str}.md")

        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            reports.append({"date": date_str, "content": content, "path": path})
            print(f"  ✅ 已读取: {path}")
        else:
            reports.append({"date": date_str, "content": "", "path": path})
            print(f"  ⚠️ 未找到: {path}")
    return reports


def call_deepseek(api_key: str, prompt: str) -> str:
    """调用 DeepSeek API"""
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个专业的A股复盘分析师，擅长用通俗易懂的语言总结一周市场变化。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 2048,
    })

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    conn = http.client.HTTPSConnection("api.deepseek.com", 443, timeout=60, context=ctx)
    conn.request(
        "POST", "/v1/chat/completions",
        body=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    resp = conn.getresponse()
    result = json.loads(resp.read().decode("utf-8"))
    conn.close()

    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0]["message"]["content"].strip()
    else:
        raise Exception(f"DeepSeek API 返回异常: {result}")


def build_prompt(reports: list, monday: datetime, friday: datetime) -> str:
    """构建 DeepSeek 的 prompt"""
    week_label = f"{monday.strftime('%m/%d')} - {friday.strftime('%m/%d')}"
    year_week = monday.strftime("%Y-W%W")
    lines = [
        f"你是一个A股复盘分析师。以下是本周（{year_week}，{week_label}）每日的股票分析报告：\n",
    ]

    for report in reports:
        if report["content"]:
            lines.append(f"【{report['date']}】\n{report['content']}\n")
        else:
            lines.append(f"【{report['date']}】（无数据）\n")

    lines.append("""
请写一篇本周复盘总结，要求：
1. 开头用一句话整体评价本周市场情绪变化
2. 对每只跟踪标的，讲一下它的走势变化和信号演变
3. 如果某只股票信号发生切换（如观望转偏空/偏多），重点说明
4. 用自然的中文，像朋友在聊股票，不要 AI 套话
5. 控制在 500 字左右
6. 结尾给出下周的关注方向建议
""")

    return "\n".join(lines)


def parse_signals(reports: list) -> dict:
    """从日报中解析每只股票每天的信号（简单文本匹配）"""
    stock_signals = {}  # {stock_name: {date: signal}}

    for report in reports:
        content = report["content"]
        date = report["date"]
        if not content:
            continue

        # 寻找 ### 标题行（股票名）
        for line in content.split("\n"):
            if line.startswith("### "):
                # 格式: "### 芭田股份（002170）📉 偏空"
                parts = line.replace("### ", "").split("（")
                name = parts[0].strip()

                # 提取 emoji 信号
                signal = "未知"
                for emoji, tag in [("🚀", "买入"), ("📈", "偏多"), ("⏳", "观望"),
                                   ("📉", "偏空"), ("⚠️", "回避")]:
                    if emoji in line:
                        signal = tag
                        break

                if name not in stock_signals:
                    stock_signals[name] = {}
                stock_signals[name][date] = signal

    return stock_signals


def format_signal_table(stock_signals: dict, reports: list) -> str:
    """生成信号统计 Markdown 表格"""
    # 收集所有有数据的日期
    dates = [r["date"] for r in reports if r["content"]]

    if not stock_signals or not dates:
        return "（本周无交易数据）"

    lines = ["| 股票 | " + " | ".join(dates) + " | 本周小结 |"]
    lines.append("|" + "---|" * (len(dates) + 2))

    for name, signals in stock_signals.items():
        # 本周每天的信号
        row_signals = [signals.get(d, "-") for d in dates]
        # 判断趋势
        unique_signals = list(dict.fromkeys([s for s in row_signals if s != "-"]))
        if len(unique_signals) <= 1:
            summary = "持续" + (unique_signals[0] if unique_signals else "无数据")
        else:
            summary = f"{unique_signals[0]}→{unique_signals[-1]}"

        lines.append(f"| {name} | " + " | ".join(row_signals) + f" | {summary} |")

    return "\n".join(lines)


def push_weekly_report(sendkey: str, title: str, body: str) -> dict:
    """推送周复盘到微信"""
    if not sendkey:
        print("⚠️ 未配置 SERVERCHAN_SENDKEY，跳过微信推送")
        return {"code": -1}

    if len(title) > 100:
        title = title[:97] + "..."

    payload = urllib.parse.urlencode({"title": title, "desp": body}).encode("utf-8")
    path = f"/{sendkey}.send"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    conn = http.client.HTTPSConnection("sctapi.ftqq.com", 443, timeout=30, context=ctx)
    conn.request("POST", path, body=payload,
                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    resp = conn.getresponse()
    result = json.loads(resp.read().decode("utf-8"))
    conn.close()

    if result.get("code") == 0:
        print(f"✅ 周复盘推送成功: {title}")
    else:
        print(f"⚠️ 推送异常: {result}")
    return result


def main():
    start_time = time.time()

    # 计算本周范围
    monday, friday = get_week_range()
    week_label = f"{monday.strftime('%m/%d')} - {friday.strftime('%m/%d')}"
    year_week = monday.strftime("%Y-W%W")
    print(f"📆 周复盘 | {year_week} ({week_label})")

    # 读取日报
    print("📖 读取本周日报...")
    reports = load_daily_reports(monday, friday)
    valid_reports = [r for r in reports if r["content"]]
    if not valid_reports:
        print("⚠️ 本周没有找到已归档的日报（首次运行时历史数据尚未归档）")
        print("   ✅ 下周开始，每日报告会自动归档到 reports/daily/ 目录下")
        body = (
            f"# 📆 周复盘 | {year_week} ({week_label})\n\n"
            "## 📝 周评\n\n"
            "本周是复盘功能首次启用，暂无历史日报数据。\n\n"
            "从下周开始，每个交易日的分析报告将自动归档，届时周复盘将包含完整的 AI 分析和信号统计。\n\n"
            "---\n\n"
            f"📬 自动生成于 {datetime.now().strftime('%Y-%m-%d')} · 仅供参考，不构成投资建议"
        )
        # 保存文件并退出（不报错）
        os.makedirs("reports/weekly", exist_ok=True)
        output_path = os.path.join("reports", "weekly", f"weekly-{year_week}.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"✅ 已保存占位周报: {output_path}")
        return
    print(f"   ️共找到 {len(valid_reports)} 天有效日报")

    # 解析信号统计
    print("📊 解析信号变化...")
    stock_signals = parse_signals(reports)
    signal_table = format_signal_table(stock_signals, reports)
    print(f"   ️跟踪 {len(stock_signals)} 只股票")

    # 调用 DeepSeek 生成周评
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("❌ 未配置 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)

    print("🤖 调用 DeepSeek 生成周评...")
    prompt = build_prompt(valid_reports, monday, friday)
    try:
        review = call_deepseek(api_key, prompt)
        print(f"   ✅ DeepSeek 返回 {len(review)} 字")
    except Exception as e:
        print(f"❌ DeepSeek 调用失败: {e}")
        review = "（AI 复盘生成失败，请稍后重试）"

    # 组装周报
    title = f"📆 周复盘 | {year_week} ({week_label})"
    body_lines = [
        f"# {title}",
        "",
        "## 📝 周评",
        "",
        review,
        "",
        "---",
        "",
        "## 📊 本周信号统计",
        "",
        signal_table,
        "",
        "---",
        "",
        f"📬 自动生成于 {datetime.now().strftime('%Y-%m-%d')} · 仅供参考，不构成投资建议",
        "",
    ]
    body = "\n".join(body_lines)

    # 保存文件
    os.makedirs("reports/weekly", exist_ok=True)
    output_path = os.path.join("reports", "weekly", f"weekly-{year_week}.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"✅ 已保存: {output_path}")

    # 推送微信
    sendkey = os.getenv("SERVERCHAN_SENDKEY", "")
    if sendkey:
        print("📤 推送周报到微信...")
        push_weekly_report(sendkey, title, body)

    # 输出到控制台
    if not os.getenv("GITHUB_ACTIONS"):
        print("\n" + body)

    elapsed = time.time() - start_time
    print(f"\n⏱️ 耗时 {elapsed:.1f} 秒")


if __name__ == "__main__":
    main()
