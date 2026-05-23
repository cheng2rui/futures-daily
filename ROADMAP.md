# Futures Daily Roadmap

## 产品方向（2026-05-22 确认）

核心定位：**不做实时行情，不做交易终端，只做日报类资讯收集和拆解分析**。

目标用户打开后应该立刻知道：

1. 今天全市场哪些板块和品种最值得关注
2. 异动来自价格、持仓、席位、仓单/库存、基差还是资讯事件
3. 明天需要继续观察哪些变量
4. 当前日报的数据覆盖和可信度如何

### P0：日报闭环

- 市场总览：涨跌、成交、持仓、数据覆盖
- 异动拆解卡片：每个重点品种给出原因、维度评分、方向标签和次日观察
- 持仓席位日报：多空前 20、净变化、席位集中度
- 仓单/库存/基差增强源接入
- 数据质量提示：缺失不隐藏，不造假

### P1：投资者视角增强

- 自选品种日报：配置自选 + 默认关注池合并，聚合价格/席位/仓单/基差/资讯观点/次日观察
- 机构/资讯观点摘要：看多、看空、震荡、风险点
- 公开资讯采集：东方财富/新浪等来源入库，按品种关键词自动归类并关联异动卡片
- 规则化观点抽取：按品种输出偏多/偏空/分歧/中性、驱动标签、代表资讯和复核提示
- 明日观察清单：重点品种后续验证、数据质量复核、宏观/产业事件、交易所公告
- 推送日报模板：生成 Telegram/微信可读的纯文本摘要，并提供 API/定时任务发送入口
- 前端推送操作：首页支持一键复制推送文案、一键调用后端推送日报
- 通知配置前端化：设置页支持 Telegram 开关、bot token/chat id 保存和测试推送
- 推送历史记录：手动/定时推送写入 JobRun，任务页展示 sent/skipped/failed 和通道详情
- 明日交易日历：宏观数据、EIA/USDA、交易所公告、交割/保证金提醒
- 日报结论与看板证据链联动（v0.1.8：异动/自选卡片输出价格量仓 → 席位 → 基差/仓单 → 资讯观点 → 明日观察的结构化 evidence_chain，并在看板直接展示）

### 已完成能力补充

- v0.1.8：TodayView 开始组件化拆分，抽出头图操作区与核心指标区，降低后续看板迭代耦合。
- v0.1.8：复盘证据链增强，后端报告 payload 增加 `evidence_chain`，前端异动卡片/自选监控可直接看到关键证据来源与次日验证项。
- v0.2.0：修复 DCE 不可恢复标记误判（当日行情存在时不应标记为不可恢复）；修复数据资产页 qualityFilter 重复条件；设置页增加窄屏响应式适配。
- v0.2.1：统一后端/前端版本号到 0.2.x，并在 `/api/health` 暴露构建 commit，方便部署版本诊断。

### P2：专业分析能力

- 基差/期限结构
- 产业链看板
- 持仓/仓单信号历史验证
- CSV/JSON/API 导出

---


## 专业终端对标优化（Wind / iFinD 启发，2026-05-23）

原则：不把 Futures Daily 做成实时交易终端，也不默认依赖 Wind/iFinD 私有接口；只借鉴专业终端的数据组织方式，增强日报型市场情报。

详见：`docs/wind-ifind-benchmark.md`

### v0.2.7：历史分位 / 异常度（优先）
- 基于现有历史库计算 20/60/120 日分位：涨跌幅、成交、持仓、仓单、基差、席位净变化。
- 异动卡片增加 `history_context`，展示“这次变化在历史上算不算极端”。
- 问日报支持“这个异动历史上极端吗？”
- 前端异动卡片展示历史位置。

### v0.2.8：期限结构 / 月差
- 同品种多合约曲线。
- 主力-次主力价差、近远月价差。
- contango / backwardation / mixed 标签。
- 明日观察新增“期限结构验证”。

### v0.2.9：产业链联动
- 静态产业链图谱：上游/下游/替代/相关品。
- 链条强弱、链条内背离、异动扩散。
- 前端新增产业链联动卡片。

