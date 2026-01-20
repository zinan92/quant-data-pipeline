# 股票添加标准化流程指南

## 概述

本文档描述了如何使用标准化模版和自动验证系统添加股票到自选列表。

## 核心概念

### 标准化股票模版 (Stock Template)

每个添加到自选的股票都遵循统一的模版，确保：
- ✅ 数据格式一致性
- ✅ 交易所自动识别
- ✅ 不支持的股票（北交所）预警
- ✅ 赛道分类标准化

### 自动验证系统

添加股票后自动验证：
1. **数据完整性** - 数据库中的记录完整
2. **API服务** - 所有API端点正常响应
3. **前端卡片** - UI显示所有必需元素

## 使用方法

### 1. 添加单个股票

#### 基本用法

```bash
python scripts/add_stock.py <ticker> <name> --sector <sector>
```

#### 示例

```bash
# 添加贵州茅台
python scripts/add_stock.py 600519 贵州茅台 --sector 消费

# 添加平安银行
python scripts/add_stock.py 000001 平安银行 --sector 金融

# 添加宁德时代（同时加入模拟组合）
python scripts/add_stock.py 300750 宁德时代 --sector 新能源 --simulate
```

#### 参数说明

- `ticker`: 6位股票代码（必需）
- `name`: 股票名称（必需）
- `--sector, -s`: 赛道分类（可选，默认"未分类"）
- `--simulate`: 同时添加到模拟组合（可选）
- `--skip-validation`: 跳过验证（不推荐，仅用于批量添加时节省时间）

### 2. 批量添加股票

#### 准备批量文件

创建文本文件 `stocks.txt`，格式：

```
# 格式: ticker,name,sector
600519,贵州茅台,消费
000001,平安银行,金融
300750,宁德时代,新能源
```

#### 执行批量添加

```bash
python scripts/add_stock.py --batch stocks.txt
```

### 3. 验证现有股票

如果股票已经在自选列表中，可以单独验证：

```bash
# 数据完整性验证
python scripts/validators/data_validator.py

# API服务验证
python scripts/validators/api_validator.py
```

## 验证检查项

### 数据完整性验证 (DataValidator)

检查项 | 说明
---|---
Watchlist Entry | 股票是否在watchlist表中
Sector Classification | 赛道分类是否正确设置
Daily K-line Data | 日线数据是否存在
30-min K-line Data | 30分钟线数据是否存在
Market Value | 市值数据是否存在
PE Ratio | PE比率数据是否存在

### API服务验证 (APIValidator)

检查项 | 端点 | 说明
---|---|---
Watchlist API | `/api/watchlist` | 股票出现在列表中
Watchlist Check | `/api/watchlist/check/{ticker}` | 返回inWatchlist=true
Daily K-line | `/api/candles/{ticker}?timeframe=day` | 返回K线数据
30-min K-line | `/api/candles/{ticker}?timeframe=30m` | 返回K线数据
Realtime Price | `/api/realtime/prices?tickers={ticker}` | 返回实时价格（非BSE）
Evaluation | `/api/evaluations?ticker={ticker}` | 评估数据
Sectors | `/api/sectors/` | 赛道数据

### 前端卡片验证 (E2E测试)

检查项 | 说明
---|---
Card Display | 卡片正确显示
Stock Info | 名称、代码显示正确
Price Display | 价格格式正确 (¥XX.XX)
Today's Change | 今日涨跌幅显示 (今 ±X.XX%)
Yesterday's Change | 昨日涨跌幅显示 (昨 ±X.XX%)
Live Indicator | 实时指示器 (🔴 HH:MM:SS)
Market Value | 市值显示 (XXX亿)
PE Ratio | PE比率显示
Sector Tag | 赛道标签显示
K-line Charts | 日线图和30分钟图渲染
Action Buttons | 业绩、详情、移除按钮可用

## 标准化赛道分类

推荐使用以下标准赛道分类：

分类 | 说明
---|---
创新药 | 创新药物研发与生产
AI应用 | 人工智能应用
半导体 | 半导体芯片制造
新能源 | 新能源汽车与电池
医疗服务 | 医疗健康服务
消费电子 | 消费电子产品
消费 | 消费品与零售
金融 | 金融服务
科技 | 科技与互联网
未分类 | 未分类

