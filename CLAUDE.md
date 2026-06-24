# A股全自动分析系统

## 项目概述
基于 Python 标准库的 A 股自动分析系统，每天定时运行，通过微信推送分析结果。

## 运行入口
- `run_daily.py` — 每日全自动运行（基础分析 → yyPZ老龙反抽 → 郑希研报 → 合并推送）

## 模块结构
| 文件 | 功能 |
|------|------|
| `analyzer.py` | 基础分析主程序 |
| `data_fetcher.py` | 股票数据抓取（腾讯财经 API） |
| `indicators.py` | 技术指标计算 |
| `swing_strategy.py` | 波段策略信号判断 |
| `formatter.py` | 基础报告格式化 |
| `notifier.py` | 方糖 ServerChan 微信推送 |
| `yypz_strategy.py` | yyPZ游资盘子·老龙反抽选股策略 |
| `zhengxi_report.py` | 郑希视角研报生成器 |
| `scripts/weekly_review.py` | 周复盘生成 |

## 数据源
- 腾讯财经 API: qt.gtimg.cn / web.ifzq.gtimg.cn
- 郑希观点语料: `.claude/skills/zhengxi-views/references/`

## 配置文件
- `config.json` — 主要股票配置（跟踪标的列表）
- `config.yaml` — 备选配置（仅保留核心标的）

## yyPZ·老龙反抽策略
- 候选池: 约20只前强股/赛道龙头（AI算力、半导体、新能源、机器人、低空经济）
- 选股逻辑: 深度回调 → 缩量企稳 → RSI超卖 → 均线支撑
- 评分系统: 0-100分，35分以上推送

## 郑希视角研报
- 基于 zhengxi-views skill（安装于 `.claude/skills/zhengxi-views/`）
- 研报结构：宏观判断 → 行业聚焦 → 持仓印证 → 策略展望
- 数据来源：郑希公开语料（2012-2026）+ 基金真实持仓

## GitHub Actions
- `daily-analysis.yml` — 每日两推（12:00 UTC+8 / 18:00 UTC+8）
- `weekly-review.yml` — 每周六 10:00 UTC+8

## 环境变量
- `SERVERCHAN_SENDKEY` — 方糖推送密钥
- `DEEPSEEK_API_KEY` — DeepSeek API 密钥（周复盘用）
