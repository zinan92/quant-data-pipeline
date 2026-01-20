# 快速开始 - 板块监控系统

## 🎯 功能特性

✅ 实时监控涨幅前20概念板块
✅ 自定义自选热门概念
✅ 自动计算涨停家数
✅ 2-3分钟自动更新
✅ RESTful API接口
✅ 完美融合到你的交易面板

---

## 🚀 10秒快速启动

### 1. 安装依赖（首次运行）

```bash
cd /Users/park/a-share-data
pip3 install flask flask-cors akshare pandas
```

### 2. 启动API服务

```bash
python3 scripts/api_server.py
```

看到这个界面说明成功启动：

```
🚀 板块监控API服务已启动
============================================================
API端点:
  - GET  /api/concepts/top        涨幅前N板块
  - GET  /api/concepts/watch      自选板块
  - GET  /api/concepts/all        所有板块（分页）
  - GET  /api/status              系统状态
============================================================
```

### 3. 查看Demo效果

用浏览器打开：
```
file:///Users/park/a-share-data/docs/demo.html
```

---

## 📡 API接口说明

### 获取涨幅前20板块

```bash
curl http://localhost:5000/api/concepts/top?n=20
```

### 获取自选热门概念

```bash
curl http://localhost:5000/api/concepts/watch
```

### 获取所有板块（分页）

```bash
curl http://localhost:5000/api/concepts/all?page=1&pageSize=50&sort=changePct&order=desc
```

### 查看系统状态

```bash
curl http://localhost:5000/api/status
```

---

## 🔧 修改自选概念列表

编辑 `scripts/api_server.py` 中的 `WATCH_LIST`：

```python
WATCH_LIST = [
    "先进封装",
    "存储芯片",
    "光刻机",
    "第三代半导体",
    # 添加你的自选概念...
]
```

重启服务即可生效。

---

## 🎨 集成到你的前端

### React示例

```jsx
import React, { useState, useEffect } from 'react';

function ConceptTable() {
  const [data, setData] = useState([]);

  useEffect(() => {
    const fetchData = async () => {
      const res = await fetch('http://localhost:5000/api/concepts/top?n=20');
      const json = await res.json();
      if (json.success) setData(json.data);
    };

    fetchData();
    const interval = setInterval(fetchData, 150000); // 2.5分钟
    return () => clearInterval(interval);
  }, []);

  return (
    <table>
      <thead>
        <tr>
          <th>排名</th>
          <th>名称</th>
          <th>涨幅%</th>
          <th>涨停数</th>
          <th>涨家数</th>
          <th>跌家数</th>
          {/* 更多列... */}
        </tr>
      </thead>
      <tbody>
        {data.map(row => (
          <tr key={row.rank}>
            <td>{row.rank}</td>
            <td>{row.name}</td>
            <td style={{ color: row.changePct > 0 ? '#ff4d4f' : '#52c41a' }}>
              {row.changePct.toFixed(2)}%
            </td>
            <td style={{ color: '#ff4d4f', fontWeight: 'bold' }}>
              {row.limitUp}
            </td>
            <td>{row.upCount}</td>
            <td>{row.downCount}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

### Vue示例

```vue
<template>
  <table>
    <thead>
      <tr>
        <th>排名</th>
        <th>名称</th>
        <th>涨幅%</th>
        <th>涨停数</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in data" :key="row.rank">
        <td>{{ row.rank }}</td>
        <td>{{ row.name }}</td>
        <td :style="{ color: row.changePct > 0 ? '#ff4d4f' : '#52c41a' }">
          {{ row.changePct.toFixed(2) }}%
        </td>
        <td style="color: #ff4d4f; font-weight: bold">{{ row.limitUp }}</td>
      </tr>
    </tbody>
  </table>
</template>

<script setup>
import { ref, onMounted } from 'vue';

const data = ref([]);

const fetchData = async () => {
  const res = await fetch('http://localhost:5000/api/concepts/top?n=20');
  const json = await res.json();
  if (json.success) data.value = json.data;
};

onMounted(() => {
  fetchData();
  setInterval(fetchData, 150000);
});
</script>
```

---

## 📊 数据字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| rank | int | 排名 |
| name | string | 板块名称 |
| code | string | 板块代码 |
| changePct | float | 涨幅% |
| changeValue | float | 涨速 |
| mainVolume | float | 主力净量 |
| moneyInflow | float | 主力净流入（亿元）|
| volumeRatio | float | 量比 |
| upCount | int | 涨家数 |
| downCount | int | 跌家数 |
| **limitUp** | int | **涨停数** ⭐新增 |
| day5Change | float | 5日涨幅% |
| day10Change | float | 10日涨幅% |
| day20Change | float | 20日涨幅% |
| volume | float | 总量（万手）|
| turnover | float | 总金额（亿元）|
| marketCap | float | 总市值（万亿）|
| circulatingCap | float | 流通市值（万亿）|

---

## ⚙️ 配置说明

### 更新频率

在 `api_server.py` 中修改：

```python
time.sleep(150)  # 150秒 = 2.5分钟
```

### 监控板块数量

```python
# 获取涨幅前N
http://localhost:5000/api/concepts/top?n=30  # 改为30
```

---

## 🐛 常见问题

### Q: 启动时报错 `ModuleNotFoundError: No module named 'flask'`

A: 安装依赖：
```bash
pip3 install flask flask-cors akshare pandas
```

### Q: 浏览器显示"连接失败"

A: 确保API服务已启动，检查控制台输出

### Q: 数据更新慢

A: 正常现象，首次启动需要获取所有板块数据（约5-10分钟）

### Q: 如何后台运行

A: 使用 nohup：
```bash
nohup python3 scripts/api_server.py > monitor.log 2>&1 &
```

### Q: 如何停止服务

A: 查找进程并杀死：
```bash
ps aux | grep api_server
kill -9 <PID>
```

---

## 📁 文件结构

```
/Users/park/a-share-data/
├── scripts/
│   ├── api_server.py           # API服务（核心）
│   ├── requirements.txt        # Python依赖
│   └── start_monitor.sh        # 启动脚本
├── docs/
│   ├── demo.html               # 效果演示页面
│   ├── frontend_integration.md # 前端集成文档
│   └── QUICKSTART.md           # 本文档
└── docs/monitor/               # 数据输出目录（自动创建）
    ├── latest.json             # 最新数据
    └── history_*.json          # 历史数据
```

---

## 💡 下一步

1. **定制化**：修改自选概念列表
2. **集成**：嵌入到你的交易面板
3. **优化**：根据需求调整字段和样式
4. **扩展**：添加告警功能（如涨停数>10时推送）

详细集成文档见：`docs/frontend_integration.md`
