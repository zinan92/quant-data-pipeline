# K线数据统一化 - 详细任务清单

> 配套文档: [kline-data-unification-prd.md](./kline-data-unification-prd.md)
>
> 更新时间: 2026-01-05
>
> 说明: 每完成一个任务，将 `[ ]` 改为 `[x]`

---

## Phase 1: 数据库准备

### 1.1 创建数据模型
- [x] 在 `src/models.py` 中添加 `SymbolType` 枚举 (stock/index/concept)
- [x] 在 `src/models.py` 中添加 `KlineTimeframe` 枚举 (day/30m/5m/1m)
- [x] 在 `src/models.py` 中添加 `Kline` 模型
  - [x] 字段: symbol_type, symbol_code, symbol_name
  - [x] 字段: timeframe, trade_time
  - [x] 字段: open, high, low, close, volume, amount
  - [x] 字段: dif, dea, macd (技术指标)
  - [x] 字段: created_at, updated_at
  - [x] 唯一约束: (symbol_type, symbol_code, timeframe, trade_time)
  - [x] 索引: ix_klines_symbol, ix_klines_trade_time, ix_klines_lookup
- [x] 在 `src/models.py` 中添加 `DataUpdateStatus` 枚举
- [x] 在 `src/models.py` 中添加 `DataUpdateLog` 模型
- [x] 在 `src/models.py` 中添加 `TradeCalendar` 模型

### 1.2 创建数据库表
- [x] 运行 `init_db()` 创建 `klines` 表
- [x] 运行 `init_db()` 创建 `data_update_log` 表
- [x] 运行 `init_db()` 创建 `trade_calendar` 表
- [ ] 验证表结构正确 (`sqlite3 data/market.db ".schema klines"`)

---

## Phase 2: 数据迁移

### 2.1 创建迁移脚本
- [x] 创建 `scripts/migrate_klines.py`
- [x] 实现 `calculate_macd()` 函数
- [x] 实现 `migrate_candles_to_klines()` 函数
- [x] 实现 `migrate_concept_klines_from_csv()` 函数
- [x] 实现 `init_trade_calendar()` 函数
- [x] 实现 `log_update()` 函数

### 2.2 优化迁移脚本 (解决重复数据问题)
- [x] 修改迁移逻辑使用 `INSERT OR IGNORE` 或批量 upsert
- [x] 添加进度显示和断点续传支持
- [x] 添加命令行参数支持 (--skip-candles, --skip-concepts, --skip-indices, --skip-calendar)
- [ ] 添加数据验证步骤

### 2.3 执行数据迁移
- [x] 迁移 `candles` 表中的个股日线数据 (2,210,834条)
- [x] 迁移 `candles` 表中的个股30分钟数据 (2,037,284条)
- [x] 迁移 `concept_klines_daily.csv` 中的概念日线数据 (13,433条)
- [x] 迁移 `concept_klines_30min.csv` 中的概念30分钟数据 (12,600条)
- [x] 初始化交易日历数据 (从 Tushare 获取) (366条)

### 2.4 下载指数K线数据
- [x] 下载上证指数 (000001.SH) 日线数据到 klines 表 (242条)
- [x] 下载深证成指 (399001.SZ) 日线数据到 klines 表 (242条)
- [x] 下载创业板指 (399006.SZ) 日线数据到 klines 表 (242条)
- [x] 下载科创50 (000688.SH) 日线数据到 klines 表 (242条)
- [x] 下载北证50 (899050.BJ) 日线数据到 klines 表 (242条)
- [x] 下载上述指数的30分钟数据到 klines 表 (5x240=1200条)

### 2.5 验证迁移结果
- [ ] 验证 klines 表记录数
- [ ] 验证各类型数据分布 (SELECT symbol_type, COUNT(*) FROM klines GROUP BY symbol_type)
- [ ] 抽查数据准确性

---

## Phase 3: 后端重构

### 3.1 创建统一K线服务
- [x] 创建 `src/services/kline_service.py`
- [x] 实现 `KlineService` 类
- [x] 实现 `get_klines()` 方法 - 从数据库读取K线
- [x] 实现 `save_klines()` 方法 - 批量保存K线
- [x] 实现 `get_latest_trade_time()` 方法 - 获取最新K线时间
- [x] 实现 `calculate_macd()` 函数 - 计算MACD指标
- [x] 实现 `get_klines_with_meta()` 方法 - 获取K线及元信息
- [x] 实现 `delete_old_klines()` 方法 - 清理旧数据

### 3.2 创建统一K线API
- [x] 创建 `src/api/routes_klines.py`
- [x] 实现 `GET /api/klines/{symbol_type}/{symbol_code}` 端点
  - [x] 参数: timeframe (day/30m)
  - [x] 参数: limit (默认120)
  - [x] 参数: start_date, end_date (可选)
