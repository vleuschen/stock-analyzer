# 📊 A股自动分析 & 微信推送

每个交易日收盘后自动运行技术分析，通过方糖推送到微信。

**🔥 零外部依赖** — 全部使用 Python 内置模块，无需安装任何第三方库。

## 功能

- 📈 **技术指标**：MA均线/RSI/MACD/布林带/量价分析
- 🎯 **波段策略**：综合多指标给出买入/观望/回避信号
- 📱 **微信推送**：方糖ServerChan，收盘后自动推送到手机
- ⏰ **定时运行**：GitHub Actions，每个交易日18:00自动执行
- 🔧 **可扩展**：JSON/YAML配置，加减股票只改一行
- 🪶 **零依赖**：仅用Python标准库，GitHub Actions和本地均可直接运行

## 快速开始

### 1. 注册方糖 & 获取 SendKey

1. 访问 [方糖 ServerChan](https://sct.ftqq.com/) → 微信扫码登录
2. 复制你的 **SendKey**（页面顶部就能看到）

> 免费版每天可推送 5 条消息，完全够用

### 2. Fork 本项目

```bash
# GitHub 页面点 Fork，或者：
git clone https://github.com/你的用户名/stock-analyzer.git
cd stock-analyzer
```

### 3. 配置 Secrets

在 GitHub 仓库页面：
**Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `SERVERCHAN_SENDKEY` | 你的方糖 SendKey |

### 4. 配置股票列表

编辑 `config.json`：

```json
{
  "stocks": [
    {"code": "002170", "name": "芭田股份", "market": "sz"},
    {"code": "600519", "name": "贵州茅台", "market": "sh"},
    {"code": "300750", "name": "宁德时代", "market": "sz"}
  ],
  "analysis": {
    "kline_days": 120
  }
}
```

> market: `sh`=上海, `sz`=深圳, `bj`=北京

### 5. 手动测试

在 GitHub 仓库页面：
**Actions → Daily Stock Analysis → Run workflow → Run workflow**

等待1-2分钟，查看微信是否收到推送。

### 6. 完成 🎉

之后每个交易日18:00会自动运行。也可以在本地运行：

```bash
# 无需安装任何依赖！直接用 Python 内置模块
set SERVERCHAN_SENDKEY=你的SendKey    # Windows
export SERVERCHAN_SENDKEY=你的SendKey  # Linux/Mac
python analyzer.py
```

## 推送效果示例

```
📊 A股波段分析 | 2026-06-12

信号总览:
| 股票     | 最新价 | 涨跌幅 | 信号      | 建议        |
|---------|-------|-------|----------|------------|
| 芭田股份 | 11.35 | +2.44% | 🟡 观望  | 信号不明确... |

---

芭田股份（002170）
行情快照 📈
最新价: 11.35 (+2.44%) | 成交: 2.71亿 | 换手: 3.05%

技术信号: 🟡 观望
- 均线: 空头排列 📉
- RSI(14): 45.3 (中性)
- MACD: 空头区域
- 布林: 中轨附近

波段建议
支撑位: MA60(12.41) / 布林下轨(10.81)
压力位: MA10(11.42) / MA20(11.65)
操作: 信号不明确，建议等待方向明朗
```

## 项目结构

```
├── .github/workflows/daily-analysis.yml   # GitHub Actions 定时任务
├── config.yaml                            # 股票列表 & 配置
├── run_daily.py                           # 每日运行入口（分析 → 合并 → 推送）
├── analyzer.py                            # 自选股分析主程序
├── data_fetcher.py                        # 行情/K线/资金流抓取（腾讯 + 东财 + 新浪）
├── indicators.py                          # 技术指标计算
├── swing_strategy.py                      # 波段信号评分（趋势/动能/位置/量价/资金）
├── formatter.py                           # 归档报告（Markdown）格式化
├── push_format.py                         # 微信推送正文排版（纯文本，手机友好）
├── yypz_strategy.py                       # yyPZ·老龙反抽策略
├── zhengxi_report.py                      # 郑希视角研报
├── notifier.py                            # 方糖推送
├── scripts/weekly_review.py               # 周复盘
├── scripts/backtest_signals.py            # 信号回测（分布 + 前瞻收益校验）
└── requirements.txt                       # 依赖
```

## 信号说明

| 信号 | 含义 | 综合评分 |
|---|---|---|
| 🟢 强烈买入 | 趋势、动能、资金共振 | ≥ 50 |
| 🟢 偏多 | 多头因子占优 | 25 ~ 50 |
| 🟡 观望 | 多空力量接近 | -25 ~ 25 |
| 🔴 偏空 | 空头因子占优 | -50 ~ -25 |
| ⚠️ 回避 | 趋势与动能同步走坏 | ≤ -50 |

评分由五个维度加权而成：趋势 ±36、动能 ±30、位置 ±25、量价 ±10、资金 ±12。
**超买/超卖按趋势方向解读**——上升趋势里的超买不扣分，下跌趋势里的超卖也不加分（避免接飞刀）。

## 数据来源

- **腾讯财经 API**：实时行情、日K线（前复权）
  - 注意：接口内嵌的 62/70/71 号字段是「年初至今/20日/60日涨跌幅」，**不是资金流向**
- **资金流向**：东方财富 fflow（主力/大单/超大单/中单/小单全口径）
  - 备用源：新浪资金流（超大单口径），东财不可用时自动切换并在推送中如实标注口径
  - 两个源都失败时自动隐藏资金相关内容，不会输出错误数据
- 支持沪深京全部交易所

## 推送格式

推送正文由 `push_format.py` 生成，刻意只使用纯文本 + emoji + 【】分节：

```
📊 9月18日 盘后复盘
【大盘】…
【自选表现】…
【今日变化】🔻 芭田股份 观望→回避（-0.2%）· 跌破 MA5/MA10
【值得关注】买点/止损/目标 + 盈亏比
【自选一览】每只一行：价格 涨跌｜信号 评分 资金
【老龙反抽】…
```

- 不使用 Markdown 表格、`#` 标题、`**` 加粗——微信卡片不渲染，会露出原始符号
- 「今日变化」优先于「今日状态」，避免每天推送内容雷同
- 顶部日期为**行情数据日期**（周末/节假日运行不会误标成当天）
- 郑希观点语料超过 60 天未更新时自动隐藏该板块

## 注意事项

- GitHub Actions cron 有最多 15 分钟延迟
- 法定节假日仍会触发（但数据为上一交易日）
- 东方财富 API 有频率限制，多只股票间隔 1 秒
- 方糖免费版每天 5 条，多只股票合并为 1 条推送
- **技术分析仅供参考，不构成投资建议**

## 扩展

### 添加更多股票

编辑 `config.yaml` 的 `stocks` 列表即可，支持无限添加。

### 调整推送时间

编辑 `.github/workflows/daily-analysis.yml` 的 cron 表达式：
```
# UTC 时间，比北京时间少 8 小时
# 例：北京时间 18:00 = UTC 10:00
- cron: '0 10 * * 1-5'
```

### 本地定时运行（不用 GitHub Actions）

```bash
# Windows 任务计划程序
# Linux crontab
30 15 * * 1-5 cd /path/to/stock-analyzer && python analyzer.py
```

## License

MIT
