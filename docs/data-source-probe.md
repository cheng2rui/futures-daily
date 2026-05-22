# AkShare 期货数据接口探测报告

> 探测日期: 2026-05-21  
> AkShare 版本: 1.18.55  
> 探测目的: futures-daily 项目 source adapter 设计验证

---

## 一、探测执行摘要

| 类别 | 交易所 | 接口函数 | 状态 | 说明 |
|------|--------|---------|------|------|
| **日行情** | CZCE | `get_czce_daily()` | ✅ 可用 | 241 条，12 字段 |
| **日行情** | SHFE | `get_shfe_daily()` | ✅ 可用 | 305 条，13 字段（含 index 列）|
| **日行情** | CFFEX | `get_cffex_daily()` | ✅ 可用 | 28 条，12 字段 |
| **日行情** | GFEX | `get_gfex_daily()` | ✅ 可用 | 48 条，12 字段 |
| **日行情** | INE | `get_ine_daily()` | ✅ 可用 | 67 条，12 字段 |
| **日行情** | DCE | `get_dce_daily()` | ❌ 失败 | JSONDecodeError，源站结构变更 |
| **持仓排名** | SHFE | `get_shfe_rank_table()` | ✅ 可用 | dict[contract] → DataFrame |
| **持仓排名** | CFFEX | `get_cffex_rank_table()` | ✅ 可用 | dict[contract] → DataFrame |
| **持仓排名** | GFEX | `futures_gfex_position_rank()` | ✅ 可用 | dict[contract] → DataFrame |
| **持仓排名** | DCE | `get_dce_rank_table()` | ⚠️ 空数据 | 返回 `{}`，近期数据缺失 |
| **持仓排名** | DCE | `futures_dce_position_rank()` | ❌ 失败 | BadZipFile |
| **席位排名** | SHFE | `get_rank_sum()` | ❌ 失败 | BadZipFile |
| **合约信息** | CZCE | `futures_contract_info_czce()` | ✅ 可用 | 241 条，40 字段（最全）|
| **合约信息** | SHFE | `futures_contract_info_shfe()` | ✅ 可用 | 302 条，8 字段 |
| **合约信息** | CFFEX | `futures_contract_info_cffex()` | ✅ 可用 | 722 条，12 字段 |
| **合约信息** | GFEX | `futures_contract_info_gfex()` | ✅ 可用 | 48 条，7 字段 |
| **合约信息** | INE | `futures_contract_info_ine()` | ✅ 可用 | 64 条，7 字段 |
| **合约信息** | DCE | `futures_contract_info_dce()` | ❌ 失败 | JSONDecodeError |
| **单一合约详情** | 通用 | `futures_contract_detail()` | ✅ 可用 | item/value 键值对形式 |

---

## 二、日行情接口详解

### 2.1 字段差异（六个交易所）

| 字段 | CZCE | SHFE | CFFEX | GFEX | INE |
|------|------|------|-------|------|-----|
| `symbol` | str | str | str | str | str |
| `date` | **int** (如 20260521) | **str** ("20260521") | **str** | str | str |
| `open` | float64 | **object**（需转float）| float64 | float64 | **object** |
| `high` | float64 | **object** | float64 | float64 | **object** |
| `low` | float64 | **object** | float64 | float64 | **object** |
| `close` | float64 | float64 | float64 | float64 | **object** |
| `volume` | int64 | int64 | int64 | int64 | **object** |
| `open_interest` | int64 | **object** | int64 | int64 | **object** |
| `turnover` | float64 | float64 | float64 | float64 | **object** |
| `settle` | float64 | **object** | float64 | float64 | **object** |
| `pre_settle` | float64 | **object** | float64 | float64 | **object** |
| `variety` | str | str | str | str | str |
| `index` | ❌ 无 | **int**（行号）| ❌ 无 | ❌ 无 | ❌ 无 |

**关键风险**:
- SHFE 和 INE 返回大量 `object` 类型字段，需主动 `pd.to_numeric()` 转换
- SHFE 有一个多余的 `index` 列（DCE 历史遗留）
- CZCE 的 date 是 int 类型，其他是 str

### 2.2 日行情字段标准化映射建议

```
symbol           ← 合约代码（如 CU2607, IF2606）
date             ← 交易日期（统一转为 YYYYMMDD int 或 str）
open             ← 开盘价（统一 float64）
high             ← 最高价
low              ← 最低价
close            ← 收盘价
volume           ← 成交量（统一 int64）
open_interest    ← 持仓量（统一 int64）
turnover         ← 成交额（float64，INE/SHFE object 需转换）
settle           ← 结算价
pre_settle       ← 前结算价
variety          ← 品种代码（如 CU, IF, M）
```

### 2.3 DCE 日行情替代方案

