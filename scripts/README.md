# 股票管理脚本工具集

## 目录结构

```
scripts/
├── README.md                      # 本文档
├── add_stock.py                   # 🎯 统一添加入口（推荐使用）
├── test_stock_workflow.py         # 🧪 工作流程测试脚本
│
├── templates/                     # 标准化模版
│   └── stock_template.py          # 股票模版定义
│
├── validators/                    # 验证器
│   ├── __init__.py
│   ├── data_validator.py          # 数据完整性验证
│   └── api_validator.py           # API服务验证
│
├── examples/                      # 示例文件
│   └── stocks_example.txt         # 批量添加示例
│
└── legacy/                        # 旧脚本（仅供参考）
    ├── batch_add_to_watchlist.py
    ├── update_stock_sectors.py
    ├── add_innovative_drugs.py
    └── ...
```

## 快速开始

### 1. 添加单个股票

```bash
# 基本用法
python scripts/add_stock.py 600519 贵州茅台 --sector 消费

# 同时加入模拟组合
python scripts/add_stock.py 000001 平安银行 --sector 金融 --simulate
```

### 2. 批量添加股票

```bash
# 从文件批量添加
python scripts/add_stock.py --batch scripts/examples/stocks_example.txt
```

### 3. 测试完整工作流程

```bash
# 运行测试验证所有功能
python scripts/test_stock_workflow.py
```

### 4. 运行E2E测试

```bash
# 测试前端卡片显示
npx playwright test tests/e2e/test_watchlist_card.spec.ts
```

## 核心功能

### ✨ add_stock.py - 统一添加入口

**功能**：
- 使用标准化模版创建股票
- 自动验证数据格式
- 添加到数据库
- 自动验证完整性
- 生成详细报告

**优势**：
- ✅ 一键完成所有步骤
- ✅ 自动验证数据和API
- ✅ 详细的错误报告
- ✅ 支持批量添加

**示例**：
```bash
# 添加单个股票
python scripts/add_stock.py 600519 贵州茅台 --sector 消费

# 批量添加
python scripts/add_stock.py --batch stocks.txt

# 跳过验证（快速模式，不推荐）
python scripts/add_stock.py 600519 贵州茅台 --sector 消费 --skip-validation
```

### 🎯 stock_template.py - 标准化模版

**功能**：
- 定义统一的股票数据结构
- 自动识别交易所（SH/SZ/BJ）
- 验证ticker格式
- 检测不支持的股票（BSE）

**使用**：
```python
from scripts.templates.stock_template import create_stock_template

# 创建模版
stock = create_stock_template("600519", "贵州茅台", "消费")

print(stock.get_full_ticker())  # 600519.SH
print(stock.is_supported())     # True
print(stock.to_dict())          # {...}
```

### ✅ data_validator.py - 数据验证器

**功能**：
- 验证watchlist表记录
- 检查赛道分类
- 验证K线数据
- 检查基本信息（市值、PE）

**使用**：
```python
from scripts.validators.data_validator import DataValidator
from scripts.templates.stock_template import create_stock_template

stock = create_stock_template("600519", "贵州茅台", "消费")

with DataValidator(stock) as validator:
    result = validator.validate_all()
    result.print_report()
```

**或直接运行**：
```bash
python scripts/validators/data_validator.py
```

### 🌐 api_validator.py - API验证器

**功能**：
- 测试所有API端点
- 验证响应数据
- 检查实时价格服务
- 确保前端能获取数据

**使用**：
```python
from scripts.validators.api_validator import APIValidator
from scripts.templates.stock_template import create_stock_template

stock = create_stock_template("600519", "贵州茅台", "消费")

validator = APIValidator(stock, base_url="http://localhost:5173")
result = validator.validate_all()
result.print_report()
```

**或直接运行**：
```bash
python scripts/validators/api_validator.py
```

### 🧪 test_stock_workflow.py - 工作流测试

**功能**：
- 端到端测试完整流程
- 使用真实数据
- 生成综合报告
- 验证所有功能

**使用**：
```bash
python scripts/test_stock_workflow.py
```

## 验证检查项

### 数据完整性 (14项检查)

| 检查项 | 说明 | 严重程度 |
|--------|------|----------|
| Watchlist Entry | 记录存在 | ❌ Critical |
| Category | 分类设置 | ✅ Pass |
| Sector | 赛道分类 | ❌ Critical |
| Daily K-line | 日线数据 | ❌ Critical |
| 30-min K-line | 分时数据 | ⚠️ Warning |
| Market Value | 市值 | ⚠️ Warning |
| PE Ratio | PE比率 | ⚠️ Warning |

### API服务 (8项检查)

| 端点 | 说明 | 严重程度 |
|------|------|----------|
| /api/watchlist | 列表API | ❌ Critical |
| /api/watchlist/check/{ticker} | 检查API | ❌ Critical |
| /api/candles (day) | 日线API | ❌ Critical |
| /api/candles (30m) | 分时API | ⚠️ Warning |
| /api/realtime/prices | 实时价格 | ⚠️ Warning |
| /api/evaluations | 评估数据 | ⚠️ Warning |
| /api/sectors | 赛道API | ❌ Critical |

### 前端E2E (15项检查)

