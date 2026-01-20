# 数据字段更新策略

**创建日期**: 2025-11-15
**目标**: 区分静态字段和动态字段，优化数据更新效率

---

## 问题3: 静态字段 vs 动态字段

### 当前问题

**代码位置**: `src/services/data_pipeline.py:165-180`

目前系统每次refresh都会更新**所有字段**，包括：
```python
# 每次都更新这些字段（包括不变的静态字段）
instance.name = row.name                      # ← 静态字段，不应每天更新
instance.list_date = row.list_date            # ← 静态字段，不应每天更新
instance.industry_lv1 = row.industry_lv1      # ← 静态字段，不应每天更新
instance.total_mv = row.total_mv              # ← 动态字段，需要每天更新 ✓
instance.pe_ttm = row.pe_ttm                  # ← 动态字段，需要每天更新 ✓
```

**问题**: 浪费API调用和计算资源

---

## 字段分类详解

### 📌 静态字段（一次性下载，极少变化）

| 字段 | 类型 | 说明 | 更新频率 | API来源 |
|------|------|------|----------|---------|
| `ticker` | str | 股票代码 | **不变** | stock_basic |
| `name` | str | 股票名称 | **极少变** (改名) | stock_basic |
| `list_date` | str | 上市日期 YYYYMMDD | **不变** | stock_basic |
| `industry_lv1` | str | 一级行业 | **年度更新** | stock_basic.industry |
| `industry_lv2` | str | 二级行业 | **年度更新** | (未使用) |
| `industry_lv3` | str | 三级行业 | **年度更新** | (未使用) |
| `concepts` | list | 概念板块 | **月度更新** | board_mapping |

**建议更新频率**:
- **首次下载**: 下载所有静态字段
- **日常更新**: **不更新**
- **触发更新**: 仅当股票改名、行业调整时手动更新

---

### 📈 动态字段（随股价波动，需每日更新）

| 字段 | 类型 | 说明 | 更新频率 | API来源 |
|------|------|------|----------|---------|
| `total_mv` | float | 总市值（万元） | **每日** | daily_basic |
| `circ_mv` | float | 流通市值（万元） | **每日** | daily_basic |
| `pe_ttm` | float | 市盈率 TTM | **每日** | daily_basic |
| `pb` | float | 市净率 | **每日** | daily_basic |
| `close_price` | float | 收盘价 | **每日** | daily (K线) |
| `last_sync` | datetime | 最后同步时间 | **每日** | 系统生成 |

**建议更新频率**: **每天盘后更新**

---

### 📊 行业聚合字段 ⭐ **新增 - 存储在独立表**

| 字段 | 类型 | 说明 | 更新频率 | 数据来源 |
|------|------|------|----------|---------|
| `industry` | str | 行业名称 | **每日** | industry_daily 表 |
| `ts_code` | str | 板块代码 | **每日** | industry_daily 表 |
| `close` | float | 板块收盘指数 | **每日** | moneyflow_ind_ths |
| `pct_change` | float | 板块涨跌幅 | **每日** | moneyflow_ind_ths |
| `company_num` | int | 成分股数量 | **每日** | moneyflow_ind_ths |
| `up_count` | int | 上涨家数 | **每日** | 计算得出 |
| `down_count` | int | 下跌家数 | **每日** | 计算得出 |
| `industry_pe` | float | 行业PE（加权） | **每日** | 计算得出 |
| `total_mv` | float | 行业总市值 | **每日** | 计算得出 |
| `net_amount` | float | 净流入资金 | **每日** | moneyflow_ind_ths |
| `lead_stock` | str | 领涨股 | **每日** | moneyflow_ind_ths |

**建议更新频率**: **每天盘后更新**

**更新脚本**: `scripts/update_industry_daily.py`

**数据流程**:
1. 从Tushare获取90个行业的资金流向数据（`moneyflow_ind_ths`）
2. 计算每个行业的上涨/下跌家数（查询candle表）
3. 计算行业PE（市值加权平均）
4. 保存到 `industry_daily` 表
5. API直接从数据库读取（不再实时计算）

**优势**:
- ✅ 涨跌幅更准确（基于板块指数）
- ✅ 性能大幅提升（数据库查询 vs 实时计算）
- ✅ 包含资金流向等额外数据
- ✅ 可追溯历史数据

---

## 优化方案

### 方案1: 分离静态和动态表 ⭐ 推荐

**拆分表结构**:
```python
# 表1: 静态信息表 (symbol_static_info)
class SymbolStaticInfo(Base):
    ticker: str              # PK
    name: str               # 股票名称
    list_date: str          # 上市日期
    industry_lv1: str       # 行业分类
    industry_lv2: str
    industry_lv3: str
    concepts: list          # 概念板块
    created_at: datetime
    updated_at: datetime    # 用于追踪变更

# 表2: 每日动态指标表 (symbol_daily_metrics)
class SymbolDailyMetrics(Base):
    id: int                 # PK
    ticker: str             # FK
    trade_date: datetime    # 交易日期
    close_price: float      # 收盘价
    total_mv: float         # 总市值
    circ_mv: float          # 流通市值
    pe_ttm: float           # PE
    pb: float               # PB
    turnover_rate: float    # 换手率
```

**优势**:
- ✅ 静态数据只下载一次
- ✅ 可查询历史PE/市值变化
- ✅ 数据结构清晰，职责分离
- ✅ 大幅减少API调用