`get_dce_daily()` 持续失败（源站 JSON 解析空响应），目前已知无直接替代函数。

可能的 workaround：
- `futures_display_main_sina()` 获取主力合约，再逐个查 `futures_zh_daily_sina`（但后者在实测中也失败）
- 考虑换用 `ak.adapt()` 等其他数据源适配层

---

## 三、持仓排名接口详解

### 3.1 接口函数对照

| 交易所 | 席位排名（成交量/成交额）| 持仓排名（多空持仓）| 备注 |
|--------|----------------------|------------------|------|
| SHFE | `get_shfe_rank_table()` | 同上（合并）| ✅ 可用 |
| CFFEX | `get_cffex_rank_table()` | 同上（合并）| ✅ 可用 |
| GFEX | `futures_gfex_position_rank()` | 同上 | ✅ 可用 |
| DCE | `get_dce_rank_table()` | `futures_dce_position_rank()` | ❌ 均失败 |
| CZCE | 无独立接口 | 无独立接口 | ⚠️ 依赖 `get_rank_sum`（失败）|

### 3.2 字段结构差异

**SHFE rank table (可用)**:
```
symbol, short_party_name, long_party_name, rank, vol_party_name,
long_open_interest, vol, vol_chg,
short_open_interest_chg, short_open_interest, long_open_interest_chg, variety
→ 12 列，多空分开，有席位名，有成交量 + 持仓量
```

**CFFEX rank table (可用)**:
```
long_open_interest, long_open_interest_chg, long_party_name, rank,
short_open_interest, short_open_interest_chg, short_party_name,
symbol, vol, vol_chg, vol_party_name, variety
→ 12 列，字段顺序不同（long 相关在前）
```

**GFEX position rank (可用)**:
```
rank, vol_party_name, vol, vol_chg,
long_party_name, long_open_interest, long_open_interest_chg,
short_party_name, short_open_interest, short_open_interest_chg,
symbol, variety
→ 12 列，与 CFFEX 类似
```

**字段统一映射建议**:
```
rank, party_name(L 多方 / S 空方), open_interest, open_interest_chg, 
vol, vol_chg, symbol, variety
```

---

## 四、合约信息接口

### 4.1 各交易所字段对比

| 字段 | CZCE | SHFE | CFFEX | GFEX | INE |
|------|------|------|-------|------|-----|
| 合约代码 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 上市日 | — | ✅ | ✅ | ✅ | ✅ |
| 到期日 | — | ✅ | — | ✅ | ✅ |
| 最后交易日 | ✅ | — | ✅ | ✅ | — |
| 挂盘基准价 | — | ✅ | ✅ | — | ✅ |
| 涨跌停板幅度 | — | — | ✅ | — | — |
| 持仓限额 | — | — | ✅ | — | — |
| 交易保证金率 | ✅ | — | — | — | — |
| 交易手续费 | ✅ | — | — | — | — |
| 产品名称 | ✅ | — | — | ✅（品种）| — |

> CZCE 的 `futures_contract_info_czce` 信息最全面（40字段），适合交割/保证金规则配置。  
> SHFE/CFFEX 侧重交易日期，适合合约生命周期管理。

---

## 五、已知故障点汇总

| # | 接口 | 故障现象 | 可能原因 | 影响 |
|---|------|---------|---------|------|
| 1 | `get_dce_daily()` | JSONDecodeError | 源站（大商所）可能已更换数据格式或增加反爬 | **无法获取 DCE 日行情** |
| 2 | `get_dce_rank_table()` | 返回 `{}`（空）| 大商所近期无数据发布或格式变更 | DCE 席位/持仓排名不可用 |
| 3 | `futures_dce_position_rank()` | BadZipFile | 下载的 ZIP 包损坏/不是 ZIP | DCE 持仓排名不可用 |
| 4 | `get_rank_sum()` | BadZipFile | 同上 | 跨交易所统一席位排名不可用 |
| 5 | `futures_contract_info_dce()` | JSONDecodeError | 源站变更 | DCE 合约信息不可用 |
| 6 | `futures_zh_daily_sina()` | Length mismatch | 单合约查询返回空DF后再赋值失败 | 无法通过此函数查询单品种 |
| 7 | `futures_contract_detail_em()` | AttributeError | HTML 解析失败（symbol 参数格式不对）| 单一合约详情可能需换方法 |

---

## 六、Source Adapter 设计建议

### 6.1 推荐的架构

