# 多金融市场监控平台

实时监控 A股、美股、信息流，整合多数据源的综合金融监控系统。

## 功能特性

### 📈 A股监控
- ✅ **实时数据更新**：交易时间内自动轮询
- 📊 **多维度K线**：日线、30分钟线，可配置均线
- 🎯 **概念板块监控**：涨幅Top20、自选概念实时追踪
- ⚡ **盘口异动**：大笔买入/卖出、涨停/跌停实时提醒

### 🇺🇸 美股监控
- 📊 **主要指数**：S&P 500、道琼斯、纳斯达克、VIX
- 🏢 **科技股**：AAPL、MSFT、GOOGL、NVDA、META、TSLA
- 🇨🇳 **中概股**：阿里、拼多多、京东、百度、蔚来
- 🤖 **AI概念**：NVDA、AMD、PLTR、AI

### 📰 信息流
- 🇨🇳 **中文快讯**：财联社、同花顺、东方财富
- 🇺🇸 **英文信息**：Twitter、RSS feeds
- 🔔 **智能推送**：关键词过滤、自选股提醒

## 技术栈

### 后端
- **FastAPI** - 异步 Web 框架
- **AKShare** - A股数据
- **TuShare** - 历史数据
- **Yahoo Finance** - 美股数据
- **SQLAlchemy** - 数据库 ORM
- **APScheduler** - 定时任务

### 前端
- **React + TypeScript**
- **TanStack Query** - 数据缓存
- **Lightweight Charts** - K线图表
- **Vite** - 构建工具

## 快速开始

### 1. 安装依赖

```bash
# 后端
cd ashare
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 前端
cd frontend
npm install
```

### 2. 启动服务

```bash
# 后端 (端口 8000)
uvicorn web.app:app --host 0.0.0.0 --port 8000

# 前端 (端口 5173)
cd frontend && npm run dev
```

## API 端点

### A股数据
| 端点 | 说明 |
|------|------|
| `GET /api/symbols` | 股票列表 |
| `GET /api/candles/{ticker}` | K线数据 |
| `GET /api/concepts` | 概念板块 |
| `GET /api/watchlist` | 自选股 |
| `GET /api/realtime/prices` | 实时行情 |

### 美股数据 `/api/us-stock/`
| 端点 | 说明 |
|------|------|
| `GET /indexes` | 美股指数 |
| `GET /china-adr` | 中概股 |
| `GET /tech` | 科技股 |
| `GET /ai` | AI概念股 |
| `GET /quote/{symbol}` | 单股报价 |
| `GET /kline/{symbol}` | K线数据 |

### 信息流 `/api/news/`
| 端点 | 说明 |
|------|------|
| `GET /latest` | 最新快讯 |
| `GET /source/{source}` | 指定数据源 (cls/ths/sina) |
| `GET /market-alerts` | 异动摘要 |
| `GET /market-alerts/{type}` | 指定类型异动 |
| `GET /twitter/search?q=...` | Twitter搜索 |
| `GET /rss?url=...` | RSS feed |
| `POST /smart-alerts/scan` | 智能推送扫描 |

## 数据源

| 数据源 | 用途 | 说明 |
|--------|------|------|
| **TuShare** | A股历史数据 | 需要 token |
| **AKShare** | A股实时/概念 | 免费 |
| **新浪财经** | A股实时行情 | 免费 |
| **Yahoo Finance** | 美股数据 | 免费 |
| **财联社** | 中文快讯 | 通过 AKShare |
| **同花顺** | 中文快讯 | 通过 AKShare |
| **Twitter** | 英文信息 | 需要 bird CLI |

## 项目结构

```
ashare/
├── src/
│   ├── api/              # API 路由
│   │   ├── routes_news.py        # 信息流
│   │   ├── routes_us_stock.py    # 美股
│   │   └── ...
│   ├── services/         # 业务逻辑
│   │   ├── news/                 # 信息流服务
│   │   │   ├── news_service.py
│   │   │   ├── alerts_service.py
│   │   │   ├── smart_alerts.py
│   │   │   └── external_service.py
│   │   ├── us_stock/             # 美股服务
│   │   └── ...
│   └── models/           # 数据模型
├── frontend/             # React 前端
├── scripts/              # 脚本工具
│   └── market_briefing.py
├── data/                 # 数据存储
└── docs/                 # 文档
```

## 智能推送

系统内置关键词规则，自动监控：
- **AI热点**：DeepSeek, OpenAI, ChatGPT, Claude
- **芯片半导体**：英伟达, NVIDIA, 芯片, 光刻机
- **新能源**：特斯拉, 宁德时代, 比亚迪, 锂电池
- **贵金属**：黄金, 白银, gold, silver

## License

MIT
