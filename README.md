# Futures Daily

全市场期货日报系统：商品期货 + 金融期货 + 席位持仓日报 + 资讯收集 + 异动归因 + 历史数据保存 + Docker Web。

## 产品定位

Futures Daily **不做实时行情和交易终端**，这些交给专业行情软件。

本项目专注于日报型市场情报：

- 收盘后/阶段性收集全市场行情、席位、仓单、库存、基差、公告和资讯线索
- 自动识别值得关注的品种异动
- 拆解价格、持仓、席位、仓单/库存、基差和新闻之间的关系
- 生成投资者能快速阅读的全市场日报、自选品种日报和次日观察清单

一句话：**让投资者第一时间了解整个期货市场发生了什么，以及为什么值得关注。**

## 范围

交易所：

- DCE 大商所
- CZCE 郑商所
- SHFE 上期所
- CFFEX 中金所
- GFEX 广期所
- INE 上海国际能源中心

第一阶段：

- 下午收盘后生成一份全市场日报
- 生成“异动拆解卡片”：价格 + 持仓 + 席位 + 仓单/库存 + 基差 + 资讯线索
- 保存历史日报和原始行情快照
- 席位持仓日报和结构化净多/净空变化
- 自选品种日报和重点提醒
- 通知接口预留：Telegram / 企业微信 / WeChatBot

## 快速启动

```bash
docker compose up -d --build
```

访问：<http://localhost:8500>


## 发版

使用脚本统一后端版本、前端版本、Git tag、Docker 构建 commit 和 `/api/health` 校验：

```bash
scripts/release.sh 0.2.2
```

常用选项：

- `--no-push`：只本地提交/tag/部署，不推送 GitHub
- `--no-deploy`：只更新版本并提交/tag，不重建容器
- `--no-tag`：只做版本提交，不创建 tag

发版后可检查：

```bash
curl http://localhost:8500/api/health
```

## 开发

后端：FastAPI + SQLite + APScheduler + AkShare

前端：Vue 3 + Vite + ECharts
