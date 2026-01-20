# 板块分类系统总览

**创建日期**: 2025-11-15
**数据源**: Tushare Pro + 同花顺 + 东方财富

---

## 📊 分类系统汇总

| 编号 | 分类系统 | 数量 | 类型 | 数据源 | 文件位置 | 当前状态 |
|------|---------|------|------|--------|----------|---------|
| 1 | **同花顺90行业（资金流向）** ⭐ | **90个** | Industry | 同花顺 | `industry_daily` 表 | ✅ **主力使用** |
| 2 | 同花顺全部板块指数 | 1,234个 | 混合 | 同花顺 | `data/ths_all_indexes.csv` | ✅ 已下载 |
| 2.1 | └─ 概念指数 | 406个 | Concept | 同花顺 | ↑ | 📊 可用 |
| 2.2 | └─ 行业指数 | 594个 | Industry | 同花顺 | ↑ | 📊 可用 |
| 2.3 | └─ 地域指数 | 33个 | Region | 同花顺 | ↑ | 📊 可用 |
| 2.4 | └─ 特色指数 | 124个 | Special | 同花顺 | ↑ | 📊 可用 |
| 2.5 | └─ 风格指数 | 21个 | Style | 同花顺 | ↑ | 📊 可用 |
| 2.6 | └─ 主题指数 | 10个 | Theme | 同花顺 | ↑ | 📊 可用 |
| 2.7 | └─ 宽基指数 | 46个 | Broad | 同花顺 | ↑ | 📊 可用 |
| 3 | **东方财富概念板块** | **559个** | Concept | 东方财富 | `data/dc_concept_boards.csv` | ✅ 已下载 |
| 4 | 东方财富行业板块 | 86个 | Industry | 东方财富 | `data/industry_boards_em.csv` | ⚠️ 已弃用 |
| 5 | Tushare申万行业 | 227个 | Industry | Tushare | API | ⚠️ 未启用 |

**总计**: 2,196个板块分类（不含重复）

---

## 详细说明

### 1. 同花顺90行业（资金流向） ⭐ 主要使用

**数据源**: Tushare Pro API (`moneyflow_ind_ths` 接口)
**存储位置**: 数据库表 `industry_daily`

**数据格式**:
```python
# industry_daily 表字段
{
    "trade_date": "20251115",           # 交易日期
    "ts_code": "881126.TI",             # 板块代码
    "industry": "汽车零部件",            # 板块名称
    "close": 1234.56,                   # 收盘指数
    "pct_change": 2.34,                 # 涨跌幅（基于板块指数）
    "company_num": 280,                 # 成分股数量
    "up_count": 150,                    # 上涨家数（计算得出）
    "down_count": 130,                  # 下跌家数（计算得出）
    "industry_pe": 25.67,               # 行业PE（市值加权）
    "total_mv": 1234567.89,             # 行业总市值
    "net_amount": 12345.67,             # 净流入资金
    "lead_stock": "比亚迪",              # 领涨股
    "pct_change_stock": 5.67            # 领涨股涨跌幅
}
```

**特点**:
- ✅ **精选90个核心行业**，覆盖主要产业
- ✅ 包含板块指数OHLC数据（准确的涨跌幅）
- ✅ 包含资金流向数据（净流入/流出）
- ✅ 包含领涨股信息
- ✅ 自动计算上涨/下跌家数
- ✅ 市值加权平均PE（准确的估值指标）
- ✅ 数据库存储，前端直接读取（性能优化）

**用途**:
- 前端首页展示行业涨跌幅排名
- 行业资金流向分析
- 行业轮动分析
- 行业估值分析（PE对比）

**示例行业**:
- 汽车零部件 (280只)
- 通用设备 (275只)
- 专用设备 (209只)
- 化学制品 (184只)

**数据流程**:
1. 每日盘后运行 `scripts/update_industry_daily.py`
2. 从Tushare获取90个行业的资金流向数据
3. 计算每个行业的上涨/下跌家数（查询candle表）
4. 计算行业PE（市值加权平均，查询symbol_metadata表）
5. 保存到 `industry_daily` 表
6. 前端API `/api/symbols/industries` 直接从数据库读取

