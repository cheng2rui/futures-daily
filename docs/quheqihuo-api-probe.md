# 曲合期货数据接口探测

探测时间：2026-05-21
入口页面：`https://m.quheqihuo.com/data/zijin.html`
JS：`https://res.quheqihuo.com/mobile/js/m_quhe_datacenter.js`

## 总结

曲合期货数据中心有一批可直接 GET 的 JSON 接口，无需登录、无需 Playwright，普通 `requests/curl` 可用。

适合接入 `futures-daily` 作为**第三方备用/增强源**：

1. 资金流向：可直接补充品种资金流信号
2. 基差：可补充现货价/主力价/基差/基差率
3. 仓单：可补充仓单数量和变化
4. 合约树：可补充交易所-品种-合约映射、主力合约、JO quote code
5. 单合约多空龙虎榜：可作为 DCE/SHFE/CZCE/GFEX 部分品种席位备用源
6. 历史多空持仓：可补充连续多空总持仓走势

注意：这是第三方加工数据，不能替代交易所官方原始数据；应标记 `source=quheqihuo`。

---

## Base URLs

```text
数据中心： https://api.quheqihuo.com/api/v2/datacenter
主站 API： https://www.quheqihuo.com
移动端：   https://m.quheqihuo.com
```

通用 headers：

```bash
-H 'User-Agent: Mozilla/5.0'
-H 'Referer: https://m.quheqihuo.com/data/zijin.html'
```

---

## 1. 资金流向

```text
GET https://www.quheqihuo.com/api/exchange_variety/capital
GET https://m.quheqihuo.com/api/exchange_variety/capital
```

返回：

```json
{
  "returnCode": 0,
  "code": 0,
  "data": {
    "data": [
      {"productCode":"cu", "productName":"沪铜", "price":-744838348.5}
    ],
    "time": 1779371106964
  }
}
```

字段：

- `productCode`：品种代码，大小写混用
- `productName`：品种名
- `price`：资金流向金额，单位元；前端 `/100000000` 显示为亿元
- `time`：毫秒时间戳

样本：2026-05-21 返回 55 个品种。

---

## 2. 基差报告

```text
GET https://api.quheqihuo.com/api/v2/datacenter/app/basis/getBasisDataList.html
```

样本字段：

```json
{
  "name": "锡",
  "productCode": "sn",
  "price": 420450.0,
  "code": "2607",
  "mainPrice": 414110.0,
  "basis": 6340.0,
  "basisRate": 1.51,
  "highest": 18212.5,
  "lowest": -22822.5,
  "average": -344.64,
  "exchange": "上海期货交易所",
  "publishTime": "2026-05-21",
  "marginRatio": 70398.7
}
```

样本返回 51 个品种。适合落表 `basis_daily` 或并入 `variety_daily_facts`。

---

## 3. 仓单日报

```text
GET https://api.quheqihuo.com/api/v2/datacenter/app/position/positionOrder.html
```

样本字段：

```json
{
  "day": "2026-05-21",
  "type": "A",
  "productName": "黄豆一号",
  "receiptNumber": 24570,
  "increaseNumber": 0,
  "increaseRatio": 0.0,
  "handNumber": 24570
}
```

样本返回 72 个品种。

### 仓单历史

```text
GET https://api.quheqihuo.com/api/v2/datacenter/app/position/positionOrderByDates.html?startDate=2026-05-01&endDate=2026-05-21&type=RB
```

`type` 使用大写品种代码，如 `RB`、`I`、`FG`、`LC`、`CU`、`SC`。

返回字段同仓单日报，适合做仓单趋势。

---

## 4. 交易所/品种/合约树

### 交易所列表

```text
GET https://api.quheqihuo.com/api/v2/datacenter/futures/getExchange/
```

返回：

```json
[
  {"exchangeCode":918,"name":"上海期货交易所"},
  {"exchangeCode":919,"name":"大连商品交易所"},
  {"exchangeCode":920,"name":"郑州商品交易所"},
  {"exchangeCode":934,"name":"中国金融期货交易所"},
  {"exchangeCode":927,"name":"上海国际能源交易中心"},
  {"exchangeCode":937,"name":"广州期货交易所"}
]
```

### 可用交易日