## 特殊情况处理

### 北交所股票 (BSE)

北交所股票（8、9开头）不支持新浪财经实时行情API：

```bash
$ python scripts/add_stock.py 920670 数字人 --sector 创新药

⚠️  WARNING: 数字人 is a Beijing Stock Exchange (BSE) stock.
    Realtime price data will not be available via Sina Finance API.
    Continue anyway? (y/N):
```

**建议**：
- 如需实时行情，不建议添加BSE股票
- 如只关注基本面和历史数据，可以继续添加

### 验证失败处理

如果验证失败，通常原因：

1. **K线数据缺失** → 运行数据同步：
   ```bash
   python scripts/sync_stock_data.py 600519
   ```

2. **API未响应** → 检查后端服务是否运行：
   ```bash
   # 启动后端
   uvicorn src.main:app --reload --port 8000
   ```

3. **实时价格失败** → 可能是：
   - 非交易时间（正常）
   - API限流（等待后重试）
   - 股票代码错误

## 工作流程图

```
┌─────────────────────┐
│ 创建Stock Template  │
│ - ticker: 600519    │
│ - name: 贵州茅台     │
│ - sector: 消费      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 验证模版             │
│ - 格式检查           │
│ - 交易所识别         │
│ - BSE检查            │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 添加到数据库         │
│ - watchlist表        │
│ - stock_sectors表    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 数据完整性验证       │
│ - 数据库记录         │
│ - K线数据            │
│ - 基本信息           │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ API服务验证          │
│ - 所有端点测试       │
│ - 响应数据检查       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 前端E2E测试 (可选)   │
│ - 卡片显示           │
│ - 数据渲染           │
│ - 交互功能           │
└─────────────────────┘
```

## E2E测试

### 运行E2E测试

```bash
# 安装Playwright（首次）
npm install -D @playwright/test

# 运行测试
npx playwright test tests/e2e/test_watchlist_card.spec.ts

# 带UI运行
npx playwright test --ui

# 调试模式
npx playwright test --debug
```

### 测试覆盖

- ✅ 卡片元素完整性
- ✅ 价格数据显示
- ✅ 实时指示器
- ✅ K线图渲染
- ✅ 交互按钮
- ✅ 赛道筛选
- ✅ 统计面板

## 最佳实践

### 1. 始终使用标准化流程

❌ **不推荐**：直接操作数据库
```bash
sqlite3 data/stocks.db "INSERT INTO watchlist ..."
```

✅ **推荐**：使用add_stock.py
```bash
python scripts/add_stock.py 600519 贵州茅台 --sector 消费
```

### 2. 批量添加时检查结果

```bash
python scripts/add_stock.py --batch stocks.txt

# 查看添加结果
# Success: X stocks
# Failed: Y stocks
```

### 3. 定期验证数据完整性

```bash
# 每周或添加大量股票后运行
python scripts/validators/data_validator.py
```

### 4. 使用E2E测试确保UI正常

```bash
# 添加关键股票后运行
npx playwright test tests/e2e/test_watchlist_card.spec.ts
```

## 故障排查

### 问题：添加失败

**检查**：
1. 股票代码是否正确（6位数字）
2. 股票是否已存在
3. 数据库是否可写

### 问题：验证失败

**检查**：
1. 后端服务是否运行
2. 数据库文件是否存在
3. 网络连接是否正常

### 问题：前端不显示

**检查**：
1. 浏览器刷新
2. 检查浏览器控制台错误
3. 验证API响应

## 相关文件

- `scripts/templates/stock_template.py` - 股票模版定义
- `scripts/validators/data_validator.py` - 数据验证器
- `scripts/validators/api_validator.py` - API验证器
- `scripts/add_stock.py` - 统一添加入口
- `tests/e2e/test_watchlist_card.spec.ts` - E2E测试

## 总结

使用标准化流程的优势：

1. **一致性** - 所有股票数据格式统一
2. **可靠性** - 自动验证确保数据完整
3. **可维护** - 清晰的流程易于维护
4. **可追溯** - 完整的验证报告
5. **自动化** - 减少人工错误

遵循本指南，确保每个添加到自选的股票都经过完整验证，前端卡片显示所有必需信息！
