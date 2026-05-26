# Futures Daily 后续优化计划（2026-05-26）

结合今天学习/安装的能力：Bumblebee 只读供应链扫描模型、ClawHub skill 市场、安全审查思路、小龙虾自改进流程、CloakBrowser。

## 核心判断

Futures Daily 当前方向不要变：不做实时交易终端，继续做“收盘后/阶段性日报型市场情报”。下一阶段重点不是堆页面，而是把“数据可信度 + 席位采集稳定性 + 证据链 + 发布质量”做硬。

## P0：CloakBrowser 席位采集适配层

目标：给 DCE/CZCE/SHFE/CFFEX/GFEX/INE 官方页面和弱源页面新增浏览器采集能力，但不破坏现有 AkShare / rsstsx 归档链路。

建议实现：

1. 新增 `app/services/browser/` 或 `app/sources/browser_official_source.py`。
2. 用独立 venv：`/Users/rey/.openclaw/workspace/.venvs/cloakbrowser`。
3. 默认用：
   - `from cloakbrowser import launch`
   - 需要 cookie/session 时用 `launch_persistent_context`
4. 采集动作拆成三层：
   - `fetch`: 只负责打开页面、下载 HTML/JSON/CSV/Excel、截图/har 可选。
   - `archive`: 原始响应写入 `raw_archive`。
   - `parse`: parser 从 raw archive 读取并 dry-run/replay。
5. 每个交易所单独 adapter，不要写一个大爬虫：
   - `dce_official_browser`
   - `czce_official_browser`
   - `shfe_official_browser`
   - `cffex_official_browser`
   - `gfex_official_browser`
   - `ine_official_browser`
6. Browser source 先进入 retry planner 的“低频/人工触发补采”步骤，不要一开始每日全自动高频跑。

验收：

- 能对一个指定交易日 + 交易所采集原始页面/文件并写入 source_files。
- parser replay 能解析或明确失败原因。
- 覆盖矩阵显示 browser source 是否补齐 daily / seat_rank。

## P1：席位日报资产内化

当前 `rsstsx_bot` 结构化归档已经成熟，Futures Daily 还偏“读取依赖”。下一步应该迁移成正式 source adapter。

建议：

1. 新增 `RsstsxArchiveSource`，实现 `FuturesDataProvider` 或单独 `SeatArchiveProvider`。
2. 把 Focus5、CR5、多空比、净变化、席位别名规范化变成 app 内部服务。
3. 把 archive 文件行级数据转换进 `seat_rank_rows` 或新的 seat factor 表。
4. 前端席位卡片增加：
   - Focus5 当日动作
   - CR5 集中度变化
   - 多空比极端分位
   - 净多/净空连续性

验收：

- 不依赖外部页面时也能从历史归档重建席位报告。
- 同一品种能看到最近 N 日席位结构变化。

## P2：Bumblebee 式“数据采集 run 模型”

借鉴 Bumblebee：每次采集 run 必须有完整终止记录，receiver/UI 只信 `complete` 的 run。

建议增强现有 `crawler_runs/job_runs`：

1. 给每次采集生成 `run_id`。
2. 每个 source output 类似 NDJSON record：
   - `source_record`
   - `parsed_record`
   - `data_gap`
   - `run_summary`
3. `run_summary.status=complete|partial|error` 成为是否提升为“当前日报状态”的依据。
4. `record_id` 用 canonical tuple hash：`trade_date + exchange + kind + source + source_file + parser_version`。
5. UI 上明确显示“当前日报使用的是哪次 complete run”。

收益：避免补采半失败覆盖好数据，也能让 parser 升级后的差异可追踪。

## P3：供应链与 Skill 安全门禁

Futures Daily 有 Python、Node、Docker、OpenClaw skill/脚本链路，后续应加安全检查。

建议：

1. release 前增加只读依赖快照：
   - `package-lock.json`
   - Python env / requirements / pyproject
   - Dockerfile / compose
2. 借鉴 Bumblebee exposure catalog：维护本地 `security/exposure_catalog.json`。
3. 后续可做 `scripts/security_inventory.py`：输出 NDJSON，不联网、不执行包管理器。
4. 第三方 skill/自动化脚本进入项目前，先用 skill-vetter/skillscan 思路做红线检查：
   - 自启动/LaunchAgent/cron
   - 隐藏持久化
   - base64/混淆 payload
   - 外发 token/密钥
   - 大范围删除

## P4：日报分析增强

继续围绕“投资者打开就知道发生了什么”：

1. 异动卡片加“可信度层级”：
   - high：行情 + 席位 + 仓单/基差 + 新闻多证据一致
   - medium：两类证据一致
   - low：只有单源或有缺口
