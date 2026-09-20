# A股全自动分析系统

## 项目概述
基于 Python 标准库的 A 股自动分析系统，每天定时运行，通过微信推送分析结果。

## 运行入口
- `run_daily.py` — 每日全自动运行（基础分析 → yyPZ老龙反抽 → 郑希研报 → 合并推送）

## 模块结构
| 文件 | 功能 |
|------|------|
| `analyzer.py` | 基础分析主程序 |
| `data_fetcher.py` | 行情/K线抓取（腾讯）+ 资金流（东财，新浪兜底） |
| `indicators.py` | 技术指标计算 |
| `swing_strategy.py` | 波段信号判断（趋势/动能/位置/量价/资金五维评分） |
| `formatter.py` | 归档报告（Markdown）格式化 |
| `push_format.py` | 微信推送正文排版（纯文本，避免 Markdown 在微信里错乱） |
| `notifier.py` | 方糖 ServerChan 微信推送 |
| `yypz_strategy.py` | yyPZ游资盘子·老龙反抽选股策略 |
| `zhengxi_report.py` | 郑希视角研报生成器 |
| `scripts/weekly_review.py` | 周复盘生成 |
| `scripts/backtest_signals.py` | 信号回测（分布 + 5 日前瞻收益） |

## 数据源
- 腾讯财经 API: qt.gtimg.cn / web.ifzq.gtimg.cn
  - ⚠️ 该接口第 62/70/71 号字段是区间涨跌幅，**不是资金流向**（历史版本曾误用）
- 资金流向: 东方财富 `push2.eastmoney.com` fflow（主力全口径）
  - 备用: 新浪 `MoneyFlow.ssl_qsfx_zjlrqs`（超大单口径），失败自动切换并标注
  - 连续失败 3 次会熔断该数据源，避免被封 IP
- 郑希观点语料: `.claude/skills/zhengxi-views/references/`

## 配置文件
- `config.json` — 主要股票配置（跟踪标的列表）
- `config.yaml` — 备选配置（仅保留核心标的）

## yyPZ·老龙反抽策略
- 候选池: 约20只前强股/赛道龙头（AI算力、半导体、新能源、机器人、低空经济）
- 选股逻辑: 深度回调 → 缩量企稳 → RSI超卖 → 均线支撑
- 评分系统: 0-100分，**52分以上**推送，68分以上标记强反抽

## 推送规则
- 正文由 `push_format.py` 生成，纯文本 + emoji + 【】分节，不用 Markdown 表格/标题/加粗
- 板块顺序: 大盘 → 自选表现 → 今日变化 → 值得关注（含买点/止损/目标）→ 自选一览 → 老龙反抽 → 郑希观点
- 「今日变化」对比 `reports/daily/` 里上一份日报的信号，没有切换就明说没有
- 顶部日期用 K 线最新日期（`data_date`），避免周末/节假日误标成当天
- 郑希语料超过 60 天未更新时自动隐藏该板块

## 郑希视角研报
- 基于 zhengxi-views skill（安装于 `.claude/skills/zhengxi-views/`）
- 研报结构：宏观判断 → 行业聚焦 → 持仓印证 → 策略展望
- 数据来源：郑希公开语料（2012-2026）+ 基金真实持仓

## GitHub Actions
- `daily-analysis.yml` — 每日一推（18:00 UTC+8 收盘后）
- `weekly-review.yml` — 每周六 10:00 UTC+8

## 环境变量
- `SERVERCHAN_SENDKEY` — 方糖推送密钥
- `DEEPSEEK_API_KEY` — DeepSeek API 密钥（周复盘用）