- [x] 实现响应格式与前端兼容
- [x] 在 `src/api/router.py` 中注册路由

### 3.3 重构现有概念K线API
- [x] 修改 `src/api/routes_concepts.py`
- [x] 修改 `/api/concepts/kline/{code}` 使用 `KlineService`
- [x] ~~修改 `/api/concepts/kline30m/{code}` 使用 `KlineService`~~ (已合并到 `/kline/{code}?period=30min`)
- [x] 保持响应格式兼容

### 3.4 重构现有指数K线API
- [x] 修改 `src/api/routes_index.py`
- [x] 修改 `/api/index/kline/{ts_code}` 使用 `KlineService`
- [x] 修改 `/api/index/kline30m/{ts_code}` 使用 `KlineService`
- [x] 保持响应格式兼容
- [x] 保留 `/api/index/realtime/{ts_code}` (实时数据不入库)

### 3.5 测试API
- [ ] 测试新的统一K线API
- [ ] 测试修改后的概念K线API
- [ ] 测试修改后的指数K线API
- [ ] 验证前端显示正常

---

## Phase 4: 定时任务

### 4.1 创建K线更新器
- [x] 创建 `src/services/kline_updater.py`
- [x] 实现 `KlineUpdater` 类
- [x] 实现 `update_index_daily()` - 更新指数日线
- [x] 实现 `update_index_30m()` - 更新指数30分钟线
- [x] 实现 `update_concept_daily()` - 更新概念日线
- [x] 实现 `update_concept_30m()` - 更新概念30分钟线
- [x] ~~实现 `update_stock_daily()` - 更新自选股日线~~ (由现有 SchedulerManager 处理)
- [x] ~~实现 `update_stock_30m()` - 更新自选股30分钟线~~ (暂不实现，数据量过大)
- [x] 实现 `update_trade_calendar()` - 更新交易日历
- [x] 实现 `cleanup_old_klines()` - 清理旧数据

### 4.2 创建调度器
- [x] 创建 `src/services/kline_scheduler.py`
- [x] 实现 `KlineScheduler` 类
- [x] 实现 `is_trading_day()` 方法
- [x] 实现 `is_trading_time()` 方法
- [x] 配置日线更新任务 (交易日 15:30)
- [x] 配置30分钟更新任务 (交易时间每30分钟)
- [x] 配置数据清理任务 (每周日 00:00)
- [x] 配置交易日历更新任务 (每天 00:01)

### 4.3 集成调度器
- [x] 修改 `src/lifecycle.py` 添加调度器启动
- [x] 添加调度器关闭钩子
- [ ] 测试定时任务触发

### 4.4 添加监控和日志
- [x] 每次更新记录到 `data_update_log` 表
- [ ] 添加更新失败告警 (可选)
- [x] 创建 `/api/admin/update-status` 端点查看更新状态
- [x] 创建 `/api/admin/scheduler/jobs` 端点查看调度任务
- [x] 创建 `/api/admin/scheduler/run/{job_id}` 端点手动触发任务
- [x] 创建 `/api/admin/kline-summary` 端点查看K线统计
- [x] 创建 `/api/admin/trading-status` 端点查看交易状态

---

## Phase 5: 前端适配

### 5.1 更新指数图表组件
- [x] 检查 `frontend/src/components/IndexChart.tsx` - **API兼容，无需修改**
- [x] 验证 `fetchIndexKline()` 响应格式兼容
- [x] 验证 `fetchIndexKline30m()` 响应格式兼容 (datetime为Unix timestamp)
- [ ] 测试指数日线显示
- [ ] 测试指数30分钟线显示

### 5.2 更新概念图表组件
- [x] 检查 `frontend/src/components/ConceptKlineCard.tsx`
- [x] 修复后端 `routes_concepts.py` datetime 格式
  - 日线: "YYYY-MM-DD" -> "YYYYMMDD"
  - 30分钟: "YYYY-MM-DD HH:MM:SS" -> "YYYYMMDDHHMM"
- [ ] 测试概念日线显示
- [ ] 测试概念30分钟线显示

### 5.3 更新个股图表组件
- [x] 检查 `frontend/src/hooks/useCandles.ts` - **使用独立的 candles API，无需修改**
- [x] 个股K线仍使用 `/api/candles/{ticker}` 端点
- [ ] 测试个股K线显示

### 5.4 全面测试
- [ ] 测试所有指数K线图正常显示
- [ ] 测试所有概念K线图正常显示
- [ ] 测试个股K线图正常显示
- [ ] 测试实时数据更新正常
- [ ] 测试MA均线显示正常
- [ ] 测试MACD指标显示正常

