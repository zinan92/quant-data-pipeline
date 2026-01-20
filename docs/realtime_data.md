# 前端实时数据显示总结

本文档记录了前端所有实时数据（不包括日线和30分钟K线）的API端点、刷新频率和显示位置。

---

## 1. 指数实时数据 (IndexChart.tsx)

### API端点
- `/api/index/realtime/{tsCode}`

### 刷新频率
- **30秒** (`refetchInterval: 1000 * 30`)

### 数据内容
- 实时价格 (price)
- 涨跌额 (change)
- 涨跌幅 (change_pct)
- 成交量 (volume)
- 成交额 (amount)
- 更新时间 (last_update)

### 显示位置
首页指数卡片上方的实时价格和涨跌幅

### 覆盖指数
- 上证指数 (000001.SH)
- 科创50 (000688.SH)
- 创业板指 (399006.SZ)
- 其他用户选择的指数

### 代码位置
```typescript
// frontend/src/components/IndexChart.tsx:142-147
const { data: realtimeData } = useQuery({
  queryKey: ["index-realtime", tsCode],
  queryFn: () => fetchIndexRealtime(tsCode),
  staleTime: 1000 * 30,
  refetchInterval: 1000 * 30,
});
```

---

## 2. 指数行情统计 (IndexChart.tsx)

### API端点
- `/api/index/quote/{tsCode}`

### 刷新频率
- **30分钟** (`REFRESH_INTERVALS.boards`)

### 数据内容
- 涨跌家数统计 (up_count, down_count, flat_count)
- 成交额、成交量
- PE、PB等估值指标
- 前收盘价 (prev_close)
- 振幅 (amplitude)
- 换手率 (turnover_rate)

### 显示位置
指数卡片下方的市场统计信息

### 代码位置
```typescript
// frontend/src/components/IndexChart.tsx:166-171
const { data: quoteData } = useQuery({
  queryKey: ["index-quote", tsCode],
  queryFn: () => fetchIndexQuote(tsCode),
  staleTime: REFRESH_INTERVALS.boards,
  refetchInterval: REFRESH_INTERVALS.boards,
});
```

---

## 3. 股票实时价格 (useRealtimePrice hook)

### API端点
- `/api/realtime/prices?tickers={tickers}`

### 刷新频率
- **60秒** (在多个组件中使用)
- **30分钟** (仅StockDetail组件)

### 数据内容
- 当前价格 (price)
- 涨跌额 (change)
- 涨跌幅 (changePercent)
- 更新时间 (lastUpdate)

### 使用位置

#### WatchlistView (我的自选)
- 刷新频率: 60秒
- 代码位置: `frontend/src/components/WatchlistView.tsx:126-130`

```typescript
const realtimePrices = useRealtimePrice({
  tickers,
  interval: 60000,
  enabled: true
});
```

#### ChartGrid (概念板块网格)
- 刷新频率: 60秒
- 代码位置: `frontend/src/components/ChartGrid.tsx`

```typescript
const realtimePrices = useRealtimePrice({
  tickers,
  interval: 60000,
  enabled: true
});
```

#### TrackChartGrid (持仓网格)
- 刷新频率: 60秒
- 代码位置: `frontend/src/components/TrackChartGrid.tsx:48-52`

```typescript
const realtimePrices = useRealtimePrice({
  tickers,
  interval: 60000,
  enabled: true
});
```

#### StockDetail (股票详情页)
- 刷新频率: **30分钟**
- 代码位置: `frontend/src/components/StockDetail.tsx:46-50`

```typescript
const realtimePrices = useRealtimePrice({
  tickers: [ticker],
  interval: 1800000, // 30 minutes
  enabled: true
});
```

#### ConceptDetailView (概念详情)
- 刷新频率: 60秒
- 代码位置: `frontend/src/components/ConceptDetailView.tsx`

```typescript
const rawRealtimePrices = useRealtimePrice({
  tickers: tickersWithoutSuffix,
  interval: 60000,
  enabled: true
});
```

### Hook实现
```typescript
// frontend/src/hooks/useRealtimePrice.ts
export function useRealtimePrice(options: UseRealtimePriceOptions): Map<string, RealtimePrice> {
  const { tickers, interval = 60000, enabled = true } = options;
  // 轮询实现
  const url = buildApiUrl(`/api/realtime/prices?tickers=${encodeURIComponent(tickerStr)}`);
}
```

---

## 4. 概念板块实时价格 (ConceptKlineCard.tsx)

### API端点
- `/api/concepts/realtime/{code}`

### 刷新频率
- **30秒** (`staleTime: 1000 * 30`)

### 数据内容
- 当前价格 (price)
- 涨跌幅 (change_pct)
- 今日涨跌 (todayChangePct)

### 显示位置
概念K线卡片头部的实时价格显示

### 代码位置
```typescript
// frontend/src/components/ConceptKlineCard.tsx:71-76
const { data: realtimeData } = useQuery({
  queryKey: ["concept-realtime", concept.code],
  queryFn: fetchConceptRealtime,
  staleTime: 1000 * 30,
  refetchInterval: 1000 * 30,
});
```

---

## 5. 概念监控排行 (useConceptMonitor hook)

### API端点
- `/api/concept-monitor/top?n=20` - 涨幅前20
- `/api/concept-monitor/watch` - 自选概念

### 刷新频率
- **150秒** (2.5分钟)

### 数据内容
- 板块涨幅 (changePct)
- 涨跌变动 (changeValue)
- 资金流入 (moneyInflow)
- 量比 (volumeRatio)
- 上涨家数 (upCount)
- 下跌家数 (downCount)
- 涨停家数 (limitUp)
- 成分股总数 (totalStocks)
- 成交额 (turnover)
- 成交量 (volume)
- 5日涨幅 (day5Change)
- 10日涨幅 (day10Change)
- 20日涨幅 (day20Change)

