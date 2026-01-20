# 数据来源与计算逻辑

本文档记录系统中所有数据的来源API接口以及计算逻辑。

## 1. 基础股票数据

### 1.1 股票列表和基本信息

**数据来源**: Tushare Pro API `stock_basic`

**接口调用**:
```python
pro.stock_basic(
    exchange='',
    list_status='L',
    fields='ts_code,symbol,name,area,industry,market,list_date'
)
```

**返回字段**:
- `ts_code`: 股票代码（如 000001.SZ）
- `symbol`: 股票代码（如 000001）
- `name`: 股票名称
- `area`: 地区
- `industry`: Tushare基础行业分类（41个行业，已弃用）
- `market`: 市场（主板/创业板/科创板）
- `list_date`: 上市日期

**存储位置**: `symbol_metadata` 表

---

### 1.2 股票实时行情数据

**数据来源**: Tushare Pro API `daily`

**接口调用**:
```python
pro.daily(
    ts_code=ts_code,
    trade_date=trade_date,
    fields='ts_code,trade_date,open,high,low,close,vol,amount'
)
```

**返回字段**:
- `ts_code`: 股票代码
- `trade_date`: 交易日期（YYYYMMDD格式）
- `open`: 开盘价
- `high`: 最高价
- `low`: 最低价
- `close`: 收盘价
- `vol`: 成交量（手）
- `amount`: 成交额（千元）

**存储位置**: `candles` 表（timeframe='DAY'）

---

### 1.3 股票财务指标（PE/PB/市值）

**数据来源**: Tushare Pro API `daily_basic`

**接口调用**:
```python
pro.daily_basic(
    ts_code=ts_code,
    trade_date=trade_date,
    fields='ts_code,trade_date,turnover_rate,pe_ttm,pb,total_mv,circ_mv'
)
```

**返回字段**:
- `turnover_rate`: 换手率（%）
- `pe_ttm`: 市盈率（TTM，滚动12个月）
- `pb`: 市净率
- `total_mv`: 总市值（万元）
- `circ_mv`: 流通市值（万元）

**存储位置**: `symbol_metadata` 表
- `turnover_rate_pct` → turnover_rate
- `pe_ttm` → pe_ttm
- `pb` → pb
- `total_mv` → total_mv
- `circ_mv` → circ_mv

---

## 2. 行业分类数据

### 2.1 同花顺90个核心行业

**数据来源**: TuShare Pro

- 行业列表：`moneyflow_ind_ths(trade_date=latest)`（字段包含 `ts_code`, `industry`）
- 成分股：`ths_member(ts_code=行业代码)`

**实现流程**（`scripts/map_stocks_to_core_industries.py`）:
1. 获取最新交易日 (`TushareClient.get_latest_trade_date`)
2. 调用 `moneyflow_ind_ths(trade_date)` 拉取 90 个核心行业列表
3. 针对每个行业 `ts_code` 调用 `ths_member(ts_code)` 获取所有成分股
4. 将 `con_code/code` 去除后缀并标准化为 6 位代码，构建 `ticker → 行业名称` 映射
5. 批量更新 `symbol_metadata.industry_lv1`

**存储位置**:
- `symbol_metadata.industry_lv1`（一级行业名称）
- `symbol_metadata.industry_lv2` / `industry_lv3` 预留但未使用
- 行业代码暂存于 CSV（`data/ths_core_industries.csv`），数据库未单独存储

---

### 2.2 行业成分股映射

**数据来源**: Tushare Pro API `ths_member`

**接口调用**:
```python
pro.ths_member(
    ts_code=board_code,  # 如 881126.TI
    trade_date=trade_date
)
```

**返回字段**:
- `ts_code`: 行业代码
- `code`: 股票代码（需转换为 ts_code 格式）
- `name`: 股票名称

**映射逻辑**:
```python
# 每只股票只属于一个行业（先到先得）
if ticker not in stock_industry_map:
    stock_industry_map[ticker] = board_name
```

**执行脚本**: `scripts/map_stocks_to_core_industries.py`

---

## 3. 周K线和月K线数据

### 3.1 周K线数据

**数据来源**: Tushare Pro API `weekly`

**接口调用**:
```python
pro.weekly(
    ts_code=ts_code,
    start_date=start_date,
    end_date=end_date,
    fields='ts_code,trade_date,open,high,low,close,vol,amount'
)
```

**存储位置**: `candles` 表（timeframe='WEEK'）

---

### 3.2 月K线数据

**数据来源**: Tushare Pro API `monthly`

**接口调用**:
```python
pro.monthly(
    ts_code=ts_code,
    start_date=start_date,
    end_date=end_date,
    fields='ts_code,trade_date,open,high,low,close,vol,amount'
)
```

**存储位置**: `candles` 表（timeframe='MONTH'）

---

## 4. 计算指标

### 4.1 行业涨跌幅

**计算逻辑**: 基于行业内所有股票的日涨跌幅取平均值

**数据来源**:
- 最新2根日K线（`candles` 表，timeframe='DAY'）

**计算公式**:
```python
# 单个股票的涨跌幅
change_pct = ((latest.close - prev.close) / prev.close) * 100

# 行业平均涨跌幅
industry_change = sum(stock_changes) / len(stock_changes)
```

**实现位置**: `src/api/routes_meta.py:62-78`

**API返回字段**: `涨跌幅` (float)

---

### 4.2 行业上涨/下跌家数

**计算逻辑**: 统计行业内股票的涨跌情况

**数据来源**:
- 最新2根日K线（`candles` 表，timeframe='DAY'）

