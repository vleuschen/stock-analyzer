# A股全自动分析系统

## 项目概述
基于 Python 标准库的 A 股自动分析系统，每个工作日 18:00（北京时间）自动运行，
把当天收盘复盘通过微信推送出去。

## 运行入口
- `run_daily.py` — 每日全自动运行（基础分析 → yyPZ老龙反抽 → 股票合并推送）

## 模块结构
| 文件 | 功能 |
|------|------|
| `analyzer.py` | 基础分析主程序 |
| `data_fetcher.py` | 行情/K线抓取（腾讯）+ 资金流（东财，新浪兜底） |
| `indicators.py` | 技术指标计算 |
| `signals.py` | 信号词表（档位名 / emoji）唯一来源 |
| `swing_strategy.py` | 波段信号判断（趋势/动能/位置/量价/资金五维评分） |
| `formatter.py` | 归档报告（Markdown）格式化 |
| `push_format.py` | 微信推送正文排版（纯文本模拟表格，手机不折行） |
| `scripts/check_push_layout.py` | 排版体检 + 手机预览图（改完排版先跑这个） |
| `notifier.py` | 方糖 ServerChan 微信推送 |
| `yypz_strategy.py` | yyPZ游资盘子·老龙反抽选股策略 |
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

## 配置文件
- `config.json` — 主要股票配置（跟踪标的列表）
- `config.yaml` — 备选配置（仅保留核心标的）

## yyPZ·老龙反抽策略
- 候选池: 约20只前强股/赛道龙头（AI算力、半导体、新能源、机器人、低空经济）
- 选股逻辑: 深度回调 → 缩量企稳 → RSI超卖 → 均线支撑
- 评分系统: 0-100分，**52分以上**推送，68分以上标记强反抽

## 波段信号口径（2026-09 回测后收紧）
- 五维评分不变（趋势/动能/位置/量价/资金），但口径偏进攻：
  「强烈买入」= 评分 ≥45 **且** 均线多头排列 **且** RSI<75 **且** 资金不流出
- 评分 ≥35 且站上 MA20、动能不弱、资金不流出的 → 「偏多」，推送提示激进者小仓试错；
  其余偏多仍只作强弱排序
- RSI≥75、均线未多头或资金流出时，即使高分也不追高，明确写出缺的确认条件
- 完整操作计划只在「强烈买入」档给出；偏多档只给小仓/确认后加仓路径；
  止损按买点 -6% 封顶，盈亏比 <1.5 标注「偏低」
- 回测口径：本自选池 150 个交易日 / 1885 个样本 / 前瞻 5 日，命令见
  `python scripts/backtest_signals.py`；样本小（8~13 只票、7 个月），结论会随行情漂移

## 推送规则
- 正文由 `push_format.py` 生成：**一个段落 = 卡片里的一行**，用纯文本 + emoji + 全角空格
  拼出表格，不用 Markdown（`**加粗**`/`#`/表格在卡片端不渲染，会露出原始符号）
- 微信卡片的四条渲染定律（来自历史推送截图复盘，改排版前先读 `push_format.py` 顶部注释）：
  - 段内单个 `\n` 会被折成一个空格 → 要换行只能空行，统一用 `PARA`（`\n\n`）拼段落
  - **ASCII 空格会被折叠**（连续多个算一个、行首直接吃掉）→ 列对齐**只能**用全角空格
    `PAD`（U+3000，宽度正好 1 个汉字，不折叠也不被吃）
  - 一行约 20 个汉字，超了就折行，而折行会把表格打散 → 所有行都过 `_fit()` 截断
  - 宽度按 em 估算（1 em = 1 汉字），半角字符查 `_HALF_EM` / `_UPPER_EM` 实测表，
    预算 `PHONE_EM = 20.0`
- 板块顺序: ▎一句话 → ▎大盘 → ▎自选表现 → ▎今日变化 → ▎值得关注 → ▎自选全览（画线表格）→ ▎老龙反抽
- 「自选全览」是真正的表格：一票一行「emoji 标记 ｜ 名称 ｜ 涨跌 ｜ 评分」，按评分降序，
  档位靠 emoji 列区分（不再另起分组标题）
- 「今日变化」对比 `reports/daily/` 里上一份日报的信号（反解析 `signals.MARK` 里的 emoji），
  没有切换就明说没有；降级条目只引 ❌/⚠️ 理由，找不到就不引
- 顶部日期用 K 线最新日期（`data_date`），避免周末/节假日误标成当天
- 资金流数据若比 `data_date` 旧，行内标注〔MM-DD〕，避免把旧资金当成当天；
  加不下就整条略去（不截断，数字截一半比不写更误导）
- 正文每次运行都会存 `reports/push_<data_date>.md`（随日报归档），
  微信里看到的和仓库里存的必须一致

## 本地调试推送排版
- `python scripts/check_push_layout.py --png reports/preview_push.png`
  —— 内置样例数据渲染手机预览图，并逐行量宽度、标出会折行的行；改完排版**必须**跑一遍
- 也可以体检真实输出：`python scripts/check_push_layout.py reports/push_2026-09-18.md`
- `PUSH_DRY_RUN=1 python run_daily.py` —— 只生成正文并打印预览，不发送
- 不配 `SERVERCHAN_SENDKEY` 时同样只生成不发送

## GitHub Actions
- `daily-analysis.yml` — 每个工作日 18:00 UTC+8 一推（cron `0 10 * * 1-5` UTC），
  内容是**当天**的收盘复盘
- `weekly-review.yml` — 每周六 10:00 UTC+8
- 日报 workflow 锁 `TZ: Asia/Shanghai`，避免 Python 写的北京日期和 shell 的归档日期错位
- 归档文件名一律按 **data_date**（K 线最新日期）而不是运行日期命名 ——
  18 点运行时两者通常相同，仍以行情数据日期为准。`run_daily.py` 把 data_date 写进
  `GITHUB_OUTPUT`，归档步骤用它去找文件
- 改代码触发的运行（`push` 事件）自动带 `PUSH_DRY_RUN=1`，只生成不推送
- 同一交易日不重复推：`reports/.last_push_date` 记着最后一次推出去的数据日期，
  和本次 `data_date` 相同就只归档不发送（周一和周六早上取到的都是周五的收盘数据，
  节假日更是天天一样）。这个文件要提交进仓库，否则干净检出时状态就丢了

## 环境变量
- `SERVERCHAN_SENDKEY` — 方糖推送密钥
- `PUSH_DRY_RUN` — 设为 `1` 时只生成推送正文不发送（本地调排版用）
- `DEEPSEEK_API_KEY` — DeepSeek API 密钥（周复盘用）

## 已安装的 skills
- `~/.zcode/skills/aws-wechat-article-*` — 微信公众号排版 skills（共 9 个，
  来自 https://github.com/aiworkskills/wechat-article-skills）。
  注意：那套 skill 走的是**公众号 API 富 HTML 发布**，与本项目「方糖 → 微信服务号模板消息」
  的纯文本卡片是两条路，排版结论不可直接套用