---

### 方案2: 添加更新策略标记

**在当前表结构基础上优化**:
```python
class SymbolMetadata(Base):
    # ... 所有字段 ...

    # 新增字段
    static_info_updated_at: datetime  # 静态信息最后更新时间
    metrics_updated_at: datetime      # 动态指标最后更新时间

def refresh_universe(self, tickers, update_static=False):
    """
    update_static=True: 更新所有字段 (首次下载或手动全量更新)
    update_static=False: 仅更新动态字段 (日常增量更新)
    """
    for ticker in tickers:
        if update_static:
            # 下载静态字段 (stock_basic) + 动态字段 (daily_basic)
            metadata = fetch_full_metadata(ticker)
        else:
            # 仅下载动态字段 (daily_basic)
            metadata = fetch_dynamic_metrics_only(ticker)
```

---

## 当前API调用分析

### Tushare Pro API接口

#### stock_basic - 股票基本信息
**调用频率**: 首次下载 + 年度更新

**返回字段**:
```python
{
    'ts_code': '000001.SZ',
    'symbol': '000001',
    'name': '平安银行',          # ← 静态
    'area': '深圳',              # ← 静态
    'industry': '银行',           # ← 静态（年度变化）
    'list_date': '19910403'      # ← 静态
}
```

**API成本**: 1次调用返回所有A股（5000+只）

---

#### daily_basic - 每日指标
**调用频率**: 每日盘后

**返回字段**:
```python
{
    'ts_code': '000001.SZ',
    'trade_date': '20251115',
    'close': 12.34,              # ← 收盘价
    'total_mv': 123456.78,       # ← 总市值（万元）
    'circ_mv': 98765.43,         # ← 流通市值（万元）
    'pe_ttm': 5.67,              # ← PE (动态)
    'pb': 0.89,                  # ← PB (动态)
    'turnover_rate': 1.23        # ← 换手率
}
```

**API成本**:
- 方式1: 按trade_date查询所有股票 → **1次调用** ⭐
- 方式2: 按ts_code逐个查询 → 5000次调用 ❌

**当前实现**: ✅ 已优化为按trade_date批量查询（1次）

---

## 更新成本对比

### 当前方式（全量更新）

**每天的API调用**:
```
stock_basic: 1次 (获取静态信息，不必要)
daily_basic: 1次 (获取动态指标，必要)
总计: 2次
```

**下载字段**: 静态 + 动态（全部）

**浪费**:
- 每天重复下载不变的静态字段
- 占用网络带宽和处理时间

---

### 优化方式（分离更新）

**首次下载（First Time）**:
```
stock_basic: 1次 (5000只股票)
daily_basic: 1次 (5000只股票)
总计: 2次
```

**日常更新（Daily Incremental）**:
```
stock_basic: 0次 (不调用) ✅
daily_basic: 1次 (仅当日数据) ✅
总计: 1次
```

**节省**: 每天减少1次API调用（节省50%）

---

## 实施建议

### 阶段1: 短期优化（无需改表结构）

**修改 `refresh_universe` 方法**:
```python
def refresh_universe(self, tickers, update_static=False):
    if update_static:
        # 完整更新（首次或手动触发）
        metadata_df = self.provider.fetch_symbol_metadata(tickers)
        self._persist_metadata(session, metadata_df)

    # 总是更新动态指标
    metrics_df = self.provider.fetch_daily_metrics(tickers)
    self._update_metrics(session, metrics_df)
```

**新增方法**: `fetch_daily_metrics`
```python
def fetch_daily_metrics(self, tickers):
    """仅获取动态指标，不获取静态信息"""
    daily_basic_df = self.client.fetch_daily_basic(trade_date=latest_date)
    return daily_basic_df[['ts_code', 'total_mv', 'circ_mv', 'pe_ttm', 'pb']]
```

---

### 阶段2: 长期优化（拆分表结构）

**迁移步骤**:
1. 创建新表 `symbol_static_info` 和 `symbol_daily_metrics`
2. 将现有数据迁移到新表
3. 修改API返回格式，合并两表数据
4. 删除旧表 `symbol_metadata`

**数据迁移脚本**:
```python
# 1. 复制静态字段
INSERT INTO symbol_static_info (ticker, name, list_date, industry_lv1)
SELECT ticker, name, list_date, industry_lv1 FROM symbol_metadata;

# 2. 复制动态字段（仅最新一天）
INSERT INTO symbol_daily_metrics (ticker, trade_date, total_mv, pe_ttm, ...)
SELECT ticker, CURRENT_DATE, total_mv, pe_ttm, ... FROM symbol_metadata;
```

---

## 总结

### ✅ 确认结论

**当前系统每次都更新所有字段，包括不变的静态字段**

**不变字段**:
- ticker (股票代码)
- name (股票名称，极少变)
- list_date (上市日期)
- industry (行业分类，年度变化)

**每日变化字段**:
- total_mv (总市值)
- circ_mv (流通市值)
- pe_ttm (市盈率)
- pb (市净率)

### 🎯 优化建议

1. **短期**: 添加 `update_static` 参数，日常更新时仅获取动态指标
2. **长期**: 拆分表结构，静态和动态字段分开存储
3. **收益**: 减少50%的API调用，加快更新速度

---

**相关文件**:
- `src/services/data_pipeline.py:165-180`
- `src/services/tushare_data_provider.py:173-290`
- `src/models.py:34-65`
