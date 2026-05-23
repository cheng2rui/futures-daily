# Wind / iFinD 对标优化清单

日期：2026-05-23

## 背景

本次参考 Wind / iFinD 这类专业金融终端的期货使用场景，目标不是把 Futures Daily 做成实时交易终端，而是借鉴它们在“数据维度、产业链、事件日历、历史对比、研报资讯、可追溯性”上的成熟做法，增强日报型市场情报能力。

外部官网/搜索在当前环境被 DNS/内网解析策略拦截，本文不引用不可验证的具体页面或私有接口；只抽象专业终端常见能力，并映射到本项目可落地方案。

## 当前 Futures Daily 已具备

- 全市场日行情：DCE/CZCE/SHFE/CFFEX/GFEX/INE，DCE 有 Sina 主连 fallback。
- 席位排名：部分交易所可用，并接入 rsstsx 席位归档能力。
- 自选品种日报：关注池 + 价格/席位/资讯/次日观察。
- 仓单/基差/资金流：Quhe + AkShare 官方/100ppi fallback，带 source capability 降噪。
- 资讯摘要：公开财经资讯采集、品种关联、观点摘要。
- 异动归因：价格、持仓、席位、仓单/基差、资讯证据链。
- 明日观察：结构化 category/title/body/priority/evidence/impact。
- 推送闭环：预览、复制、推送、运行记录、推送文案回看。
- 数据质量：交易所维度 coverage、缺口分类、可补采动作。

## 对标专业终端后的关键差距

### 1. 历史分位和异常度不足

Wind/iFinD 类终端的强项不是只看今天涨跌，而是告诉用户“今天这个变化在历史上有多异常”。

当前 Futures Daily 主要看当日截面，建议新增：

- 20/60/120 日涨跌幅分位
- 成交量/持仓量历史分位
- 仓单变化历史分位
- 基差率历史分位
- 席位净变化历史分位
- 异常度 z-score / percentile rank

落地方式：

- 基于现有 `DailyBar`、`VarietyDailyFact`、`BasisDaily`、`WarehouseReceiptDaily`、`QuheHistoryHolding` 做窗口聚合。
- 新增 service：`app/services/history_factors.py`。
- 在 `abnormal_cards` 里加入 `history_context`：
  - `price_percentile_60d`
  - `volume_percentile_60d`
  - `oi_percentile_60d`
  - `basis_percentile_120d`
  - `seat_net_delta_percentile_60d`
- 前端异动卡片展示“历史位置”：例如“成交量处于近 60 日 92% 分位”。

优先级：P0。

### 2. 期限结构/跨期结构缺失

专业终端里期货品种常看主力、近月、远月、月差、contango/backwardation。当前系统只挑主力和部分合约排行。

建议新增：

- 每品种合约曲线：按月份排序的 close/settlement/open_interest。
- 主力-次主力价差。
- 近远月价差：near-far spread。
- 期限结构标签：contango / backwardation / mixed。
- 月差变化：今日价差 vs 前一交易日价差。

落地方式：

- 基于 `DailyBar` 同一 symbol 多合约计算。
- 新增 `term_structure` 写入 report payload：
  - `symbol`
  - `main_contract`
  - `second_contract`
  - `main_second_spread`
  - `near_far_spread`
  - `structure_type`
  - `curve_points`
- 在日报“明日观察”中，如果某品种月差异动明显，加入“期限结构验证”。

优先级：P0/P1。

### 3. 产业链视角还偏弱

Wind/iFinD 的核心价值之一是把品种放进产业链：上游原料、下游消费、替代品、利润、库存、开工率。当前 Futures Daily 主要按 sector 分组，产业链关系还不够。

建议新增：

- 静态产业链图谱：品种 → 上游/下游/替代/相关品。
- 链条联动评分：同一产业链多个品种同向/背离。
- “异动扩散”判断：例如 PTA 异动时同步看 PX、MEG、短纤、瓶片。
- 产业链日报卡片：今日最强/最弱链条、链条内背离品种。

