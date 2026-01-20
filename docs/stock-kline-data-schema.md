# 股票K线数据架构设计

## 概述

本文档描述股票K线数据的完整生命周期：获取、存储、更新、展示。

```
┌─────────────────────────────────────────────────────────────────────┐
│                          数据流架构                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   东方财富    │    │   新浪财经    │    │   同花顺     │          │
│  │  (日线数据)   │    │  (30m数据)   │    │  (实时价格)  │          │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘          │
│         │                   │                   │                   │
│         ▼                   ▼                   │                   │
│  ┌─────────────────────────────────────┐       │                   │
│  │         KlineUpdater (后端)          │       │                   │
│  │  - 定时任务调度                      │       │                   │
│  │  - 数据标准化                        │       │                   │
│  │  - 批量写入数据库                    │       │                   │
│  └──────────────┬──────────────────────┘       │                   │
│                 │                               │                   │
│                 ▼                               │                   │
│  ┌─────────────────────────────────────┐       │                   │
│  │         SQLite (klines表)            │       │                   │
│  │  - 日线数据                          │       │                   │
│  │  - 30分钟数据                        │       │                   │
│  │  - 指数/概念/股票                    │       │                   │
│  └──────────────┬──────────────────────┘       │                   │
│                 │                               │                   │
│                 ▼                               ▼                   │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                    FastAPI (后端)                        │       │
│  │  /api/candles/{ticker}  ─── 读取数据库                  │       │
│  │  /api/realtime/prices   ─── 代理转发实时价格             │       │
│  └──────────────┬──────────────────────────────────────────┘       │
│                 │                                                   │
│                 ▼                                                   │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                    前端 (React)                          │       │
│  │  - K线图表 (Lightweight Charts)                         │       │
│  │  - 实时价格轮询 (60秒)                                  │       │
│  └─────────────────────────────────────────────────────────┘       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. 数据存储

### 1.1 数据库表结构

```sql
CREATE TABLE klines (
    id INTEGER PRIMARY KEY,
    symbol_type VARCHAR(7) NOT NULL,    -- STOCK / INDEX / CONCEPT
    symbol_code VARCHAR(16) NOT NULL,   -- 6位代码: 000001
    symbol_name VARCHAR(64),            -- 股票名称
    timeframe VARCHAR(7) NOT NULL,      -- DAY / MINS_30
    trade_time VARCHAR(32) NOT NULL,    -- ISO格式: 2026-01-06 / 2026-01-06 10:30:00
    open FLOAT NOT NULL,
    high FLOAT NOT NULL,
    low FLOAT NOT NULL,
    close FLOAT NOT NULL,
    volume FLOAT NOT NULL,
    amount FLOAT NOT NULL,
    dif FLOAT,                          -- MACD指标 (可选)
    dea FLOAT,
    macd FLOAT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,

    UNIQUE (symbol_type, symbol_code, timeframe, trade_time)
);
```

### 1.2 数据量估算

| 类型 | 数量 | 日线记录/天 | 30m记录/天 |
|------|------|------------|-----------|
| 股票 | ~5,500只 | 5,500 | 44,000 (8根/只) |
| 指数 | ~10只 | 10 | 80 |
| 概念 | ~100只 | 100 | 800 |

**每日新增**: 约 5,610 条日线 + 44,880 条30分钟线

**历史数据存储** (假设保留1年):
- 日线: 5,610 × 250天 ≈ 140万条
- 30分钟: 44,880 × 250天 ≈ 1,100万条

---

## 2. 数据获取

### 2.1 数据源

| 数据类型 | 数据源 | API | 限制 |
|---------|-------|-----|------|
| 股票日线 | 东方财富 | EastMoneyKlineProvider | 无明显限制 |
| 股票30分钟 | 新浪财经 | SinaKlineProvider | ~100只/批 |
| 指数日线 | Tushare | TushareClient | 需要积分 |
| 指数30分钟 | 新浪财经 | SinaKlineProvider | 无限制 |
| 概念日线 | 同花顺 | ThsKlineProvider | 需要headers |
| 概念30分钟 | 同花顺 | ThsKlineProvider | 需要headers |
| 实时价格 | 新浪财经 | hq.sinajs.cn | 3-5秒延迟 |

### 2.2 数据格式标准化

所有外部数据进入系统前必须标准化:

```python
# 内部统一格式
{
    "symbol_type": "STOCK",           # STOCK / INDEX / CONCEPT
    "symbol_code": "000001",          # 6位代码
    "symbol_name": "平安银行",
    "timeframe": "DAY",               # DAY / MINS_30
    "trade_time": "2026-01-06",       # 日线: YYYY-MM-DD
                                      # 30m: YYYY-MM-DD HH:MM:SS
    "open": 10.50,
    "high": 10.80,
    "low": 10.45,
    "close": 10.75,
    "volume": 12345678,
    "amount": 135000000
}
```

---

## 3. 更新策略

### 3.1 更新时间表

```
┌────────────────────────────────────────────────────────────────────┐
│                        交易日时间线                                 │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  09:30                           15:00    15:30                    │
│    │                               │        │                      │
│    ├─────── 上午盘 ────┬─── 午休 ──┼─ 下午盘 ┤                      │
│    │                   │           │        │                      │
│ 开盘                 11:30       13:00    收盘                     │
│                                                                    │
│  ════════════════════════════════════════════════════════════════  │
│                                                                    │
│  自选股更新 (盘中):                                                 │
│    10:00, 10:30, 11:00, 11:30, 13:30, 14:00, 14:30, 15:00          │
│    └─ 日线 + 30分钟                                                │
│                                                                    │
│  全市场更新 (收盘后):                                               │
│    15:30 ─── 全量股票日线 + 30分钟                                  │
│                                                                    │
│  其他任务:                                                         │
│    00:01 ─── 交易日历更新                                          │
│    周日 00:00 ─── 清理1年前的旧数据                                 │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### 3.2 更新任务详情