**优势**:
- ✅ 涨跌幅基于官方板块指数（比简单平均更准确）
- ✅ 包含资金流向等额外数据
- ✅ 性能大幅提升（数据库查询 vs 实时计算）
- ✅ 可追溯历史数据

---

### 2. 同花顺行业板块 (594个) ⚠️ 未使用

**文件**: `data/ths_industry_boards.csv`

**格式**:
```csv
板块代码,板块名称,成分股数量
700308.TI,信息技术(A股),1350
700303.TI,工业(A股),1328
700322.TI,资本品(A股),983
```

**特点**:
- 包含594个细分行业板块
- 分类过于细致，不适合日常监控
- 存在大量交叉和重复

**状态**: ⚠️ 已下载但未在系统中使用

**建议**:
- 可作为行业详情页的二级分类
- 或完全弃用，避免混淆

**来源**: 通过 `scripts/fetch_ths_industry_boards.py` 获取

---

### 3. 东方财富概念板块 (559个) ⭐ 主要使用

**数据源**: Tushare Pro API (`dc_index` 接口)
**文件**: `data/dc_concept_boards.csv`

**格式**:
```csv
板块代码,板块名称,领涨股名称,领涨股代码,涨跌幅,领涨股涨跌幅,总市值,换手率,上涨家数,下跌家数
BK1169,Kimi概念,月之暗面,688095,3.45,10.2,12345678900,2.5,18,6
```

**特点**:
- ✅ **559个概念板块**，涵盖各类主题投资
- ✅ 包含最新热点概念（如"Kimi概念"、"ChatGPT"等）
- ✅ 包含领涨股信息
- ✅ 包含涨跌幅、市值、换手率等行情数据
- ✅ 数据更新频率高

**用途**:
- 存储在 `symbol_metadata.concepts` 字段（JSON数组）
- 概念板块轮动分析
- 热点追踪
- 主题投资机会识别

**示例概念**:
- Kimi概念 (24只)
- ChatGPT (多只)
- 新能源汽车 (多只)
- 芯片概念 (多只)
- 人工智能 (多只)

**数据提取**:
- 使用 `scripts/fetch_dc_concept_boards.py` 获取
- 从东方财富获取实时概念板块数据

---

### 4. 东方财富行业板块 (86个) ⚠️ 已弃用

**文件**: `data/industry_boards_em.csv`

**格式**:
```csv
排名,板块名称,板块代码,最新价,涨跌额,涨跌幅,总市值,换手率,上涨家数,下跌家数,领涨股票,领涨股票-涨跌幅
1,生物制品,BK1044,1157.77,47.75,4.3,1772110512000,2.53,70,5,三生国健,20.0
```

**特点**:
- 86个行业板块
- 包含实时行情数据（价格、涨跌幅）
- 与同花顺90核心行业重叠度高

**状态**: ⚠️ 已弃用，系统已改用同花顺核心行业

**原因**:
- 同花顺行业分类更权威
- 避免多套行业分类标准混用

---

### 5. Tushare申万行业分类 (227个) ⚠️ 未启用

**数据源**: Tushare Pro API (`ths_index` 接口)

**特点**:
- 227个申万行业指数
- 三级分类体系（一级/二级/三级）
- 官方权威分类标准

**当前状态**:
- 数据库表 `symbol_metadata` 已预留字段:
  ```python
  industry_lv1: str  # 一级行业
  industry_lv2: str  # 二级行业
  industry_lv3: str  # 三级行业
  ```
- ⚠️ 但实际未填充申万数据

**建议**:
- 如需官方行业分类，可启用申万三级分类
- 或保留字段用于存储同花顺行业映射

---

## 当前系统使用的分类

### ✅ 正在使用

1. **同花顺90行业（资金流向）** → 用于前端展示和行业分析
   - 数据源: `moneyflow_ind_ths` API
   - 存储位置: `industry_daily` 表
   - 包含: OHLC数据、资金流向、PE估值

