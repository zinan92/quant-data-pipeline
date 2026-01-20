# 前端数据SKU清单

**创建日期**: 2025-11-15
**目标**: 记录所有前端展示的数据字段（SKU），以及对应的更新频率

---

## 数据模型概览

### Key-Value 结构

**Key**: `ticker` (股票代码，如 `000001`, `600519`)

**Value**: 包含多个columns，分为三类：
1. **静态元数据** (Static Metadata) - 极少变化
2. **每日动态指标** (Daily Metrics) - 每天更新
3. **K线数据** (Candle Data) - 多时间周期，每天/每周/每月更新

---

## 1. 单个Ticker的完整SKU列表

### API端点: `GET /api/symbols`

**返回格式**: `List[SymbolMeta]`

**单个ticker包含的字段**:

| 序号 | 字段名 (Database) | 字段名 (API) | 类型 | 说明 | 更新频率 | 数据来源 |
|------|-------------------|--------------|------|------|----------|----------|
| 1 | `ticker` | `ticker` | str | 股票代码 (6位数字) | **不变** | stock_basic |
| 2 | `name` | `name` | str | 股票名称 | **极少变** (改名时) | stock_basic |
| 3 | `list_date` | `listDate` | str | 上市日期 YYYYMMDD | **不变** | stock_basic |
| 4 | `industry_lv1` | `industryLv1` | str | 一级行业 (同花顺90核心行业) | **年度更新** | stock_basic.industry |
| 5 | `industry_lv2` | `industryLv2` | str | 二级行业 (预留字段) | **年度更新** | (未使用) |
| 6 | `industry_lv3` | `industryLv3` | str | 三级行业 (预留字段) | **年度更新** | (未使用) |
| 7 | `concepts` | `concepts` | list | 概念板块列表 | **月度更新** | board_mapping |
| 8 | `total_mv` | `totalMv` | float | 总市值（万元） | **每日** | daily_basic |
| 9 | `circ_mv` | `circMv` | float | 流通市值（万元） | **每日** | daily_basic |
| 10 | `pe_ttm` | `peTtm` | float | 市盈率 TTM | **每日** | daily_basic |
| 11 | `pb` | `pb` | float | 市净率 | **每日** | daily_basic |
| 12 | `last_sync` | `lastUpdated` | datetime | 最后同步时间 | **每日** | 系统生成 |
| 13 | `eastmoney_board` | `eastmoneyBoard` | list | 行业层级 (computed) | **年度更新** | 计算字段 |

**总计**: 每个ticker有 **13个字段**

---

### API端点: `GET /api/candles/{ticker}`

**返回格式**: `CandleBatchResponse`

**包含的字段**:

| 序号 | 字段名 | 类型 | 说明 | 更新频率 | 数据来源 |
|------|--------|------|------|----------|----------|
| 1 | `ticker` | str | 股票代码 | - | - |
| 2 | `timeframe` | enum | 时间周期 (day/week/month) | - | - |
| 3 | `candles` | list | K线数据数组 | 见下表 | - |

**每根K线 (CandlePoint) 包含的字段**:

| 序号 | 字段名 | 类型 | 说明 | 更新频率 | 数据来源 |
|------|--------|------|------|----------|----------|
| 1 | `timestamp` | datetime | 时间戳 | **每日/每周/每月** | daily/weekly/monthly |
| 2 | `open` | float | 开盘价 | **每日/每周/每月** | daily/weekly/monthly |
| 3 | `high` | float | 最高价 | **每日/每周/每月** | daily/weekly/monthly |
| 4 | `low` | float | 最低价 | **每日/每周/每月** | daily/weekly/monthly |
| 5 | `close` | float | 收盘价 | **每日/每周/每月** | daily/weekly/monthly |
| 6 | `volume` | float | 成交量 | **每日/每周/每月** | daily/weekly/monthly |
| 7 | `turnover` | float | 成交额 | **每日/每周/每月** | daily/weekly/monthly |
| 8 | `ma5` | float | 5日均线 | **每日/每周/每月** | 系统计算 |
| 9 | `ma10` | float | 10日均线 | **每日/每周/每月** | 系统计算 |
| 10 | `ma20` | float | 20日均线 | **每日/每周/每月** | 系统计算 |
| 11 | `ma50` | float | 50日均线 | **每日/每周/每月** | 系统计算 |

