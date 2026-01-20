# Tushare 股票数据采集 PRD

## 📋 项目概述

### 目标
构建完整的 A 股市场数据采集系统，覆盖 5500+ 支股票的历史行情和每日指标数据。

### 数据范围
- **股票数量**: 5500+ 支 A 股
- **历史数据**: 200 根 K 线（日线/周线/月线）
- **每日更新**: PE、PB、市值等基本指标
- **预计存储**: ~240MB（未压缩）/ ~80-120MB（压缩）

---

## 🎯 核心数据需求

### 1. 基础数据（一次性获取）
- 股票列表（代码、名称、上市日期、行业等）
- 交易日历

### 2. 历史行情数据（一次性获取）
- 日线行情：200 根
- 周线行情：200 根
- 月线行情：200 根

### 3. 每日指标数据（每日更新）
- PE/PB/PS 估值指标
- 总市值/流通市值
- 换手率、成交量比

---

## 📡 Tushare API 接口详细说明

### 接口 1: stock_basic - 股票列表

**接口名称**: `stock_basic`

**功能**: 获取所有 A 股基础信息

**输入参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| ts_code | str | N | 股票代码 |
| name | str | N | 股票名称 |
| market | str | N | 市场类型（主板/创业板/科创板等） |
| list_status | str | N | 上市状态：L=上市 D=退市 P=暂停；默认 L |
| exchange | str | N | 交易所：SSE=上交所 SZSE=深交所 BSE=北交所 |
| is_hs | str | N | 是否沪深港通：N=否 H=沪股通 S=深股通 |

**输出字段**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| ts_code | str | TS 代码（如 000001.SZ） |
| symbol | str | 股票代码（如 000001） |
| name | str | 股票名称 |
| area | str | 地域 |
| industry | str | 行业 |
| fullname | str | 公司全称 |
| enname | str | 英文名称 |
| market | str | 市场类型 |
| list_date | str | 上市日期 YYYYMMDD |
| delist_date | str | 退市日期 |
| is_hs | str | 沪深港通标识 |

**调用示例**:
```python
import tushare as ts

pro = ts.pro_api('YOUR_TOKEN')

# 获取所有上市股票
df = pro.stock_basic(
    exchange='',
    list_status='L',
    fields='ts_code,symbol,name,area,industry,list_date'
)

print(f"股票总数: {len(df)}")
```

**使用建议**:
- 每天或每周更新一次即可
- 重点关注 `ts_code`（用于后续查询）和 `list_date`（判断上市时间）

---

### 接口 2: daily - 日线行情

**接口名称**: `daily`

**功能**: 获取 A 股日线行情数据

**输入参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| ts_code | str | N | 股票代码（支持逗号分隔的多股票） |
| trade_date | str | N | 交易日期 YYYYMMDD |
| start_date | str | N | 开始日期 YYYYMMDD |
| end_date | str | N | 结束日期 YYYYMMDD |

**输出字段**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| ts_code | str | 股票代码 |
| trade_date | str | 交易日期 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| pre_close | float | 昨收价（除权调整后） |
| change | float | 涨跌额 |
| pct_chg | float | 涨跌幅 (%) |
| vol | float | 成交量（手） |
| amount | float | 成交额（千元） |

**调用示例**:
```python
# 方式1: 获取单只股票的历史数据
df = pro.daily(
    ts_code='000001.SZ',
    start_date='20230101',
    end_date='20231231'
)

# 方式2: 获取多只股票
df = pro.daily(
    ts_code='000001.SZ,600000.SH',
    start_date='20230101',
    end_date='20231231'
)

# 方式3: 获取某日所有股票（适合每日更新）
df = pro.daily(trade_date='20231231')
```

**注意事项**:
- 此接口返回的是**未复权**数据
- 需要复权数据请使用 `pro.adj_factor()` 获取复权因子
- 单次查询建议不超过 5000 行

**获取 200 根 K 线的策略**:
```python
# 从今天往前推 300 个交易日（确保有 200+ 根）
import pandas as pd
from datetime import datetime, timedelta

end_date = datetime.now().strftime('%Y%m%d')
start_date = (datetime.now() - timedelta(days=450)).strftime('%Y%m%d')

df = pro.daily(
    ts_code='000001.SZ',
    start_date=start_date,
    end_date=end_date
)

# 取最近 200 根
df = df.head(200)
```

