# 板块与概念分类一览

汇总当前代码库涉及的行业/概念分类来源、规模及使用方式，方便对齐前端展示与数据刷新策略。

| 分类 | 数据源 & 接口 | 存储位置 / 触达方式 | 当前数量 | 更新时间/刷新方式 | 备注 |
|------|---------------|----------------------|-----------|--------------------|------|
| 同花顺核心行业 | TuShare `ths_industry_moneyflow` + `ths_member` | `data/ths_core_industries.csv`，`scripts/map_stocks_to_core_industries.py` | **90** (CSV 91 行含表头) | 通过 `TushareClient.get_latest_trade_date()` 获取最新交易日后可随时重建；通常月度/季度变动 | 用于“90个核心行业”视图，也是 `SymbolMetadata.industry_lv1` 的主要来源 |
| 东方财富行业板块 | 东方财富 Web API（原始 CSV `data/industry_boards_em.csv`） | `data/industry_boards_em.csv`、`data/industry_board_constituents.csv` | **86** | 手动脚本生成；当前 CSV 为 2025-11 快照 | 仍保留供比对/回归使用，前端默认使用同花顺 90 行业 |
| 东方财富概念板块 | 东方财富 Web API (`data/concept_board_constituents.csv`) | `data/concept_board_constituents.csv` | **442** | 手动脚本生成；与 `BoardMappingService` 无直接关联 | 保留历史概念划分，现阶段概念同步主要走 TuShare/同花顺 |
| 同花顺概念板块 | TuShare `ths_index(type='N')` + `ths_member` | 运行 `src/services/tushare_board_service.py` 或 `scripts/test_tushare_migration.py` 时实时获取 | 400+（依赖账号权限，运行时决定） | 需要 5000+ 积分；`TushareBoardService.sync_concept_boards()` 会全量替换 `board_mapping` 中 `concept` 记录 | 当前 API 端 `/api/boards/*` 面向该数据集 |

> 注：如果需要新增分类（如地域、风格等），`TushareClient.fetch_ths_index` 同样支持 `type='R'/'S'/...`，只需在 BoardMappingService/TushareBoardService 中扩展映射逻辑即可。
