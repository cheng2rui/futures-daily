
## 数据库与爬虫增强路线（Rey 2026-05-21 指定）

核心目标：后期建立稳定数据库与更强的数据采集/爬虫能力，尽量把 6 个交易所（DCE/CZCE/SHFE/CFFEX/GFEX/INE）每天数据都集齐。

### P0：每日完整性优先
- 每个交易日收盘后，按交易所逐个采集并入库。
- 对每个交易所分别记录：日行情、席位排名、原始响应、采集状态、错误原因、fallback 来源。
- 失败不吞掉：必须在数据质量页明确显示哪个交易所/哪个数据类型失败。
- 不造假：DCE、INE 等缺席位数据时，只标记失败/缺失，不用行情数据伪造席位。

### P1：数据库沉淀
- 保留 raw archive：每次采集原始 JSON/HTML/CSV 保存，便于后续重放解析。
- 标准化表继续扩展：daily_bars、seat_rank_rows、market_snapshots、reports、job_runs。
- 后续增加：crawler_runs、source_files、data_gaps、exchange_calendar、contract_metadata。
- 支持按日期、交易所、品种、席位查询历史连续数据。

### P2：爬虫增强
- DCE：优先解决官方 412/挑战页问题；可尝试 Playwright/Chrome session、FlareSolverr、历史归档接口、多源 fallback。
- CZCE/SHFE/CFFEX/GFEX/INE：保留 AkShare 通道，同时增加官方页面/API 原始抓取备用。
- 每个 source adapter 要有独立 timeout、retry、结构校验、字段映射和错误日志。
- 将“抓取”和“解析”拆开，方便用 raw archive 回放修复 parser。

### P3：完整性监控
- 每日报告生成前先跑 coverage check。
- 缺数据时自动重试，仍失败则记录 data_gaps。
- Dashboard 显示 6 所当天覆盖矩阵：日行情 / 席位 / 原始归档 / fallback。
- 支持一键补采指定日期或指定交易所。

### P4：复用现有席位日报资产
- 继续吸收 `/Users/rey/.openclaw/workspace-rsstsx-bot/structured_archive` 的成熟结构：Focus5、CR5、多空比、净变化。
- 逐步把 rsstsx 的成熟抓取逻辑迁移/重构为 futures-daily 的 source adapter，而不是长期只读依赖。
