# K线数据统一化重构 PRD

## 文档信息
- **版本**: 1.0
- **创建日期**: 2026-01-05
- **状态**: 待实施

---

## 1. 背景与目标

### 1.1 当前问题

目前系统中的K线数据存储和更新存在以下问题：

| 问题 | 描述 |
|-----|------|
| **数据源分散** | 指数用Tushare+Sina，概念用同花顺+CSV，个股用Tushare+SQLite |
| **存储不统一** | 概念K线存CSV文件，个股K线存SQLite数据库 |
| **更新时机不同步** | 各类数据独立更新，可能出现时间不一致 |
| **维护复杂** | 需要管理多种数据格式和更新逻辑 |
| **前后端耦合** | 部分数据直接从CSV读取，缺乏统一的API层 |

### 1.2 目标

1. **统一存储**: 所有K线数据存入SQLite数据库
2. **统一更新**: 同类型数据在相同时间点更新
3. **前后端分离**: 前端只通过API访问数据，不直接读取文件
4. **简化维护**: 单一数据源，统一的更新和查询逻辑

---

## 2. 当前架构分析

### 2.1 数据流现状

```
┌─────────────────────────────────────────────────────────────────┐
│                         当前数据流                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐     ┌─────────┐     ┌─────────┐                   │
│  │ Tushare │     │  Sina   │     │ 同花顺   │                   │
│  └────┬────┘     └────┬────┘     └────┬────┘                   │
│       │               │               │                         │
│       ▼               ▼               ▼                         │
│  ┌─────────┐     ┌─────────┐     ┌─────────┐                   │
│  │ SQLite  │     │ 直接返回 │     │   CSV   │                   │
│  │(个股K线)│     │(实时数据)│     │(概念K线)│                   │
│  └────┬────┘     └────┬────┘     └────┬────┘                   │
│       │               │               │                         │
│       ▼               ▼               ▼                         │
│  ┌─────────────────────────────────────────┐                   │
│  │              Backend API                 │                   │
│  │  /api/candles  /api/realtime  /api/concepts/kline           │
│  └─────────────────────┬───────────────────┘                   │
│                        │                                        │
│                        ▼                                        │
│  ┌─────────────────────────────────────────┐                   │
│  │              Frontend                    │                   │
│  └─────────────────────────────────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 现有数据表

**SQLite (market.db)**:
- `candles` - 个股K线数据
- `symbol_metadata` - 股票元数据
- `watchlist` - 自选股列表

**CSV文件**:
- `data/concept_klines/concept_klines_daily.csv` - 概念日线
- `data/concept_klines/concept_klines_30min.csv` - 概念30分钟线
- `data/hot_concept_categories.csv` - 热门概念分类
- `data/concept_to_tickers.csv` - 概念与股票映射

### 2.3 现有更新机制

| 数据类型 | 更新方式 | 触发时机 |
|---------|---------|---------|
| 个股日线/30m | 请求时增量更新 | 用户访问时 |
| 概念日线/30m | 手动运行脚本 | `python scripts/fetch_ths_concept_kline.py` |
| 指数日线 | 请求时从Tushare获取 | 用户访问时 |
| 指数30m | 请求时从Sina获取 | 用户访问时 |
| 实时价格 | 直接API请求 | 前端30秒轮询 |

---

## 3. 目标架构设计

### 3.1 新数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                         目标数据流                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐     ┌─────────┐     ┌─────────┐                   │
│  │ Tushare │     │  Sina   │     │ 同花顺   │                   │
│  │(个股/指数)│    │(指数30m) │     │(概念K线) │                   │
│  └────┬────┘     └────┬────┘     └────┬────┘                   │
│       │               │               │                         │
│       └───────────────┼───────────────┘                         │
│                       │                                         │
│                       ▼                                         │
│            ┌─────────────────────┐                              │
│            │   Scheduler 定时任务  │                              │
│            │  (APScheduler)       │                              │
│            └──────────┬──────────┘                              │
│                       │                                         │
│                       ▼                                         │
│            ┌─────────────────────┐                              │
│            │      SQLite         │                              │
│            │  ┌───────────────┐  │                              │
│            │  │ klines (统一)  │  │                              │
│            │  │ - stock       │  │                              │
│            │  │ - index       │  │                              │
│            │  │ - concept     │  │                              │
│            │  └───────────────┘  │                              │
│            └──────────┬──────────┘                              │
│                       │                                         │
│                       ▼                                         │
│            ┌─────────────────────┐     ┌─────────────┐         │
│            │    Backend API      │◄────│ Sina/同花顺  │         │
│            │  (统一K线接口)       │     │ (实时价格)   │         │
│            └──────────┬──────────┘     └─────────────┘         │
│                       │                                         │
│                       ▼                                         │
│            ┌─────────────────────┐                              │
│            │      Frontend       │                              │
│            └─────────────────────┘                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 数据库Schema设计

#### 3.2.1 klines 表 (新建/重构)

```sql
CREATE TABLE klines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 标的信息
    symbol_type TEXT NOT NULL,      -- 'stock', 'index', 'concept'
    symbol_code TEXT NOT NULL,      -- '000001', '000001.SH', '885728'
    symbol_name TEXT,               -- '平安银行', '上证指数', '人工智能'

    -- 时间周期
    timeframe TEXT NOT NULL,        -- 'day', '30m', '5m', '1m'

    -- K线数据
    datetime TEXT NOT NULL,         -- ISO格式: '2026-01-05' 或 '2026-01-05 10:00:00'
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL DEFAULT 0,          -- 成交量
    amount REAL DEFAULT 0,          -- 成交额

    -- 技术指标 (可选，后续计算)
    dif REAL,                       -- MACD DIF
    dea REAL,                       -- MACD DEA
    macd REAL,                      -- MACD 柱

    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 唯一约束
    UNIQUE(symbol_type, symbol_code, timeframe, datetime)
);

