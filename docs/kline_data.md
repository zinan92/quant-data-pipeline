# K线数据更新总结（日线 + 30分钟线）

本文档记录了系统中所有日线和30分钟K线数据的更新频率、数据范围和监督机制。

---

## 📊 数据概览

### 数据类型统计

| 类型 | 日线数据 | 30分钟数据 | 数据源 |
|------|---------|-----------|-------|
| **指数** | 5个指数 | 5个指数 | 新浪财经 API |
| **概念板块** | 100个热门概念 | 100个热门概念 | 同花顺 API |
| **自选股** | 动态（用户自选） | 动态（用户自选） | 东方财富 + 新浪财经 |
| **全市场股票** | 全部A股（约5450只） | ❌ 不更新 | 东方财富 API |

---

## 1. 指数K线数据

### 覆盖指数列表

| 代码 | 名称 | 市场 |
|------|------|------|
| 000001.SH | 上证指数 | 上海 |
| 399001.SZ | 深证成指 | 深圳 |
| 399006.SZ | 创业板指 | 深圳 |
| 000688.SH | 科创50 | 上海 |
| 899050.BJ | 北证50 | 北京 |

### 日线数据 (index_daily)

- **更新时间**: 每个交易日 15:30
- **更新频率**: 每天1次（仅交易日）
- **数据源**: 新浪财经 API (`https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?scale=240`)
- **数据量**: 每个指数最近60条
- **保留期**: 365天（自动清理）
- **代码位置**: `src/services/kline_updater.py:95-175`
- **调度器**: `src/services/kline_scheduler.py:91-114` (CronTrigger: 15:30)
- **并发策略**: 5个指数并发获取

### 30分钟数据 (index_30m)

- **更新时间**: 交易日 10:00, 10:30, 11:00, 11:30, 13:30, 14:00, 14:30, 15:00
- **更新频率**: 每30分钟1次（仅交易时段）
- **数据源**: 新浪财经 API (`scale=30`)
- **数据量**: 每个指数最近60条（约2天）
- **保留期**: 90天（自动清理）
- **代码位置**: `src/services/kline_updater.py:177-256`
- **调度器**: `src/services/kline_scheduler.py:116-153` (CronTrigger: 每小时 :00 和 :30)
- **并发策略**: 5个指数并发获取

---

## 2. 概念板块K线数据

### 数据范围

- **概念总数**: 100个热门概念
- **来源文件**: `/data/hot_concept_categories.csv`
- **分类维度**: AI人工智能、智能硬件、芯片半导体、新能源、消费、医药、金融、元宇宙等

**热门概念示例**:
- AI人工智能: 人工智能 (991只)、DeepSeek概念 (739只)、数据中心 (542只)
- 芯片半导体: 先进封装、存储芯片、第三代半导体、中芯国际概念
- 新能源: 锂电池、光伏、风电、储能
- 智能硬件: 人形机器人、汽车芯片、消费电子

### 日线数据 (concept_daily)

- **更新时间**: 每个交易日 15:30
- **更新频率**: 每天1次（仅交易日）
- **数据源**: 同花顺 API (`http://d.10jqka.com.cn/v4/line/bk_{code}/01/last.js`)
- **数据量**: 每个概念约120-240条（历史数据）
- **保留期**: 365天（自动清理）
- **代码位置**: `src/services/kline_updater.py:361-413`
- **调度器**: `src/services/kline_scheduler.py:91-114` (与指数同时更新)
- **并发策略**: 批量获取，每批10个概念，批次间延迟0.5秒

### 30分钟数据 (concept_30m)

- **更新时间**: 交易日 10:00, 10:30, 11:00, 11:30, 13:30, 14:00, 14:30, 15:00
- **更新频率**: 每30分钟1次（仅交易时段）
- **数据源**: 同花顺 API (`period=30`)
- **数据量**: 每个概念最近500条（约10天）
- **保留期**: 90天（自动清理）
- **代码位置**: `src/services/kline_updater.py:415-464`
- **调度器**: `src/services/kline_scheduler.py:116-153` (与指数同时更新)
- **并发策略**: 批量获取，每批10个概念，批次间延迟0.5秒

---

## 3. 自选股K线数据

### 数据范围

- **股票数量**: 动态，取决于用户自选列表
- **数据来源**: `watchlist` 数据库表
- **触发时机**:
  1. 定时更新（每日15:30 / 每30分钟）
  2. 添加自选时立即更新（单股更新）

### 日线数据 (stock_daily)