| 检查项 | 说明 |
|--------|------|
| Card Display | 卡片显示 |
| Stock Name | 名称正确 |
| Stock Ticker | 代码正确 |
| Current Price | 价格格式 |
| Today's Change | 今日涨跌 |
| Yesterday's Change | 昨日涨跌 |
| Live Indicator | 实时指示器 |
| Market Value | 市值显示 |
| PE Ratio | PE显示 |
| Sector Tag | 赛道标签 |
| Daily Chart | 日线图 |
| 30-min Chart | 分时图 |
| Performance Button | 业绩按钮 |
| Detail Button | 详情按钮 |
| Remove Button | 移除按钮 |

## 工作流程

```
用户输入
   │
   ▼
┌──────────────────┐
│ StockTemplate    │ ← 标准化模版
│ 验证格式、交易所  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 添加到数据库      │
│ - watchlist      │
│ - stock_sectors  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ DataValidator    │ ← 数据验证
│ 检查数据完整性    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ APIValidator     │ ← API验证
│ 测试所有端点      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ E2E Tests        │ ← 前端验证
│ 验证UI显示        │
└────────┬─────────┘
         │
         ▼
      完成 ✅
```

## 命令速查表

### 添加股票

```bash
# 单个
python scripts/add_stock.py 600519 贵州茅台 --sector 消费

# 批量
python scripts/add_stock.py --batch stocks.txt

# 带模拟组合
python scripts/add_stock.py 600519 贵州茅台 --sector 消费 --simulate

# 快速模式（跳过验证）
python scripts/add_stock.py 600519 贵州茅台 --skip-validation
```

### 验证

```bash
# 数据验证
python scripts/validators/data_validator.py

# API验证
python scripts/validators/api_validator.py

# 完整测试
python scripts/test_stock_workflow.py

# E2E测试
npx playwright test tests/e2e/test_watchlist_card.spec.ts
```

### 查看帮助

```bash
# 查看所有选项
python scripts/add_stock.py --help

# 查看模版示例
python scripts/templates/stock_template.py
```

## 最佳实践

### ✅ DO

1. **始终使用 add_stock.py**
   ```bash
   python scripts/add_stock.py 600519 贵州茅台 --sector 消费
   ```

2. **批量添加前准备好文件**
   ```
   # stocks.txt
   600519,贵州茅台,消费
   000001,平安银行,金融
   ```

3. **定期运行验证**
   ```bash
   python scripts/test_stock_workflow.py
   ```

4. **重要更新后运行E2E**
   ```bash
   npx playwright test
   ```

### ❌ DON'T

1. **不要直接修改数据库**
   ```bash
   # ❌ 不要这样做
   sqlite3 data/stocks.db "INSERT INTO ..."
   ```

2. **不要跳过验证（除非批量添加）**
   ```bash
   # ⚠️ 仅在批量添加时使用
   python scripts/add_stock.py ... --skip-validation
   ```

3. **不要使用旧脚本**
   ```bash
   # ❌ 已废弃
   python scripts/batch_add_to_watchlist.py
   ```

## 故障排查

### 问题：添加失败

```
❌ Failed to create stock template: Invalid ticker
```

**解决**：
- 确认ticker是6位数字
- 检查格式是否正确

### 问题：验证失败

```
❌ FAILED (3): Watchlist API, K-line data, Realtime price
```

**解决**：
1. 检查后端是否运行：`lsof -i :8000`
2. 重启后端：`uvicorn src.main:app --reload`
3. 检查数据库：`ls -lh data/stocks.db`

### 问题：前端不显示

**解决**：
1. 刷新浏览器（Cmd+Shift+R）
2. 检查控制台错误
3. 验证API：`curl http://localhost:5173/api/watchlist`

## 迁移指南

### 从旧脚本迁移

**旧方式**：
```bash
# 步骤1：添加到watchlist
python scripts/batch_add_to_watchlist.py

# 步骤2：更新赛道
python scripts/update_stock_sectors.py

# 步骤3：手动验证
# ...
```

**新方式**（一步完成）：
```bash
python scripts/add_stock.py 600519 贵州茅台 --sector 消费
```

## 相关文档

- [详细指南](../../docs/STOCK_ADDITION_GUIDE.md) - 完整使用文档
- [E2E测试](../../tests/e2e/test_watchlist_card.spec.ts) - Playwright测试
- [API文档](../../docs/API.md) - API端点说明

## 维护

### 添加新的验证检查

1. 在 `validators/data_validator.py` 添加方法
2. 在 `validators/api_validator.py` 添加端点测试
3. 在 `tests/e2e/test_watchlist_card.spec.ts` 添加UI测试

### 添加新的赛道分类

在 `templates/stock_template.py` 更新：

```python
STANDARD_SECTORS = {
    "创新药": "创新药物研发与生产",
    "新赛道": "新赛道描述",  # 添加这里
    # ...
}
```

## 总结

使用统一的 `add_stock.py` 脚本：

- ✅ 标准化数据格式
- ✅ 自动验证完整性
- ✅ 一键完成所有步骤
- ✅ 详细的报告和日志
- ✅ 支持批量操作

遵循最佳实践，确保每个添加的股票都经过完整验证！