2. **东方财富559概念板块** → 存储在 `symbol_metadata.concepts`
   - 数据源: `dc_index` API
   - 文件位置: `data/dc_concept_boards.csv`
   - 包含: 热点概念、领涨股、行情数据

### ⚠️ 已下载未使用

3. **同花顺1,234板块指数** → 数据已有，但系统未使用
   - 包含: 594行业 + 406概念 + 33地域 + 124特色 + 21风格 + 10主题 + 46宽基
   - 文件位置: `data/ths_all_indexes.csv`
   - 用途: 可用于二级分类或详细分析

4. **东方财富86行业板块** → 已弃用，被同花顺90行业替代

### ❌ 未启用

5. **Tushare申万227行业** → 数据库字段已预留，但未填充

---

## 数据存储位置

### 数据库表结构

#### industry_daily 表 ⭐ **新增 - 主要使用**
```python
id: int                     # 主键
trade_date: str             # 交易日期 YYYYMMDD
ts_code: str                # 板块代码 (如 881126.TI)
industry: str               # 板块名称 (如 "汽车零部件")

# 行情数据（来自Tushare）
close: float                # 收盘指数
pct_change: float           # 涨跌幅
company_num: int            # 成分股数量

# 成分股统计（计算得出）
up_count: int               # 上涨家数
down_count: int             # 下跌家数

# 领涨股信息（来自Tushare）
lead_stock: str             # 领涨股名称
lead_stock_code: str        # 领涨股代码
pct_change_stock: float     # 领涨股涨跌幅
close_price: float          # 领涨股收盘价

# 资金流向（来自Tushare）
net_buy_amount: float       # 净买入金额
net_sell_amount: float      # 净卖出金额
net_amount: float           # 净额

# 估值数据（计算得出）
industry_pe: float          # 行业PE（市值加权）
total_mv: float             # 行业总市值
```

#### symbol_metadata 表
```python
industry_lv1: str | None    # 一级行业（存储同花顺90行业名称）
industry_lv2: str | None    # 二级行业（预留，未使用）
industry_lv3: str | None    # 三级行业（预留，未使用）
concepts: list | None       # 概念板块列表 ["Kimi概念", "ChatGPT", ...]
```

#### board_mapping 表
```python
board_name: str       # 板块名称
board_type: str       # "industry" 或 "concept"
board_code: str       # 板块代码
constituents: list    # 成分股列表 ["000001", "600519", ...]
```

### CSV文件

| 文件 | 大小 | 行数 | 用途 | 状态 |
|------|------|------|------|------|
| `ths_all_indexes.csv` | 45KB | 1,235 | 1,234个同花顺板块指数 | ✅ 已下载 |
| `dc_concept_boards.csv` | ~200KB | 560 | 559个东财概念板块 | ✅ 已下载 |
| `ths_core_industries.csv` | 2.3KB | 91 | 90个核心行业（旧） | ⚠️ 已弃用 |
| `ths_industry_boards.csv` | 18KB | 595 | 594个细分行业 | ⚠️ 未使用 |
| `concept_board_constituents.csv` | 150KB | 443 | 442个概念板块（旧） | ⚠️ 已弃用 |
| `industry_boards_em.csv` | 7.2KB | 87 | 86个东财行业 | ❌ 已弃用 |

---

## 板块重叠度分析

### 行业板块对比

| 来源 | 数量 | 特点 | 重叠度 |
|------|------|------|--------|
| 同花顺核心 | 90个 | 精选主流行业 | - |
| 同花顺全量 | 594个 | 过于细分 | 90个是594个的子集 |
| 东财行业 | 86个 | 与同花顺核心基本一致 | 约80%重叠 |
| 申万行业 | 227个 | 官方标准，三级分类 | 低 (分类维度不同) |

### 概念板块

- **东财概念**: 559个（热点概念，更新频繁）
- **同花顺概念**: 406个（已下载，可通过`ths_all_indexes.csv`获取）

---

## SKU数量统计

### 每个Ticker的板块归属

假设某只股票 `000001 平安银行`:

