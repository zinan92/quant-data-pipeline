<div align="center">

# quant-data-pipeline

**多市场量化数据平台 — A股、美股、加密货币、大宗商品，一站式实时数据与感知信号**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB)](https://react.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 痛点

散户同时关注 A股、美股、加密货币、大宗商品时，需要在同花顺、TradingView、CoinGecko 等多个平台之间来回切换。数据源分散、格式不统一，无法快速形成跨市场全局视角。盘中异动容易遗漏，盘后复盘缺少结构化数据支撑。

## 解决方案

quant-data-pipeline 将 AKShare、TuShare、Yahoo Finance、新浪财经等数据源统一接入，通过 FastAPI 异步后端提供 28 组 REST API，覆盖行情、K线、概念板块、板块轮动、异动监控、新闻信息流、模拟交易等场景。内置 Perception Pipeline 自动检测价格/成交量/资金流异常并聚合信号。React 前端提供 K线图表与实时看板。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                       │
│          (TanStack Query + Lightweight Charts)          │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / WebSocket
┌────────────────────────▼────────────────────────────────┐
│                   FastAPI Backend (:8000)                │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐  │
│  │ 28 Route │  │ Services │  │  Perception Pipeline  │  │
│  │ Modules  │→ │  Layer   │→ │  Sources → Detectors  │  │
│  └──────────┘  └────┬─────┘  │  → Aggregator         │  │
│                     │        └───────────────────────┘  │
│  ┌──────────────────▼──────────────────────────────┐    │
│  │           Repositories (SQLAlchemy 2.0)          │    │
│  └──────────────────┬──────────────────────────────┘    │
│                     │                                    │
│  ┌──────────────────▼──────────────────────────────┐    │
│  │             SQLite (WAL mode)                    │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
         ▲           ▲           ▲           ▲
    ┌────┘     ┌─────┘     ┌─────┘     ┌─────┘
 AKShare   TuShare Pro  Yahoo Fin  新浪财经/同花顺
```

## 快速开始

**1. 克隆并安装依赖**

```bash
git clone https://github.com/zinan92/quant-data-pipeline.git
cd quant-data-pipeline
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. 配置环境变量**

```bash
cp .env.example .env
# 编辑 .env，填入 TUSHARE_TOKEN（必填）
```

**3. 启动后端**

```bash
python -m uvicorn web.app:create_app --factory --port 8000
```

**4. 启动前端（可选）**

```bash
cd frontend && npm install && npm run dev
# 浏览器访问 http://localhost:5173
```

**5. Docker 部署（可选）**

```bash
docker compose up -d
# API: http://localhost:8090  前端: http://localhost:4173
```

## 功能一览

| 模块 | 说明 | 数据源 |
|------|------|--------|
| A股行情 | K线（日线/30分钟）、实时报价、均线指标 | AKShare, TuShare, 新浪 |
| 概念板块 | 概念涨幅 Top20、板块成分股、概念监控 | AKShare, 同花顺 |
| 板块轮动 | 行业/板块轮动分析 | TuShare |
| 美股 | 主要指数、科技股、中概股、AI 概念股 | Yahoo Finance |
| 加密货币 | 行情查询、WebSocket 实时推送 | 公开 API |
| 大宗商品 | 贵金属、能源等商品行情 | AKShare |
| 新闻信息流 | 财联社/同花顺/东方财富快讯、Twitter、RSS | AKShare, Twitter |
| 智能推送 | 关键词过滤、自选股异动提醒 | 内置规则引擎 |
| 异动监控 | 大笔买卖、涨跌停检测 | AKShare |
| Perception Pipeline | 多源信号检测与聚合（价格/量/资金流/关键词/叙事） | 全部数据源 |
| 自选股 | 自选股管理、分类、买入价跟踪 | 本地 SQLite |
| 模拟交易 | 纸盘买卖、持仓、收益计算 | 本地 SQLite |
| 选股器 | 条件筛选 A 股 | TuShare |
| 每日简报 | A股/美股结构化盘后简报脚本 | 全部数据源 |
| 定时任务 | APScheduler 自动刷新行情与 K 线 | — |

## API 参考

所有端点前缀为 `/api`。

| 路由前缀 | 说明 | 主要端点 |
|----------|------|----------|
| `/symbols` | 股票元数据 | `GET /` 列表 |
| `/candles` | K线数据 | `GET /{ticker}` |
| `/watchlist` | 自选股 | `GET /`, `POST /`, `DELETE /{id}` |
| `/realtime` | 实时行情 | `GET /prices` |
| `/index` | 大盘指数 | `GET /` |
| `/concepts` | 概念板块 | `GET /`, `GET /{code}` |
| `/concept-monitor` | 概念监控 v2 | `GET /top`, `GET /tracked` |
| `/sectors` | 行业板块 | `GET /` |
| `/us-stock` | 美股 | `GET /indexes`, `/tech`, `/china-adr`, `/ai`, `/quote/{symbol}`, `/kline/{symbol}` |
| `/crypto` | 加密货币 | `GET /`, WebSocket 实时流 |
| `/commodities` | 大宗商品 | `GET /` |
| `/news` | 新闻信息流 | `GET /latest`, `/source/{source}`, `/market-alerts` |
| `/simulated` | 模拟交易 | `POST /buy`, `POST /sell`, `GET /positions` |
| `/screener` | 选股器 | `POST /scan` |
| `/perception` | 感知信号 | `GET /signals`, `POST /scan` |
| `/decision` | 决策辅助 | `GET /`, `POST /` |
| `/earnings` | 财报日历 | `GET /` |
| `/evaluations` | 估值数据 | `GET /` |
| `/intel` | 情报对接 | `GET /` (对接 qualitative-data-pipeline) |
| `/health` | 健康检查 | `GET /` |
| `/status` | 系统状态 | `GET /` |
| `/tasks` | 任务管理 | `GET /`, `POST /trigger` |

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| Web 框架 | FastAPI | 0.110 |
| ORM | SQLAlchemy | 2.0 |
| 数据验证 | Pydantic | 2.6 |
| 定时任务 | APScheduler | 3.10 |
| HTTP 客户端 | httpx | 0.27 |
| 数据分析 | pandas + numpy | 2.2 / 1.26 |
| 限流 | slowapi | 0.1.9+ |
| 前端框架 | React + TypeScript | 18 |
| 状态管理 | TanStack Query | 5 |
| 图表 | Lightweight Charts | 5 |
| 构建工具 | Vite | — |
| 数据库 | SQLite (WAL) | — |
| 容器化 | Docker + Compose | — |

## 项目结构

```
quant-data-pipeline/
├── web/
│   └── app.py                  # FastAPI 应用工厂
├── src/
│   ├── api/                    # 28 个路由模块 (routes_*.py)
│   │   ├── router.py           # 路由注册
│   │   ├── dependencies.py     # 依赖注入
│   │   └── rate_limit.py       # 限流配置
│   ├── services/               # 业务逻辑层
│   │   ├── news/               # 新闻聚合 & 智能推送
│   │   ├── us_stock/           # 美股服务
│   │   ├── kline_service.py    # K线服务
│   │   ├── simulated_service.py# 模拟交易
│   │   ├── crypto_service.py   # 加密货币
│   │   └── ...                 # 70+ 服务模块
│   ├── perception/             # 感知管线
│   │   ├── pipeline.py         # 管线编排
│   │   ├── aggregator.py       # 信号聚合
│   │   ├── detectors/          # 检测器 (价格/量/资金流/关键词/叙事/技术面/异常)
│   │   ├── sources/            # 数据源适配 (AKShare/TuShare/新浪/新闻)
│   │   └── integration/        # 交易桥接 & 信号发布
│   ├── repositories/           # 数据访问层 (Repository 模式)
│   ├── models/                 # SQLAlchemy ORM 模型
│   ├── schemas/                # Pydantic 请求/响应模型
│   ├── tasks/                  # APScheduler 定时任务
│   ├── utils/                  # 工具函数 (指标计算/情绪分析/格式化)
│   ├── config.py               # Pydantic Settings
│   └── exceptions.py           # 自定义异常层级
├── frontend/                   # React + TypeScript 前端
│   ├── src/components/         # UI 组件
│   ├── src/hooks/              # 自定义 Hooks
│   └── src/types/              # TypeScript 类型
├── scripts/                    # 脚本工具 (110+ 文件)
│   ├── full_briefing.py        # A股每日简报
│   ├── us_briefing_v2.py       # 美股每日简报
│   └── ...
├── data/                       # SQLite 数据库 & CSV
├── tests/                      # pytest 测试
├── Dockerfile                  # 后端容器
├── docker-compose.yml          # 全栈编排
└── requirements.txt            # Python 依赖
```

## 配置

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `TUSHARE_TOKEN` | TuShare Pro API Token（必填） | — |
| `TUSHARE_POINTS` | TuShare 积分等级 | `120` |
| `TUSHARE_DELAY` | TuShare 请求间隔（秒） | `0.5` |
| `DATABASE_URL` | 数据库连接字符串 | `sqlite:///data/market.db` |
| `DEFAULT_SYMBOLS` | 默认自选股（逗号分隔） | `600519,601318,...` |
| `CANDLE_LOOKBACK` | K线回溯天数 | `200` |
| `ALLOW_ORIGINS` | CORS 允许的前端地址 | `http://localhost:5173` |
| `DAILY_REFRESH_CRON` | 每日刷新 cron 表达式 | `30 16 * * 1-5` |
| `SCHEDULER_TIMEZONE` | 调度时区 | `Asia/Shanghai` |
| `PARK_INTEL_URL` | qualitative-data-pipeline 地址 | `http://127.0.0.1:8001` |
| `ENABLE_CONCEPT_BOARDS` | 启用概念板块 | `true` |
| `ENABLE_INDUSTRY_LEVELS` | 启用多级行业分类 | `true` |

完整模板见 [`.env.example`](.env.example)。

## For AI Agents

### Structured Metadata

```yaml
name: quant-data-pipeline
description: Multi-market quantitative data platform with perception pipeline
version: 0.1.0
api_base_url: http://localhost:8000/api
capabilities:
  - A-share realtime quotes and klines
  - US stock quotes (Yahoo Finance)
  - Crypto market data and WebSocket streaming
  - Commodities pricing
  - News aggregation (CLS, THS, Sina, Twitter, RSS)
  - Concept/sector board monitoring
  - Sector rotation analysis
  - Anomaly detection (price, volume, flow)
  - Perception pipeline (multi-source signal aggregation)
  - Simulated trading (paper trading)
  - Stock screener
  - Daily market briefing scripts
install_command: pip install -r requirements.txt
start_command: python -m uvicorn web.app:create_app --factory --port 8000
input_format: JSON (query params for GET, JSON body for POST)
output_format: JSON
endpoints:
  health: GET /api/health
  symbols: GET /api/symbols
  klines: GET /api/candles/{ticker}
  realtime: GET /api/realtime/prices
  watchlist: GET /api/watchlist
  us_stock: GET /api/us-stock/indexes
  crypto: GET /api/crypto
  commodities: GET /api/commodities
  news: GET /api/news/latest
  perception: POST /api/perception/scan
  simulated_buy: POST /api/simulated/buy
  screener: POST /api/screener/scan
  decision: GET /api/decision
```

### Agent Workflow Example

```python
import httpx

BASE = "http://localhost:8000/api"

async def agent_workflow():
    async with httpx.AsyncClient(timeout=30) as c:
        # 1. 健康检查
        health = (await c.get(f"{BASE}/health")).json()

        # 2. 获取自选股列表
        watchlist = (await c.get(f"{BASE}/watchlist")).json()

        # 3. 获取某只股票 K 线
        klines = (await c.get(f"{BASE}/candles/600519")).json()

        # 4. 触发感知管线扫描
        signals = (await c.post(f"{BASE}/perception/scan")).json()

        # 5. 获取最新新闻
        news = (await c.get(f"{BASE}/news/latest")).json()

        return {"watchlist": watchlist, "klines": klines, "signals": signals, "news": news}
```

## 相关项目

| 项目 | 说明 | 端口 | 仓库 |
|------|------|------|------|
| **qualitative-data-pipeline** | 定性数据管线（新闻情绪、社交媒体、宏观分析） | 8001 | [zinan92/qualitative-data-pipeline](https://github.com/zinan92/qualitative-data-pipeline) |

两个管线通过 `PARK_INTEL_URL` 环境变量对接，`/api/intel` 端点从 qualitative-data-pipeline 拉取定性信号。

## License

MIT
