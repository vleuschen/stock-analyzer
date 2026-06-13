# 每日归档 & 周末复盘 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 stock-analyzer 基础上增加每日报告归档（commit 到仓库）和周末 AI 复盘（DeepSeek 生成周评并推送微信）

**Architecture:** 不改动 analyzer.py/formatter.py 等现有代码，纯增量。Makefile 作为统一入口，scripts/ 放归档脚本和复盘脚本，.github/workflows/ 放 CI 编排。所有文件（包括归档报告）都提交到 stock-analyzer 同一仓库。

**Tech Stack:** Python 标准库 + DeepSeek API + ServerChan + GitHub Actions

---

### 结构修正说明

原设计文档将 harness 放在 `D:\code\financial\` 根目录，但 `stock-analyzer` 才是 Git 仓库。所有文件实际位置调整如下：

```
stock-analyzer/                    ← Git 仓库根目录
├── Makefile                       # 统一入口
├── scripts/
│   ├── archive_report.sh          # 归档日报脚本
│   └── weekly_review.py           # DeepSeek 周复盘脚本
├── .github/workflows/
│   ├── daily-analysis.yml         # 现有——追加归档步骤
│   └── weekly-review.yml          # 新建——周六复盘
├── reports/
│   ├── daily/YYYY/MM/             # 每日归档（新建）
│   └── weekly/                    # 周末复盘（新建）
│   └── report_YYYY-MM-DD.md       # 现有，不变
├── analyzer.py                    # 现有，不改
├── formatter.py                   # 现有，不改
├── notifier.py                    # 现有，不改
└── ...其他现有文件...
```

---

### Task 1: 创建 harness 骨架（Makefile + 目录结构）

**Files:**
- Create: `stock-analyzer/Makefile`
- Create: `stock-analyzer/reports/daily/.gitkeep`
- Create: `stock-analyzer/reports/weekly/.gitkeep`

- [ ] **Step 1: 创建 Makefile**

```makefile
.PHONY: analyze archive weekly push-test

# 运行每日分析（本地）
analyze:
	python analyzer.py

# 归档最新日报到 reports/daily/YYYY/MM/
archive:
	bash scripts/archive_report.sh

# 生成本周复盘总结
weekly:
	python scripts/weekly_review.py

# 发送测试推送
push-test:
	python -c "from notifier import push_test; import os; push_test(os.getenv('SERVERCHAN_SENDKEY', ''))"
```

- [ ] **Step 2: 创建目录占位文件**

```bash
mkdir -p reports/daily reports/weekly
touch reports/daily/.gitkeep reports/weekly/.gitkeep
```

- [ ] **Step 3: Commit**

```bash
git add Makefile reports/daily/.gitkeep reports/weekly/.gitkeep
git commit -m "🚜 add: Makefile harness + reports directory skeleton"
```

---

### Task 2: 归档脚本 + 修改 workflow

**Files:**
- Create: `stock-analyzer/scripts/archive_report.sh`
- Modify: `stock-analyzer/.github/workflows/daily-analysis.yml`

- [ ] **Step 1: 创建归档脚本**

`scripts/archive_report.sh`：

```bash
#!/usr/bin/env bash
# 将最新日报复制到 reports/daily/YYYY/MM/ 并 commit
set -euo pipefail

DATE=$(date +%F)
YEAR=$(date +%Y)
MONTH=$(date +%m)
SOURCE="reports/report_${DATE}.md"
TARGET_DIR="reports/daily/${YEAR}/${MONTH}"
TARGET="${TARGET_DIR}/report_${DATE}.md"

# 检查源文件是否存在
if [ ! -f "$SOURCE" ]; then
    echo "⚠️ 日报文件不存在: $SOURCE，跳过归档"
    exit 0
fi

# 创建目标目录
mkdir -p "$TARGET_DIR"

# 复制文件（如果内容不同）
if [ -f "$TARGET" ] && cmp -s "$SOURCE" "$TARGET"; then
    echo "⏭️ 日报 $DATE 已归档且无变化，跳过"
    exit 0
fi

cp "$SOURCE" "$TARGET"
echo "✅ 已归档: $SOURCE → $TARGET"

# 配置 git（GitHub Actions 环境需要）
git config user.name "stock-analyzer[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

# commit + push
git add "reports/daily/${YEAR}/${MONTH}/"
if git diff --quiet && git diff --staged --quiet; then
    echo "⏭️ 无新内容可提交"
else
    git commit -m "📁 归档日报 ${DATE}"
    git push
    echo "✅ 已推送到仓库"
fi
```

- [ ] **Step 2: 给脚本加执行权限**

```bash
chmod +x scripts/archive_report.sh
```

- [ ] **Step 3: 修改 daily-analysis.yml——追加归档步骤**

在现有 workflow 的末尾（`upload-artifact` 步骤之后）追加：

```yaml
      - name: 📁 归档日报到仓库
        if: always()
        run: bash scripts/archive_report.sh
```

改动后完整文件：

```yaml
# ============================================
# A股自动分析 - GitHub Actions 定时任务
# 每个交易日北京时间 16:00（UTC 08:00）运行
# 零外部依赖，直接使用 Python 内置模块
# ============================================