### 显示位置
首页概念监控表格（涨幅前20和自选概念）

### 代码位置
```typescript
// frontend/src/hooks/useConceptMonitor.ts:52-110
export function useConceptMonitor(options: UseConceptMonitorOptions) {
  const { type, topN = 20, interval = 150000, enabled = true } = options;

  useEffect(() => {
    const fetchData = async () => {
      const endpoint = type === 'top'
        ? `/api/concept-monitor/top?n=${topN}`
        : `/api/concept-monitor/watch`;
      // ...
    };

    fetchData();
    const intervalId = setInterval(fetchData, interval);
    return () => clearInterval(intervalId);
  }, [type, topN, interval, enabled]);
}
```

---

## 6. 动量信号 (MomentumSignalsView.tsx)

### API端点
- `/api/concept-monitor/momentum-signals`

### 刷新频率
- **60秒** (`refetchInterval: 60000`)

### 数据内容

#### 上涨激增信号 (surge)
- 概念名称/代码 (concept_name, concept_code)
- 成分股总数 (total_stocks)
- 前次上涨家数 (prev_up_count)
- 当前上涨家数 (current_up_count)
- 新增上涨家数 (delta_up_count)
- 触发阈值 (threshold)
- 板块类型 (board_type: large/small)
- 触发时间 (timestamp)

#### K线形态信号 (kline_pattern)
- 概念名称/代码 (concept_name, concept_code)
- 成分股总数 (total_stocks)
- 当前涨幅 (current_change_pct)
- K线信息 (kline_info):
  - K线时间 (trade_time)
  - 开盘价 (open)
  - 最高价 (high)
  - 最低价 (low)
  - 收盘价 (close)
  - 上影线比例 (upper_shadow_ratio)
- 触发时间 (timestamp)

### 显示位置
动量信号独立页面（点击"🔔 动量信号"按钮进入）

### 代码位置
```typescript
// frontend/src/components/MomentumSignalsView.tsx:52-57
const { data, isLoading, error, refetch } = useQuery({
  queryKey: ["momentumSignals"],
  queryFn: fetchMomentumSignals,
  refetchInterval: autoRefresh ? 60000 : false,
  staleTime: 30000,
});
```

---

## 📊 实时数据汇总表

| 数据类型 | API端点 | 刷新频率 | 显示位置 | 备注 |
|---------|---------|---------|---------|------|
| 指数实时价格 | `/api/index/realtime/{code}` | **30秒** | 首页指数卡片 | 最快刷新 |
| 指数行情统计 | `/api/index/quote/{code}` | 30分钟 | 首页指数卡片 | 涨跌家数统计 |
| 股票实时价格 | `/api/realtime/prices?tickers=` | **60秒** | 自选/持仓/概念详情 | 批量查询 |
| 股票实时价格 | `/api/realtime/prices?tickers=` | 30分钟 | 股票详情页 | 降低频率 |
| 概念实时价格 | `/api/concepts/realtime/{code}` | **30秒** | 概念K线卡片 | 最快刷新 |
| 概念监控排行 | `/api/concept-monitor/top` | 150秒 | 首页监控表格 | 涨幅前20 |
| 概念监控自选 | `/api/concept-monitor/watch` | 150秒 | 首页监控表格 | 自选概念 |
| 动量信号 | `/api/concept-monitor/momentum-signals` | **60秒** | 动量信号页面 | 独立页面 |

---

## 🔍 关键发现

### 1. 没有1分钟K线数据
- 所有"实时"数据都是通过**轮询API**获取的实时价格/行情快照
- 最细粒度的K线数据是**30分钟K线**
- 没有1分钟、5分钟等更细粒度的K线数据

### 2. 最快刷新频率
- **30秒**: 指数实时价格、概念实时价格
- **60秒**: 股票实时价格（大部分页面）、动量信号
- **150秒**: 概念监控排行
- **30分钟**: 指数行情统计、股票详情页实时价格

### 3. 数据更新机制
- 使用 **React Query** 的 `refetchInterval` 实现轮询
- 使用 `staleTime` 控制数据新鲜度
- 所有实时数据都是前端主动拉取（Pull），非WebSocket推送（Push）

### 4. 数据源
- 指数数据: Tushare API
- 股票实时价格: 腾讯财经API (批量查询)
- 概念数据: 同花顺 API (通过AKShare)

---

## 💡 优化建议

### 短期优化
1. **统一刷新频率**: 将指数和概念实时价格统一为60秒，减少API调用
2. **批量查询优化**: 合并相同频率的API调用，减少网络请求
3. **缓存策略**: 增加 `staleTime`，避免重复刷新相同数据

### 长期优化
1. **WebSocket推送**: 对于高频刷新数据（30秒、60秒），考虑使用WebSocket替代轮询
2. **1分钟K线**: 如需更细粒度分析，可添加1分钟K线数据
3. **增量更新**: 仅推送变化的数据，减少带宽消耗
4. **智能刷新**: 交易时间内高频，非交易时间降频或停止

---

## 📝 更新记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-01-19 | 1.0 | 初始版本，记录所有实时数据端点和刷新频率 |

---

## 相关文档

- [动量信号实现文档](./MOMENTUM_SIGNALS_IMPLEMENTATION.md)
- [动量信号快速开始](./MOMENTUM_SIGNALS_QUICK_START.md)
- [API文档](./tonghuashun_akshare_api.md)