```
sources/
├── akshare_daily/        # 日行情适配器
│   ├── __init__.py
│   ├── base.py           # DailyMarketSource 基类
│   ├── czce.py           # get_czce_daily + 类型规范化
│   ├── shfe.py           # get_shfe_daily + object→float64
│   ├── cffex.py          # get_cffex_daily
│   ├── gfex.py           # get_gfex_daily
│   ├── ine.py            # get_ine_daily
│   └── dce.py           # get_dce_daily（标记为 DEPRECATED / fallback）
│
├── akshare_rank/         # 持仓排名适配器
│   ├── base.py
│   ├── shfe_rank.py      # get_shfe_rank_table → 标准化 DataFrame
│   ├── cffex_rank.py     # get_cffex_rank_table
│   ├── gfex_rank.py      # futures_gfex_position_rank
│   └── dce_rank.py       # 标记为 DEPRECATED（两个接口均失败）
│
├── akshare_contract/     # 合约信息适配器
│   ├── czce.py           # 40字段，最丰富
│   ├── shfe.py           # 交易日期为主
│   ├── cffex.py          # 持仓限额等
│   ├── gfex.py           # 基本字段
│   ├── ine.py            # 基本字段
│   └── dce.py            # 标记为 DEPRECATED
```

### 6.2 标准化返回结构

**日行情 (DailyMarketRow)**:
```python
@dataclass
class DailyMarketRow:
    symbol: str          # "CU2607"
    date: int            # 20260521
    open: float
    high: float
    low: float
    close: float
    volume: int
    open_interest: int
    turnover: float     # 成交额
    settle: float       # 结算价
    pre_settle: float   # 前结算价
    variety: str        # "CU"
    # source 元数据
    exchange: str
    fetched_at: datetime
```

**持仓排名 (PositionRankRow)**:
```python
@dataclass
class PositionRankRow:
    date: int
    symbol: str
    variety: str
    exchange: str
    rank: int
    # 多方
    long_party: str      # 席位名
    long_vol: int
    long_vol_chg: int
    long_oi: int
    long_oi_chg: int
    # 空方
    short_party: str
    short_vol: int
    short_vol_chg: int
    short_oi: int
    short_oi_chg: int
    fetched_at: datetime
```

### 6.3 关键设计决策

1. **类型强制转换层**: SHFE/INE 的 object 字段必须经过 `pd.to_numeric()` 校验再落入 schema，避免 silent coercion（pandas 的 object+int 会变成 float）。

2. **日期格式统一**: CZCE 返回 `int` (20260521)，SHFE/CFFEX 返回 `str`，adapter 应统一转为 `int` 或 `datetime.date`。

3. **DCE 降级策略**: 标记为 deprecated source，运行时记录 `warning`，数据质量仪表盘标记为 `partial coverage`。

4. **Pagination**: `get_rank_table()` 返回 `dict[contract_symbol] → DataFrame`，需要 flatten 后再合并。

5. **错误处理**: 网络超时 → retry 3次 with exponential backoff；JSON 空响应 → 记录 "source_unavailable" 而非 raise。

6. **增量更新**: 日行情建议用 `trading_date` 作为 id，在数据库中做 upsert，避免重复写入。

---

## 七、字段数据类型总览（已验证）

```
# 日行情 — 目标 schema
字段          | CZCE     | SHFE          | CFFEX    | GFEX     | INE
--------------|----------|---------------|----------|----------|-----------
symbol        | str      | str           | str      | str      | str
date          | int      | str           | str      | str      | str
open          | float64  | object→float | float64  | float64  | object→float
high          | float64  | object→float  | float64  | float64  | object→float
low           | float64  | object→float  | float64  | float64  | object→float
close         | float64  | float64       | float64  | float64  | object→float
volume        | int64    | int64         | int64    | int64    | object→int
open_interest | int64    | object→int    | int64    | int64    | object→int
turnover      | float64  | float64       | float64  | float64  | object→float
settle        | float64  | object→float  | float64  | float64  | object→float
pre_settle    | float64  | object→float  | float64  | float64  | object→float
variety       | str      | str           | str      | str      | str
```

---

## 八、风险项

1. **⚠️ 高风险**: DCE 日行情和持仓排名接口均不可用，需评估是否有其他数据源（如 Tushare、Baostock）可互补。

2. **⚠️ 中风险**: `get_rank_sum()` 和 `futures_dce_position_rank()` 的 BadZipFile 错误可能意味着交易所近期换了数据压缩格式（gz vs zip），需要追踪 akshare 的更新。

3. **⚠️ 低风险**: SHFE/INE 的 object 类型字段在 pandas 中容易 silent overflow（如 126493 字符串转 float 再转 int 可能丢精度），建议在 adapter 层做 schema validation。

4. **机会**: CZCE 的合约信息字段最全（40个字段），适合做交易成本分析/保证金优化模块。

---

## 附录：探测脚本

脚本位置: `futures-daily/tmp/akshare_probe.py`  
JSON 结果: `futures-daily/tmp/akshare_probe.json`（完整原始返回）