- **更新时间**: 每个交易日 15:30
- **更新频率**: 每天1次（仅交易日）
- **数据源**: 东方财富 API (`EastMoneyKlineProvider`)
- **数据量**: 每只股票最近120条
- **保留期**: 365天（自动清理）
- **代码位置**: `src/services/kline_updater.py:479-548`
- **调度器**: `src/services/kline_scheduler.py:91-114` (与指数、概念同时更新)
- **并发策略**: 顺序获取，每只股票间延迟0.1秒

### 30分钟数据 (stock_30m)

- **更新时间**: 交易日 10:00, 10:30, 11:00, 11:30, 13:30, 14:00, 14:30, 15:00
- **更新频率**: 每30分钟1次（仅交易时段）
- **数据源**: 新浪财经 API (`SinaKlineProvider`)
- **数据量**: 每只股票最近500条（约10天）
- **保留期**: 90天（自动清理）
- **代码位置**: `src/services/kline_updater.py:550-619`
- **调度器**: `src/services/kline_scheduler.py:116-153` (与指数、概念同时更新)
- **并发策略**: 顺序获取，每只股票间延迟0.5秒

### 单股立即更新 (添加自选时触发)

- **触发条件**: 用户添加自选股时自动触发
- **更新内容**: 日线 + 30分钟线
- **代码位置**: `src/services/kline_updater.py:722-786`
- **数据源**:
  - 日线: 东方财富 API (最近120条)
  - 30分钟: 新浪财经 API (最近80条)

---

## 4. 全市场股票日线数据

### 数据范围

- **股票数量**: 全部A股（约5450只）
- **数据来源**: `symbol_metadata` 数据库表
- **更新目的**: 全市场历史数据存档

### 日线数据 (all_stock_daily)

- **更新时间**: 每个交易日 16:00
- **更新频率**: 每天1次（仅交易日）
- **数据源**: 东方财富 API
- **数据量**: 每只股票最近20条（增量更新）
- **保留期**: 365天（自动清理）
- **代码位置**: `src/services/kline_updater.py:621-718`
- **调度器**: `src/services/kline_scheduler.py:246-253` (CronTrigger: 16:00)
- **并发策略**: 顺序获取，每只股票间延迟0.1秒
- **预计耗时**: 约9分钟（5450只 × 0.1秒）
- **进度日志**: 每500只打印一次进度和预计剩余时间

**注意**: 全市场股票**不更新30分钟线**，仅更新日线数据。

---

## 5. 前端显示与刷新频率

### 指数K线显示 (IndexChart.tsx)

| 数据类型 | API端点 | 前端刷新频率 | 显示位置 |
|---------|---------|------------|---------|
| 日线 | `/api/index/kline/{code}?period=daily` | 30分钟 | 首页指数卡片 |
| 30分钟线 | `/api/index/kline/{code}?period=30min` | 5分钟 | 首页指数卡片 |

**代码位置**: `frontend/src/components/IndexChart.tsx:150-163`

### 概念K线显示 (ConceptKlineCard.tsx)

| 数据类型 | API端点 | 前端刷新频率 | 显示位置 |
|---------|---------|------------|---------|
| 日线 | `/api/concepts/kline/{code}?period=daily&limit=120` | 30分钟 | 概念K线卡片 |
| 30分钟线 | `/api/concepts/kline/{code}?period=30min&limit=120` | 5分钟 | 概念K线卡片 |

**代码位置**: `frontend/src/components/ConceptKlineCard.tsx:79-92`

### 自选股K线显示 (StockDetail.tsx)

| 数据类型 | API端点 | 前端刷新频率 | 显示位置 |
|---------|---------|------------|---------|
| 日线 | `/api/stock/kline/{ticker}?period=day&limit=120` | 30分钟 | 股票详情页 |
| 30分钟线 | `/api/stock/kline/{ticker}?period=30min&limit=120` | 5分钟 | 股票详情页 |

**代码位置**: `frontend/src/components/StockDetail.tsx`

### ETF K线显示 (EtfKlineCard.tsx)

| 数据类型 | API端点 | 前端刷新频率 | 显示位置 |
|---------|---------|------------|---------|
| 日线 | `/api/etf/kline/{ticker}?limit=120` | 30分钟 | ETF资金流卡片 |

**代码位置**: `frontend/src/components/EtfKlineCard.tsx:55-59`

### 全局刷新间隔配置

```typescript
// frontend/src/utils/api.ts:15-20
export const REFRESH_INTERVALS = {
  symbols: 60 * 60 * 1000,     // 1小时
  watchlist: 30 * 60 * 1000,   // 30分钟
  boards: 30 * 60 * 1000,      // 30分钟 (用于日线)
  portfolio: 30 * 60 * 1000    // 30分钟
};
```

**30分钟线刷新**: 各组件独立设置为 5分钟 (`1000 * 60 * 5`)

---