---

## Phase 6: 清理与优化

### 6.1 清理旧代码
- [ ] 删除 `src/api/routes_concepts.py` 中的CSV读取逻辑
- [ ] 删除 `scripts/fetch_ths_concept_kline.py` (或标记为废弃)
- [ ] 清理不再使用的导入

### 6.2 数据清理
- [ ] 确认 klines 表数据完整后，可选择删除:
  - [ ] `data/concept_klines/` 目录 (建议先备份)
  - [ ] `candles` 表 (建议先备份)

### 6.3 性能优化
- [ ] 添加数据库连接池配置
- [ ] 优化K线查询SQL
- [ ] 添加API响应缓存 (可选)
- [ ] 测试K线API响应时间 < 200ms

### 6.4 文档更新
- [ ] 更新 README.md 数据架构说明
- [ ] 更新 API 文档
- [ ] 标记 PRD 状态为"已完成"

---

## 验收检查清单

### 功能验收
- [ ] 所有K线数据从SQLite读取
- [ ] 日线数据每天15:30自动更新
- [ ] 30分钟数据交易时间每30分钟更新
- [ ] 前端所有K线图正常显示
- [ ] 实时价格正常更新

### 性能验收
- [ ] K线API响应时间 < 200ms
- [ ] 日线批量更新时间 < 5分钟
- [ ] 30分钟批量更新时间 < 2分钟

### 稳定性验收
- [ ] 连续运行7天无报错
- [ ] 周末/节假日正确跳过更新
- [ ] API失败时有重试和降级机制

---

## 当前进度

**最后更新**: 2026-01-05 19:30

**当前阶段**: Phase 5 (前端适配) - ✅ 代码修改完成，待测试

**已完成**:
- ✅ Phase 1: 数据库准备完成 (klines, data_update_log, trade_calendar 表)
- ✅ Phase 2: 数据迁移全部完成!
  - 个股K线: 4,248,118 条 (日线 2,210,834 + 30分钟 2,037,284)
  - 概念K线: 26,033 条 (日线 13,433 + 30分钟 12,600)
  - 指数K线: 2,410 条 (日线 1,210 + 30分钟 1,200)
  - 交易日历: 366 条
  - **总计: 4,276,561 条K线数据**
- ✅ Phase 3.1: `src/services/kline_service.py` 创建完成
- ✅ Phase 3.2: `src/api/routes_klines.py` 创建完成，已注册到路由
- ✅ Phase 3.3: `routes_concepts.py` 重构完成，使用 KlineService
- ✅ Phase 3.4: `routes_index.py` 重构完成，使用 KlineService
- ✅ Phase 4.1: `src/services/kline_updater.py` 创建完成
- ✅ Phase 4.2: `src/services/kline_scheduler.py` 创建完成
- ✅ Phase 4.3: 调度器集成到 `src/lifecycle.py`
- ✅ Phase 4.4: `src/api/routes_admin.py` 管理API创建完成
- ✅ Phase 5.1: IndexChart.tsx 检查完成 (API兼容，无需修改)
- ✅ Phase 5.2: ConceptKlineCard.tsx 检查并修复后端datetime格式
- ✅ Phase 5.3: useCandles.ts 检查完成 (使用独立的candles API)

**待执行**:
- Phase 5.4: 前端全面测试
- Phase 6: 清理和优化

**新增定时任务**:
| 任务 | 触发时间 | 说明 |
|------|----------|------|
| daily_update | 每日 15:30 | 更新指数和概念日线 |
| 30m_update | 每30分钟 | 更新指数和概念30分钟线 (交易时间) |
| calendar_update | 每日 00:01 | 更新交易日历 |
| cleanup | 每周日 00:00 | 清理旧K线数据 |

**新增管理API**:
- `GET /api/admin/update-status` - 查看数据更新状态
- `GET /api/admin/scheduler/jobs` - 查看调度任务
- `POST /api/admin/scheduler/run/{job_id}` - 手动触发任务
- `GET /api/admin/kline-summary` - 查看K线数据统计
- `GET /api/admin/trading-status` - 查看交易状态

**新增 API**:
```
GET /api/klines/{symbol_type}/{symbol_code}?timeframe=day&limit=120
```
- symbol_type: stock, index, concept
- timeframe: day, 30m

**数据库统计**:
```sql
SELECT symbol_type, timeframe, COUNT(*) FROM klines GROUP BY symbol_type, timeframe;
-- CONCEPT|DAY|13433
-- CONCEPT|MINS_30|12600
-- INDEX|DAY|1210
-- INDEX|MINS_30|1200
-- STOCK|DAY|2210834
-- STOCK|MINS_30|2037284
```
