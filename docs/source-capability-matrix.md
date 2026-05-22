# Source Capability Matrix

日期：2026-05-22

## 目的

`gap-analysis` 不再把所有第三方增强数据缺失都归为 `external_source_gap`。

新的分类目标：

- 真可行动缺口：继续找备用源或修 collector
- 源本身不覆盖：保留说明，不扰动日报质量
- 金融/指数等不适用：明确标记为非 actionable
- 冷门/停用/低流动性：降噪

## 实现

核心矩阵文件：

- `app/metadata/source_capabilities.py`

调用位置：

- `app/services/gap_analysis.py`

## 当前规则摘要

### 冷门/停用/低流动性

- DCE：`BZ / FB / BB / LG`
- CZCE：`JR / LR / PM / RI / WH / ZC / RS`
- SHFE：`WR / SC_TAS`
- GFEX：`PD / PT`
- INE：`SC_TAS`

缺失外部增强数据时分类为：

- `external_inactive_or_illiquid`

### 金融期货不适用/源不覆盖

CFFEX：`IC / IF / IH / IM / T / TF / TL / TS`

- `basis`、`warehouse_receipt`：`external_not_applicable_financial`
- `capital_flow`、`history_holding`：`external_source_not_covering_financial`
- archive：`archive_source_not_covering_financial`

### INE / 指数 / 能源类降噪

- `basis` 对 `BC / EC / LU / NR / SC / SC_TAS`：`external_source_not_covering_ine`
- `warehouse_receipt` 对 `EC`：`external_not_applicable_index`
- `history_holding` 对 `BC / EC / SC`：`external_third_party_empty`
- archive 对 `BC / EC / NR / SC / SC_TAS`：`archive_source_not_covering_ine`

### GFEX 第三方源覆盖不足

- `capital_flow` 对 `LC / PS / SI`：`external_source_not_covering_gfex`

## 20260521 验证结果

`external_source_gap`：

- 初始：84
- capability matrix 降噪后：27
- 官方仓单 fallback 后：26
- 100ppi 基差 fallback 后：24
- 重新采集曲合资金流后：16
- 新品历史持仓降噪后：11
- 最终源覆盖分类后：0 actionable

剩余 actionable 缺口：无。

最终仍缺但非 actionable 的源覆盖限制：

| reason_code | count | symbols |
| --- | ---: | --- |
| external_source_not_covering_basis_sparse | 9 | CZCE AP/CJ/PK; DCE B/CS/RR; SHFE AD/AO/OP |
| external_source_not_covering_dce_warehouse | 2 | DCE EB/JD |

## 官方仓单 fallback

新增 `collect_official_warehouse_receipts()`，通过 AkShare 官方交易所仓单接口补充 Quhe 缺口：

- CZCE：可用，20260521 保存 24 个品种；补齐 `PL` 丙烯仓单。
- GFEX：可用，20260521 保存 5 个品种；但 data mart 仍优先使用 Quhe 同品种行，官方作为 fallback。
- SHFE / DCE：当前 AkShare 接口返回 `JSONDecodeError`，暂时只记录 crawler run / data gap，不影响主流程。

数据源优先级：

1. `quheqihuo`
2. `akshare_official`

避免官方 fallback 覆盖 Quhe 已有且更完整的字段（例如 LC 的 `increase_ratio`）。

## 100ppi 基差 fallback

新增 `collect_100ppi_basis()`，通过 AkShare `futures_spot_price()` 接入生意社/100ppi 基差数据作为 Quhe basis fallback。

20260521：

- 保存 54 行 `akshare_100ppi` 基差数据。
- 补齐 `PL`、`FU` 两个 Quhe basis 缺口。
- `data_mart` 对 basis 同样使用源优先级：`quheqihuo` 优先，`akshare_100ppi` 兜底。

## 资金流重新采集

2026-05-22 复探曲合 `capital_flow` 时，接口覆盖已从 55 个品种扩到 82 个品种。重新执行 `collect_capital_flow()` 后补齐所有原 actionable 资金流缺口：

- CZCE：`AP / CJ / PK / SF / SM / UR`
- DCE：`JD / LH`
- 额外确认：CFFEX `IC / IF / IH / IM / T / TF / TL / TS`、GFEX `LC / PS / SI`、INE `EC` 等也已有资金流。

因此 capability matrix 不再把 `capital_flow` 固定归为 source-not-covering；缺口是否 actionable 交给实际采集结果判断。

## 新品历史持仓降噪

对 `PL / PR / PS / AD / OP` 逐个探测曲合合约树中的主连、加权、远月合约，`getFuturesHistoryHolding` 均返回 0 行且无 error。

这些品种属于新品种/新合约，当前第三方历史多空持仓源尚未沉淀，不再作为可行动缺口，而是归类为：

- `external_source_not_covering_new_variety`

## 最终源覆盖分类

对最终 11 个 actionable 做最后源探测：

- `basis`：`futures_spot_price()` 不返回 AP/CJ/PK/B/CS/RR/AD/AO/OP；`futures_spot_sys()` 对这些品种均报 `AttributeError 'NoneType' object has no attribute 'find_all'`。
- `warehouse_receipt`：DCE EB/JD 在曲合仓单为空；AkShare `futures_warehouse_receipt_dce()` 对 `20260521` / `202605` / `2026-05-21` 均 `JSONDecodeError`。

因此这 11 个不再算当前系统可行动缺口，而是明确标为：

- `external_source_not_covering_basis_sparse`
- `external_source_not_covering_dce_warehouse`

## 验证命令

```bash
PYTHONPATH=. FUTURES_DAILY_DB=/Users/rey/.openclaw/workspace/futures-daily/data/futures_daily.db .venv/bin/python tests/test_gap_analysis.py
python3 -m compileall app
curl -X POST http://localhost:8500/api/dataset/materialize/20260521
curl http://localhost:8500/api/dataset/gap-analysis/20260521
```
