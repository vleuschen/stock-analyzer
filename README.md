# 📊 A股自动分析 & 微信推送

每个交易日收盘后自动运行技术分析，通过方糖推送到微信。

**🔥 零外部依赖** — 全部使用 Python 内置模块，无需安装任何第三方库。

## 功能

- 📈 **技术指标**：MA均线/RSI/MACD/布林带/量价分析
- 🎯 **波段策略**：综合多指标给出买入/观望/回避信号
- 📱 **微信推送**：方糖ServerChan，收盘后自动推送到手机
- ⏰ **定时运行**：GitHub Actions，每个工作日16:00自动执行
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

之后每个工作日16:00会自动运行。也可以在本地运行：

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
├── analyzer.py                            # 主程序
├── data_fetcher.py                        # 东方财富 API 数据抓取
├── indicators.py                          # 技术指标计算
├── swing_strategy.py                      # 波段策略信号
├── formatter.py                           # 报告格式化
├── notifier.py                            # 方糖推送
└── requirements.txt                       # 依赖
```

## 信号说明

| 信号 | 含义 | 条件 |
|---|---|---|
| 🟢 强烈买入 | 多指标共振看多 | MACD金叉 + RSI超卖回升 + 放量突破均线 |
| 🟢 偏多 | 部分指标看多 | 综合评分 15~40 |
| 🟡 观望 | 信号不明确 | 综合评分 -15~15 |
| 🔴 偏空 | 部分指标看空 | 综合评分 -40~-15 |
| 🔴 强烈回避 | 多指标共振看空 | MACD死叉 + RSI超买回落 + 缩量跌破均线 |

## 数据来源

- **东方财富 API**（免费、无需Key）
  - 实时行情、日K线（前复权）、资金流向
  - 支持沪深京全部交易所

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
# 例：北京时间 16:30 = UTC 08:30
- cron: '30 8 * * 1-5'
```

### 本地定时运行（不用 GitHub Actions）

```bash
# Windows 任务计划程序
# Linux crontab
30 15 * * 1-5 cd /path/to/stock-analyzer && python analyzer.py
```

## License

MIT