**总计**: 每根K线有 **11个字段**

---

## 2. 单个Ticker的总SKU数量

### 基础元数据
- **静态字段**: 7个 (`ticker`, `name`, `list_date`, `industry_lv1/2/3`, `eastmoney_board`)
- **动态字段**: 6个 (`total_mv`, `circ_mv`, `pe_ttm`, `pb`, `concepts`, `last_sync`)
- **小计**: **13个SKU**

### K线数据 (每个timeframe)
- **3种时间周期**: `day`, `week`, `month`
- **每根K线**: 11个字段
- **存储数量**: 200根K线 × 3个时间周期 = 600根K线
- **SKU总数**: 600根 × 11字段 = **6,600个K线SKU**

### 单个Ticker总计
```
基础元数据:    13 个SKU
K线数据:      6,600 个SKU (200根 × 3周期 × 11字段)
─────────────────────────
总计:         6,613 个SKU
```

---

## 3. 全市场SKU统计

假设系统监控 **5000只股票**:

### 元数据SKU
```
5000只股票 × 13个字段 = 65,000 个元数据SKU
```

### K线SKU
```
5000只股票 × 600根K线 × 11个字段 = 33,000,000 个K线SKU
```

### 全市场总计
```
元数据SKU:       65,000
K线SKU:      33,000,000
─────────────────────────
总计:        33,065,000 个SKU
```

---

## 4. 更新频率详细说明

### 静态字段 (首次下载，极少更新)

| 字段 | 初始下载 | 日常更新 | 触发更新条件 | API成本 |
|------|----------|----------|--------------|---------|
| `ticker` | ✓ | ❌ | 永不更新 | 0 |
| `name` | ✓ | ❌ | 公司改名时 (极少) | 0 |
| `list_date` | ✓ | ❌ | 永不更新 | 0 |
| `industry_lv1` | ✓ | ❌ | 行业重新分类 (年度) | 1次/年 |
| `industry_lv2` | ✓ | ❌ | (未使用) | 0 |
| `industry_lv3` | ✓ | ❌ | (未使用) | 0 |

**API调用**:
- **首次**: `stock_basic` 1次 (获取所有5000只股票)
- **日常**: 0次

---

### 半静态字段 (定期更新)

| 字段 | 初始下载 | 日常更新 | 更新频率 | API成本 |
|------|----------|----------|----------|---------|
| `concepts` | ✓ | **每周/每月** | 概念板块成分股变化时 | 442次 |

**API调用**:
- **首次**: 442次 (获取所有概念板块的成分股)
- **日常**: 442次 (每周或每月重新获取)

---

### 动态字段 (每日更新)

| 字段 | 初始下载 | 日常更新 | 更新时间 | API成本 |
|------|----------|----------|----------|---------|
| `total_mv` | ✓ | **每日** | 盘后 (16:00后) | 1次/天 |
| `circ_mv` | ✓ | **每日** | 盘后 (16:00后) | 1次/天 |
| `pe_ttm` | ✓ | **每日** | 盘后 (16:00后) | 1次/天 |
| `pb` | ✓ | **每日** | 盘后 (16:00后) | 1次/天 |
| `last_sync` | ✓ | **每日** | 每次同步时 | 0 (系统生成) |

**API调用**:
- **首次**: `daily_basic(trade_date=latest)` 1次 (批量获取所有股票)
- **日常**: `daily_basic(trade_date=latest)` 1次/天

---

### K线数据 (每日/每周/每月更新)

#### 日线 (DAY)