---

### 接口 3: weekly - 周线行情

**接口名称**: `weekly`

**功能**: 获取 A 股周线行情（每周最后一个交易日更新）

**输入参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| ts_code | str | N | 股票代码 |
| trade_date | str | N | 交易日期 YYYYMMDD |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

**输出字段**:
与日线接口相同：ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount

**调用示例**:
```python
# 按股票代码查询
df = pro.weekly(
    ts_code='000001.SZ',
    start_date='20180101',
    end_date='20231231',
    fields='ts_code,trade_date,open,high,low,close,vol,amount'
)

# 按交易日期查询（某周所有股票）
df = pro.weekly(
    trade_date='20231229',  # 周五
    fields='ts_code,trade_date,open,high,low,close,vol,amount'
)
```

**限制条件**:
- 单次最大 6000 行
- 需要至少 2000 积分

---

### 接口 4: monthly - 月线行情

**接口名称**: `monthly`

**功能**: 获取 A 股月线数据（每月最后一个交易日）

**输入参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| ts_code | str | N | 股票代码 |
| trade_date | str | N | 交易日期（月末最后一个交易日） |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

**输出字段**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| ts_code | str | 股票代码 |
| trade_date | str | 交易日期 |
| open | float | 月开盘价 |
| high | float | 月最高价 |
| low | float | 月最低价 |
| close | float | 月收盘价 |
| pre_close | float | 上月收盘价 |
| change | float | 月涨跌额 |
| pct_chg | float | 月涨跌幅（未复权） |
| vol | float | 月成交量（手） |
| amount | float | 月成交额（千元） |

**调用示例**:
```python
# 按股票代码查询
df = pro.monthly(
    ts_code='000001.SZ',
    start_date='20180101',
    end_date='20231231',
    fields='ts_code,trade_date,open,high,low,close,vol,amount'
)

# 按月末日期查询
df = pro.monthly(
    trade_date='20231229',  # 月末最后交易日
    fields='ts_code,trade_date,open,high,low,close,vol,amount'
)
```

**限制条件**:
- 单次最大 4500 行
- 需要至少 2000 积分

---

### 接口 5: daily_basic - 每日指标（重要！）

**接口名称**: `daily_basic`

**功能**: 获取每日估值指标和市值数据

**输入参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| ts_code | str | Y | 股票代码（与 trade_date 二选一） |
| trade_date | str | Y | 交易日期 YYYYMMDD（与 ts_code 二选一） |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

**输出字段**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| ts_code | str | 股票代码 |
| trade_date | str | 交易日期 |
| close | float | 当日收盘价 |
| turnover_rate | float | 换手率 (%) |
| turnover_rate_f | float | 换手率（自由流通股） |
| volume_ratio | float | 量比 |
| pe | float | 市盈率（总市值/净利润） |
| pe_ttm | float | 市盈率 TTM |
| pb | float | 市净率 |
| ps | float | 市销率 |
| ps_ttm | float | 市销率 TTM |
| dv_ratio | float | 股息率 (%) |
| dv_ttm | float | 股息率 TTM (%) |
| total_share | float | 总股本（万股） |
| float_share | float | 流通股本（万股） |
| free_share | float | 自由流通股本（万股） |
| total_mv | float | **总市值（万元）** ⭐ |
| circ_mv | float | **流通市值（万元）** ⭐ |

**调用示例**:
```python
# 方式1: 获取某日所有股票的指标（推荐用于每日更新）
df = pro.daily_basic(
    ts_code='',
    trade_date='20231229',
    fields='ts_code,trade_date,pe,pe_ttm,pb,ps,total_mv,circ_mv'
)

# 方式2: 获取单只股票的历史指标
df = pro.daily_basic(
    ts_code='000001.SZ',
    start_date='20230101',
    end_date='20231231',
    fields='ts_code,trade_date,pe,pe_ttm,pb,total_mv'
)
```

**核心字段说明**:
- **pe_ttm**: 市盈率（滚动 12 个月），比 pe 更准确
- **total_mv**: 总市值 = 股价 × 总股本，单位**万元**
- **circ_mv**: 流通市值 = 股价 × 流通股本
- **turnover_rate**: 换手率 = 成交量 / 流通股本