## 6. 监督与监控机制

### APScheduler 调度器

- **类型**: AsyncIOScheduler
- **启动方式**: FastAPI 启动时自动启动 (`main.py:lifespan`)
- **代码位置**: `src/services/kline_scheduler.py`
- **状态检查**: `/api/scheduler/status` 端点

### 定时任务列表

| 任务ID | 任务名称 | 触发时间 | 执行内容 |
|--------|---------|---------|---------|
| `daily_update` | 每日K线更新 | 15:30 (交易日) | 指数日线 + 概念日线 + 自选股日线 |
| `30m_update` | 30分钟K线更新 | :00, :30 (交易时段) | 指数30分钟 + 概念30分钟 + 自选股30分钟 |
| `all_stock_daily` | 全市场日线更新 | 16:00 (交易日) | 全部A股日线（增量更新） |
| `update_calendar` | 交易日历更新 | 00:01 (每天) | 更新当年+次年交易日历 |
| `cleanup` | 数据清理 | 周日 00:00 | 删除过期K线（90天/365天） |

### 交易日判断

**逻辑**:
- 查询 `trade_calendar` 表判断当前日期是否为交易日
- 如果非交易日，跳过所有K线更新任务
- 代码位置: `src/services/kline_scheduler.py:80-89`

### 更新日志 (data_update_log)

**数据库表**: `data_update_log`

**字段**:
- `update_type`: 更新类型 (index_daily, concept_30m, stock_daily, etc.)
- `status`: 状态 (COMPLETED / FAILED)
- `records_updated`: 更新记录数
- `error_message`: 错误信息（失败时）
- `started_at`: 开始时间
- `completed_at`: 完成时间

**记录时机**:
- 每次更新任务完成时自动记录
- 代码位置: `src/services/kline_updater.py:72-91`

### 错误处理机制

1. **重试机制**: Tushare API有自动重试（`TushareClient.max_retries`）
2. **异常捕获**: 每个更新函数都有 try-except，记录错误到日志
3. **部分失败**: 单个股票/概念失败不影响整体任务
4. **日志输出**: 使用 `src/utils/logging.py` 统一日志记录

### 监控状态查询

**API端点**: `GET /api/scheduler/status`

**返回内容**:
```json
{
  "running": true,
  "job_count": 5,
  "jobs": [
    {
      "id": "daily_update",
      "name": "每日K线更新",
      "next_run_time": "2026-01-20T15:30:00+08:00",
      "trigger": "cron[hour='15', minute='30']"
    },
    ...
  ]
}
```

---

## 7. 数据存储与保留策略

### 数据库表: `klines`

**表结构**:
```sql
CREATE TABLE klines (
    id INTEGER PRIMARY KEY,
    symbol_type VARCHAR(16),      -- 'stock', 'index', 'concept'
    symbol_code VARCHAR(16),       -- 代码 (如 000001.SH, 885556)
    symbol_name VARCHAR(64),       -- 名称
    timeframe VARCHAR(16),         -- 'day', '30m', '5m', '1m'
    trade_time VARCHAR(32),        -- ISO格式时间
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume BIGINT,
    amount REAL,
    macd REAL,
    macd_signal REAL,
    macd_hist REAL,
    UNIQUE (symbol_type, symbol_code, timeframe, trade_time)
);
```

### 数据保留策略

| 数据类型 | 保留期限 | 清理触发 |
|---------|---------|---------|
| **日线** | 365天 | 每周日 00:00 |
| **30分钟线** | 90天 | 每周日 00:00 |

**清理逻辑**:
- 代码位置: `src/services/kline_updater.py:850-904`
- 调度器: `src/services/kline_scheduler.py:255-262`
- 删除策略:
  - 30分钟线: `trade_time < (今天 - 90天)`
  - 日线: `trade_time < (今天 - 365天)`

### 数据去重机制

**UNIQUE 约束**: `(symbol_type, symbol_code, timeframe, trade_time)`

**插入策略**: 使用 `INSERT OR REPLACE` (SQLite) / `ON CONFLICT DO UPDATE` (PostgreSQL)

**代码位置**: `src/services/kline_service.py` (KlineService.save_klines)

---

## 8. 数据源API汇总

### 新浪财经 API

**用途**: 指数日线、指数30分钟线、股票30分钟线

**端点格式**:
```
https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol={code}&scale={scale}&datalen={limit}
```

**参数**:
- `scale`: 240=日线, 30=30分钟线
- `datalen`: 数据条数（60-500）

**限制**:
- 无官方限流说明，代码中使用0.5秒延迟
- 数据延迟约15秒

### 同花顺 API

**用途**: 概念板块日线、概念板块30分钟线

