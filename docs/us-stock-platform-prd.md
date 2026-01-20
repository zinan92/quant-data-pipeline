# 美股数据平台 PRD (产品需求文档)

> 基于现有 A股数据平台架构，构建美股版本数据分析系统

---

## 一、项目概述

### 1.1 项目背景

现有 A股数据平台已具备完整的功能体系：
- K线数据获取与存储
- 实时行情展示
- 自选股管理
- 投资组合分析
- 行业/概念板块分析

基于该架构的高复用性，计划开发美股版本，覆盖美股市场的数据分析需求。

### 1.2 项目目标

| 目标 | 描述 |
|-----|------|
| **功能对标** | 实现与 A股平台对等的核心功能 |
| **架构复用** | 最大化复用现有代码，降低开发成本 |
| **数据合规** | 使用开放/免费数据源，确保合规性 |
| **独立部署** | 支持独立运行，不影响 A股系统 |

### 1.3 目标用户

- 个人投资者：关注美股市场
- 量化研究者：需要历史数据进行回测
- 开发者：学习金融数据系统架构

---

## 二、现有架构分析

### 2.1 A股平台技术栈

| 层级 | 技术选型 | 说明 |
|-----|---------|------|
| **后端框架** | FastAPI | 异步高性能 API |
| **ORM** | SQLAlchemy 2.0 | 类型安全的数据库操作 |
| **数据库** | SQLite | 轻量级，可升级 PostgreSQL |
| **数据源** | Tushare Pro | A股专业数据 |
| **实时行情** | 新浪财经 | HTTP 轮询 |
| **任务调度** | APScheduler | 定时数据更新 |
| **前端框架** | React 18 + TypeScript | 类型安全的 UI |
| **构建工具** | Vite | 快速开发构建 |
| **图表库** | lightweight-charts + ECharts | K线 + 仪表板 |
| **状态管理** | React Query | 服务端状态缓存 |

### 2.2 核心模块清单

```
src/
├── api/                          # API 路由层 (18个模块)
│   ├── routes_candles.py         # K线数据
│   ├── routes_watchlist.py       # 自选股管理
│   ├── routes_boards.py          # 板块成分
│   ├── routes_realtime.py        # 实时行情
│   ├── routes_concepts.py        # 概念板块
│   └── ...
├── services/                     # 业务逻辑层
│   ├── tushare_data_provider.py  # 数据源适配器
│   ├── kline_service.py          # K线服务
│   ├── kline_updater.py          # 数据更新器
│   ├── kline_scheduler.py        # 调度器
│   └── ...
├── models.py                     # 数据模型
├── database.py                   # 数据库连接
└── config.py                     # 配置管理

frontend/src/
├── components/                   # React 组件 (29个)
│   ├── WatchlistView.tsx         # 自选股列表
│   ├── PortfolioDashboard.tsx    # 投资组合分析
│   ├── charts/KlineChart.tsx     # K线图组件
│   └── ...
├── hooks/                        # 自定义 Hooks
├── types/                        # TypeScript 类型
└── utils/                        # 工具函数
```

### 2.3 架构复用度评估

| 模块 | 复用度 | 改动说明 |
|-----|-------|---------|
| **数据库设计** | 90% | 删除 A股特定字段 (industry_lv1/2/3, concepts) |
| **API 路由模式** | 95% | REST 设计完全通用 |
| **K线服务** | 95% | 仅改数据源调用 |
| **前端组件** | 80% | 调整行业筛选、类型定义 |
| **图表组件** | 100% | 完全通用 |
| **数据源层** | 10% | 需重写，替换为美股 API |
| **调度器** | 90% | 改交易时间配置 |

---

## 三、美股数据源调研

### 3.1 数据源对比

