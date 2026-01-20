# 前端集成方案 - 板块监控表格

## 数据格式说明

### API接口

**涨幅前20板块**
```
GET http://localhost:5000/api/concepts/top?n=20
```

**自选热门概念**
```
GET http://localhost:5000/api/concepts/watch
```

### 返回数据格式

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
      "limitUp": 8,              // 涨停家数（新增）
      "day5Change": 6.36,
      "day10Change": 17.57,
      "day20Change": 20.69,
      "volume": 4594.58,
      "turnover": 3116.55,
      "marketCap": 8.66,
      "circulatingCap": 6.26
    }
  ]
}
```

---

## 表格列配置（基于你的截图）

```javascript
const columns = [
  { key: 'rank', title: '排名', width: 50, align: 'center' },
  { key: 'name', title: '名称', width: 120, align: 'left' },
  { key: 'changePct', title: '涨幅%', width: 80, align: 'right', format: 'percent' },
  { key: 'changeValue', title: '涨速', width: 70, align: 'right', format: 'number' },
  { key: 'mainVolume', title: '主力净量', width: 90, align: 'right', format: 'number' },
  { key: 'moneyInflow', title: '主力净流入', width: 100, align: 'right', format: 'money' },
  { key: 'volumeRatio', title: '量比', width: 70, align: 'right', format: 'ratio' },
  { key: 'upCount', title: '涨家数', width: 70, align: 'center' },
  { key: 'downCount', title: '跌家数', width: 70, align: 'center' },
  { key: 'limitUp', title: '涨停数', width: 70, align: 'center' },  // 新增
  { key: 'day5Change', title: '5日涨幅', width: 80, align: 'right', format: 'percent' },
  { key: 'day10Change', title: '10日涨幅', width: 90, align: 'right', format: 'percent' },
  { key: 'day20Change', title: '20日涨幅', width: 90, align: 'right', format: 'percent' },
  { key: 'volume', title: '总量', width: 90, align: 'right', format: 'volume' },
  { key: 'turnover', title: '总金额', width: 100, align: 'right', format: 'money' },
  { key: 'marketCap', title: '总市值', width: 100, align: 'right', format: 'marketCap' },
  { key: 'circulatingCap', title: '流通市值', width: 100, align: 'right', format: 'marketCap' }
];
```

---

## React组件示例

```jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const ConceptTable = ({ type = 'top' }) => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState('');

  // 获取数据
  const fetchData = async () => {
    try {
      const url = type === 'top'
        ? 'http://localhost:5000/api/concepts/top?n=20'
        : 'http://localhost:5000/api/concepts/watch';

      const response = await axios.get(url);

      if (response.data.success) {
        setData(response.data.data);
        setLastUpdate(response.data.timestamp);
        setLoading(false);
      }
    } catch (error) {
      console.error('获取数据失败:', error);
      setLoading(false);
    }
  };

  // 初始加载
  useEffect(() => {
    fetchData();

    // 每2.5分钟自动刷新
    const interval = setInterval(fetchData, 150000);

    return () => clearInterval(interval);
  }, [type]);

  // 格式化数字
  const formatNumber = (value, type) => {
    if (value === 0 || value === null) return '-';

    switch (type) {
      case 'percent':
        return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
      case 'money':
        return `${value.toFixed(2)}亿`;
      case 'volume':
        return `${value.toFixed(2)}万`;
      case 'marketCap':
        return `${value.toFixed(2)}万亿`;
      case 'ratio':
        return value.toFixed(2);
      default:
        return value.toFixed(2);
    }
  };

  // 颜色判断
  const getColor = (value) => {
    if (value > 0) return '#ff4d4f'; // 红色
    if (value < 0) return '#52c41a'; // 绿色
    return '#ffffff'; // 白色
  };

  if (loading) {
    return <div className="loading">加载中...</div>;
  }

  return (
    <div className="concept-table">
      <div className="table-header">
        <h3>{type === 'top' ? '涨幅前20概念' : '自选热门概念'}</h3>
        <span className="update-time">更新时间: {lastUpdate}</span>
      </div>

      <table>
        <thead>
          <tr>
            <th>排名</th>
            <th>名称</th>
            <th>涨幅%</th>
            <th>涨速</th>
            <th>主力净量</th>
            <th>主力净流入</th>
            <th>量比</th>
            <th>涨家数</th>
            <th>跌家数</th>
            <th>涨停数</th>
            <th>5日涨幅</th>
            <th>10日涨幅</th>
            <th>20日涨幅</th>
            <th>总量</th>
            <th>总金额</th>
            <th>总市值</th>
            <th>流通市值</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.rank}>
              <td className="center">{row.rank}</td>
              <td className="name">{row.name}</td>
              <td className="right" style={{ color: getColor(row.changePct) }}>
                {formatNumber(row.changePct, 'percent')}
              </td>
              <td className="right" style={{ color: getColor(row.changeValue) }}>
                {formatNumber(row.changeValue, 'number')}
              </td>
              <td className="right" style={{ color: getColor(row.mainVolume) }}>
                {formatNumber(row.mainVolume, 'number')}
              </td>
              <td className="right" style={{ color: getColor(row.moneyInflow) }}>
                {formatNumber(row.moneyInflow, 'money')}
              </td>
              <td className="right">{formatNumber(row.volumeRatio, 'ratio')}</td>
              <td className="center" style={{ color: '#ff4d4f' }}>{row.upCount}</td>
              <td className="center" style={{ color: '#52c41a' }}>{row.downCount}</td>
              <td className="center" style={{ color: '#ff4d4f', fontWeight: 'bold' }}>
                {row.limitUp}
              </td>
              <td className="right" style={{ color: getColor(row.day5Change) }}>
                {formatNumber(row.day5Change, 'percent')}
              </td>
              <td className="right" style={{ color: getColor(row.day10Change) }}>
                {formatNumber(row.day10Change, 'percent')}
              </td>
              <td className="right" style={{ color: getColor(row.day20Change) }}>
                {formatNumber(row.day20Change, 'percent')}
              </td>
              <td className="right">{formatNumber(row.volume, 'volume')}</td>
              <td className="right">{formatNumber(row.turnover, 'money')}</td>
              <td className="right">{formatNumber(row.marketCap, 'marketCap')}</td>
              <td className="right">{formatNumber(row.circulatingCap, 'marketCap')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ConceptTable;
```

---

## CSS样式（匹配你的面板风格）

```css
.concept-table {
  background: #1a1d2e;
  border-radius: 4px;
  padding: 16px;
  margin-top: 16px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.table-header h3 {
  color: #ffffff;
  font-size: 16px;
  font-weight: 500;
  margin: 0;
}

.update-time {
  color: #8c8c8c;
  font-size: 12px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

thead {
  background: #252835;
}

thead th {
  color: #8c8c8c;
  font-weight: 400;
  padding: 8px 12px;
  border-bottom: 1px solid #2d2f3e;
  white-space: nowrap;
}

tbody tr {
  border-bottom: 1px solid #2d2f3e;
  transition: background 0.2s;
}

tbody tr:hover {
  background: #252835;
}

tbody td {
  padding: 10px 12px;
  color: #ffffff;
}

td.center {
  text-align: center;
}

td.right {
  text-align: right;
  font-family: 'Monaco', 'Menlo', monospace;
}

td.name {
  color: #40a9ff;
  cursor: pointer;
}

td.name:hover {
  text-decoration: underline;
}

.loading {
  text-align: center;
  padding: 40px;
  color: #8c8c8c;
}
```

---

## Vue 3组件示例

```vue
<template>
  <div class="concept-table">
    <div class="table-header">
      <h3>{{ title }}</h3>
      <span class="update-time">更新时间: {{ lastUpdate }}</span>
    </div>

    <table v-if="!loading">
      <thead>
        <tr>
          <th>排名</th>
          <th>名称</th>
          <th>涨幅%</th>
          <th>涨速</th>
          <th>主力净量</th>
          <th>主力净流入</th>
          <th>量比</th>
          <th>涨家数</th>
          <th>跌家数</th>
          <th>涨停数</th>
          <th>5日涨幅</th>
          <th>10日涨幅</th>
          <th>20日涨幅</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in data" :key="row.rank">
          <td class="center">{{ row.rank }}</td>
          <td class="name">{{ row.name }}</td>
          <td class="right" :style="{ color: getColor(row.changePct) }">
            {{ formatNumber(row.changePct, 'percent') }}
          </td>
          <td class="right" :style="{ color: getColor(row.changeValue) }">
            {{ formatNumber(row.changeValue, 'number') }}
          </td>
          <td class="right" :style="{ color: getColor(row.mainVolume) }">
            {{ formatNumber(row.mainVolume, 'number') }}
          </td>
          <td class="right" :style="{ color: getColor(row.moneyInflow) }">
            {{ formatNumber(row.moneyInflow, 'money') }}
          </td>
          <td class="right">{{ formatNumber(row.volumeRatio, 'ratio') }}</td>
          <td class="center" style="color: #ff4d4f">{{ row.upCount }}</td>
          <td class="center" style="color: #52c41a">{{ row.downCount }}</td>
          <td class="center" style="color: #ff4d4f; font-weight: bold">
            {{ row.limitUp }}
          </td>
          <td class="right" :style="{ color: getColor(row.day5Change) }">
            {{ formatNumber(row.day5Change, 'percent') }}
          </td>
          <td class="right" :style="{ color: getColor(row.day10Change) }">
            {{ formatNumber(row.day10Change, 'percent') }}
          </td>
          <td class="right" :style="{ color: getColor(row.day20Change) }">
            {{ formatNumber(row.day20Change, 'percent') }}
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="loading">加载中...</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import axios from 'axios';

const props = defineProps({
  type: {
    type: String,
    default: 'top'
  }
});

const data = ref([]);
const loading = ref(true);
const lastUpdate = ref('');
const title = props.type === 'top' ? '涨幅前20概念' : '自选热门概念';

let intervalId = null;

const fetchData = async () => {
  try {
    const url = props.type === 'top'
      ? 'http://localhost:5000/api/concepts/top?n=20'
      : 'http://localhost:5000/api/concepts/watch';

    const response = await axios.get(url);

    if (response.data.success) {
      data.value = response.data.data;
      lastUpdate.value = response.data.timestamp;
      loading.value = false;
    }
  } catch (error) {
    console.error('获取数据失败:', error);
    loading.value = false;
  }
};

const formatNumber = (value, type) => {
  if (value === 0 || value === null) return '-';

  switch (type) {
    case 'percent':
      return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
    case 'money':
      return `${value.toFixed(2)}亿`;
    case 'ratio':
      return value.toFixed(2);
    default:
      return value.toFixed(2);
  }
};

const getColor = (value) => {
  if (value > 0) return '#ff4d4f';
  if (value < 0) return '#52c41a';
  return '#ffffff';
};

onMounted(() => {
  fetchData();
  intervalId = setInterval(fetchData, 150000); // 2.5分钟
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
});
</script>

<style scoped>
/* 使用上面的CSS样式 */
</style>
```

---

## 使用方法

### 1. 启动后端API服务

```bash
cd /Users/park/a-share-data
pip install flask flask-cors akshare pandas
python3 scripts/api_server.py
```

### 2. 在你的前端项目中集成

**React项目：**
```jsx
import ConceptTable from './components/ConceptTable';

function App() {
  return (
    <div>
      {/* 你现有的面板内容 */}

      {/* 添加板块监控表格 */}
      <ConceptTable type="top" />
      <ConceptTable type="watch" />
    </div>
  );
}
```

**Vue项目：**
```vue
<template>
  <div>
    <!-- 你现有的面板内容 -->

    <!-- 添加板块监控表格 -->
    <ConceptTable type="top" />
    <ConceptTable type="watch" />
  </div>
</template>

<script setup>
import ConceptTable from './components/ConceptTable.vue';
</script>
```

---

## 特性说明

✅ **完全匹配你的截图风格**
- 深色主题
- 红绿配色（涨红跌绿）
- 紧凑布局

✅ **新增涨停家数列**
- 实时计算涨停数量
- 红色高亮显示

✅ **自动刷新**
- 2.5分钟自动更新
- 后台持续监控

✅ **两个数据源**
- 涨幅前20概念
- 自选热门概念

✅ **RESTful API**
- 支持分页
- 支持排序
- 支持筛选