2. 明日观察清单自动绑定数据缺口：
   - 如果 DCE 席位缺失，明确写“明日先复核 DCE seat_rank”。
3. 席位信号历史验证：
   - Focus5 加仓后 1/3/5 日价格表现
   - CR5 极端后回归/延续概率
4. 把 `history_context` 扩展到席位维度：
   - 净变化分位
   - CR5 分位
   - 多空比分位

## P5：自改进闭环

1. 每次 futures-daily 迭代后，把真实问题写入 `memory/YYYY-MM-DD.md`。
2. 每周自改进 cron 会抽取高分教训。
3. 对 futures-daily 特有教训，沉淀到：
   - `MEMORY.md`
   - `ROADMAP.md`
   - `docs/ops-runbook.md`（建议新增）

## 推荐近期版本拆分

### v0.5.13：CloakBrowser 基础设施
- 新增 browser source 基础封装和配置。
- 增加一个官方页面 smoke test / data URL test。
- Retry Planner 能识别 browser source 作为可选补采动作。

### v0.5.14：DCE/CZCE 席位 browser probe
- 先选 DCE 或 CZCE 一个最痛的交易所做 browser raw archive。
- 不承诺完全解析，先保存原始响应 + replay。

### v0.5.15：席位归档内化
- `rsstsx_structured_archive` 正式 provider 化。
- 席位卡片增强 Focus5/CR5/多空比。

### v0.5.16：run_summary / stable record id
- 采集 run 完整性语义收口。
- UI 显示当前报告使用的完整 run。

### v0.5.17：安全 inventory
- 本地只读依赖/脚本/skill inventory。
- release 前安全检查进入 `scripts/test.sh` 或单独 `scripts/security_check.sh`。

## 发布纪律

每次 futures-daily 迭代完成必须执行：

1. `scripts/test.sh`
2. `npm run build --prefix frontend`
3. commit + push
4. `docker compose up -d --build futures-daily`
5. 验证 `http://localhost:8500/api/health` version/commit
6. tag + GitHub Release
7. 再汇报

## v0.5.14-v0.5.17 执行记录

- v0.5.14：新增 `app/services/browser/official_probe.py`，用 CloakBrowser 对交易所官方页面做低频 browser raw archive probe；当前只归档原始 browser observation，不提升解析数据。
- v0.5.15：新增 `app/sources/rsstsx_archive_source.py`，把 rsstsx 结构化席位归档 provider 化，输出 Focus5/CR5/多空比/净变化信号。
- v0.5.16：新增 `app/services/run_records.py`，提供 stable record id 与 run_summary 工具，为后续 complete run 提升 current-state 铺路。
- v0.5.17：新增 `scripts/security_inventory.py`，提供本地只读安全 inventory，扫描持久化、curl pipe shell、混淆 payload、危险删除、明文 secret 等风险模式。

## v0.5.18 执行记录

- 新增 `POST /api/dataset/browser-probe/{trade_date}/{exchange}`，可指定 kind/url，用 CloakBrowser 低频抓取官方页并写入 `source_files`。
- `raw_replay` 支持 `*_browser_probe` 归档：提取 title/status/html_length/webdriver/user_agent，并识别 table、Excel 链接、席位关键词、challenge-like 页面信号。
- 当前仍保持 dry-run/replay 语义：browser probe 只作为 raw archive 证据，不直接入库 seat_rank_rows。

## v0.5.19 执行记录

- 数据诊断页的 Retry Planner 步骤现在展示 `browser_probe` 提示：原因、下一步和 provider。
- 对带 `browser_probe` 的席位缺口新增一键 `Browser Probe` 按钮，调用 `POST /api/dataset/browser-probe/{trade_date}/{exchange}`；完成后自动切换 Raw Archive 过滤到 `seat_rank_browser_probe` 并尝试 replay。
- Raw Archive 类型筛选新增“席位 Browser Probe”。

## v0.5.20 执行记录

- `raw_replay` 对 `*_browser_probe` 增加结构化候选提取：HTML table candidates、Excel/CSV/席位相关链接、席位关键词上下文块。
- Replay stats 增加 `table_candidates`、`excel_links`、`keyword_blocks`，方便在数据诊断页直接判断官方页是否有可写 parser 的候选对象。
- 仍保持 dry-run：候选只作为 parser 开发线索，不直接提升正式席位数据。

## v0.5.21 执行记录

- 新增 `app/services/browser_probe_analysis.py`：DCE browser probe 候选分析器雏形。
- 对 replay 提取出的 table/link/keyword block 进行打分，输出 `candidate_analysis`、`best_candidate`、`parser_plan`、置信度和下一步动作。
- DCE 优先识别会员/名次/成交/持买/持卖/持仓/排名等表头和 Excel 下载链接；其他交易所暂返回 unsupported_exchange。