| 数据源 | 免费限制 | 历史数据 | 实时数据 | 基本面 | 推荐度 |
|-------|---------|---------|---------|-------|-------|
| **yfinance** | 无限制 | 全量 | 延迟15分钟 | 丰富 | ⭐⭐⭐⭐⭐ |
| **Finnhub** | 60次/分钟 | 有限 | 实时 | 丰富 | ⭐⭐⭐⭐ |
| **Alpaca** | 200次/分钟 | 7年 | 仅IEX | 基础 | ⭐⭐⭐⭐ |
| **Alpha Vantage** | 25次/天 | 全量 | 实时 | 丰富 | ⭐⭐ |
| **Polygon.io** | 5次/分钟 | 全量 | 实时 | 丰富 | ⭐⭐ |

### 3.2 推荐方案

**主数据源: yfinance**
- 完全免费，无 API 密钥要求
- 历史 K线数据完整 (支持分钟/日/周/月级别)
- 基本面数据丰富 (PE/PB/市值/行业)
- Python 原生库，集成简单
- 社区活跃，持续维护

**补充数据源: Finnhub**
- 实时行情 (60次/分钟足够轮询)
- 公司新闻和情绪数据
- 财报日历和预期

### 3.3 数据源详情

#### yfinance

```python
# 安装
pip install yfinance

# 使用示例
import yfinance as yf

# 获取股票信息
ticker = yf.Ticker("AAPL")
info = ticker.info  # 基本面数据
hist = ticker.history(period="2y", interval="1d")  # K线数据

# 支持的时间周期
# period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
# interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo
```

**数据字段**:
- 行情: open, high, low, close, volume
- 基本面: marketCap, trailingPE, priceToBook, dividendYield
- 分类: sector, industry, exchange
- 公司: longName, website, fullTimeEmployees

#### Finnhub

```python
# 安装
pip install finnhub-python

# 使用示例
import finnhub
client = finnhub.Client(api_key="your_api_key")

# 实时报价
quote = client.quote("AAPL")
# 返回: {'c': 150.0, 'h': 151.0, 'l': 149.0, 'o': 149.5, ...}

# 公司资料
profile = client.company_profile2(symbol="AAPL")
```

**免费额度**:
- 60 次/分钟 API 调用
- 实时报价
- 公司新闻 (1年)
- 财报日历 (1个月)

---

## 四、功能需求

### 4.1 核心功能 (P0)

#### 4.1.1 股票列表管理

| 功能 | 描述 | 对标 A股 |
|-----|------|---------|
| 股票搜索 | 按代码/名称模糊搜索 | ✅ 复用 |
| 股票列表 | S&P 500 / NASDAQ 100 成分股 | ✅ 复用 |
| 行业分类 | GICS 行业分类 (11大行业) | ⚠️ 改造 |
| 基本面筛选 | 按市值/PE/PB 筛选 | ✅ 复用 |

#### 4.1.2 K线数据

| 功能 | 描述 | 对标 A股 |
|-----|------|---------|
| 日K线 | 历史日线数据 (2年+) | ✅ 复用 |
| 周K线 | 历史周线数据 | ✅ 复用 |
| 月K线 | 历史月线数据 | ✅ 复用 |
| 分钟K线 | 30分钟/5分钟级别 | ✅ 复用 |
| 技术指标 | MA5/10/20/50, MACD | ✅ 复用 |

#### 4.1.3 自选股管理

| 功能 | 描述 | 对标 A股 |
|-----|------|---------|
| 添加自选 | 添加股票到自选列表 | ✅ 复用 |
| 移除自选 | 从自选列表移除 | ✅ 复用 |
| 虚拟持仓 | 按 $10,000 模拟买入 | ✅ 复用 (改币种) |
| 批量管理 | 批量添加/清空 | ✅ 复用 |

#### 4.1.4 投资组合分析

| 功能 | 描述 | 对标 A股 |
|-----|------|---------|
| 净值曲线 | 组合历史净值走势 | ✅ 复用 |
| 行业配置 | 按 GICS 行业分布 | ⚠️ 改造 |
| 涨跌榜 | Top 5 涨/跌股票 | ✅ 复用 |
| 盈亏分布 | 收益率分布直方图 | ✅ 复用 |

### 4.2 扩展功能 (P1)