```text
GET https://api.quheqihuo.com/api/v2/datacenter/futures/getAvailableTradingDay/
```

返回毫秒时间戳列表，样本 22 个交易日。

### 按交易所获取品种

```text
GET https://api.quheqihuo.com/api/v2/datacenter/futures/getProductByExchangeCode/?exchangeCode=919
```

### 按品种获取合约

```text
GET https://api.quheqihuo.com/api/v2/datacenter/futures/getSymbolByProduct/?productCode=i
```

### 完整合约树（推荐）

```text
GET https://www.quheqihuo.com/api/exchange_variety/tree_by_product_code
```

返回 88 个品种，含 `symbolList`、`varietyCode`、`quotaCode`、`boardId`、`boardName`、`isMain` 等。适合补充本地合约元数据。

---

## 5. 单合约多空龙虎榜（重点）

```text
GET https://api.quheqihuo.com/api/v2/datacenter/app/position/rank.html?symbolCode=rb2610&transactionTime=2026-05-21&type=2
GET https://api.quheqihuo.com/api/v2/datacenter/app/position/rank.html?symbolCode=rb2610&transactionTime=2026-05-21&type=3
```

参数：

- `symbolCode`：合约代码，如 `rb2610`、`i2609`、`FG609`、`lc2609`
- `transactionTime`：`YYYY-MM-DD`
- `type=2`：多头持仓排行
- `type=3`：空头持仓排行

样本字段：

```json
{
  "productCode": "rb",
  "productName": "螺纹钢",
  "symbolCode": "rb2610",
  "symbolName": "螺纹钢2610",
  "companyName": "中信期货",
  "volume": 318436.0,
  "changes": -8580.0,
  "transactionTime": 1779292800000,
  "type": 2,
  "createdAt": 1779358803000
}
```

### 价值

这个接口能补 DCE 主力合约多空席位，是当前 `futures-daily` 最大缺口的备用来源。

已验证：

- DCE 铁矿石 `i2609`：多 19 行、空 20 行
- DCE 聚丙烯 `pp2609`：多 19 行、空 20 行
- SHFE 螺纹 `rb2610`：多 20 行、空 20 行
- CZCE 玻璃 `FG609`：多 20 行、空 20 行
- GFEX 碳酸锂 `lc2609`：多 20 行、空 20 行

中金所 CFFEX 多数为空，INE 原油/集运也为空。

### 全品种覆盖探测（2026-05-21）

88 个品种里，按主力合约探测结果：

```text
上海期货交易所：20 品种，17 有 rank，17 有 history
大连商品交易所：23 品种，19 有 rank，19 有 history
郑州商品交易所：27 品种，18 有 rank，18 有 history
广州期货交易所：5 品种，2 有 rank，2 有 history
上期能源：4 品种，2 有 rank，2 有 history
中国金融期货交易所：8 品种，0 有 rank，0 有 history
上海国际能源交易中心：1 品种，0 有 rank，0 有 history
```

结论：非常适合做商品期货席位备用源，尤其是 DCE。

---

## 6. 历史多空持仓

```text
GET https://api.quheqihuo.com/api/v2/datacenter/app/futures/getFuturesHistoryHolding.html?symbolCode=rb2610&sum=1500
```

样本字段：

```json
{
  "date": 1779292800000,
  "manyTo": 1214079.0,
  "emptyTo": 1199641.0
}
```

字段：

- `manyTo`：多头总持仓
- `emptyTo`：空头总持仓

适合补充连续多空持仓趋势。

---

## 建议接入顺序

### P0：先接资金流/基差/仓单

低风险、单接口、全量返回：

- `capital_flow_daily`
- `basis_daily`
- `warehouse_receipt_daily`

### P1：接合约树

- 保存 88 个品种与主力合约映射
- 用作 Quhe rank/history 的 symbolCode 来源

### P2：接 Quhe 单合约多空龙虎榜作为备用席位源

- source 标记 `quheqihuo`
- 只作为 DCE/缺失交易所 fallback，不覆盖官方 AkShare/交易所数据
- 入库时字段映射到 `SeatRankRow` 或单独 `third_party_position_rank`

### P3：接历史多空持仓

- 可做趋势图和连续动作判断
- 不替代会员席位明细，只补总多空结构