落地方式：

- 新增 `app/metadata/industry_chain.py`。
- `report_builder` 计算 `industry_chain_digest`。
- 前端新增“产业链联动”卡片。

优先级：P1。

### 4. 事件日历不足

专业终端通常有宏观日历、交易所公告、交割/换月/保证金、EIA/USDA 等事件。当前明日观察已有“交易日历/宏观产业事件”分类，但数据源和规则还薄。

建议新增：

- 交易所公告抓取/手动录入入口。
- 交割月/临近交割提醒。
- 主力换月检测。
- 固定产业事件模板：EIA、USDA、MPOB、OPEC、钢联库存等。
- 宏观事件：CPI/PPI/PMI/FOMC 等。

落地方式：

- 先做规则化本地 calendar，不急着爬全量。
- 新增表或 JSON 配置：`event_calendar`。
- 每次生成日报时输出 `tomorrow_events`，并进入 `tomorrow_watch`。

优先级：P1。

### 5. 研报/资讯深度不够

Wind/iFinD 强在研报、公告、新闻和数据同屏。Futures Daily 已有公开资讯摘要，但还可以更像“投资者读法”：按品种归因、按多空立场、按证据强弱排序。

建议新增：

- 资讯证据评分：source_weight、recency、symbol_match、event_type。
- 研报/新闻分层：公告 > 交易所 > 行业机构 > 财经媒体 > 普通转载。
- 对每个异动卡片输出“资讯是否能解释价格/持仓变化”。
- 对冲突信息标记“分歧”。

落地方式：

- 扩展 `news_digest.viewpoints` 字段：`confidence`、`source_type`、`event_tags`。
- `abnormal_cards` 增加 `news_explains_move: true/false/partial`。

优先级：P1。

### 6. 数据权限/商业源接入预留不足

如果未来用户手里有 Wind/iFinD/Tushare/Choice/交易所付费数据，系统应该能接，而不是重写架构。

建议新增统一 Adapter 协议：

```python
class FuturesDataProvider:
    def daily_bars(trade_date, exchange): ...
    def seat_ranks(trade_date, exchange): ...
    def warehouse_receipts(trade_date): ...
    def basis(trade_date): ...
    def news(trade_date): ...
    def event_calendar(start, end): ...
```

并把来源标为：

- `akshare`
- `quheqihuo`
- `official_exchange`
- `wind_optional`
- `ifind_optional`
- `manual_import`

注意：不要默认依赖 Wind/iFinD 私有接口；只做合法授权后的本地适配层。

优先级：P1/P2。

## 推荐下一轮版本路线

### v0.2.7：历史分位/异常度

最值得先做，因为完全基于现有数据库，不依赖外部新源。

交付：

- `history_factors.py`
- 异动卡片加入历史分位证据
- 问日报支持“这个异动历史上算不算极端？”
- 前端异动卡片展示历史位置

### v0.2.8：期限结构/月差

交付：

- 同品种多合约曲线
- 主力/次主力价差
- contango/backwardation 标签
- 明日观察新增“期限结构验证”

### v0.2.9：产业链联动

交付：

- 静态产业链关系表
- 链条强弱/背离判断
- 前端产业链联动卡片

### v0.3.0：事件日历 + 商业源 Adapter 预留

交付：

- 本地事件日历配置
- 交易所公告/宏观事件/交割换月提醒
- `FuturesDataProvider` adapter 协议
- manual import / optional Wind/iFinD adapter skeleton

## 立刻可做的小优化

1. 在 ROADMAP 增加“专业终端对标”章节。
2. 把 v0.2.7 定为历史分位/异常度。
3. 不碰 Wind/iFinD 私有接口，只保留合法授权 adapter 位置。
4. 先用本地已有历史表做历史分位，最大 ROI。
