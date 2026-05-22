# Futures Daily

全市场期货日报系统：商品期货 + 金融期货 + 席位持仓日报 + 历史数据保存 + Docker Web。

## 范围

交易所：

- DCE 大商所
- CZCE 郑商所
- SHFE 上期所
- CFFEX 中金所
- GFEX 广期所
- INE 上海国际能源中心

第一阶段：

- 下午收盘后生成一份日报
- 保存历史日报和原始行情快照
- 席位持仓日报
- 自选品种预留
- 通知接口预留：Telegram / 企业微信 / WeChatBot

## 快速启动

```bash
docker compose up -d --build
```

访问：<http://localhost:8500>

## 开发

后端：FastAPI + SQLite + APScheduler + AkShare

前端：Vue 3 + Vite + ECharts
