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
| `signals.py` | 信号词表（档位名 / emoji）唯一来源 |
| `swing_strategy.py` | 波段信号判断（趋势/动能/位置/量价/资金五维评分） |
| `formatter.py` | 归档报告（Markdown）格式化 |
| `push_format.py` | 微信推送正文排版（纯文本，避免 Markdown 在微信里错乱） |
| `notifier.py` | 方糖 ServerChan 微信推送 |
| `yypz_strategy.py` | yyPZ游资盘子·老龙反抽选股策略 |
| `zhengxi_report.py` | 郑希视角研报生成器 |
| `scripts/weekly_review.py` | 周复盘生成 |
| `scripts/backtest_signals.py` | 信号回测（分布 + 5 日前瞻收益 + 超额） |

## 数据源
- 腾讯财经 API: qt.gtimg.cn / web.ifzq.gtimg.cn
  - ⚠️ 该接口第 62/70/71 号字段是区间涨跌幅，**不是资金流向**（历史版本曾误用）
- 资金流向: 东方财富 `push2his.eastmoney.com` `/api/qt/stock/fflow/daykline/get`（主力全口径）
  - ⚠️ 只有 `push2his` 提供历史，`push2` / `push2delay` 只返回 1 行；路径是
    `fflow/daykline/get`（旧版写成 `fflow/kline/get`，一直取不到数据，静默退化成新浪口径）
  - 备用: 新浪 `MoneyFlow.ssl_qsfx_zjlrqs`（超大单口径），失败自动切换并标注
  - 连续失败 3 次会熔断该数据源，避免被封 IP；东财按 IP 限频，冷却是正常现象
- 郑希观点语料: `.claude/skills/zhengxi-views/references/`

## 配置文件
- `config.json` — 主要股票配置（跟踪标的列表）
- `config.yaml` — 备选配置（仅保留核心标的）

## yyPZ·老龙反抽策略
- 候选池: 约20只前强股/赛道龙头（AI算力、半导体、新能源、机器人、低空经济）
- 选股逻辑: 深度回调 → 缩量企稳 → RSI超卖 → 均线支撑
- 评分系统: 0-100分，**52分以上**推送，68分以上标记强反抽

## 波段信号口径（2026-09 回测后收紧）
- 五维评分不变（趋势/动能/位置/量价/资金），但**出手门槛变了**：
  「强烈买入」= 评分 ≥50 **且** 均线多头排列 **且** RSI<70 **且** 资金不流出
- 够 50 分但缺上述确认的 → 降级为「偏多（观察）」，不给买点
- 「偏多」(25~50) 这一档回测 5 日超额为 **-0.77%**、三段行情全为负，
  只作强弱排序，不作为买点，推送里与「强烈买入」分开展示
- 操作计划只在「强烈买入」档给出；止损按买点 -6% 封顶，盈亏比 <1.5 标注「偏低」
- 回测口径：本自选池 150 个交易日 / 1885 个样本 / 前瞻 5 日，命令见
  `python scripts/backtest_signals.py`；样本小（8~13 只票、7 个月），结论会随行情漂移

## 推送规则
- 正文由 `push_format.py` 生成，纯文本 + emoji + 【】分节，不用 Markdown 表格/标题/加粗
- 微信卡片的排版硬约束（来自历史推送复盘，改排版前先看 `push_format.py` 顶部说明）：
  - **单个换行会被吞掉**，只有空行才真换段 —— 所以段与段之间统一用 `PARA`（`\n\n`）拼
  - `**加粗**` / `#` / 表格在卡片端不渲染，会露出原始符号
  - 一行约 22 个汉字，单段控制在 1~2 行，宁可多分段
- 板块顺序: 大盘 → 自选表现 → 今日变化 → 值得关注（含买点/止损/目标）→ 自选全览 → 老龙反抽 → 郑希观点
- 「今日变化」对比 `reports/daily/` 里上一份日报的信号（反解析 `signals.MARK` 里的 emoji），
  没有切换就明说没有；降级条目只引 ❌/⚠️ 理由，找不到就不引
- 顶部日期用 K 线最新日期（`data_date`），避免周末/节假日误标成当天
- 资金流数据若比 `data_date` 旧，行内标注〔截至 MM-DD〕，避免把旧资金当成当天
- 郑希语料超过 60 天未更新时自动隐藏该板块
- 正文每次运行都会存 `reports/push_YYYY-MM-DD.md`（随日报归档），
  微信里看到的和仓库里存的必须一致

## 本地调试推送排版
- `PUSH_DRY_RUN=1 python run_daily.py` —— 只生成正文并打印预览，不发送
- 不配 `SERVERCHAN_SENDKEY` 时同样只生成不发送

## 郑希视角研报
- 基于 zhengxi-views skill（安装于 `.claude/skills/zhengxi-views/`）
- 研报结构：宏观判断 → 行业聚焦 → 持仓印证 → 策略展望
- 数据来源：郑希公开语料（2012-2026）+ 基金真实持仓

## GitHub Actions
- `daily-analysis.yml` — 每日一推（18:00 UTC+8 收盘后）
- `weekly-review.yml` — 每周六 10:00 UTC+8

## 环境变量
- `SERVERCHAN_SENDKEY` — 方糖推送密钥
- `PUSH_DRY_RUN` — 设为 `1` 时只生成推送正文不发送（本地调排版用）
- `DEEPSEEK_API_KEY` — DeepSeek API 密钥（周复盘用）

## 已安装的 skills
- `.claude/skills/zhengxi-views/` — 郑希观点语料（项目内）
- `~/.zcode/skills/aws-wechat-article-*` — 微信公众号排版 skills（共 9 个，
  来自 https://github.com/aiworkskills/wechat-article-skills）。
  注意：那套 skill 走的是**公众号 API 富 HTML 发布**，与本项目「方糖 → 微信服务号模板消息」
  的纯文本卡片是两条路，排版结论不可直接套用
