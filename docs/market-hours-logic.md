# A股市场开盘/收盘时间逻辑 (Market On/Off)

## 📅 交易时间定义

**时区**: UTC+8 (Asia/Shanghai)

**交易时间** (Market On):
- 上午：09:30 - 11:30
- 下午：13:00 - 15:00

**非交易时间** (Market Off):
- 其他所有时间（包括午休、盘后、周末、节假日）

---

## 🔄 数据更新策略

### Market On（交易时间）

| 数据类型 | 更新频率 | 数据源 | 说明 |
|---------|---------|--------|------|
| **实时价格** | 每30秒 | API轮询 | 股票/指数/概念的最新价格 |
| **日线K线** | 停止轮询 | 数据库缓存 | 等待15:30定时更新 |
| **30分钟K线** | 每5分钟 | API轮询 | 交易时间内每30分钟更新一次数据 |
| **行情详情** | 每30秒 | API轮询 | 涨跌统计、成交额等 |

### Market Off（收盘后）

| 数据类型 | 更新频率 | 数据源 | 说明 |
|---------|---------|--------|------|
| **实时价格** | ❌ 停止轮询 | 缓存 | 显示最后获取的收盘价 |
| **日线K线** | ❌ 停止轮询 | 数据库 | 显示当日收盘数据 |
| **30分钟K线** | ❌ 停止轮询 | 数据库 | 显示15:00的最后数据 |
| **行情详情** | ❌ 停止轮询 | 缓存 | 显示收盘时的数据 |

---

## 🎯 收盘后的数据一致性

### 预期行为

收盘后（15:00之后），以下三个价格应该一致（容忍度0.01%）：

1. **实时价格** - 最后获取的收盘价
2. **日线收盘价** - 数据库中当日的收盘价
3. **30分钟收盘价** - 15:00的K线收盘价

### 验证机制

- **自动验证**: 每交易日15:45
- **手动验证**:
  - API: `POST /api/admin/validate-data-consistency`
  - 脚本: `python scripts/test_data_consistency.py`

---

## 💻 前端实现

### 通用函数

```typescript
// frontend/src/hooks/useRealtimePrice.ts
export function isMarketOpen(): boolean {
  const now = new Date();
  const day = now.getDay();

  // 周末不交易
  if (day === 0 || day === 6) {
    return false;
  }

  const hours = now.getHours();
  const minutes = now.getMinutes();
  const time = hours * 100 + minutes;

  // 9:30-11:30 或 13:00-15:00
  return (time >= 930 && time <= 1130) || (time >= 1300 && time <= 1500);
}
```

### 概念K线卡片

```typescript
// frontend/src/components/ConceptKlineCard.tsx

// 实时数据
const { data: realtimeData } = useQuery({
  queryKey: ["concept-realtime", concept.code],
  queryFn: () => fetchConceptRealtime(concept.code),
  staleTime: 1000 * 30,
  refetchInterval: isMarketOpen() ? 1000 * 30 : false, // ✅ Market Off停止
});

// 日线K线
const { data: dailyData } = useQuery({
  queryKey: ["concept-kline", concept.code, "daily"],
  queryFn: () => fetchConceptKline(concept.code, "daily"),
  staleTime: REFRESH_INTERVALS.boards,
  refetchInterval: isMarketOpen() ? REFRESH_INTERVALS.boards : false, // ✅ Market Off停止
});

// 30分钟K线
const { data: mins30Data } = useQuery({
  queryKey: ["concept-kline", concept.code, "30min"],
  queryFn: () => fetchConceptKline(concept.code, "30min"),
  staleTime: 1000 * 60 * 5,
  refetchInterval: isMarketOpen() ? 1000 * 60 * 5 : false, // ✅ Market Off停止
});
```

### 指数图表

```typescript
// frontend/src/components/IndexChart.tsx

// 实时数据
const { data: realtimeData } = useQuery({
  queryKey: ["index-realtime", tsCode],
  queryFn: () => fetchIndexRealtime(tsCode),
  staleTime: 1000 * 30,
  refetchInterval: isMarketOpen() ? 1000 * 30 : false, // ✅ Market Off停止
});

// 日线K线
const { data: klineData } = useQuery({
  queryKey: ["index-kline", tsCode],
  queryFn: () => fetchIndexKline(tsCode),
  staleTime: REFRESH_INTERVALS.boards,
  refetchInterval: isMarketOpen() ? REFRESH_INTERVALS.boards : false, // ✅ Market Off停止
});

// 30分钟K线
const { data: kline30mData } = useQuery({
  queryKey: ["index-kline30m", tsCode],
  queryFn: () => fetchIndexKline30m(tsCode),
  staleTime: 1000 * 60 * 5,
  refetchInterval: isMarketOpen() ? 1000 * 60 * 5 : false, // ✅ Market Off停止
});

// 行情详情
const { data: quoteData } = useQuery({
  queryKey: ["index-quote", tsCode],
  queryFn: () => fetchIndexQuote(tsCode),
  staleTime: REFRESH_INTERVALS.boards,
  refetchInterval: isMarketOpen() ? REFRESH_INTERVALS.boards : false, // ✅ Market Off停止
});
```

### 自选股卡片

```typescript
// frontend/src/components/WatchlistCard.tsx

// 使用 useRealtimePrice hook（已内置 isMarketOpen 判断）
const prices = useRealtimePrice({
  tickers: [symbol.ticker],
  interval: 60000,
  enabled: true
});

// K线数据没有 refetchInterval，不会自动轮询 ✅
```

---

## 🖥️ 后端实现

### 定时任务

