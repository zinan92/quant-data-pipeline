# 板块映射功能使用指南

## 功能概述

板块映射功能允许你构建和维护股票与板块（行业/概念）的对应关系，无需每次都遍历所有板块。

### 核心特性

1. **一次性构建** - 首次运行时构建完整映射表
2. **增量验证** - 只检查变化，不重新遍历
3. **手动触发** - 通过前端按钮控制更新时机
4. **避免限流** - 内置12秒延迟，保护免费数据源

---

## 数据结构

### 数据库表

#### `board_mapping` - 板块成分股映射
```sql
board_name      VARCHAR(64)   -- 板块名称（如"银行"）
board_type      VARCHAR(16)   -- 'industry' 或 'concept'
board_code      VARCHAR(16)   -- 板块代码
constituents    JSON          -- 成分股列表 ["000001", "600036", ...]
last_updated    DATETIME      -- 最后更新时间
```

#### `symbol_metadata.concepts` - 股票概念列表
```sql
concepts        JSON          -- 该股票所属的概念板块 ["人工智能", "云计算"]
```

---

## 使用方法

### 方法1：通过前端按钮

访问 http://localhost:5173，在页面顶部找到板块同步按钮：

#### **"构建板块映射"** 按钮
- **用途**: 首次部署或完全重建映射
- **耗时**: 约15-20分钟（90个行业板块）
- **动作**: 遍历所有行业板块，获取成分股并保存

#### **"验证变化"** 按钮
- **用途**: 日常检查板块成分是否有变化
- **耗时**: 约10-15秒（单个板块）
- **动作**: 对比新旧成分股，显示增删情况

---

### 方法2：通过API

#### 1. 构建板块映射

```bash
# 只构建行业板块（推荐）
curl -X POST http://localhost:8000/api/boards/build \
  -H 'Content-Type: application/json' \
  -d '{"board_types": ["industry"]}'

# 构建行业+概念（警告：需要1-2小时！）
curl -X POST http://localhost:8000/api/boards/build \
  -H 'Content-Type: application/json' \
  -d '{"board_types": ["industry", "concept"]}'
```

#### 2. 验证板块变化

```bash
# 验证"银行"行业板块
curl -X POST http://localhost:8000/api/boards/verify \
  -H 'Content-Type: application/json' \
  -d '{
    "board_name": "银行",
    "board_type": "industry"
  }'

# 返回示例
{
  "board_name": "银行",
  "board_type": "industry",
  "has_changes": true,
  "added": ["000001"],
  "removed": [],
  "current_count": 42,
  "previous_count": 41
}
```

#### 3. 查询股票的概念列表

```bash
curl http://localhost:8000/api/boards/concepts/000001

# 返回
{
  "ticker": "000001",
  "concepts": ["银行", "金融科技", "FinTech"]
}
```

#### 4. 列出所有板块映射

```bash
# 列出所有
curl http://localhost:8000/api/boards/list

# 只列出行业板块
curl http://localhost:8000/api/boards/list?board_type=industry

# 只列出概念板块
curl http://localhost:8000/api/boards/list?board_type=concept
```

---

## 工作流程

### 初始部署流程

1. **首次构建**（只需运行一次）
   ```bash
   # 方式A: 通过前端按钮
   访问 http://localhost:5173
   点击"构建板块映射" → 等待15-20分钟

   # 方式B: 通过API
   curl -X POST http://localhost:8000/api/boards/build \
     -H 'Content-Type: application/json' \
     -d '{"board_types": ["industry"]}'
   ```

2. **验证构建结果**
   ```bash
   curl http://localhost:8000/api/boards/list
   # 应该看到90个行业板块
   ```

### 日常维护流程

1. **定期验证变化**（建议每周一次）
   - 前端点击"验证变化"按钮
   - 或通过API逐个验证重要板块

2. **有变化时更新**
   - 如果验证发现变化，重新构建该板块映射

---

## 注意事项

### ⚠️ 限流保护

- 每个API请求之间自动延迟12秒
- 避免频繁调用构建接口
- 建议在非交易时段（晚上）运行大批量构建

### 💡 最佳实践

1. **行业板块优先**
   - 90个行业板块，数据相对稳定
   - 442个概念板块，数据量太大且变化频繁
   - 建议只构建行业板块

2. **增量验证**
   - 日常使用验证接口，不要频繁重建
   - 只在发现变化时才重新构建

3. **定时任务**
   - 可以通过cron定时验证重要板块
   - 不建议自动化全量重建

### 🐛 故障排查

**问题**: 构建失败，提示连接错误
- **原因**: 东财服务器限流
- **解决**: 等待5-10分钟后重试

**问题**: 验证一直显示"无变化"
- **原因**: 可能板块确实没变化
- **解决**: 手动检查东财网站确认

**问题**: 前端按钮无响应
- **原因**: 后端服务未启动或API未正确注册
- **解决**: 检查 `http://localhost:8000/docs` 是否有 `/api/boards` 端点

---

## API参考

### POST /api/boards/build
构建板块映射

**请求体**:
```json
{
  "board_types": ["industry"]  // 或 ["industry", "concept"]
}
```

**响应**:
```json
{
  "status": "success",
  "stats": {
    "industry": 90
  },
  "message": "Successfully built 90 board mappings (Industry: 90)"
}
```

### POST /api/boards/verify
验证板块变化

**请求体**:
```json
{
  "board_name": "银行",
  "board_type": "industry"
}
```

**响应**:
```json
{
  "board_name": "银行",
  "board_type": "industry",
  "has_changes": false,
  "added": [],
  "removed": [],
  "current_count": 42,
  "previous_count": 42
}
```

### GET /api/boards/concepts/{ticker}
获取股票概念列表

**响应**:
```json
{
  "ticker": "000001",
  "concepts": ["银行", "金融科技"]
}
```

### GET /api/boards/list
列出所有板块

**查询参数**:
- `board_type` (可选): "industry" 或 "concept"

**响应**:
```json
{
  "total": 90,
  "boards": [
    {
      "name": "银行",
      "type": "industry",
      "code": "BK0475",
      "stock_count": 42,
      "last_updated": "2025-10-31T13:00:00Z"
    }
  ]
}
```

---

## 常见问题

**Q: 为什么不默认构建概念板块？**
A: 442个概念板块需要约1-2小时，且容易触发限流。建议只构建常用概念。

**Q: 多久需要更新一次映射？**
A: 行业板块变化不频繁，建议每月验证一次。新股上市时可能需要更新。

**Q: 可以自动化验证吗？**
A: 可以，但建议手动触发。自动化请注意限流保护。

**Q: 映射数据存在哪里？**
A: SQLite数据库的 `board_mapping` 表，位于 `data/market.db`

---

## 技术细节

### 数据流程

```
用户点击"构建板块映射"
  ↓
POST /api/boards/build
  ↓
BoardMappingService.build_all_mappings()
  ↓
遍历90个行业板块
  ├─ 调用 ak.stock_board_industry_cons_em("银行")
  ├─ 等待12秒（避免限流）
  └─ 保存到 board_mapping 表
  ↓
返回构建统计
```

### 反向索引

构建概念板块时，会同时更新反向索引：

```python
# 板块 → 股票
board_mapping表: {"银行": ["000001", "600036", ...]}

# 股票 → 概念
symbol_metadata.concepts: {"000001": ["银行", "金融科技"]}
```

---

## 更新日志

**v1.0.0** (2025-10-31)
- ✅ 初始版本
- ✅ 支持行业和概念板块映射
- ✅ 前端手动触发按钮
- ✅ 增量验证功能
- ✅ 自动限流保护（12秒/请求）