name: Daily Stock Analysis

on:
  schedule:
    # UTC 08:00 = 北京时间 16:00
    # 周一到周五运行（法定节假日需手动跳过）
    - cron: '0 8 * * 1-5'

  # 支持手动触发（仓库页面 → Actions → Run workflow）
  workflow_dispatch:

  # 推送代码时也运行（用于调试）
  push:
    branches:
      - main
    paths:
      - '**.py'
      - 'config.json'
      - 'config.yaml'

jobs:
  analyze:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: 📥 拉取代码
        uses: actions/checkout@v4

      - name: 🐍 设置 Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 📊 运行分析
        env:
          SERVERCHAN_SENDKEY: ${{ secrets.SERVERCHAN_SENDKEY }}
        run: python analyzer.py

      - name: 📁 归档日报到仓库
        if: always()
        run: bash scripts/archive_report.sh

      - name: 💾 保存报告
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: analysis-report-${{ github.run_number }}
          path: reports/
          retention-days: 30
```

- [ ] **Step 4: Commit**

```bash
git add scripts/archive_report.sh .github/workflows/daily-analysis.yml
git commit -m "📁 add: 日报归档脚本 + workflow 归档步骤"
```

---

### Task 3: 本地归档测试（可选）

- [ ] **Step 1: 运行本地分析**

```bash
cd stock-analyzer && python analyzer.py
```

验证 `reports/report_2026-06-13.md` 已生成。

- [ ] **Step 2: 测试归档脚本**

```bash
bash scripts/archive_report.sh
```

验证：`ls reports/daily/2026/06/report_2026-06-13.md` 存在，内容与源文件一致。

---

### Task 4: 周复盘脚本

**Files:**
- Create: `stock-analyzer/scripts/weekly_review.py`
- Create: `stock-analyzer/.github/workflows/weekly-review.yml`

- [ ] **Step 1: 创建 weekly_review.py**

```python
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
    """读取周一至周五的所有日报"""
    reports = []
    for i in range(5):
        day = monday + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        year = day.strftime("%Y")
        month = day.strftime("%m")
        path = os.path.join("reports", "daily", year, month, f"report_{date_str}.md")
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

        # 计算本日涨幅（可选——如果有价格数据可以加上）
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
        print("❌ 本周没有找到任何日报，无法生成复盘")
        sys.exit(1)
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
```

- [ ] **Step 2: 创建 weekly-review.yml**

```yaml
# ============================================
# 周末复盘总结 - GitHub Actions 定时任务
# 每周六北京时间 10:00（UTC 02:00）运行
# 读取本周日报 → DeepSeek 生成周评 → 推送微信
# ============================================

name: Weekly Review

on:
  schedule:
    # UTC 02:00 = 北京时间 10:00，仅周六
    - cron: '0 2 * * 6'

  # 支持手动触发
  workflow_dispatch:

jobs:
  review:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: 📥 拉取代码
        uses: actions/checkout@v4

      - name: 🐍 设置 Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 🤖 生成周复盘总结
        id: weekly
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          SERVERCHAN_SENDKEY: ${{ secrets.SERVERCHAN_SENDKEY }}
        run: python scripts/weekly_review.py

      - name: 📁 提交周报到仓库
        if: always()
        run: |
          DATE=$(date +%F)
          git config user.name "stock-analyzer[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add reports/weekly/
          if git diff --quiet && git diff --staged --quiet; then
            echo "⏭️ 无新内容可提交"
          else
            git commit -m "📆 周复盘 ${DATE}"
            git push
            echo "✅ 周报已推送到仓库"
          fi

      - name: 💾 保存周报
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: weekly-review-${{ github.run_number }}
          path: reports/weekly/
          retention-days: 90
```

- [ ] **Step 3: Commit**

```bash
git add scripts/weekly_review.py .github/workflows/weekly-review.yml
git commit -m "🤖 add: 周末复盘脚本 + GitHub Actions workflow"
```

---

### Task 5: 推送本地改动并验证

- [ ] **Step 1: 推送最新代码到远程仓库**

```bash
git push
```

- [ ] **Step 2: 在 GitHub 上验证 Actions**

访问 `https://github.com/vleuschen/stock-analyzer/actions`：
- 确认 `Daily Stock Analysis` workflow 正常
- 手动触发 `Weekly Review` workflow，验证 DeepSeek 调用是否成功

- [ ] **Step 3: 设置 DEEPSEEK_API_KEY 到 GitHub Secrets**

访问：`https://github.com/vleuschen/stock-analyzer/settings/secrets/actions`
添加：
- Name: `DEEPSEEK_API_KEY`
- Value: `（你的 DeepSeek API Key）`

---

### Task 6: 最终验证

- [ ] **Step 1: 手动触发一次 weekly-review workflow**

GitHub 页面 → Actions → Weekly Review → Run workflow → 等待完成 🟢

- [ ] **Step 2: 验证输出**

检查：
- `reports/weekly/weekly-2026-W24.md` 是否生成到仓库
- 微信是否收到周复盘推送
- 信号统计表是否正确

- [ ] **Step 3: 确认每日归档也正常**

检查仓库中 `reports/daily/2026/06/` 目录下是否有归档文件。