| 字段 | 初始下载 | 日常更新 | 更新频率 | API成本 |
|------|----------|----------|----------|---------|
| OHLCV + MA | ✓ (200根) | **每日新增1根** | 每天盘后 | 5000次/天 |

**当前实现**: ❌ 每天下载200根 (全量更新)
**理想实现**: ✅ 每天仅下载1根新K线 (增量更新)

#### 周线 (WEEK)

| 字段 | 初始下载 | 日常更新 | 更新频率 | API成本 |
|------|----------|----------|----------|---------|
| OHLCV + MA | ✓ (200根) | **每周一更新1根** | 周一盘后 | 5000次/周 |

**当前实现**: ❌ 每天下载200根 (浪费)
**理想实现**: ✅ 仅周一下载1根新K线

#### 月线 (MONTH)

| 字段 | 初始下载 | 日常更新 | 更新频率 | API成本 |
|------|----------|----------|----------|---------|
| OHLCV + MA | ✓ (200根) | **每月1号更新1根** | 月初盘后 | 5000次/月 |

**当前实现**: ❌ 每天下载200根 (浪费)
**理想实现**: ✅ 仅月初下载1根新K线

---

## 5. API调用成本分析

### 当前实现 (全量更新)

**每天的API调用**:
```
stock_basic:   1次 (获取静态信息，不必要 ❌)
daily_basic:   1次 (获取每日指标，必要 ✓)
daily (日线):  5000次 × 200根 = 1,000,000 条K线 ❌
weekly (周线): 5000次 × 200根 = 1,000,000 条K线 ❌
monthly (月线): 5000次 × 200根 = 1,000,000 条K线 ❌
─────────────────────────
总计:          3,000,000 条K线 + 2次元数据
```

**浪费**:
- 静态字段每天重复下载 (浪费100%)
- 日线每天下载200根，只需要1根 (浪费99.5%)
- 周线/月线每天下载，大部分时间不需要 (浪费99.8%)

---

### 优化后实现 (增量更新)

#### 首次下载 (First Time)
```
stock_basic:   1次 (所有静态信息)
daily_basic:   1次 (当日动态指标)
daily (日线):  5000次 × 200根 = 1,000,000 条K线
weekly (周线): 5000次 × 200根 = 1,000,000 条K线
monthly (月线): 5000次 × 200根 = 1,000,000 条K线
─────────────────────────
总计:          3,000,000 条K线 + 2次元数据
```

#### 日常更新 (Daily Incremental)
```
stock_basic:   0次 (不调用) ✅
daily_basic:   1次 (仅当日数据) ✅
daily (日线):  5000次 × 1根 = 5,000 条K线 ✅
weekly (周线): 0次 (非周一) ✅
monthly (月线): 0次 (非月初) ✅
─────────────────────────
总计:          5,000 条K线 + 1次元数据

节省比例:      99.8% ⭐
```

#### 每周一更新 (Monday)
```
stock_basic:   0次
daily_basic:   1次
daily (日线):  5000次 × 1根 = 5,000 条K线
weekly (周线): 5000次 × 1根 = 5,000 条K线 ✅
monthly (月线): 0次
─────────────────────────
总计:          10,000 条K线 + 1次元数据
```

#### 每月1号更新 (1st of Month)
```
stock_basic:   0次
daily_basic:   1次
daily (日线):  5000次 × 1根 = 5,000 条K线
weekly (周线): 5000次 × 1根 = 5,000 条K线 (如果是周一)
monthly (月线): 5000次 × 1根 = 5,000 条K线 ✅
─────────────────────────
总计:          15,000 条K线 + 1次元数据
```

---

## 6. 行业聚合数据 ⭐ **已升级为数据库存储**

### API端点: `GET /api/symbols/industries`

**返回格式**: `List[Dict]`

**数据来源**: ✅ **从 `industry_daily` 表读取**（不再实时计算）

**单个行业包含的字段**:

