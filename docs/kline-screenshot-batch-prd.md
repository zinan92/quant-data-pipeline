# K线批量截图系统 PRD

> 后端批量生成K线截图，供 Claude Code 进行形态分析

---

## 一、项目背景

### 1.1 需求场景

用户希望对自选股进行K线形态分析，使用 Claude Code 的视觉能力来识别形态（双底、头肩底、MACD背离等）。

**工作流程**：
1. 后端批量生成自选股K线截图
2. 保存到本地目录
3. 用户在 Claude Code 中请求分析
4. Claude Code 读取图片并输出形态识别结果

### 1.2 为什么用后端生成而非前端截图

| 方案 | 优点 | 缺点 |
|-----|------|------|
| **前端截图** | 所见即所得 | 需要处理scroll、等待渲染、时序复杂 |
| **后端生成** | 不依赖浏览器、可并行、风格统一 | 需要额外实现图表生成 |

**选择后端生成**，因为：
- 160只自选股，前端需要滚动截图，复杂且慢
- 后端可以并行生成，几秒完成
- 图片风格统一，更适合AI分析
- 不依赖浏览器状态

---

## 二、功能设计

### 2.1 核心功能

#### 批量生成自选股K线截图

```
POST /api/screenshots/generate

请求参数：
{
  "scope": "watchlist",      // watchlist=自选股, 或指定tickers列表
  "tickers": [],             // 可选，指定股票列表
  "timeframe": "day",        // day/week/30m
  "limit": 120,              // K线数量
  "include_volume": true,    // 是否包含成交量
  "include_macd": true       // 是否包含MACD
}

响应：
{
  "success": true,
  "total": 164,
  "generated": 164,
  "failed": 0,
  "output_dir": "data/screenshots/2026-01-10",
  "files": [
    "600519_贵州茅台_day.png",
    "000858_五粮液_day.png",
    ...
  ]
}
```

#### 获取截图列表

```
GET /api/screenshots/list?date=2026-01-10

响应：
{
  "date": "2026-01-10",
  "count": 164,
  "files": [
    {
      "filename": "600519_贵州茅台_day.png",
      "ticker": "600519",
      "name": "贵州茅台",
      "timeframe": "day",
      "path": "data/screenshots/2026-01-10/600519_贵州茅台_day.png"
    },
    ...
  ]
}
```

### 2.2 截图规格