-- 索引优化查询性能
CREATE INDEX idx_klines_symbol ON klines(symbol_type, symbol_code, timeframe);
CREATE INDEX idx_klines_datetime ON klines(datetime DESC);
CREATE INDEX idx_klines_lookup ON klines(symbol_type, symbol_code, timeframe, datetime DESC);
```

#### 3.2.2 data_update_log 表 (新建)

```sql
CREATE TABLE data_update_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    update_type TEXT NOT NULL,      -- 'stock_day', 'stock_30m', 'index_day', 'concept_day', etc.
    symbol_type TEXT,               -- 'stock', 'index', 'concept', 'all'
    timeframe TEXT,                 -- 'day', '30m'

    status TEXT NOT NULL,           -- 'started', 'completed', 'failed'
    records_updated INTEGER DEFAULT 0,
    error_message TEXT,

    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_update_log_type ON data_update_log(update_type, status);
```

#### 3.2.3 trade_calendar 表 (新建)

```sql
CREATE TABLE trade_calendar (
    date TEXT PRIMARY KEY,          -- '2026-01-05'
    is_trading_day BOOLEAN NOT NULL,
    exchange TEXT DEFAULT 'SSE',    -- 'SSE', 'SZSE'

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_calendar_trading ON trade_calendar(is_trading_day, date);
```

### 3.3 API设计

#### 3.3.1 统一K线API

**GET /api/klines/{symbol_type}/{symbol_code}**

参数:
- `symbol_type`: `stock` | `index` | `concept`
- `symbol_code`: 标的代码
- `timeframe`: `day` | `30m` (query param)
- `limit`: 返回数量，默认120 (query param)
- `start_date`: 开始日期 (query param, optional)
- `end_date`: 结束日期 (query param, optional)

响应:
```json
{
  "symbol_type": "concept",
  "symbol_code": "885728",
  "symbol_name": "人工智能",
  "timeframe": "day",
  "count": 120,
  "klines": [
    {
      "datetime": "2026-01-03",
      "open": 1380.5,
      "high": 1395.2,
      "low": 1375.0,
      "close": 1390.8,
      "volume": 12345678,
      "amount": 98765432.5,
      "dif": 10.5,
      "dea": 8.2,
      "macd": 4.6
    }
  ]
}
```

#### 3.3.2 保留的实时API

实时价格不存数据库，保持现有API:

- `GET /api/index/realtime/{ts_code}` - 指数实时 (Sina)
- `GET /api/concepts/realtime/{code}` - 概念实时 (同花顺)
- `GET /api/realtime/price/{ticker}` - 个股实时 (Sina)

---

## 4. 更新策略设计

### 4.1 更新时间表

| 数据类型 | 触发时间 | 数据源 | 说明 |
|---------|---------|-------|------|
| **交易日历** | 每天00:01 | Tushare | 获取未来30天交易日 |
| **日线数据** | 交易日15:30 | 各数据源 | 收盘后统一更新 |
| **30分钟数据** | 交易日每30分钟 | 各数据源 | 09:30-15:00期间 |

### 4.2 更新顺序

#### 日线更新 (15:30)
```
1. 检查是否为交易日
2. 更新指数日线 (3个指数，Tushare)
3. 更新概念日线 (96个概念，同花顺)
4. 更新自选股日线 (用户自选，Tushare)
5. 计算MACD指标
6. 记录更新日志
```

#### 30分钟更新 (交易时间每30分钟)
```
1. 检查是否为交易时间
2. 更新指数30m (Sina)
3. 更新概念30m (同花顺)
4. 更新自选股30m (Tushare)
5. 计算MACD指标
6. 记录更新日志
```

### 4.3 错误处理

| 场景 | 处理方式 |
|-----|---------|
| API请求失败 | 重试3次，间隔递增(1s, 3s, 5s) |
| 部分数据失败 | 记录失败项，继续其他更新 |
| 数据库写入失败 | 事务回滚，记录错误日志 |
| 非交易日 | 跳过更新，不报错 |

### 4.4 数据保留策略

| 数据类型 | 保留时长 | 清理时机 |
|---------|---------|---------|
| 日线 | 2年 | 每周日00:00 |
| 30分钟 | 6个月 | 每周日00:00 |
| 5分钟 | 1个月 | 每周日00:00 |
| 更新日志 | 30天 | 每周日00:00 |

---

## 5. 实施计划

### 5.1 阶段一: 数据库准备 (Day 1)

**任务**:
1. 创建新的 `klines` 表
2. 创建 `data_update_log` 表
3. 创建 `trade_calendar` 表
4. 编写数据迁移脚本

**涉及文件**:
- `src/database.py` - 添加新表定义
- `src/models.py` - 添加新模型
- `scripts/migrate_klines.py` - 迁移脚本

### 5.2 阶段二: 数据迁移 (Day 1)

**任务**:
1. 迁移现有 `candles` 表数据到 `klines` 表
2. 迁移 CSV 概念K线数据到 `klines` 表
3. 下载并存储指数K线数据
4. 验证数据完整性

**迁移SQL示例**:
```sql
-- 迁移个股K线
INSERT INTO klines (symbol_type, symbol_code, timeframe, datetime, open, high, low, close, volume, amount)
SELECT 'stock', ticker, timeframe, timestamp, open, high, low, close, volume, 0
FROM candles;

-- 迁移概念K线 (从CSV导入)
-- 通过Python脚本执行
```

### 5.3 阶段三: 后端重构 (Day 2)

**任务**:
1. 创建统一的 K线数据访问层 (`src/services/kline_service.py`)
2. 重构 `/api/concepts/kline` 接口
3. 重构 `/api/index/kline` 接口
4. 创建新的统一接口 `/api/klines`
5. 保持旧接口兼容，内部调用新逻辑

**涉及文件**:
- `src/services/kline_service.py` - 新建，统一数据访问
- `src/api/routes_klines.py` - 新建，统一API
- `src/api/routes_concepts.py` - 修改，使用新服务
- `src/api/routes_index.py` - 修改，使用新服务

### 5.4 阶段四: 定时任务 (Day 2-3)

**任务**:
1. 创建定时任务管理器 (`src/services/kline_scheduler.py`)
2. 实现日线更新任务
3. 实现30分钟更新任务
4. 实现数据清理任务
5. 添加交易日历检查

**涉及文件**:
- `src/services/kline_scheduler.py` - 新建
- `src/services/kline_updater.py` - 新建，更新逻辑
- `src/main.py` - 注册定时任务

### 5.5 阶段五: 前端适配 (Day 3)

**任务**:
1. 更新 `IndexChart` 使用新API
2. 更新 `ConceptKlineCard` 使用新API
3. 确保数据格式兼容
4. 测试所有K线显示

**涉及文件**:
- `frontend/src/components/IndexChart.tsx`
- `frontend/src/components/ConceptKlineCard.tsx`
- `frontend/src/hooks/useCandles.ts`

### 5.6 阶段六: 清理与优化 (Day 4)

**任务**:
1. 删除旧的 CSV 读取逻辑
2. 删除旧的 `candles` 表（可选，或保留备份）
3. 添加数据更新状态监控
4. 性能测试与优化
5. 文档更新

---

## 6. 风险与应对

| 风险 | 影响 | 应对措施 |
|-----|-----|---------|
| 数据迁移失败 | 丢失历史数据 | 先备份，分批迁移，验证后再删除旧数据 |
| API兼容性问题 | 前端显示异常 | 保持旧API工作，逐步切换 |
| 定时任务冲突 | 数据更新延迟 | 使用锁机制，避免并发更新 |
| 第三方API限制 | 更新失败 | 合理安排请求间隔，实现重试机制 |

---

## 7. 验收标准

### 7.1 功能验收

- [ ] 所有K线数据从SQLite读取
- [ ] 日线数据每天15:30自动更新
- [ ] 30分钟数据交易时间每30分钟更新
- [ ] 前端所有K线图正常显示
- [ ] 实时价格正常更新

### 7.2 性能验收

- [ ] K线API响应时间 < 200ms
- [ ] 日线批量更新时间 < 5分钟
- [ ] 30分钟批量更新时间 < 2分钟
- [ ] 数据库大小增长合理

### 7.3 稳定性验收

- [ ] 连续运行7天无报错
- [ ] 周末/节假日正确跳过更新
- [ ] API失败时有重试和降级机制

---

## 8. 附录

### 8.1 现有代码位置参考

```
src/
├── api/
│   ├── routes_candles.py      # 个股K线API
│   ├── routes_concepts.py     # 概念K线API (读CSV)
│   ├── routes_index.py        # 指数K线API
│   └── routes_realtime.py     # 实时价格API
├── services/
│   ├── data_pipeline.py       # 个股数据获取
│   ├── tushare_client.py      # Tushare客户端
│   └── scheduler.py           # 现有定时任务
├── database.py                # 数据库连接
└── models.py                  # SQLAlchemy模型

data/
├── concept_klines/
│   ├── concept_klines_daily.csv
│   └── concept_klines_30min.csv
└── market.db                  # SQLite数据库

scripts/
└── fetch_ths_concept_kline.py # 概念K线下载脚本
```

### 8.2 数据源API参考

| 数据源 | 用途 | 限制 |
|-------|-----|-----|
| Tushare | 个股/指数日线、基本面 | 180次/分钟 |
| Sina Finance | 指数30m、实时价格 | 无明显限制 |
| 同花顺 | 概念K线、实时价格 | 偶有502错误 |

---

*文档结束*