```python
# src/services/kline_scheduler.py

class KlineScheduler:
    def is_trading_day(self, date: datetime = None) -> bool:
        """判断是否为交易日"""
        # 检查交易日历数据库

    def is_trading_time(self, dt: datetime = None) -> bool:
        """判断是否为交易时间"""
        if not self.is_trading_day(dt):
            return False

        current_time = dt.time()
        morning_start = time(9, 30)
        morning_end = time(11, 30)
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)

        return (morning_start <= current_time <= morning_end) or \
               (afternoon_start <= current_time <= afternoon_end)
```

### 定时任务调度

| 时间 | 任务 | Market状态 | 说明 |
|-----|------|-----------|------|
| 09:30-15:00 | 30分钟K线更新 | ✅ On | 整点和半点触发，任务内部判断交易时间 |
| 15:30 | 日线K线更新 | ❌ Off | 收盘后更新所有日线数据 |
| 15:45 | 数据一致性验证 | ❌ Off | 验证三个价格是否一致 |
| 16:00 | 全市场日线更新 | ❌ Off | 更新全市场股票数据 |
| 00:01 | 交易日历更新 | ❌ Off | 更新下一年的交易日历 |

---

## 🔍 用户体验

### Market On（交易时间）

**显示效果**:
- ✅ 价格实时跳动
- ✅ "下次更新: X分钟后"
- ✅ 🔴 实时标记（红点）
- ✅ K线图实时更新

**用户感受**: 数据鲜活，价格跳动

### Market Off（收盘后）

**显示效果**:
- ✅ 价格静止（显示收盘价）
- ❌ 不显示"下次更新"倒计时
- ❌ 没有红点标记
- ✅ K线图显示完整的当日数据

**用户感受**: 数据稳定，三个价格一致

---

## ⚠️ 重要注意事项

### 1. 时区一致性

**所有时间判断必须使用 UTC+8**:
- ✅ 前端: 使用 `new Date()` 获取本地时间（浏览器自动处理时区）
- ✅ 后端: 使用 `datetime.now()` 并确保服务器时区为UTC+8
- ✅ 数据库: 时间戳存储使用UTC+8

### 2. 周末和节假日

**周末处理**:
- `isMarketOpen()` 会检查 `day === 0 || day === 6`
- 周末自动返回 `false`

**节假日处理**:
- 后端使用交易日历数据库 (`TradeCalendar` 表)
- 前端只做简单的时间判断（假设工作日都是交易日）
- **建议**: 前端从后端API获取当前是否为交易日

### 3. 午休时间 (11:30-13:00)

**当前行为**:
- `isMarketOpen()` 返回 `false`
- 停止所有数据轮询

**预期行为**:
- ✅ 符合设计：午休期间不交易，不需要轮询

### 4. 集合竞价时间 (09:15-09:25)

**当前行为**:
- `isMarketOpen()` 返回 `false`（因为09:30才开始）
- 不进行数据轮询

**如需支持集合竞价**:
```typescript
// 修改 isMarketOpen 函数
const time = hours * 100 + minutes;
// 包含集合竞价时间 09:15-09:25
return (time >= 915 && time <= 1130) || (time >= 1300 && time <= 1500);
```

---

## 📊 性能优化

### API请求减少

**Market On期间** (6.5小时):
- 实时数据: 780次/天 (每30秒)
- 30分钟K线: 78次/天 (每5分钟)

**Market Off期间** (17.5小时):
- 实时数据: ❌ 0次（停止轮询）
- 30分钟K线: ❌ 0次（停止轮询）

**节省**: 约70%的API请求

### 带宽节省

**每个查询的大小**:
- 实时数据: ~1KB
- 日线K线: ~10KB
- 30分钟K线: ~10KB

**每日节省**:
- Market On: 正常请求
- Market Off: 节省约 (1KB × 2100次) ≈ 2MB/标的/天

---

## 🧪 测试方法

### 手动测试

**1. 测试 Market On 行为** (交易时间内):
```bash
# 访问前端
open http://localhost:3000

# 观察：
# - 价格应该每30秒跳动
# - 显示"下次更新: XX秒后"
# - 有🔴实时标记
```

**2. 测试 Market Off 行为** (收盘后):
```bash
# 访问前端
open http://localhost:3000

# 观察：
# - 价格静止不变
# - 不显示"下次更新"
# - 没有🔴实时标记
# - 三个价格一致
```

### 自动化测试

```bash
# 1. 修改系统时间到交易时间
# 观察前端是否开始轮询

# 2. 修改系统时间到收盘后
# 观察前端是否停止轮询

# 3. 检查浏览器Network标签
# Market On: 应该看到持续的API请求
# Market Off: 应该没有新的API请求
```

---

## 📝 总结

### ✅ 已实现

1. **前端Market On/Off判断** - `isMarketOpen()` 函数
2. **实时数据收盘后停止** - 所有实时数据查询
3. **K线数据收盘后停止** - 日线、30分钟线
4. **行情详情收盘后停止** - 指数行情统计
5. **数据一致性验证** - 15:45自动验证

### 🎯 用户体验

- **Market On**: 数据鲜活，实时更新
- **Market Off**: 数据稳定，三价一致
- **性能**: 节省70%的API请求

### 🔄 数据流

```
Market On (09:30-15:00):
  实时API ─(每30秒)→ 前端显示 ─(实时跳动)→ 用户

Market Off (15:00+):
  数据库缓存 ─(一次性)→ 前端显示 ─(静止不变)→ 用户
  ↑
  15:30 日线更新
  15:45 数据验证 ✓
```

---

**最后更新**: 2026-01-19 17:30
**版本**: v2.0 (完整Market On/Off实现)