```json
{
  "ticker": "000001",
  "name": "平安银行",
  "industry_lv1": "银行",           // ← 1个核心行业
  "industry_lv2": null,             // ← 未使用
  "industry_lv3": null,             // ← 未使用
  "concepts": [                     // ← 可能属于多个概念
    "银行概念",
    "金融科技",
    "数字货币"
  ]
}
```

**每个ticker的板块SKU**:
- 行业归属: **1个** (只归属于1个核心行业)
- 概念归属: **0-10个** (可能属于多个概念板块)

### 全市场SKU统计

假设5000只股票:
- 行业板块映射: 5000 × 1 = **5,000条**
- 概念板块映射: 5000 × 3 (平均) = **15,000条**
- **总SKU**: ~20,000个板块-股票映射关系

---

## 板块数据更新频率

| 数据类型 | 更新频率 | API调用 | 说明 |
|---------|---------|---------|------|
| **行业资金流向数据** ⭐ | **每日** | **1次** | 更新90个行业到`industry_daily`表 |
| **核心行业成分股** | 每月 | 1次 | 行业成分股变化不频繁 |
| **概念板块数据** | 每周 | 1次 | 更新559个概念板块数据 |
| **概念板块成分股** | 每月 | 1次 | 概念板块成分股变化不频繁 |

**说明**:
- 行业资金流向数据 (`moneyflow_ind_ths`) 每日盘后更新一次，包含90个行业的全部数据
- 数据存储到 `industry_daily` 表后，前端直接从数据库读取
- 概念板块数据 (`dc_index`) 每周更新一次，包含559个概念的行情数据

---

## 总结与建议

### 当前使用方案 ✅

```
系统使用: 同花顺90行业（资金流向）+ 东方财富559概念板块
├─ 行业分类: 90个 (适中，不过度细分)
│  ├─ 数据源: moneyflow_ind_ths API
│  ├─ 存储: industry_daily 表
│  └─ 特点: 包含OHLC、资金流向、PE估值
│
└─ 概念分类: 559个 (热点全覆盖)
   ├─ 数据源: dc_index API
   ├─ 存储: symbol_metadata.concepts
   └─ 特点: 包含领涨股、行情数据
```

### 数据架构 ⭐

**数据流程**:
```
Tushare API → 数据库存储 → 前端API → 前端展示
     ↓              ↓            ↓
moneyflow_ind  industry_daily  /api/symbols/industries
dc_index       symbol_metadata /api/boards
```

**优势**:
- ✅ 涨跌幅基于官方板块指数（准确）
- ✅ 包含资金流向等增值数据
- ✅ 数据库存储，性能大幅提升
- ✅ 可追溯历史数据

### 优化建议

1. **清理未使用的分类**
   - ❌ 删除 `industry_boards_em.csv` (已弃用)
   - ❌ 删除 `ths_core_industries.csv` (已被industry_daily替代)
   - ❌ 删除 `concept_board_constituents.csv` (已被dc_concept_boards.csv替代)
   - ⚠️ 保留 `ths_all_indexes.csv` (1,234个板块，可用于二级分类)

2. **数据库字段优化**
   - `industry_lv2/lv3` 字段可考虑删除（当前未使用）
   - 或用于存储行业层级关系

3. **板块更新策略**
   - 行业资金流向: **每日盘后更新**（运行`update_industry_daily.py`）
   - 核心行业成分股: **每月更新**
   - 概念板块数据: **每周更新**（运行`fetch_dc_concept_boards.py`）
   - 股票行业归属: **新股上市时更新**

4. **前端展示策略**
   - 首页: 90个核心行业涨跌幅排名（含资金流向）
   - 详情页: 可展开559个概念板块
   - 避免同时展示多套行业分类造成混淆

---

**数据文件位置**: `/Users/park/a-share-data/data/`
**相关API**: `/api/symbols/industries`, `/api/boards`
**更新脚本**:
- `scripts/update_industry_daily.py` - 更新90个行业数据
- `scripts/fetch_dc_concept_boards.py` - 更新559个概念板块
- `scripts/fetch_ths_all_indexes.py` - 提取1,234个板块指数