**注意事项**:
- `ts_code` 和 `trade_date` **必须提供其中一个**
- 获取所有股票时设置 `ts_code=''`（空字符串）
- 单次查询建议按日期查询，避免超时

---

## 💾 数据存储方案

### 方案 1: SQLite 数据库（推荐）

**优点**:
- 无需安装额外服务
- 支持 SQL 查询
- 自动索引优化
- 压缩率高

**表结构设计**:

```sql
-- 股票列表表
CREATE TABLE stocks (
    ts_code TEXT PRIMARY KEY,
    symbol TEXT,
    name TEXT,
    area TEXT,
    industry TEXT,
    list_date TEXT,
    INDEX idx_symbol (symbol)
);

-- 日线行情表
CREATE TABLE daily_price (
    ts_code TEXT,
    trade_date TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    pre_close REAL,
    change REAL,
    pct_chg REAL,
    vol REAL,
    amount REAL,
    PRIMARY KEY (ts_code, trade_date),
    INDEX idx_date (trade_date)
);

-- 周线行情表
CREATE TABLE weekly_price (
    ts_code TEXT,
    trade_date TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    vol REAL,
    amount REAL,
    PRIMARY KEY (ts_code, trade_date)
);

-- 月线行情表
CREATE TABLE monthly_price (
    ts_code TEXT,
    trade_date TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    vol REAL,
    amount REAL,
    PRIMARY KEY (ts_code, trade_date)
);

-- 每日指标表
CREATE TABLE daily_basic (
    ts_code TEXT,
    trade_date TEXT,
    close REAL,
    pe REAL,
    pe_ttm REAL,
    pb REAL,
    ps REAL,
    total_mv REAL,
    circ_mv REAL,
    turnover_rate REAL,
    PRIMARY KEY (ts_code, trade_date),
    INDEX idx_date (trade_date)
);
```

### 方案 2: Parquet 文件（数据分析场景）

**优点**:
- 列式存储，查询快
- 压缩率极高（70%+）
- 与 Pandas 无缝集成

**文件组织**:
```
data/
├── stocks.parquet          # 股票列表
├── daily/
│   ├── 000001.SZ.parquet
│   ├── 000002.SZ.parquet
│   └── ...
├── weekly/
│   └── ...
├── monthly/
│   └── ...
└── daily_basic/
    └── ...
```

### 方案 3: CSV 文件（简单场景）

**适用**: 小规模数据、快速原型

**缺点**: 无索引、查询慢、占用空间大

---

## 🔄 数据更新策略

### 首次全量下载

```python
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta

pro = ts.pro_api('YOUR_TOKEN')

# 1. 获取股票列表
stocks = pro.stock_basic(exchange='', list_status='L')
print(f"股票总数: {len(stocks)}")

# 2. 计算日期范围（确保有 200+ 根 K 线）
end_date = datetime.now().strftime('%Y%m%d')
start_date = (datetime.now() - timedelta(days=450)).strftime('%Y%m%d')

# 3. 循环下载每只股票
for ts_code in stocks['ts_code']:
    try:
        # 日线
        daily = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        # 周线
        weekly = pro.weekly(ts_code=ts_code, start_date=start_date, end_date=end_date)
        # 月线
        monthly = pro.monthly(ts_code=ts_code, start_date=start_date, end_date=end_date)
        # 每日指标
        basic = pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date)

        # 保存到数据库或文件
        # ...

    except Exception as e:
        print(f"下载失败: {ts_code}, 错误: {e}")
        continue
```

### 每日增量更新

```python
from datetime import datetime

# 获取当前交易日
today = datetime.now().strftime('%Y%m%d')

# 1. 更新日线（所有股票）
daily = pro.daily(trade_date=today)

# 2. 更新每日指标（所有股票）
basic = pro.daily_basic(ts_code='', trade_date=today)

# 3. 如果是周五，更新周线
if datetime.now().weekday() == 4:
    weekly = pro.weekly(trade_date=today)

# 4. 如果是月末，更新月线
# （判断是否为当月最后一个交易日）
```

---

## ⚠️ API 使用限制与注意事项

### 积分要求
| 接口 | 所需积分 |
|------|---------|
| stock_basic | 无限制 |
| daily | 无限制 |
| weekly | 2000 |
| monthly | 2000 |
| daily_basic | 无限制 |

### 调用频率限制
- **普通用户**: 200 次/分钟
- **高级用户**: 根据积分等级提升

