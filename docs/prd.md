# A-Share K-Line Monitor — PRD（合并版）

最后更新：2025-11-15  
涵盖原 docs/*.md（板块映射指南、板块分类、数据SKU、Tushare数据采集PRD、前端验证、增量更新总结、数据来源与计算逻辑、数据字段/更新策略等）与代码库现状。

---

## 1. 背景与目标
- 产品：批量监控最多 500 支 A 股（日/周/月 K 线 + MA5/10/20/50）与 90 个核心行业概览。
- 价值：统一下载/清洗/持久化 TuShare 数据，前端（Vite+React+ECharts）可同步展示、筛选板块与概念标签。
- 成熟度：Backend 以 FastAPI + SQLite 为核心，替换 AkShare 为 TuShare 并接入 APScheduler；Frontend 已支持行业概览与卡片联动。

## 2. 用户与场景
- 量化/自用投研：快速浏览 watchlist 与行业轮动，用于复盘或盘后检查。
- 数据构建者：运营脚本、监控限流，并能按需触发板块构建、概念同步。
- 前端分析：需要高 SKU（市值/PE/概念/K 线）以支撑多种视图。

## 3. 系统概览
- **后端目录**
  - `web/app.py`：FastAPI 应用（CORS、路由、生命周期），入口 `uvicorn web.app:app`.
  - `src/config.py`：Settings（.env、Scheduler、TuShare Token、Feature flags）。
  - `src/database.py`：SQLAlchemy + SQLite，辅助 `session_scope`.
  - `src/models.py`：`SymbolMetadata`、`Candle`、`BoardMapping`、`IndustryDaily`.
  - `src/services/…`：`MarketDataService`（增量刷新/持久化）、`TushareDataProvider`（TuShare 适配）、`BoardMappingService` & `TushareBoardService`。
  - `src/api/routes_*`：`/symbols`、`/candles`、`/tasks`、`/status`、`/boards`.
  - `src/tasks/scheduler.py`：APScheduler 每日 16:30 触发 refresh。
  - `tests/`：增量更新、行业 PE、Ticker 校验等单测。
- **前端**：`frontend/`（Vite + React + React Query + ECharts）；Dev server 5173，代理 `/api`.
- **数据资产**：`data/market.db`（SQLite）、`data/*.csv`（板块/概念快照）。`logs/` 记录刷新。

## 4. 数据来源与接口（TuShare）
| 场景 | 接口 | 主字段 | 频率 | 备注 |
|------|------|--------|------|------|
| 股票清单与静态信息 | `stock_basic` | `ts_code,symbol,name,industry,list_date` | 首次+年度 | 1 次批量返回 ~5500 只 (L) |
| 日线行情 | `daily` | `open,high,low,close,vol,amount` | 全量 200 根 / 日增 1 根 | 未复权，需自算 MA |
| 周线行情 | `weekly` | 同日线 | 全量 200 根 / 周一增 1 根 | 需 2000 积分 |
| 月线行情 | `monthly` | 同日线 | 全量 200 根 / 月初增 1 根 | 需 2000 积分 |
| 每日指标 | `daily_basic` | `pe,pe_ttm,pb,total_mv,circ_mv,turnover_rate` | 每日盘后 1 次 | 支撑市值/估值/SKU |
| 核心行业 | `moneyflow_ind_ths` + `ths_member` | 90 个行业列表 & 成分股 | 每日 | 存入 `industry_daily`, `industry_lv1` |
| 同花顺概念 | `ths_index(type='N')` + `ths_member` | 400+ 概念板块 | 按需（1-2 小时） | 缓存在 `board_mapping` (`concept`) |
| 东方财富概念 | `fetch_dc_index` (TuShare 网关) | 559 个概念 + 资金 | 保留 CSV | 历史快照备查 |

### API 速率/重试
- `src/services/tushare_client.py`：RateLimiter（积分 15k → 180 次/分钟），`delay=0.3s` + 3 次重试。
- `TushareDataProvider.fetch_symbol_metadata` 会一次性拉取全量 `stock_basic` 与 `daily_basic`, 后续从 dict O(1) 查询。

### 数据存储方案
- **主用**：`SQLite`（`SymbolMetadata`, `Candle`, `BoardMapping`, `IndustryDaily`）。`Candle` 约 3M 行（5000 × 200 × 3）+ 日增 5k。
- **可选**：`Parquet` 分区（`data/daily/*.parquet`）或 CSV（原型/回归）。文档中保留 3 种方案供分析场景。

## 5. 数据 SKU（前端视角）
### 每只股票 (`GET /api/symbols`)
- 静态：`ticker,name,listDate,industryLv1-3,eastmoneyBoard`（7 字段）。
- 动态：`concepts,totalMv,circMv,peTtm,pb,lastUpdated`（6 字段）。
- 合计 `13` SKU / ticker。

### K 线 (`GET /api/candles/{ticker}`)
- Timeframe：`day/week/month`，每根包含 11 字段（timestamp, OHLC, volume, turnover, MA5/10/20/50）。
- 200 根 × 3 周期 = 600 根 → 6,600 SKU / ticker。

### 行业聚合 (`GET /api/symbols/industries`)
- 来源 `industry_daily`，90 行业 × 13 字段（板块名称/代码、股票数量、总市值、涨跌幅、上涨/下跌家数、行业PE、收盘指数、领涨股、领涨股涨跌幅、净流入资金、交易日期）= 1,170 SKU。

### 板块映射
- 行业 90 + 概念 442 ≈ 532 个板块 × 5 字段（名称/类型/代码/成分数/更新时间）= 2,660 SKU。

### SKU 总量估算
```
单票：6,613 SKU
5000 票：33,000,000 (K线) + 65,000 (元数据) + 1,170 (行业) + 2,660 (板块) ≈ 33,068,830
```

## 6. 数据更新策略
### 字段分类
- **静态**（一次性/年度）：`ticker`, `name`, `list_date`, `industry_lv1-3`, `concepts`（月度）。
- **动态**（每日）：`total_mv`, `circ_mv`, `pe_ttm`, `pb`, `turnover_rate`, `last_sync`.
- **行业聚合**：每日盘后由 `scripts/update_industry_daily.py` 写入 `industry_daily`（包含涨跌幅、PE、资金流等）。

### 增量刷新实现 （见 `docs/增量更新实施总结.md` & `src/services/data_pipeline.py`）
1. `should_update_timeframe()`：DAY 每天；WEEK 仅周一；MONTH 仅每月 1 号。
2. `_get_latest_candle_timestamp()` 查询 DB，决定 `replace`（首次 200 根）或 `upsert`（仅新 timestamp）。
3. `fetch_candles_since()` 从最新时间戳后取数据，`_normalize_candle_data(limit=None)` 保留全部新行。
4. `_persist_candles(mode="upsert")`：删除重复 timestamp，再 `bulk_insert`，同时刷新 `symbol.last_sync`.
5. 日常 API 调用：3,000,000 → 5,000 条 K 线，降低 99.8%；周一/月初根据规则追加到 10k/15k。

### 静态/动态拆分后续计划
- 建议拆成 `symbol_static_info` + `symbol_daily_metrics`（记录 trade_date），以保留历史估值曲线并彻底避免每日拉 `stock_basic`。目前 `SymbolMetadata` 仍混合字段，`fetch_symbol_metadata` 每次 refresh 都会重新加载全市场静态信息。

### 调度
- `.env` → `DAILY_REFRESH_CRON` (`Asia/Shanghai 16:30` 默认)；`src/tasks/scheduler.py` 调度 `MarketDataService.refresh_universe`.
- 手动触发：`POST /api/tasks/refresh`（可传 tickers/timeframes），或运行脚本 `scripts/download_sample_data.py`, `download_all_data.py`.

### 数据质量 & 校验
- `docs/tushare-stock-data-prd.md` 覆盖：缺失值检测、涨跌幅一致性、异常涨跌幅 (>±20%)、PE 负值处理、停牌补数策略。
- `scripts/check_and_reset_candles.py`：检查/清理陈旧数据、重置指定 ticker。
- `docs/frontend-verification.md`：列出 curl 校验、数据库 SQL、Playwright 测试模板。

## 7. 板块体系
### 分类来源（详见 `docs/board-taxonomy.md` & `docs/板块分类系统总览.md`）
| 系统 | 数量 | 数据源 | 文件/表 | 用途 |
|------|------|--------|---------|------|
| 同花顺 90 核心行业 ⭐ | 90 | TuShare `moneyflow_ind_ths` + `ths_member` | `industry_daily` / `symbol_metadata.industry_lv1` | 首页主视图；含资金流 & 估值 |
| 同花顺全部指数 | 1,234 | TuShare `ths_index` | `data/ths_all_indexes.csv` | 备用分类（概念/行业/地域/风格等） |
| 东方财富概念 | 559 | 东方财富 Web → TuShare 网关 | `data/dc_concept_boards.csv` | 历史概念，用于 `SymbolMetadata.concepts` 备选 |
| 东方财富行业 | 86 | 同上 | `data/industry_boards_em.csv` | 已弃用（比较/回归） |
| TuShare 申万行业 | 227 | TuShare `ths_index(type='I')` | 需脚本扩展 | 尚未启用，但 `industry_lv2/3` 预留 |

### 板块映射流程（`docs/board-mapping-guide.md` 精简）
1. **构建**：前端按钮或 `POST /api/boards/build`，默认仅 `industry`（15-20 分钟）；若含 `concept` 需 1-2 小时。
2. **验证**：`POST /api/boards/verify` 指定板块，返回新增/移除列表；可周常检查。
3. **手动 API**：`GET /api/boards/list`（可筛选 `board_type`），`GET /api/boards/concepts/{ticker}`。
4. **限流**：BoardMappingService 内建 12 秒延迟 + 抖动，建议非交易时段运行；概念板块默认关闭以避免超时。
5. **注意事项**：行业优先（稳定 90 个），概念板块体量大 + 频繁变化；可用断点续跑与增量验证。

## 8. 前端体验与验收要点
- **首页**：展示 90 个行业，默认按总市值排序，并显示涨跌幅/上涨家数/PE。
- **行业详情**：按 `market_cap` 排序的股票卡片，日/周/月切换保持同步；卡片顶部展示 `totalMv`、`peTtm`，右下角展示 `concepts`.
- **交互**：滚动加载、双击展开、刷新按钮显示最后更新时间。
- **验证清单**（来自 docs/frontend-verification）：
  - 后端 `curl /api/candles/000001?timeframe=day&limit=5` 返回数据。
  - 前端 5173 可访问并渲染 90 个行业。
  - Playwright 用例驗證：行业数量、详情页市值/PE/概念标签可见。
- **待完成**：全量 5,500 只股票数据下载、概念板块全量同步、前端 UI 全覆盖测试。

## 9. API 概览
- `GET /api/symbols`：按 `total_mv` 降序返回 `SymbolMeta` 列表。
- `GET /api/symbols/industries`：读取最新 `industry_daily` 记录，返回 90 行业/排序。
- `GET /api/candles/{ticker}?timeframe=day|week|month`：返回 `CandleBatchResponse`，Ticker 6 位正则校验。
- `POST /api/tasks/refresh`：触发 refresh（tickers/timeframes 可选）；默认 `DEFAULT_SYMBOLS` 或 DB 中已有股票。
- `GET /api/status`：返回最后刷新时间。
- `/api/boards/*`：构建、验证、列出板块与查询概念列表。

## 10. 运维脚本与数据资产
- **采集**：`scripts/download_sample_data.py`（前 50 只）、`download_all_data.py`（全量 + 估算耗时）。
- **行业映射**：`map_stocks_to_core_industries.py`（写入 `industry_lv1`），`update_industry_daily.py`（写 `industry_daily`），`create_industry_table.py`（建表）。
- **板块/概念**：`fetch_ths_core_industries.py`, `fetch_ths_industry_boards.py`, `fetch_ths_all_indexes.py`, `fetch_dc_concept_boards.py`, `build_watchlist_csv.py`, `build_stock_info_csv.py`, `populate_all_stocks.py`.
- **诊断/校验**：`check_and_reset_candles.py`, `diagnose_csv.py`, `test_industry_api.py`, `test_tushare_migration.py`.
- **数据文件**：  
  - `data/industry_board_constituents.csv` & `concept_board_constituents.csv`（部分含 `ERROR: Failed after retries`，需重抓）。  
  - `data/ths_core_industries.csv`, `ths_all_indexes.csv`, `dc_concept_boards.csv`, `watchlist_info.csv`, `stock_comprehensive_info.csv`（该文件中 `market_cap` 字段引用已废弃属性）。  
  - `logs/*.log` 追踪下载/刷新进度。

## 11. 现状评估（问题 & 风险）
1. **静态/动态字段未拆分**：`SymbolMetadata` 仍混合字段；`fetch_symbol_metadata` 每次调用都重新加载全市场 basic + daily_basic（即使只刷新几十只）。  
2. **行业聚合依赖手工脚本**：`scripts/update_industry_daily.py` 未纳入 APScheduler，若未运行会导致 `/api/symbols/industries` 返回空。  
3. **板块服务重复**：`BoardMappingService` 与 `TushareBoardService` 均维护概念板块逻辑，需统一 RateLimit/缓存。  
4. **脚本/CSV 中存在过时字段**：`build_stock_info_csv.py` 仍引用不存在的 `market_cap` 属性，`data/*constituents.csv` 有 `ERROR` 字段需清理。  
5. **数据文档不一致**：`docs/数据更新策略分析.md` 描述“仍为全量更新”，与 `docs/增量更新实施总结.md`/代码存在矛盾；需要统一以免误导。  
6. **缺少批量行情优化**：`TushareDataProvider.fetch_latest_prices` 逐只调用 `daily`（5000 API 调用），应改用按 `trade_date` 批量拉取。  
7. **测试覆盖有限**：仅覆盖增量更新/行业接口/正则校验；缺少对板块 API、`BoardMappingService`、`TushareClient` 限流、`IndustryDaily` 脚本的自动化测试。  
8. **数据增长/清理策略未成文**：虽然支持增量，但缺乏归档计划（SQLite 预计每年新增 ~2M K 线记录），以及老数据压缩/迁移方案。  
9. **前端验证待完成**：文档标记“50 票示例下载中、全量/页面测试未完成”，需跟踪完成度。  
10. **概念板块同步成本高**：`/api/boards/build` 若含概念需 1-2 小时 + 限流，尚无任务拆分/断点状态对外暴露。

## 12. 优化与改进路线（建议）
1. **数据模型拆分**：新增 `symbol_static_info` & `symbol_daily_metrics` 表；`refresh_universe` 增加 `update_static` 开关，仅在需要时刷新 `stock_basic`。  
2. **批量指标缓存**：`fetch_symbol_metadata` 支持注入外部 `stock_basic`/`daily_basic` 缓存，或在 `MarketDataService` 内共享一次调用。  
3. **行业数据自动化**：将 `update_industry_daily.py` 整合为 APScheduler 任务或 FastAPI 任务端点，确保 `/api/symbols/industries` 恒定可用。  
4. **板块同步统一化**：合并 `BoardMappingService` 与 `TushareBoardService`，抽象 RateLimit/重试，并提供任务状态（进度、剩余板块）。  
5. **CSV 清理与校验**：重跑 `concept_board_constituents.csv`、`industry_board_constituents.csv` 以替换 `ERROR` 行；修复 `stock_comprehensive_info.csv` 中错误字段。  
6. **扩展测试**：为 `/api/boards`、`BoardMappingService.verify_changes`、`fetch_candles_since`、`scripts/update_industry_daily` 写单元/集成测试；并加上 `pytest` fixture 管理 SQLite。  
7. **监控 & 报警**：记录 TuShare API 调用统计（成功/失败/重试），写入 logs + Prometheus 以监控限流/积分消耗。  
8. **前端验收自动化**：实现 `tests/frontend-validation.spec.ts`（Playwright）并接入 CI；覆盖首页行业数量、详情页指标显示。  
9. **数据归档策略**：考虑每年将旧 K 线迁移到 Parquet + 压缩，SQLite 保持最近 N 年数据，或定期 VACUUM。  
10. **概念板块增量**：为 `BoardMappingService` 引入 `since` 参数，结合 `verify_changes` 自动触发单板块重建而非全量。

## 13. 时间线 / Milestones
| 阶段 | 目标 | 产出 |
|------|------|------|
| Phase 1 | 完成示例 50 票 + 行业数据全通 | `download_sample_data`、`update_industry_daily` 定时、前端可浏览 | 
| Phase 2 | 全量 5,500 票 + 概念板块同步 | `download_all_data`, `map_stocks_to_core_industries`, `/boards` API 可用 | 
| Phase 3 | 增量策略上云 + 测试 | `SymbolDailyMetrics` 拆分、`pytest` 全量、Playwright 验收 | 
| Phase 4 | 规模化 & 监控 | API 调用统计、归档策略、CI 报告与仪表板 |

## 14. 附录
- **文档索引**（`docs/archive/`，保留细节以供查阅）  
  | 文档 | 作用 | 备注 |
  |------|------|------|
  | `tushare-ingestion-spec.md` | TuShare 接口、落库方案、更新节奏、FAQ | 原 `tushare-stock-data-prd.md` |
  | `frontend-data-sku-inventory.md` | 前端 SKU 统计、字段分类、更新频率、调用成本 | 原《前端数据SKU清单》 |
  | `data-refresh-analysis.md` | 全量 vs 增量流程痛点、下载量对比、时间周期判断 | 原《数据更新策略分析》 |
  | `field-update-strategy.md` | 静态/动态字段划分、拆表建议、刷新策略开关 | 原《数据字段更新策略》 |
  | `incremental-refresh-implementation.md` | `should_update_timeframe`、`fetch_candles_since`、upsert 实现与测试 | 原《增量更新实施总结》 |
  | `data-sources-and-calculations.md` | 指标/表的来源、计算逻辑（行业涨跌幅、PE、家数等） | 原《数据来源与计算逻辑》 |
  | `board-mapping-operations.md` | 板块构建、验证、限流策略与故障排查 | 原《板块映射功能使用指南》 |
  | `board-taxonomy-overview.md` & `board-classification-overview.md` | 不同板块体系（同花顺/东方财富/申万）规模与定位 | 原《board-taxonomy》《板块分类系统总览》 |
  | `frontend-verification-checklist.md` | 端到端验证脚本、Playwright 模板、DB 检查 SQL | 原《frontend-verification》 |
- README：整体结构、运行命令、下一步建议。
- **关键数据文件**：见第 10 节列出的 CSV 及 `data/market.db`.

---

> 本 PRD 合并原 9 份 Markdown，同时指明了已过时的描述（例如文档仍写“全量更新”但代码已实现增量），后续维护可围绕“静态/动态字段拆分、行业脚本自动化、板块同步统一化、文档与数据清理”四条路线推进。