**端点格式**:
```
http://d.10jqka.com.cn/v4/line/bk_{code}/{period}/last.js
```

**参数**:
- `code`: 概念代码（6位数字，如 885556）
- `period`: "01"=日线, "30"=30分钟线

**返回格式**: JSONP（需正则提取JSON）

**限制**:
- 批量获取，每批10个，批次间延迟0.5秒
- 免费接口，未知限流策略

### 东方财富 API

**用途**: 股票日线、全市场日线

**类**: `EastMoneyKlineProvider`

**代码位置**: `src/services/eastmoney_kline_provider.py`

**限制**:
- 每次请求延迟0.1秒
- 稳定性高，适合大批量获取

### Tushare API

**用途**: 交易日历

**类**: `TushareClient`

**代码位置**: `src/services/tushare_client.py`

**限制**:
- 需要token（环境变量 `TUSHARE_TOKEN`）
- 有积分限制，已配置重试机制

---

## 9. 关键发现与限制

### ✅ 已覆盖的数据

1. **指数**: 5个主要指数的日线和30分钟线
2. **概念**: 100个热门概念的日线和30分钟线
3. **自选股**: 用户自选股的日线和30分钟线（动态）
4. **全市场**: 全部A股的日线数据（每日增量）

### ❌ 不存在的数据

1. **5分钟线**: 系统中不存在5分钟K线数据
2. **1分钟线**: 系统中不存在1分钟K线数据
3. **全市场30分钟线**: 仅自选股更新30分钟线，全市场股票不更新
4. **实时tick数据**: 无实时逐笔成交数据

### ⚠️ 数据更新延迟

| 数据源 | API延迟 | 更新频率 | 总延迟 |
|-------|--------|---------|--------|
| 新浪财经 | ~15秒 | 30分钟 | 最多30分15秒 |
| 同花顺 | ~1分钟 | 30分钟 | 最多31分钟 |
| 东方财富 | ~30秒 | 每天1次 | 当天15:30后 |

### 📊 数据量估算

**当前存储量**（假设系统运行1年）:

- 指数日线: 5个 × 365天 = 1,825条
- 指数30分钟: 5个 × 90天 × 8条/天 = 3,600条
- 概念日线: 100个 × 365天 = 36,500条
- 概念30分钟: 100个 × 90天 × 8条/天 = 72,000条
- 自选股日线: 50个 × 365天 = 18,250条
- 自选股30分钟: 50个 × 90天 × 8条/天 = 36,000条
- 全市场日线: 5450个 × 365天 = 1,989,250条

**总计**: 约215万条K线记录

---

## 10. 监督机制确认

### ✅ 持续监督的任务

| 任务 | 监督方式 | 状态检查 |
|------|---------|---------|
| APScheduler运行 | FastAPI lifespan管理 | `/api/scheduler/status` |
| 交易日判断 | 每个job执行前检查 | `is_trading_day()` |
| 更新日志记录 | 每次更新自动记录 | `data_update_log` 表 |
| 异常捕获 | try-except + logger | 日志文件 |
| 数据清理 | 每周日自动执行 | 调度器触发 |

### ✅ 监督确认

- **APScheduler**: ✅ 已启动并持续运行（通过FastAPI lifespan管理）
- **定时任务**: ✅ 已注册5个定时任务，自动触发
- **交易日检查**: ✅ 每个交易相关任务都检查 `is_trading_day()`
- **错误处理**: ✅ 所有更新函数都有异常捕获和日志记录
- **数据清理**: ✅ 每周日自动删除过期数据
- **更新记录**: ✅ 每次更新都记录到 `data_update_log` 表

**结论**: 系统具备完善的监督机制，所有K线数据都在持续更新和监控中。

---

## 11. 优化建议

### 短期优化

1. **增加5分钟K线**: 对于概念和自选股，可添加5分钟K线以提高分析精度
2. **WebSocket推送**: 将30分钟更新改为实时推送，减少延迟
3. **数据预加载**: 前端启动时预加载常用K线数据到LocalStorage

### 长期优化

1. **分布式调度**: 使用Celery替代APScheduler，支持水平扩展
2. **时序数据库**: 迁移到InfluxDB或TimescaleDB，提升查询性能
3. **增量同步**: 仅获取增量数据，减少API调用
4. **智能刷新**: 非交易时段降低刷新频率，节省资源

---

## 📝 更新记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-01-19 | 1.0 | 初始版本，记录所有日线和30分钟K线数据 |

---

## 相关文档

- [实时数据文档](./realtime_data.md)
- [动量信号实现文档](./MOMENTUM_SIGNALS_IMPLEMENTATION.md)
- [API文档](./tonghuashun_akshare_api.md)