| 功能 | 描述 | 优先级 |
|-----|------|-------|
| 实时行情 | 基于 Finnhub 的实时报价 | P1 |
| 盘前盘后 | Pre-market / After-hours 数据 | P1 |
| 财报日历 | Earnings Calendar 展示 | P1 |
| 股息信息 | 分红历史和股息率 | P1 |

### 4.3 未来功能 (P2)

| 功能 | 描述 | 优先级 |
|-----|------|-------|
| ETF 支持 | SPY, QQQ 等 ETF 数据 | P2 |
| 期权数据 | 期权链展示 | P2 |
| 新闻情绪 | 基于 Finnhub 的新闻分析 | P2 |
| 多币种 | 支持港股 (HKD) | P2 |

---

## 五、技术设计

### 5.1 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (React + TypeScript)                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ WatchlistView│ │PortfolioDash│ │ KlineChart  │ │StockDetail│ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/REST
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        后端 (FastAPI)                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │routes_klines│ │routes_watch │ │routes_sectors│ │routes_real│ │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └─────┬─────┘ │
│         └────────────────┼───────────────┴───────────────┘       │
│                          ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Service Layer                          │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │  │
│  │  │KlineService │  │WatchlistSvc │  │SchedulerSvc │       │  │
│  │  └──────┬──────┘  └─────────────┘  └─────────────┘       │  │
│  └─────────┼─────────────────────────────────────────────────┘  │
│            ▼                                                     │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Data Provider Layer                     │  │
│  │  ┌─────────────────┐      ┌─────────────────┐            │  │
│  │  │ YFinanceProvider│      │ FinnhubProvider │            │  │
│  │  │   (历史数据)     │      │   (实时行情)     │            │  │
│  │  └────────┬────────┘      └────────┬────────┘            │  │
│  └───────────┼────────────────────────┼──────────────────────┘  │
└──────────────┼────────────────────────┼──────────────────────────┘
               │                        │
               ▼                        ▼
        ┌────────────┐          ┌────────────┐
        │  Yahoo     │          │  Finnhub   │
        │  Finance   │          │    API     │
        └────────────┘          └────────────┘
               │
               ▼
        ┌────────────┐
        │  SQLite    │
        │  Database  │
        └────────────┘
```

### 5.2 数据模型设计

#### 5.2.1 股票元数据表 (symbol_metadata)

```python
class SymbolMetadata(Base):
    __tablename__ = "symbol_metadata"

    # 基础信息
    ticker: str           # 主键, 如 "AAPL"
    name: str             # "Apple Inc."
    market: str           # "US_STOCK"
    exchange: str         # "NASDAQ", "NYSE"

    # GICS 行业分类 (替代 A股的 industry_lv1/2/3)
    sector: str           # "Information Technology" (11大行业)
    industry: str         # "Technology Hardware, Storage & Peripherals"

    # 估值指标
    total_mv: float       # 市值 (美元)
    pe_ratio: float       # 市盈率 TTM
    pb_ratio: float       # 市净率

    # 其他信息
    currency: str         # "USD"
    website: str          # 公司官网
    employees: int        # 员工数

    # 时间戳
    updated_at: datetime  # 最后更新时间
```

#### 5.2.2 K线数据表 (klines)

```python
class Kline(Base):
    """K线数据表 - 完全复用 A股设计"""
    __tablename__ = "klines"

    id: int               # 主键
    symbol_type: str      # "STOCK", "ETF", "INDEX"
    symbol_code: str      # "AAPL"
    symbol_name: str      # "Apple Inc."
    timeframe: str        # "DAY", "WEEK", "MONTH", "MINS_30"

    # OHLCV
    trade_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    amount: Decimal       # 成交额

    # 技术指标 (预计算存储)
    ma5: float
    ma10: float
    ma20: float
    ma50: float
    dif: float            # MACD DIF
    dea: float            # MACD DEA
    macd: float           # MACD 柱
```

#### 5.2.3 自选股表 (watchlist)

```python
class Watchlist(Base):
    """自选股表 - 完全复用 A股设计"""
    __tablename__ = "watchlist"

    id: int
    ticker: str           # 股票代码 (唯一)
    added_at: datetime    # 添加时间
    purchase_price: float # 虚拟买入价格
    purchase_date: datetime
    shares: float         # 持股数 (基于 $10,000 投资)