### 单次查询限制
- daily: 建议不超过 5000 行
- weekly: 最大 6000 行
- monthly: 最大 4500 行

### 避免超限技巧
1. **分批查询**: 按股票或日期分批
2. **增加延迟**: 每次请求间隔 0.3-0.5 秒
3. **异常重试**: 捕获异常后等待 1 秒重试

```python
import time

def safe_request(func, *args, **kwargs):
    """安全请求包装器"""
    max_retries = 3
    for i in range(max_retries):
        try:
            result = func(*args, **kwargs)
            time.sleep(0.3)  # 避免触发频率限制
            return result
        except Exception as e:
            if i == max_retries - 1:
                raise e
            print(f"请求失败，重试 {i+1}/{max_retries}: {e}")
            time.sleep(1)
```

---

## 📊 数据质量检查

### 必要检查项

1. **数据完整性**
   - 检查每只股票是否都有 200 根 K 线
   - 检查交易日期是否连续（排除停牌）

2. **数据一致性**
   - 验证 daily_basic.close 与 daily.close 是否一致
   - 检查涨跌幅计算是否正确：`(close - pre_close) / pre_close * 100`

3. **异常值检测**
   - PE 为负数或超大值（如 > 1000）
   - 涨跌幅超过 ±20%（可能是 ST 股票）
   - 成交量为 0（停牌）

```python
# 示例：数据质量检查
def check_data_quality(df):
    """检查日线数据质量"""
    issues = []

    # 检查缺失值
    if df.isnull().any().any():
        issues.append("存在缺失值")

    # 检查价格异常
    if (df['close'] <= 0).any():
        issues.append("存在负价格或零价格")

    # 检查涨跌幅计算
    calculated_pct = (df['close'] - df['pre_close']) / df['pre_close'] * 100
    diff = abs(calculated_pct - df['pct_chg'])
    if (diff > 0.01).any():
        issues.append("涨跌幅计算不一致")

    return issues
```

---

## 🚀 实施计划

### 阶段 1: 环境准备（Day 1）
- [ ] 注册 Tushare 账号并获取 Token
- [ ] 安装依赖：`pip install tushare pandas sqlalchemy`
- [ ] 创建数据库或文件存储目录

### 阶段 2: 基础数据下载（Day 1）
- [ ] 下载股票列表（~5500 只）
- [ ] 下载交易日历

### 阶段 3: 历史数据下载（Day 2-3）
- [ ] 分批下载日线数据（200 根 × 5500 只）
- [ ] 下载周线数据
- [ ] 下载月线数据
- [ ] 下载 daily_basic 历史数据

### 阶段 4: 数据验证（Day 4）
- [ ] 运行数据质量检查
- [ ] 修复异常数据
- [ ] 统计覆盖率

### 阶段 5: 自动化更新（Day 5）
- [ ] 编写每日更新脚本
- [ ] 设置定时任务（crontab 或 Windows 计划任务）
- [ ] 测试增量更新逻辑

---

## 📚 参考资源

- **Tushare 官方文档**: https://tushare.pro/document/2
- **积分获取指南**: https://tushare.pro/document/1?doc_id=13
- **API 调用示例**: https://tushare.pro/document/1?doc_id=130

---

## 🔧 常见问题

### Q1: 如何获取 Tushare Token？
A: 访问 https://tushare.pro 注册账号，在用户中心可以查看 Token。

### Q2: 积分不足怎么办？
A: 通过分享、签到、捐赠等方式获取积分。详见积分获取指南。

### Q3: 下载 5500 只股票需要多久？
A:
- 单线程：约 2-3 小时（每只股票 1-2 秒）
- 多线程（5 并发）：约 30-40 分钟

### Q4: 数据是否包含复权？
A: daily/weekly/monthly 接口返回的是**未复权**数据。如需复权，请：
1. 使用 `adj_factor` 接口获取复权因子
2. 自行计算：`复权价 = 原始价 × 复权因子`

### Q5: 如何处理停牌股票？
A: 停牌期间 Tushare 不会返回数据。建议：
- 按日期范围查询时，缺失的日期视为停牌
- 使用前一交易日的收盘价填充（forward fill）

---

## 📝 更新日志

- **2025-11-14**: 初始版本，包含 5 个核心接口的完整说明