| 序号 | 字段名 | 类型 | 说明 | 数据来源 |
|------|--------|------|------|----------|
| 1 | `板块名称` | str | 行业名称 (如"电网设备") | IndustryDaily.industry |
| 2 | `板块代码` | str | 同花顺板块代码 (如"881267.TI") | IndustryDaily.ts_code |
| 3 | `股票数量` | int | 该行业的成分股数量 | IndustryDaily.company_num |
| 4 | `总市值` | float | 行业总市值（万元） | IndustryDaily.total_mv (计算得出) |
| 5 | `涨跌幅` | float | **板块指数涨跌幅** (%) | IndustryDaily.pct_change (同花顺) |
| 6 | `上涨家数` | int | 上涨股票数量 | IndustryDaily.up_count (计算得出) |
| 7 | `下跌家数` | int | 下跌股票数量 | IndustryDaily.down_count (计算得出) |
| 8 | `行业PE` | float | **市值加权PE** | IndustryDaily.industry_pe (计算得出) |
| 9 | `收盘指数` | float | 板块收盘指数 | IndustryDaily.close |
| 10 | `领涨股` | str | 领涨股票名称 | IndustryDaily.lead_stock |
| 11 | `领涨股涨跌幅` | float | 领涨股涨跌幅 (%) | IndustryDaily.pct_change_stock |
| 12 | `净流入资金` | float | 资金净流入（亿元） | IndustryDaily.net_amount |
| 13 | `交易日期` | str | 数据日期 YYYYMMDD | IndustryDaily.trade_date |

**总计**: 每个行业有 **13个字段**

**行业数量**: 90个 (同花顺行业分类)

**行业聚合SKU**: 90 × 13 = **1,170个SKU**

**更新频率**: **每日盘后** (通过脚本 `update_industry_daily.py` 更新)

**数据接口**: Tushare `moneyflow_ind_ths` (doc_id=343)

**优势**:
- ✅ 涨跌幅更准确（基于板块指数，而非简单平均）
- ✅ 包含完整OHLC数据（收盘指数）
- ✅ 新增资金流向数据
- ✅ 性能提升（数据库查询，不再实时计算）
- ✅ PE计算保持一致（市值加权平均）

---

## 7. 板块映射数据

### API端点: `GET /api/boards/list`

**返回格式**: `List[BoardMapping]`

**单个板块包含的字段**:

| 序号 | 字段名 | 类型 | 说明 | 更新频率 |
|------|--------|------|------|----------|
| 1 | `name` | str | 板块名称 | 不变 |
| 2 | `type` | str | 板块类型 (industry/concept) | 不变 |
| 3 | `code` | str | 板块代码 | 不变 |
| 4 | `stock_count` | int | 成分股数量 | 每月更新 |
| 5 | `last_updated` | datetime | 最后更新时间 | 每月更新 |

**板块数量**:
- 行业板块: 90个
- 概念板块: 442个
- **总计**: 532个板块

**板块映射SKU**: 532 × 5 = **2,660个SKU**

---

## 8. 总SKU汇总

### 单个Ticker
```
元数据:       13 个字段
K线数据:      600根 × 11字段 = 6,600 个字段
─────────────────────────
小计:         6,613 个SKU/ticker
```

### 全市场 (5000只股票)
```
股票元数据:     5,000 × 13 =          65,000
K线数据:        5,000 × 6,600 = 33,000,000
行业聚合:       90 × 13 =             1,170  ⭐ 已更新
板块映射:       532 × 5 =             2,660
─────────────────────────────────────────
总计:                          33,068,830 个SKU
```

---

## 9. 数据更新策略总结

### ✅ 推荐更新频率

