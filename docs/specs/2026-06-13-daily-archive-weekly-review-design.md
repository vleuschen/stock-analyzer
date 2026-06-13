# 每日归档 & 周末复盘 — 设计文档

## 1. 背景

现有 `stock-analyzer` 每天下午 4:00 通过 GitHub Actions 生成 A 股分析报告并推送到微信。存在两个痛点：

1. 报告只以 GitHub Actions Artifact 形式保存（30 天过期），无法长期追溯
2. 没有跨周的趋势总结，每天的报告是孤立的

本文设计对现有系统的增量扩展，**不改动 `stock-analyzer/` 内任何代码**，仅通过新增根级 harness 工程（Makefile + scripts + workflows）实现。

## 2. 整体架构

```
D:\code\financial\
├── Makefile                       # 统一入口
├── scripts/
│   ├── archive_report.sh          # 归档日报到 reports/daily/
│   └── weekly_review.py           # 调用 DeepSeek 生成周复盘
├── .github/workflows/
│   ├── daily-report.yml           # 每日分析 + 推送 + 归档（改造现有）
│   └── weekly-review.yml          # 周六上午 10:00 复盘总结
├── reports/
│   ├── daily/YYYY/MM/             # 每日归档
│   └── weekly/                    # 周末复盘
├── stock-analyzer/                # 现有项目，不可侵入
```

## 3. 每日归档

### 3.1 触发时机

- 每个交易日 16:00（北京时间）— 与现有分析 workflow 同时
- 分析完成后追加归档步骤，不改变现有推送行为

### 3.2 归档流程

```
analyzer.py 完成
  ↓
复制 reports/report_YYYY-MM-DD.md → reports/daily/YYYY/MM/report_YYYY-MM-DD.md
  ↓
git add → git commit -m "📁 归档日报 YYYY-MM-DD"
  ↓
git push
```

### 3.3 策略

- **每个工作日一个 commit**，日志清晰
- 当天重跑会覆盖原文件并再次 commit
- 非交易日不触发，无空 commit

### 3.4 实现方式

在现有的 `daily-report.yml` 末尾增加一个 step：

```yaml
- name: Archive report
  run: |
    DATE=$(date +%F)
    YEAR=$(date +%Y)
    MONTH=$(date +%m)
    mkdir -p reports/daily/$YEAR/$MONTH
    cp stock-analyzer/reports/report_$DATE.md reports/daily/$YEAR/$MONTH/ || true
    git config user.name "stock-analyzer bot"
    git config user.email "bot@stock-analyzer"
    git add reports/daily/
    git diff --quiet && git diff --staged --quiet || \
      git commit -m "📁 归档日报 $DATE"
    git push
```

## 4. 周末复盘总结

### 4.1 触发时机

- **每周六 10:00 北京时间**（UTC 02:00）
- 周五 15:00 收盘后数据已就绪

### 4.2 日期范围

- 每周六运行，复盘 **本周一至周五**（同 ISO 周定义）
- 例如：周六 06/14 运行，复盘范围为 06/08（周一）至 06/13（周五）
- 脚本自动根据当前日期计算本周一的日期，向后取 5 个日历日

### 4.3 复盘流程

```
周六 10:00 workflow 启动
  ↓
读取本周（周一到周五）所有的 daily 报告
  ↓
拼装成 Prompt 调用 DeepSeek API
  ↓
DeepSeek 返回自然语言周评
  ↓
合并信号统计表（代码生成）
  ↓
写入 reports/weekly/weekly-YYYY-W{周数}.md
  ↓
commit + push 到仓库
  ↓
通过 ServerChan 推送到微信（复用现有 `SERVERCHAN_SENDKEY`，标题含 "📆 周复盘"）
```

### 4.4 Prompt 设计

```text
你是一个A股复盘分析师。以下是本周（{周标识}）每日的股票分析报告：

{日报内容拼接}

请写一篇本周复盘总结，要求：
1. 开头一句整体评价本周市场情绪变化
2. 对每只跟踪标的，讲一下它的走势变化和信号演变
3. 如果某只股票信号发生切换（如观望转偏空/偏多），重点说明
4. 用自然的中文，像在和朋友聊天，不要 AI 套话
5. 控制在 500 字左右
6. 结尾给出下周的关注方向建议
```

### 4.5 复盘格式

```markdown
# 📆 周复盘报告 | 2026 年第 25 周（06/08 - 06/13）

## 📝 周评

（DeepSeek 生成的 500 字左右总结，像人话，不 AI）

---

## 📊 本周信号统计

| 股票     | 周一 | 周二 | 周三 | 周四 | 周五 | 本周小结 |
|----------|------|------|------|------|------|----------|
| 芭田股份 | 📉偏空 | 📉偏空 | 📉偏空 | 📉偏空 | 📉偏空 | 持续走弱 |

📬 自动生成于 YYYY-MM-DD · 仅供参考，不构成投资建议
```

### 4.6 DeepSeek API

- API Key 存于 GitHub Secrets 中，变量名 `DEEPSEEK_API_KEY`
- DeepSeek V3 API 端点：`https://api.deepseek.com/v1/chat/completions`
- 模型：`deepseek-chat`
- 体温：0.7（平衡创造力与稳定性）
- 最大 token：2048

### 4.7 `weekly_review.py` 职责

一个独立的 Python 脚本，放在 `scripts/` 目录下：

1. 接收参数：`--date-from` `--date-to`（或自动推导本周区间）
2. 读取 `reports/daily/` 下对应日期范围的报告
3. 调用 DeepSeek API 生成周评（用 `urllib` 或 `http.client` 零依赖发请求）
4. 解析各天的信号数据，生成信号统计表
5. 写入 `reports/weekly/` 目录
6. 输出最终结果路径（供后续 ServerChan 推送）

**零外部依赖原则：** 和现有 stock-analyzer 一样，只用 Python 标准库，不装 pip 包。

## 5. Makefile 入口

```makefile
.PHONY: analyze archive weekly

analyze:
	cd stock-analyzer && py analyzer.py

archive:
	bash scripts/archive_report.sh

weekly:
	py scripts/weekly_review.py
```

## 6. 权限与密钥

| 密钥              | 用途                | 存储位置          |
|-------------------|---------------------|-------------------|
| `SERVERCHAN_SENDKEY` | 微信推送            | 已有（GitHub Secrets） |
| `DEEPSEEK_API_KEY`   | 复盘 AI 调用的 API Key | 新增 GitHub Secrets |

## 7. 约束与边界

- **不侵入现有代码：** `stock-analyzer/` 内一行不改
- **零 pip 依赖：** 所有脚本只用 Python 标准库
- **只归档工作日数据：** GitHub Actions cron `1-5` 天然保证
- **报告文件持续增长：** 一个季度约 60 个文件（~2-3 MB），长期增长可接受
