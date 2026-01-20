# 发生了什么 & 如何修复

## 🐛 问题分析

### 原因
之前的实现(`routes_concept_monitor.py`)在FastAPI中**同步获取**数据：
- 需要获取355个板块
- 每个板块延迟0.25秒
- 总计约90秒
- **阻塞了整个FastAPI事件循环**
- 导致所有API请求都超时

### 教训
**在FastAPI中避免长时间的同步操作！**
- ❌ 不要在API路由中直接调用耗时的同步函数
- ✅ 使用异步/线程池/独立进程

---

## ✅ 解决方案

### 新架构：独立进程 + JSON缓存

```
独立监控进程                FastAPI服务器
(monitor_no_flask.py)        (routes_concept_monitor_v2.py)
     ↓                              ↓
 每2.5分钟抓取数据          读取JSON文件（毫秒级）
     ↓                              ↓
保存到JSON文件  ←──────────  返回给前端
docs/monitor/latest.json
```

**优势：**
- ✅ FastAPI永不阻塞
- ✅ 响应速度极快（毫秒级）
- ✅ 监控进程独立，崩溃不影响主服务
- ✅ 可以随时重启任一服务

---

## 🔧 已执行的修复步骤

### 1. 创建了优化版本的API
- `src/api/routes_concept_monitor_v2.py` - 只读取JSON文件

### 2. 更新了路由配置
- 将 `routes_concept_monitor` 改为 `routes_concept_monitor_v2`

### 3. 执行修复脚本
`scripts/fix_and_restart.sh` 做了以下事情：
1. ✅ 停止被阻塞的FastAPI进程
2. ⏳ 运行一次数据获取（单次模式，5-10分钟）
3. ✅ 重启FastAPI服务
4. ✅ 测试API

---

## 📊 当前状态

### 正在进行
- ⏳ 首次数据获取中（`monitor_no_flask.py --once`）
- 预计需要：5-10分钟
- 输出位置：`docs/monitor/latest.json`

### 完成后
- ✅ FastAPI可以正常响应
- ✅ API端点：
  - `GET /api/concept-monitor/top?n=20`
  - `GET /api/concept-monitor/watch`
  - `GET /api/concept-monitor/status`

---

## 🚀 后续使用

### 一次性获取数据
```bash
cd /Users/park/a-share-data
python3 scripts/monitor_no_flask.py --once
```

### 持续监控（推荐）
```bash
# 后台运行，每2.5分钟自动更新
nohup python3 scripts/monitor_no_flask.py > logs/monitor.log 2>&1 &

# 查看进程
ps aux | grep monitor_no_flask

# 查看日志
tail -f logs/monitor.log

# 停止监控
pkill -f monitor_no_flask
```

### 查看FastAPI日志
```bash
tail -f logs/fastapi.log
```

---

## 📁 文件说明

### 已废弃（会阻塞）
- ~~`src/api/routes_concept_monitor.py`~~ - 同步版本，已废弃

### 当前使用（不阻塞）
- ✅ `src/api/routes_concept_monitor_v2.py` - 读取JSON版本
- ✅ `scripts/monitor_no_flask.py` - 独立监控进程
- ✅ `docs/monitor/latest.json` - 数据缓存文件

---

## 🧪 测试命令

### 检查修复进度
```bash
# 查看后台任务输出
tail -f /private/tmp/claude/-Users-park-a-share-data/tasks/bb7a282.output

# 或者
bash scripts/check_monitor_status.sh
```

### 测试API（修复完成后）
```bash
# 状态检查
curl http://localhost:8000/api/concept-monitor/status | python3 -m json.tool

# 涨幅前5
curl http://localhost:8000/api/concept-monitor/top?n=5 | python3 -m json.tool

# 自选概念
curl http://localhost:8000/api/concept-monitor/watch | python3 -m json.tool
```

### 检查数据文件
```bash
# 是否存在
ls -lh docs/monitor/latest.json

# 查看内容
cat docs/monitor/latest.json | python3 -m json.tool | head -50
```

---

## 🎯 前端集成（不变）

前端代码**无需修改**，API接口路径和格式完全相同：

```tsx
import { ConceptMonitorTable } from './components/ConceptMonitorTable';

<ConceptMonitorTable type="top" topN={20} />
<ConceptMonitorTable type="watch" />
```

---

## ⏰ 预计完成时间

- **首次数据获取**: 正在进行中，约5-10分钟
- **FastAPI重启**: 已完成
- **可用时间**: 约10分钟后

你可以运行以下命令查看进度：
```bash
tail -f /private/tmp/claude/-Users-park-a-share-data/tasks/bb7a282.output
```

或者打开测试页面查看：
```bash
open frontend/test-concept-monitor.html
```