| 数据类型 | 更新频率 | 更新时间 | API调用 | 存储增量 |
|---------|---------|---------|---------|----------|
| **静态元数据** | 首次 + 年度 | 上市/改名时 | 1次 | 65,000 SKU |
| **概念板块** | 每月 | 月初 | 442次 | 5,000 SKU |
| **每日指标** | 每天 | 盘后16:00 | 1次 | 25,000 SKU |
| **日线K线** | 每天 | 盘后16:00 | 5,000次 | 55,000 SKU |
| **周线K线** | 每周一 | 盘后16:00 | 5,000次 | 55,000 SKU |
| **月线K线** | 每月1号 | 盘后16:00 | 5,000次 | 55,000 SKU |

### ❌ 当前问题

1. **静态字段重复更新**: 每天调用`stock_basic` API (不必要)
2. **全量K线下载**: 每天下载200根K线，而不是1根 (浪费99.5%)
3. **周线/月线每日更新**: 即使不需要也每天下载 (浪费99.8%)

---

## 10. 数据库存储结构

### symbol_metadata 表
```python
ticker: str              # PK
name: str
list_date: str
industry_lv1: str
industry_lv2: str
industry_lv3: str
concepts: list           # JSON数组
total_mv: float
circ_mv: float
pe_ttm: float
pb: float
last_sync: datetime
```

**行数**: ~5,000行 (每只股票1行)

---

### candles 表
```python
id: int                  # PK
ticker: str              # FK
timeframe: enum          # day/week/month
timestamp: datetime
open: float
high: float
low: float
close: float
volume: float
turnover: float
ma5: float
ma10: float
ma20: float
ma50: float
```

**行数**: 5,000 × 200 × 3 = **3,000,000行** (当前)

**理想增长**:
- 日线: +5,000行/天
- 周线: +5,000行/周
- 月线: +5,000行/月

---

### board_mapping 表
```python
id: int                  # PK
board_name: str
board_type: str          # industry/concept
board_code: str
constituents: list       # JSON数组 ["000001", "600519", ...]
last_updated: datetime
```

**行数**: ~532行 (90个行业 + 442个概念)

---

### industry_daily 表 ⭐ **新增**
```python
id: int                      # PK
trade_date: str              # 交易日期 YYYYMMDD
ts_code: str                 # 板块代码
industry: str                # 板块名称

# 行情数据
close: float                 # 收盘指数
pct_change: float            # 指数涨跌幅

# 成分股统计
company_num: int             # 公司数量
up_count: int               # 上涨家数
down_count: int             # 下跌家数

# 领涨股信息
lead_stock: str             # 领涨股票名称
lead_stock_code: str        # 领涨股代码
pct_change_stock: float     # 领涨股涨跌幅
close_price: float          # 领涨股最新价

# 资金流向数据
net_buy_amount: float       # 流入资金(亿元)
net_sell_amount: float      # 流出资金(亿元)
net_amount: float           # 净额(亿元)

# 估值数据
industry_pe: float          # 行业PE（市值加权）
total_mv: float             # 总市值（万元）

created_at: datetime
updated_at: datetime
```

**行数**:
- 当前: 90行 (最新交易日的90个行业)
- 累积增长: +90行/天

**数据来源**: Tushare `moneyflow_ind_ths` 接口
**更新脚本**: `scripts/update_industry_daily.py`

---

## 11. 前端展示数据结构示例

### 单个Ticker的完整数据 (Key-Value)

```json
{
  "ticker": "000001",
  "name": "平安银行",
  "listDate": "19910403",
  "industryLv1": "银行",
  "industryLv2": null,
  "industryLv3": null,
  "concepts": ["银行概念", "金融科技", "数字货币"],
  "totalMv": 123456.78,
  "circMv": 98765.43,
  "peTtm": 5.67,
  "pb": 0.89,
  "lastUpdated": "2025-11-15T16:30:00Z",
  "eastmoneyBoard": ["银行"]
}
```

**SKU数量**: 13个字段

---

### K线数据

```json
{
  "ticker": "000001",
  "timeframe": "day",
  "candles": [
    {
      "timestamp": "2025-11-15T00:00:00Z",
      "open": 12.50,
      "high": 12.80,
      "low": 12.40,
      "close": 12.70,
      "volume": 1234567.0,
      "turnover": 15678900.0,
      "ma5": 12.60,
      "ma10": 12.55,
      "ma20": 12.50,
      "ma50": 12.45
    },
    // ... 199根历史K线
  ]
}
```