### v0.3.0：事件日历 + 数据源 Adapter
- 本地事件日历：交割换月、保证金、EIA/USDA/宏观数据、交易所公告。
- 统一 FuturesDataProvider adapter 协议。
- 预留合法授权后的 Wind/iFinD/manual import adapter，不接入未授权私有接口。

### v0.3.1：数据覆盖矩阵
- 新增 6 所 × 数据类型覆盖矩阵：日行情、席位、席位归档、资金流、基差、仓单、事件日历。
- 覆盖状态统一为 ok / missing / failed / fallback / partial / not_supported。
- 生成日报时同步 data_gaps，缺失不隐藏，已恢复自动标记 resolved。
- 今日看板“数据完整度”展示覆盖矩阵和核心/综合覆盖率。

### v0.3.2：raw archive 原始数据归档
- 新增 source_files 索引表，保存原始响应文件路径、hash、行数、错误信息和大小。
- 日行情、席位、曲合增强源、官方仓单补充会把 vendor-shaped payload 写入 `data/raw_archive/`。
- 新增 raw archive 查询接口，后续 parser 修复可直接读取历史原始响应重放。

### v0.3.3：raw archive parser replay
- 新增 raw replay 服务，可读取 source_files 中的原始响应并 dry-run 运行 parser。
- 首批支持日行情和席位 parser 重放，输出 parsed/skipped/error/sample/stats，不修改数据库。
- 新增 `POST /api/dataset/raw-archives/{file_id}/replay`，后续修 parser 可先 dry-run 对比。

### v0.3.4：DCE / INE 数据源诊断
- 覆盖矩阵将 INE 席位明确标为 not_supported，避免和普通采集失败混淆。
- 新增 DCE / INE 弱源诊断服务，汇总覆盖状态、最近 crawler run、data_gap、raw archive 和建议动作。
- 新增 `GET /api/quality/diagnostics/{trade_date}`，支持 `exchange=DCE|INE` 定向查看。

### v0.3.5：数据诊断前端页
- 新增“数据诊断”导航页，集中展示覆盖矩阵、DCE/INE 诊断、可补采动作和 raw archive。
- 页面支持按交易所/类型筛选 raw archive，并直接触发 parser replay dry-run。
- DCE/INE 的 daily/seat_rank 缺口支持前端一键调用 recollect 并刷新诊断结果。

### v0.3.6：补采 / replay 结果对比
- 新增 coverage diff 服务，对比补采前后核心覆盖率、综合覆盖率、cell 状态和行数变化。
- `/api/reports/{trade_date}/recollect` 返回 `coverage_diff`，JobRun 也记录 before/after coverage matrix。
- raw archive replay 增加解析成功率，数据诊断页展示最近一次补采或 replay 的影响摘要。

### v0.3.7：数据源健康评分
- 新增 source health 服务，按源统计最近运行、归档数量、开放缺口、成功率和健康评分。
- 前端“数据诊断”页新增数据源健康卡片，能直接看到 akshare / quheqihuo / fallback 的健康状态。
- 健康评分优先解释问题来源，不做黑盒分数。

### v0.3.8：自动补采策略 / Retry Planner
- 新增 retry planner，根据覆盖矩阵和 source health 自动生成补采步骤、跳过项、推荐源和风险说明。
- 新增 `GET /api/quality/retry-plan/{trade_date}`。
- 数据诊断页新增“自动补采计划”，支持执行第一步或指定步骤，核心补采走 recollect，增强数据走 collect-quhe。

### v0.3.9：自动执行补采计划 / Retry Runner
- 新增 retry runner，可按 retry planner 顺序执行安全步骤，并为每步记录 before/after coverage diff。
- 新增 `POST /api/quality/retry-plan/{trade_date}/run`，支持 max_steps、stop_on_failure、rebuild 参数。
- 数据诊断页新增“执行计划”，一次最多自动跑前三步，并展示 job、失败数和聚合改善结果。

---


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
