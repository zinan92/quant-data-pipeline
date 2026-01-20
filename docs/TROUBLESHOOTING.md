# 故障排查指南

## 🐛 问题：API响应超时

### 症状
- 访问 `/api/concept-monitor/*` 端点超时
- 其他API端点（如`/api/status`）也超时
- 后端CPU占用高

### 原因
当前实现中，`fetch_all_concepts()` 是**同步函数**，在主线程中执行：
- 需要获取355个板块数据
- 每个板块延迟0.25秒
- 总耗时约90秒+
- **阻塞了整个FastAPI事件循环**

### 解决方案

#### 方案1：使用独立进程（推荐）⭐

不在FastAPI中实时获取，而是：

1. 启动独立的Python脚本持续更新数据到JSON文件
2. FastAPI只读取JSON文件（毫秒级响应）

```bash
# 启动独立监控进程
python3 scripts/monitor_no_flask.py &

# FastAPI读取 docs/monitor/latest.json
```

#### 方案2：使用Celery异步任务

将数据获取放到Celery worker中执行（需要额外配置）

#### 方案3：使用ThreadPoolExecutor

将同步操作移到线程池执行（中等复杂度）

---

## 🚀 快速修复：使用独立进程

### 步骤1：停止当前的API触发方式

不要通过API触发更新（会阻塞）

### 步骤2：启动独立监控脚本

```bash
cd /Users/park/a-share-data

# 后台运行监控脚本
nohup python3 scripts/monitor_no_flask.py > logs/monitor.log 2>&1 &

# 查看进程
ps aux | grep monitor_no_flask
```

### 步骤3：修改FastAPI端点读取JSON文件

创建新的简单端点，只读取JSON：

```python
# src/api/routes_concept_monitor_v2.py
import json
from pathlib import Path

CACHE_FILE = Path('/Users/park/a-share-data/docs/monitor/latest.json')

@router.get("/top")
async def get_top_concepts(n: int = 20):
    if not CACHE_FILE.exists():
        raise HTTPException(503, "数据未就绪")

    with open(CACHE_FILE, 'r') as f:
        data = json.load(f)

    return {
        "success": True,
        "timestamp": data['timestamp'],
        "total": len(data['topConcepts']['data'][:n]),
        "data": data['topConcepts']['data'][:n]
    }
```

### 步骤4：重启FastAPI

```bash
# 找到进程
ps aux | grep uvicorn | grep -v grep

# 杀掉进程
kill <PID>

# 重新启动
cd /Users/park/a-share-data
uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload &
```

---

## 🎯 推荐架构

```
独立Python进程                    FastAPI服务器
    ↓                                ↓
 每2.5分钟更新              读取JSON文件（快速）
    ↓                                ↓
保存到JSON文件  ←────────────  返回给前端
docs/monitor/latest.json
```

**优势：**
- ✅ FastAPI不阻塞，毫秒级响应
- ✅ 监控进程独立，崩溃不影响主服务
- ✅ 可以随时重启任一服务
- ✅ 简单可靠，无需额外依赖

---

## 📝 当前状态总结

**问题**：同步数据获取阻塞FastAPI事件循环

**临时方案**：等待当前更新完成（可能需要10-20分钟）

**长期方案**：切换到独立进程架构

---

## 🔧 立即恢复服务

如果需要立即恢复FastAPI服务：

```bash
# 重启FastAPI（清除阻塞状态）
pkill -f "uvicorn web.app"
cd /Users/park/a-share-data
uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload &

# 使用独立脚本（不影响FastAPI）
python3 scripts/monitor_no_flask.py --once
```
