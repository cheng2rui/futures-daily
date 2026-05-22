# Fallback 数据源研究

## 结论摘要

| 场景 | 首选 | fallback | 状态 |
| --- | --- | --- | --- |
| DCE 日行情 | AkShare `get_dce_daily` / DCE official `dcereport/publicweb/dailystat/dayQuotes` | Sina 连续合约 `ak.futures_zh_daily_sina(symbol='M0')` 等 | 已接入，标记 partial |
| DCE 席位排名 | DCE official / AkShare `get_dce_rank_table` / `futures_dce_position_rank` | 暂无可靠免费公开源 | 保持失败提示，不造假 |
| INE 日行情 | `ak.get_ine_daily` | `ak.get_futures_daily(market='INE')` / settlement 接口 | 可用 |
| INE 席位排名 | 官方/上期系 rank 待研究 | 暂无稳定 adapter | 保持未实现提示 |
| 实时/盘中价格 | AkShare `futures_zh_realtime` | futures-panel 的 `hq.sinajs.cn/list=nf_<contract>` direct | 后续盘中功能可迁移 |

## DCE 官方接口状态

AkShare 1.18.55 的 DCE 官方日行情使用：

```text
POST http://www.dce.com.cn/dcereport/publicweb/dailystat/dayQuotes
```

payload:

```json
{
  "contractId": "",
  "lang": "zh",
  "optionSeries": "",
  "statisticsType": "0",
  "tradeDate": "20260521",
  "tradeType": "1",
  "varietyId": "all"
}
```

本机直接请求官方 publicweb / dcereport 多个 URL 均返回 HTTP 412，页面包含动态 challenge，疑似 DCE 防爬/前置校验。仅靠普通 headers、Referer、Origin 无法绕过。

## 已实现 DCE 日行情 fallback

文件：`app/sources/dce_fallback_source.py`

策略：

1. 用 `ak.futures_display_main_sina()` 尝试获取 DCE 连续合约列表。
2. 失败时使用内置 DCE 品种表。
3. 对每个品种请求 `ak.futures_zh_daily_sina(symbol='<品种>0')`。
4. 只取目标日期行。
5. 输出标准 daily row。

限制：

- 这是 Sina 连续/主力合约序列，不是 DCE 官方全合约日表。
- `contract` 保留 `M0` / `V0` 这类连续合约代码，不伪造月份合约。
- 无 `turnover`，`pre_settle` 可能缺失。
- 日报条目会带 `source='futures_zh_daily_sina'`。
- 因为不是官方全量数据，数据质量里 DCE 标记为 `partial`，但 coverage 按“日行情可用”计入。

## DCE 席位排名

当前不可用：

- `get_dce_rank_table()` 近期返回 `{}`。
- `futures_dce_position_rank()` 报 `BadZipFile`。
- 官方导出接口也遇到 HTTP 412。
- Sina 不提供会员席位持仓排名。

处理策略：

- 明确返回错误，不用伪数据填充。
- 后续优先方向：等 AkShare/DCE official 恢复；或接 Tushare Pro/商业源。

## 从 futures-panel 可复用

已迁移：

- `VARIETY_META` → `app/metadata/variety_meta.py`
- `POINT_VALUE` → `app/metadata/contract_specs.py`

可后续迁移：

- `hq.sinajs.cn/list=nf_<contract>` 直连 realtime fallback，用于盘中/夜盘。
- `MARGIN_RATE` / `COMMISSION` / `PRICE_LIMIT`，用于风控和涨跌停判断。