```

### 5.3 API 设计

#### 5.3.1 K线接口

```
GET /api/klines/{symbol}
    ?timeframe=day|week|month|30m
    &limit=120

Response:
{
    "symbol": {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "sector": "Information Technology",
        "pe_ratio": 28.5,
        "total_mv": 2800000000000
    },
    "klines": [
        {
            "date": "2024-01-15",
            "open": 185.50,
            "high": 187.20,
            "low": 184.80,
            "close": 186.90,
            "volume": 52000000,
            "ma5": 185.2,
            "ma10": 184.5,
            "ma20": 183.0
        }
    ]
}
```

#### 5.3.2 自选股接口

```
# 获取自选股列表
GET /api/watchlist

# 添加到自选
POST /api/watchlist
Body: { "ticker": "AAPL" }

# 移除自选
DELETE /api/watchlist/{ticker}

# 投资组合历史
GET /api/watchlist/portfolio/history

# 投资组合分析
GET /api/watchlist/analytics
```

#### 5.3.3 股票搜索

```
GET /api/symbols/search?q=apple

Response:
{
    "results": [
        {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
        {"ticker": "APLE", "name": "Apple Hospitality REIT", "sector": "Real Estate"}
    ]
}
```

### 5.4 数据源适配器

```python
# src/services/yfinance_provider.py

class YFinanceDataProvider:
    """美股数据提供者 - 基于 yfinance"""

    def fetch_candles(
        self,
        symbol: str,
        period: str = "2y",
        interval: str = "1d"
    ) -> pd.DataFrame:
        """
        获取 K线数据

        Args:
            symbol: 股票代码 (AAPL, MSFT, etc.)
            period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
            interval: 1m, 5m, 15m, 30m, 60m, 1d, 1wk, 1mo

        Returns:
            DataFrame: timestamp, open, high, low, close, volume
        """
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        df = df.reset_index()
        df = df.rename(columns={
            "Date": "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })

        return df[["timestamp", "open", "high", "low", "close", "volume"]]

    def fetch_stock_info(self, symbol: str) -> dict:
        """获取股票基本信息"""
        ticker = yf.Ticker(symbol)
        info = ticker.info

        return {
            "ticker": symbol,
            "name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "total_mv": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "currency": "USD",
            "exchange": info.get("exchange"),
            "website": info.get("website"),
            "employees": info.get("fullTimeEmployees"),
        }

    def fetch_sp500_list(self) -> list[str]:
        """获取 S&P 500 成分股列表"""
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        return tables[0]["Symbol"].tolist()

    def fetch_nasdaq100_list(self) -> list[str]:
        """获取 NASDAQ 100 成分股列表"""
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = pd.read_html(url)
        return tables[4]["Ticker"].tolist()
```

### 5.5 调度器配置

```python
# 美股交易时间配置
class USMarketScheduler:
    """美股市场调度器"""

    # 美股交易时间 (Eastern Time)
    MARKET_OPEN = time(9, 30)   # 9:30 AM ET
    MARKET_CLOSE = time(16, 0)  # 4:00 PM ET
    TIMEZONE = "America/New_York"

    # 定时更新配置
    # 每个交易日 16:30 ET 执行 (收盘 30 分钟后)
    DAILY_UPDATE_CRON = "30 16 * * 1-5"

    def is_trading_day(self, date: datetime) -> bool:
        """判断是否为交易日"""
        # 周末不交易
        if date.weekday() >= 5:
            return False
        # TODO: 添加美股节假日判断
        return True

    def is_trading_hours(self) -> bool:
        """判断是否在交易时段"""
        import pytz
        et = pytz.timezone(self.TIMEZONE)
        now = datetime.now(et)

        if not self.is_trading_day(now):
            return False

        current_time = now.time()
        return self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE
```

---

## 六、项目结构

### 6.1 推荐方案: 独立项目

```
us-stock-monitor/
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py              # 路由注册
│   │   ├── dependencies.py        # 依赖注入
│   │   ├── routes_klines.py       # K线接口
│   │   ├── routes_watchlist.py    # 自选股接口
│   │   ├── routes_symbols.py      # 股票搜索
│   │   ├── routes_sectors.py      # 行业分类 (新)
│   │   └── routes_realtime.py     # 实时行情
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── yfinance_provider.py   # yfinance 数据源 (新)
│   │   ├── finnhub_provider.py    # Finnhub 数据源 (新)
│   │   ├── kline_service.py       # K线服务 (复用)
│   │   ├── kline_updater.py       # 数据更新 (复用)
│   │   └── scheduler.py           # 调度器 (改造)
│   │
│   ├── models.py                  # 数据模型 (简化)
│   ├── database.py                # 数据库连接 (复用)
│   ├── config.py                  # 配置管理 (改造)
│   └── schemas/
│       └── base.py                # Pydantic 模型
│
├── web/
│   └── app.py                     # FastAPI 应用入口
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── WatchlistView.tsx      # 复用
│   │   │   ├── PortfolioDashboard.tsx # 复用
│   │   │   ├── charts/
│   │   │   │   └── KlineChart.tsx     # 复用
│   │   │   ├── SectorFilter.tsx       # 新增 (替代行业筛选)
│   │   │   └── ...
│   │   ├── hooks/
│   │   │   ├── useCandles.ts          # 复用
│   │   │   ├── useWatchlist.ts        # 复用
│   │   │   └── useRealtimePrice.ts    # 复用
│   │   ├── types/
│   │   │   └── index.ts               # 类型定义 (改造)
│   │   └── utils/
│   │       ├── api.ts                 # API 客户端 (复用)
│   │       └── indicators.ts          # 技术指标 (复用)
│   │
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── scripts/
│   ├── init_sp500.py              # 初始化 S&P 500 数据
│   ├── init_nasdaq100.py          # 初始化 NASDAQ 100 数据
│   └── update_klines.py           # 手动更新 K线
│
├── data/
│   └── us_market.db               # SQLite 数据库
│
├── tests/
│   ├── test_yfinance_provider.py
│   ├── test_kline_service.py
│   └── test_api.py
│
├── requirements.txt
├── .env.example
└── README.md
```

### 6.2 依赖清单

```txt
# requirements.txt

# Web 框架
fastapi==0.110.0
uvicorn==0.29.0
python-multipart==0.0.9

# 数据库
sqlalchemy==2.0.29
aiosqlite==0.20.0

# 数据源
yfinance==0.2.36
finnhub-python==2.4.19

# 数据处理
pandas==2.2.1
numpy==1.26.4

# 调度
apscheduler==3.10.4

# 工具
pydantic==2.6.4
pydantic-settings==2.2.1
python-dotenv==1.0.1
pytz==2024.1

# 开发
pytest==8.1.1
httpx==0.27.0
```

---

## 七、开发计划

### 7.1 里程碑

| 阶段 | 内容 | 交付物 |
|-----|------|-------|
| **M1: 基础架构** | 项目初始化、数据源接入 | yfinance_provider, 基础 API |
| **M2: 核心功能** | K线、自选股、投资组合 | 完整后端 API |
| **M3: 前端适配** | 组件迁移、UI 调整 | 可运行的前端 |
| **M4: 优化完善** | 实时行情、性能优化 | 生产可用版本 |

### 7.2 任务分解

#### M1: 基础架构

- [ ] 创建项目结构
- [ ] 配置 SQLite 数据库
- [ ] 实现 YFinanceDataProvider
- [ ] 实现 FinnhubProvider (可选)
- [ ] 编写数据模型
- [ ] 初始化 S&P 500 股票列表

#### M2: 核心功能

- [ ] K线数据获取接口
- [ ] K线数据存储和更新
- [ ] 自选股 CRUD 接口
- [ ] 投资组合分析接口
- [ ] 股票搜索接口
- [ ] GICS 行业分类接口

#### M3: 前端适配

- [ ] 迁移 KlineChart 组件
- [ ] 迁移 WatchlistView 组件
- [ ] 迁移 PortfolioDashboard 组件
- [ ] 实现 SectorFilter (替代行业筛选)
- [ ] 调整类型定义
- [ ] 配置 API 代理

#### M4: 优化完善

- [ ] 实时行情轮询
- [ ] 数据更新调度器
- [ ] 错误处理和日志
- [ ] 性能优化
- [ ] 文档编写

### 7.3 工作量估算

| 模块 | 工作量 | 说明 |
|-----|-------|------|
| 数据源层 | 3-4天 | yfinance + finnhub 适配 |
| 数据模型 | 1天 | 简化 A股模型 |
| API 路由 | 1-2天 | 复用 + 改造 |
| 调度器 | 0.5天 | 改交易时间 |
| 前端适配 | 2-3天 | 组件迁移 + 调整 |
| 测试联调 | 1-2天 | 端到端测试 |
| **总计** | **8-12天** | |

---

## 八、风险与应对

### 8.1 技术风险

| 风险 | 影响 | 应对措施 |
|-----|------|---------|
| yfinance 被限流 | 数据获取失败 | 添加重试机制、降低请求频率 |
| yfinance API 变更 | 功能异常 | 监控版本更新、预留适配层 |
| 实时数据延迟 | 用户体验差 | 明确标注延迟时间、考虑付费数据源 |

### 8.2 合规风险

| 风险 | 影响 | 应对措施 |
|-----|------|---------|
| 数据使用条款 | 法律风险 | 仅用于个人研究、不商业化 |
| 数据再分发 | 违反条款 | 不提供数据下载、仅展示 |

### 8.3 运维风险

| 风险 | 影响 | 应对措施 |
|-----|------|---------|
| 数据库容量 | 存储不足 | 定期清理历史数据、升级 PostgreSQL |
| 调度器故障 | 数据不更新 | 添加监控告警、手动更新脚本 |

---

## 九、参考资源

### 9.1 数据源文档

- [yfinance GitHub](https://github.com/ranaroussi/yfinance)
- [yfinance 官方文档](https://ranaroussi.github.io/yfinance/)
- [Finnhub API 文档](https://finnhub.io/docs/api)
- [Alpaca 市场数据 API](https://docs.alpaca.markets/docs/about-market-data-api)

### 9.2 技术参考

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 文档](https://docs.sqlalchemy.org/)
- [React Query 文档](https://tanstack.com/query/latest)
- [lightweight-charts 文档](https://tradingview.github.io/lightweight-charts/)

### 9.3 GICS 行业分类

| 代码 | 行业 (Sector) |
|-----|--------------|
| 10 | Energy (能源) |
| 15 | Materials (原材料) |
| 20 | Industrials (工业) |
| 25 | Consumer Discretionary (可选消费) |
| 30 | Consumer Staples (必需消费) |
| 35 | Health Care (医疗保健) |
| 40 | Financials (金融) |
| 45 | Information Technology (信息技术) |
| 50 | Communication Services (通信服务) |
| 55 | Utilities (公用事业) |
| 60 | Real Estate (房地产) |

---

## 十、附录

### A. 环境变量配置

```bash
# .env.example

# 数据库
DATABASE_URL=sqlite:///data/us_market.db

# Finnhub (可选，用于实时行情)
FINNHUB_API_KEY=your_api_key_here

# 调度器
SCHEDULER_TIMEZONE=America/New_York
DAILY_UPDATE_CRON=30 16 * * 1-5

# 前端
VITE_API_BASE=http://localhost:8000
```

### B. 快速启动

```bash
# 1. 克隆项目
git clone https://github.com/yourname/us-stock-monitor.git
cd us-stock-monitor

# 2. 安装依赖
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 3. 初始化数据
python scripts/init_sp500.py

# 4. 启动后端
uvicorn web.app:app --reload --port 8000

# 5. 启动前端
cd frontend && npm run dev
```

---

**文档版本**: v1.0
**创建日期**: 2026-01-09
**最后更新**: 2026-01-09