**SKU数量**: 200根 × 11字段 = 2,200个字段 (单个timeframe)

---

### 行业聚合数据 ⭐ **已更新**

```json
{
  "板块名称": "电网设备",
  "板块代码": "881267.TI",
  "股票数量": 123,
  "总市值": 148647000.0,
  "涨跌幅": 5.33,
  "上涨家数": 34,
  "下跌家数": 89,
  "行业PE": 43.77,
  "收盘指数": 15021.70,
  "领涨股": "保变电气",
  "领涨股涨跌幅": 9.99,
  "净流入资金": 3.50,
  "交易日期": "20251105"
}
```

**SKU数量**: 13个字段 ⭐ **从7个增加到13个**

**数据来源**: `industry_daily` 表（不再实时计算）

---

## 12. 优化建议

### 短期优化 (无需改表结构)

1. **添加增量更新逻辑**
   - 查询数据库中最新K线的timestamp
   - 仅下载从该时间点之后的新K线
   - 使用`append`而非`delete + insert`

2. **添加更新频率判断**
   ```python
   def should_update_timeframe(timeframe: Timeframe, today: datetime) -> bool:
       if timeframe == Timeframe.DAY:
           return True
       elif timeframe == Timeframe.WEEK:
           return today.weekday() == 0  # 周一
       elif timeframe == Timeframe.MONTH:
           return today.day == 1  # 月初
   ```

3. **分离静态和动态更新**
   ```python
   def refresh_universe(self, tickers, update_static=False):
       if update_static:
           # 完整更新 (首次或手动触发)
           metadata_df = self.provider.fetch_symbol_metadata(tickers)
       # 总是更新动态指标
       metrics_df = self.provider.fetch_daily_metrics(tickers)
   ```

---

### 长期优化 (拆分表结构)

**拆分表结构**:
```python
# 表1: 静态信息表
class SymbolStaticInfo:
    ticker: str              # PK
    name: str
    list_date: str
    industry_lv1: str
    industry_lv2: str
    industry_lv3: str
    concepts: list
    created_at: datetime
    updated_at: datetime

# 表2: 每日动态指标表
class SymbolDailyMetrics:
    id: int                  # PK
    ticker: str              # FK
    trade_date: datetime     # 交易日期
    close_price: float
    total_mv: float
    circ_mv: float
    pe_ttm: float
    pb: float
    turnover_rate: float
```

**优势**:
- ✅ 静态数据只下载一次
- ✅ 可查询历史PE/市值变化
- ✅ 数据结构清晰，职责分离
- ✅ 大幅减少API调用

---

## 总结

### 当前SKU统计
```
单个Ticker:     6,613 个SKU
全市场:     33,068,290 个SKU
  ├─ 元数据:        65,000
  ├─ K线数据:   33,000,000
  ├─ 行业聚合:         630
  └─ 板块映射:       2,660
```

### 更新频率建议
```
静态字段:    首次 + 年度更新
概念板块:    每月更新
动态指标:    每天更新
日线K线:     每天新增1根 (增量)
周线K线:     每周一新增1根
月线K线:     每月1号新增1根
```

### 优化收益
```
当前API调用:  3,000,002 次/天 (全量)
优化后调用:      5,001 次/天 (增量)
节省比例:       99.8% ⭐
```

---

**相关文件**:
- `src/schemas.py` - API数据模型定义
- `src/models.py` - 数据库表结构
- `src/api/routes_meta.py` - 元数据API端点
- `src/api/routes_candles.py` - K线数据API端点
- `src/api/routes_boards.py` - 板块映射API端点
- `docs/数据更新策略分析.md` - 更新策略详细分析
- `docs/数据字段更新策略.md` - 字段更新频率分析