**计算公式**:
```python
change_pct = ((latest.close - prev.close) / prev.close) * 100

if change_pct > 0:
    up_count += 1
elif change_pct < 0:
    down_count += 1
```

**实现位置**: `src/api/routes_meta.py:74-77`

**API返回字段**:
- `上涨家数` (int)
- `下跌家数` (int)

---

### 4.3 行业PE（市盈率）

**计算逻辑**: 使用市值加权平均法计算行业整体PE

**数据来源**:
- 个股PE（`symbol_metadata.pe_ttm`）
- 个股总市值（`symbol_metadata.total_mv`）

**计算公式**:
```python
# 市值加权PE计算
industry_pe = Σ(individual_pe × market_cap) / Σ(market_cap)

# 伪代码
weighted_pe_sum = 0
weighted_mv_sum = 0

for stock in industry_stocks:
    if stock.pe_ttm > 0 and stock.total_mv > 0:
        weighted_pe_sum += stock.pe_ttm * stock.total_mv
        weighted_mv_sum += stock.total_mv

if weighted_mv_sum > 0:
    industry_pe = round(weighted_pe_sum / weighted_mv_sum, 2)
```

**为什么使用市值加权**:
- 简单平均会让小市值股票和大市值股票权重相同
- 市值加权更能反映行业整体估值水平
- 大市值股票对行业估值影响更大，符合实际情况

**实现位置**: `src/api/routes_meta.py:56-90`

**API返回字段**: `行业PE` (float | null)

**特殊情况处理**:
- 如果行业内没有股票有有效PE数据，返回 `null`
- PE为负数的股票不参与计算（亏损企业）
- PE为0的股票不参与计算（数据异常）

**示例结果**:
- 保险: PE 7.09（低估值行业）
- 银行: PE 7.68（低估值行业）
- 中药: PE 391.74（高估值/高成长行业）
- 计算机设备: PE 389.61（高估值/高成长行业）

---

### 4.4 行业总市值

**计算逻辑**: 行业内所有股票总市值之和

**数据来源**:
- 个股总市值（`symbol_metadata.total_mv`，单位：万元）

**计算公式**:
```python
industry_total_mv = Σ(stock.total_mv)
```

**实现位置**: `src/api/routes_meta.py:52-53`

**API返回字段**: `总市值` (float, 单位：万元)

---

## 5. API端点汇总

### 5.1 GET `/api/symbols`

**功能**: 返回所有股票的元数据列表

**返回字段**:
- ticker (股票代码)
- name (股票名称)
- industry_lv1 (一级行业)
- industry_lv2 (二级行业，可能为空)
- industry_lv3 (三级行业，可能为空)
- pe_ttm (市盈率TTM)
- pb (市净率)
- total_mv (总市值)
- circ_mv (流通市值)
- turnover_rate_pct (换手率)

**数据来源**: `symbol_metadata` 表

**排序**: 按总市值降序

---

### 5.2 GET `/api/symbols/industries`

**功能**: 返回所有行业的汇总数据

**返回字段**:
```json
{
  "板块名称": "保险",
  "股票数量": 12,
  "总市值": 123456.78,
  "涨跌幅": 1.23,
  "上涨家数": 8,
  "下跌家数": 4,
  "行业PE": 7.09
}
```

**数据来源**:
- `板块名称`: symbol_metadata.industry_lv1
- `股票数量`: count(stocks)
- `总市值`: Σ(symbol_metadata.total_mv) - **计算得出**
- `涨跌幅`: avg(stock_change_pct) - **计算得出**
- `上涨家数`: count(change_pct > 0) - **计算得出**
- `下跌家数`: count(change_pct < 0) - **计算得出**
- `行业PE`: weighted_avg(pe_ttm) - **计算得出**

**排序**: 按涨跌幅降序

**实现位置**: `src/api/routes_meta.py:19-108`

---

## 6. 数据更新频率

### 6.1 日K线数据
- **更新频率**: 每个交易日收盘后
- **更新脚本**: `scripts/download_sample_data.py` 或 `scripts/download_all_data.py`
- **更新时间**: 建议在交易日16:00之后

### 6.2 股票基本信息
- **更新频率**: 每周一次
- **更新原因**: 新股上市、退市等变动较少

### 6.3 财务指标（PE/PB/市值）
- **更新频率**: 每个交易日收盘后
- **更新脚本**: 与日K线数据同步更新

### 6.4 行业分类映射
- **更新频率**: 每月一次或按需更新
- **更新脚本**: `scripts/map_stocks_to_core_industries.py`
- **更新原因**: 行业成分股调整

---

## 7. 数据质量说明

### 7.1 可能的数据缺失
- 新股上市初期可能没有PE数据（尚未发布财报）
- 部分股票可能没有行业分类（未被同花顺纳入行业体系）
- ST股票可能PE为负数（亏损状态）

### 7.2 数据准确性
- 所有原始数据均来自Tushare Pro官方接口
- 计算指标使用标准金融公式
- 市值加权法广泛应用于指数编制和行业分析

### 7.3 数据一致性
- 同一交易日的所有数据来自同一时间点
- 行业分类使用统一的同花顺90核心行业体系
- 每只股票只属于一个行业，避免重复计算

---

## 8. 参考文档

- [Tushare Pro 官方文档](https://tushare.pro/document/2)
- [股票日线行情 API](https://tushare.pro/document/2?doc_id=27)
- [每日指标 API](https://tushare.pro/document/2?doc_id=32)
- [同花顺概念和行业 API](https://tushare.pro/document/2?doc_id=261)
- [周/月线数据 API](https://tushare.pro/document/2?doc_id=144)

---

**最后更新**: 2025-11-15
**维护者**: 系统开发团队
