# futures-panel 可复用审计

本项目检查 `/Users/rey/.openclaw/workspace/futures-panel` 后，优先迁移低耦合、高价值配置。

## 已迁移

- `VARIETY_META` → `app/metadata/variety_meta.py`
  - 品种中文名
  - Sina 代码/简称
  - 交易所中文名
  - 提供 `get_variety_name()`、`get_exchange_code()`

- `POINT_VALUE` → `app/metadata/contract_specs.py`
  - 合约乘数 / 每点价值
  - 提供 `get_point_value()`
  - 日报中用于计算持仓名义价值 `notional_oi`

## 建议后续迁移

- `MARGIN_RATE`、`COMMISSION`、`PRICE_LIMIT`
  - 用于风控页、保证金估算、涨跌停判断。
- futures-panel 的 Sina direct realtime fallback
  - 可作为 futures-daily 的盘中/夜盘口子，不适合替代官方日行情。
- Z-score 价差分析
  - 后续做套利/跨期结构日报时复用。

## 不建议直接迁移

- Flask routes / SSE / scanner_engine
- 内存型 CircuitBreakerCache
- AI 决策模块

这些和 futures-daily 的 FastAPI + SQLite + 定时报告架构差异较大。
