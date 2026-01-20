# 概念板块监控 - 集成指南

## 🎯 回答你的问题

### 为什么不需要Flask？

**因为你已经有FastAPI后端了！**

你的架构：
```
前端 (React + Vite)
  ↓ HTTP请求
后端 (FastAPI)  ← 这里！
  ↓
数据源 (AKShare + 新浪财经)
```

- ✅ 已有后端：`/Users/park/a-share-data/web/app.py` (FastAPI)
- ✅ 已有路由：`/api/realtime`, `/api/sectors`, `/api/concepts` 等
- ✅ 前端已经在用：`useRealtimePrice` hook 每60秒轮询

**所以：直接在FastAPI中添加新端点，不需要Flask！**

---

## 📦 已完成的工作

### 1. 后端API（FastAPI）

**新增文件：** `src/api/routes_concept_monitor.py`

**端点：**
- `GET /api/concept-monitor/top?n=20` - 涨幅前N板块
- `GET /api/concept-monitor/watch` - 自选热门概念
- `GET /api/concept-monitor/status` - 监控状态
- `POST /api/concept-monitor/refresh` - 强制刷新

**特点：**
- 内存缓存，3分钟过期自动刷新
- 后台异步更新，不阻塞请求
- 自动计算涨停数
- 与现有FastAPI完全集成

### 2. 前端Hook

**新增文件：** `frontend/src/hooks/useConceptMonitor.ts`

**用法：**
```typescript
const { data, timestamp, loading, error } = useConceptMonitor({
  type: 'top',  // 或 'watch'
  topN: 20,
  interval: 150000, // 2.5分钟
  enabled: true
});
```

### 3. 前端组件

**新增文件：** `frontend/src/components/ConceptMonitorTable.tsx`

**用法：**
```tsx
<ConceptMonitorTable type="top" topN={20} />
<ConceptMonitorTable type="watch" />
```

---

## 🚀 集成步骤

### 步骤1：安装依赖（如果还没有）

```bash
pip install akshare
```

### 步骤2：重启后端

```bash
# 停止当前运行的FastAPI服务
# 然后重新启动
uvicorn web.app:app --reload
```

### 步骤3：在你的面板中添加组件

编辑 `frontend/src/App.tsx` 或任何你想放置的地方：

```tsx
import { ConceptMonitorTable } from './components/ConceptMonitorTable';

function App() {
  return (
    <div>
      {/* 你现有的面板内容 */}

      {/* 添加概念板块监控表格 */}
      <ConceptMonitorTable type="top" topN={20} />
      <ConceptMonitorTable type="watch" />
    </div>
  );
}
```

### 步骤4：重新构建前端

```bash
cd frontend
npm run build
```

---

## 🎨 样式说明

组件使用Tailwind CSS，样式已匹配你的深色主题：

- 背景色：`#1a1d2e`
- 表头：`#252835`
- 涨红跌绿：`text-red-500` / `text-green-500`
- 涨停数：红色加粗显示

---

## 📡 API响应格式

```json
{
  "success": true,
  "timestamp": "2026-01-16 15:30:25",
  "total": 20,
  "data": [
    {
      "rank": 1,
      "name": "半导体",
      "code": "307940",
      "changePct": 4.25,
      "changeValue": 0.06,
      "mainVolume": 3.77,
      "moneyInflow": 144.94,
      "volumeRatio": 1.45,
      "upCount": 160,
      "downCount": 11,
      "limitUp": 8,
      "totalStocks": 171,
      "turnover": 3116.55,
      "volume": 4594.58,
      "day5Change": 6.36,
      "day10Change": 17.57,
      "day20Change": 20.69
    }
  ]
}
```

---

## ⚙️ 配置

### 修改自选概念

编辑 `src/api/routes_concept_monitor.py` 中的 `WATCH_LIST`：

```python
WATCH_LIST = [
    "先进封装",
    "存储芯片",
    "你的自选...",
]
```

### 修改更新频率

**后端缓存：** 3分钟自动过期（routes_concept_monitor.py:169）

**前端轮询：** 2.5分钟（hooks/useConceptMonitor.ts:48，可配置）

---

## 🔍 测试API

### 1. 检查后端是否运行

```bash
curl http://localhost:8000/api/concept-monitor/status
```

### 2. 获取涨幅前20板块

```bash
curl http://localhost:8000/api/concept-monitor/top?n=20
```

### 3. 获取自选概念

```bash
curl http://localhost:8000/api/concept-monitor/watch
```

---

## 📊 与现有架构的对比

### 之前你的实时价格系统

```
前端 useRealtimePrice hook
  ↓ 60秒轮询
FastAPI /api/realtime/prices
  ↓ 代理请求
新浪财经API
```

### 新的概念板块监控

```
前端 useConceptMonitor hook
  ↓ 150秒轮询
FastAPI /api/concept-monitor/top
  ↓ 内存缓存（3分钟过期）
AKShare API
```

**完全相同的模式！** 只是数据源和轮询频率不同。

---

## 💡 优势

### 为什么不用Flask，而用FastAPI？

1. **已有架构** - 你的后端已经是FastAPI了
2. **统一端口** - 不需要额外端口（都在8000）
3. **共享中间件** - CORS、认证等统一管理
4. **类型安全** - Pydantic模型自动验证
5. **自动文档** - http://localhost:8000/docs 自动生成

### 为什么用内存缓存？

1. **减少API调用** - AKShare限流风险
2. **快速响应** - 缓存命中0延迟
3. **后台更新** - 不阻塞用户请求
4. **简单可靠** - 无需Redis等额外依赖

---

## 🐛 故障排查

### 后端启动失败

```bash
# 检查akshare是否安装
pip list | grep akshare

# 安装
pip install akshare
```

### 前端无法连接

```bash
# 检查后端是否运行
curl http://localhost:8000/api/concept-monitor/status

# 检查前端配置
cat frontend/.env.local  # 确认VITE_API_BASE正确
```

### 数据加载慢

- 首次请求需要5-10分钟（获取所有板块）
- 后续请求使用缓存，秒级响应
- 查看后端日志确认更新进度

---

## 📁 文件清单

### 后端
- ✅ `src/api/routes_concept_monitor.py` - API路由
- ✅ `src/api/router.py` - 已添加路由注册

### 前端
- ✅ `frontend/src/hooks/useConceptMonitor.ts` - 数据Hook
- ✅ `frontend/src/components/ConceptMonitorTable.tsx` - 表格组件

### 文档
- ✅ `docs/CONCEPT_MONITOR_INTEGRATION.md` - 本文档

---

## 🎯 下一步

1. **启动后端**：重启FastAPI服务
2. **测试API**：curl检查端点是否正常
3. **集成前端**：在App.tsx中添加组件
4. **定制样式**：根据需要调整表格样式
5. **配置自选**：修改WATCH_LIST

---

## 📞 参考

- FastAPI文档：https://fastapi.tiangolo.com
- AKShare文档：https://akshare.akfamily.xyz
- 你的现有实时价格实现：`frontend/src/hooks/useRealtimePrice.ts`