| 任务ID | 名称 | 触发时间 | 范围 | 预计耗时 |
|--------|------|---------|------|---------|
| `30m_update` | 盘中30分钟更新 | 每30分钟 | 自选股 (~100只) | <1分钟 |
| `daily_update` | 每日收盘更新 | 15:30 | 自选股 + 指数 + 概念 | ~5分钟 |
| `market_daily_update` | 全市场日线更新 | 15:30 | 全部股票 (~5500只) | ~15分钟 |
| `market_30m_update` | 全市场30分钟更新 | 15:30 | 全部股票 (~5500只) | ~30分钟 |
| `calendar_update` | 交易日历更新 | 00:01 | - | <1分钟 |
| `cleanup` | 旧数据清理 | 周日 00:00 | - | ~5分钟 |

### 3.3 更新逻辑

```python
# 伪代码: 全市场更新流程

async def update_all_stocks():
    """收盘后更新全市场股票"""

    # 1. 获取所有股票代码
    all_tickers = get_all_stock_tickers()  # ~5500只

    # 2. 分批更新日线 (东方财富)
    for batch in chunks(all_tickers, size=100):
        for ticker in batch:
            klines = eastmoney.fetch_daily(ticker, limit=1)  # 只取最新1条
            save_to_db(klines)
        await asyncio.sleep(0.5)  # 限速

    # 3. 分批更新30分钟 (新浪财经)
    for batch in chunks(all_tickers, size=50):
        for ticker in batch:
            klines = sina.fetch_30m(ticker, limit=8)  # 取当天8根
            save_to_db(klines)
        await asyncio.sleep(0.3)  # 限速
```

---

## 4. 前端展示

### 4.1 数据读取API

```
GET /api/candles/{ticker}?timeframe=day&limit=120

Response:
{
    "ticker": "000001",
    "timeframe": "day",
    "candles": [
        {
            "timestamp": "2026-01-06T00:00:00",
            "open": 10.50,
            "high": 10.80,
            "low": 10.45,
            "close": 10.75,
            "volume": 12345678,
            "turnover": 135000000
        },
        ...
    ]
}
```

### 4.2 实时价格API

```
GET /api/realtime/prices?tickers=000001,600000

Response:
{
    "data": "var hq_str_sz000001=\"平安银行,10.75,...\";"
}
```

### 4.3 前端刷新策略

| 数据类型 | 刷新间隔 | 条件 |
|---------|---------|------|
| K线数据 (日线) | 30分钟 | 缓存 staleTime |
| K线数据 (30分钟) | 30分钟 | 缓存 staleTime |
| 实时价格 | 60秒 | 仅交易时间 (9:30-15:00) |

### 4.4 时区处理

```
后端存储: UTC+8 北京时间字符串 (2026-01-06 10:30:00)
API返回: ISO格式无时区 (2026-01-06T10:30:00)
前端显示: 转换为Unix时间戳 + 8小时偏移
```

---

## 5. 数据一致性

### 5.1 验证规则

**收盘后 (15:30后)**:
- 日线收盘价 = 30分钟最后一根收盘价 = 实时价格

**验证API**:
```
GET /api/admin/data-consistency?symbol_codes=000001,600000
```

### 5.2 数据新鲜度检查

```
GET /api/admin/data-freshness

Response:
{
    "is_valid": true,
    "issues": [],
    "summary": {
        "error_count": 0,
        "warning_count": 0
    }
}
```

---

## 6. 实现清单

### 6.1 需要新增/修改的文件

| 文件 | 修改内容 |
|------|---------|
| `src/services/kline_updater.py` | 新增 `update_market_daily()`, `update_market_30m()` |
| `src/services/kline_scheduler.py` | 新增全市场更新任务调度 |
| `src/services/stock_list_provider.py` | 新建: 获取全市场股票列表 |

### 6.2 预计工作量

1. 实现全市场股票列表获取 - 30分钟
2. 实现全市场日线更新 - 1小时
3. 实现全市场30分钟更新 - 1小时
4. 集成到调度器 - 30分钟
5. 测试验证 - 1小时

**总计**: 约4小时

---

## 7. 附录: 数据源API详情

### 7.1 东方财富日线API

```
GET https://push2his.eastmoney.com/api/qt/stock/kline/get
?secid=0.000001  # 0=深圳, 1=上海
&fields1=f1,f2,f3,f4,f5,f6
&fields2=f51,f52,f53,f54,f55,f56,f57
&klt=101  # 101=日线
&fqt=1    # 前复权
&end=20500000
&lmt=120
```

### 7.2 新浪财经30分钟API

```
GET https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData
?symbol=sz000001
&scale=30  # 30分钟
&ma=no
&datalen=80
```

### 7.3 新浪实时价格API

```
GET https://hq.sinajs.cn/list=sz000001,sh600000
```