| 属性 | 规格 |
|-----|------|
| 尺寸 | 1200 x 800 像素 |
| 格式 | PNG |
| 背景色 | 深色 (#1a1a2e) |
| 内容 | K线 + 均线(MA5/10/20/60) + 成交量 + MACD |

### 2.3 文件组织

```
data/
└── screenshots/
    └── 2026-01-10/                    # 按日期组织
        ├── 600519_贵州茅台_day.png
        ├── 000858_五粮液_day.png
        ├── 002415_海康威视_day.png
        └── ...
```

文件命名规则：`{ticker}_{name}_{timeframe}.png`

---

## 三、技术设计

### 3.1 技术选型

| 组件 | 选择 | 说明 |
|-----|------|------|
| 图表库 | mplfinance | 专业K线图库，基于matplotlib |
| 图片格式 | PNG | 无损压缩，适合AI分析 |
| 并发处理 | 单线程顺序 | 避免数据库锁，164只约30秒 |

### 3.2 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     API Layer                                │
│                POST /api/screenshots/generate                │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 Screenshot Service                           │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ get_watchlist() │ ─► │ generate_chart()│ ─► PNG文件     │
│  │ 获取自选股列表   │    │ 生成K线图       │                │
│  └─────────────────┘    └─────────────────┘                │
│            │                     │                          │
│            ▼                     ▼                          │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │  KlineService   │    │   mplfinance    │                │
│  │  获取K线数据    │    │   渲染图表       │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
                    data/screenshots/
```

### 3.3 图表样式设计

```python
# 深色主题配色
CHART_STYLE = {
    "base_mpl_style": "dark_background",
    "marketcolors": {
        "candle": {"up": "#00d4aa", "down": "#ff6b6b"},  # 涨绿跌红(A股习惯可调)
        "edge": {"up": "#00d4aa", "down": "#ff6b6b"},
        "wick": {"up": "#00d4aa", "down": "#ff6b6b"},
        "volume": {"up": "#00d4aa", "down": "#ff6b6b"},
    },
    "mavcolors": ["#f39c12", "#3498db", "#9b59b6", "#1abc9c"],  # MA5/10/20/60
    "facecolor": "#1a1a2e",
    "gridcolor": "#2d2d44",
}

# 图表布局
CHART_LAYOUT = {
    "figsize": (12, 8),        # 1200x800
    "main_panel": 0.6,         # 主图占比60%
    "volume_panel": 0.15,      # 成交量占比15%
    "macd_panel": 0.2,         # MACD占比20%
}
```

---

## 四、文件结构

### 4.1 新增文件（不修改现有代码）

```
src/
├── services/
│   └── screenshot_service.py    # 新增：截图生成服务
└── api/
    └── routes_screenshots.py    # 新增：截图API路由

data/
└── screenshots/                  # 新增：截图存储目录
    └── .gitkeep
```

### 4.2 依赖更新

```
# requirements.txt 新增
mplfinance>=0.12.10b0
```

---

## 五、接口详细设计

### 5.1 生成截图 API

```
POST /api/screenshots/generate

Request Body:
{
  "scope": "watchlist",           // "watchlist" | "custom"
  "tickers": ["600519", "000858"], // scope=custom时必填
  "timeframe": "day",             // "day" | "week" | "30m"
  "limit": 120,                   // K线数量，默认120
  "include_volume": true,         // 是否包含成交量，默认true
  "include_macd": true,           // 是否包含MACD，默认true
  "output_dir": null              // 自定义输出目录，默认按日期
}

Response 200:
{
  "success": true,
  "total": 164,
  "generated": 162,
  "failed": 2,
  "failed_tickers": ["000001", "000002"],
  "output_dir": "data/screenshots/2026-01-10",
  "duration_seconds": 28.5,
  "files": [
    "600519_贵州茅台_day.png",
    "000858_五粮液_day.png",
    ...
  ]
}

Response 500:
{
  "success": false,
  "error": "错误信息"
}
```

### 5.2 获取截图列表 API

```
GET /api/screenshots/list?date=2026-01-10&timeframe=day

Response 200:
{
  "date": "2026-01-10",
  "timeframe": "day",
  "count": 164,
  "directory": "data/screenshots/2026-01-10",
  "files": [
    {
      "filename": "600519_贵州茅台_day.png",
      "ticker": "600519",
      "name": "贵州茅台",
      "timeframe": "day",
      "size_kb": 125,
      "created_at": "2026-01-10T16:30:00"
    },
    ...
  ]
}
```

### 5.3 获取最新截图目录 API

```
GET /api/screenshots/latest

Response 200:
{
  "date": "2026-01-10",
  "directory": "data/screenshots/2026-01-10",
  "count": 164
}
```

---

## 六、使用流程

### 6.1 生成截图

```bash
# 方式1：调用API
curl -X POST http://localhost:8000/api/screenshots/generate \
  -H "Content-Type: application/json" \
  -d '{"scope": "watchlist", "timeframe": "day"}'

# 方式2：在Claude Code中请求
"帮我生成所有自选股的K线截图"
```

### 6.2 Claude Code 分析

```
用户: 帮我分析 data/screenshots/2026-01-10 目录下的K线图，找出有双底形态的股票

Claude Code:
1. 读取目录下的所有PNG文件
2. 逐个分析K线图
3. 输出识别结果
```

---

## 七、示例输出

### 7.1 截图示例

生成的K线图包含：
- 主图：K线 + MA5(橙) + MA10(蓝) + MA20(紫) + MA60(青)
- 副图1：成交量柱状图
- 副图2：MACD (DIF/DEA/柱状)
- 标题：股票名称 + 代码 + 时间周期
- 当前价格和涨跌幅

```
┌────────────────────────────────────────────────────────┐
│  贵州茅台 (600519) 日线  ¥1,850.00 +2.35%              │
├────────────────────────────────────────────────────────┤
│                                                        │
│          K线主图 + 均线                                │
│    ┌─┐                                                │
│   ┌┴─┴┐  ┌─┐                                          │
│  ┌┴───┴┐┌┴─┴┐ ┌─┐                                     │
│ ┌┴─────┴┴───┴─┴─┴─┐                                   │
│ MA5 ─── MA10 ─── MA20 ─── MA60 ───                    │
│                                                        │
├────────────────────────────────────────────────────────┤
│  ████  ██  ████ ██   成交量                           │
├────────────────────────────────────────────────────────┤
│  ──DIF  ──DEA  ██MACD                                 │
└────────────────────────────────────────────────────────┘
```

---

## 八、开发任务

### 8.1 任务列表

- [ ] 安装 mplfinance 依赖
- [ ] 创建 `src/services/screenshot_service.py`
  - [ ] `ScreenshotService` 类
  - [ ] `generate_chart()` 方法
  - [ ] `batch_generate()` 方法
- [ ] 创建 `src/api/routes_screenshots.py`
  - [ ] POST /api/screenshots/generate
  - [ ] GET /api/screenshots/list
  - [ ] GET /api/screenshots/latest
- [ ] 在 router.py 中注册新路由
- [ ] 创建 `data/screenshots/.gitkeep`
- [ ] 测试和验证

### 8.2 预计工作量

| 任务 | 预计时间 |
|-----|---------|
| screenshot_service.py | 主要工作 |
| routes_screenshots.py | 少量工作 |
| 测试验证 | 少量工作 |

---

## 九、注意事项

### 9.1 性能预估

| 指标 | 预估值 |
|-----|-------|
| 单张截图生成时间 | ~0.2秒 |
| 164只自选股总耗时 | ~30秒 |
| 单张图片大小 | ~100-150KB |
| 164张图片总大小 | ~20MB |

### 9.2 约束条件

1. **不修改现有代码** - 只新增文件
2. **路由注册** - 需要在 router.py 中添加一行 include_router（这是唯一需要修改的地方）

---

**文档版本**: v1.0
**创建日期**: 2026-01-10
**最后更新**: 2026-01-10
