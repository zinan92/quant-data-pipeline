# Code Review Remediation Report

**Date:** 2026-02-10
**Scope:** 29 tasks across 4 sprints, based on `docs/code-review-remediation-plan.md`
**Final Test Results:** 816 passed, 4 skipped, 4 pre-existing failures (unrelated)

---

## Sprint 1: Security Hardening (T-01 ~ T-08)

### T-01: API Key Authentication
- **New file:** `src/api/auth.py`
- Created `verify_api_key` dependency using `APIKeyHeader("X-API-Key")`
- Dev mode bypass: when `api_key` setting is empty, auth is skipped
- Added `api_key: str` and `debug: bool` fields to `src/config.py` Settings

### T-02: Auth on All Write Endpoints
- Added `_: None = Depends(verify_api_key)` to all POST/PUT/DELETE/PATCH endpoints
- **Files changed:** 10+ route files under `src/api/`

### T-03: Rate Limiting
- **New file:** `src/api/rate_limit.py` (shared `limiter` instance to avoid circular imports)
- Integrated `slowapi` into `web/app.py`
- Applied rate limit to RSS endpoint in `routes_news.py`
- Added `slowapi>=0.1.9` to `requirements.txt`

### T-04: SSRF Prevention
- **File:** `src/api/routes_news.py`
- Added `validate_rss_url()` with domain allowlist (`rsshub.app`, `feedx.net`, etc.)
- Blocks private IPs and non-HTTPS URLs

### T-05: Eliminate shell=True
- **File:** `src/tasks/scheduler.py`
- Replaced `subprocess.Popen(cmd, shell=True)` with `[sys.executable, str(script_path)]` + `start_new_session=True`

### T-06: Non-root Docker User
- **File:** `Dockerfile`
- Added `useradd appuser` + `USER appuser`

### T-07: Tighten CORS
- **File:** `web/app.py`
- Changed `allow_methods=["*"]` to explicit list `["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]`
- Changed `allow_headers=["*"]` to `["Content-Type", "Authorization", "X-API-Key"]`

### T-08: Hide Error Details in Production
- **Files:** ~14 route files
- Replaced all `str(e)` in HTTPException details with `str(e) if get_settings().debug else "Internal server error"`

---

## Sprint 2: Architecture Foundation (T-09 ~ T-14)

### T-09: Unify Session Management
- Replaced all `session_scope()` context manager usage with `Depends(get_db)` FastAPI dependency injection
- **Files changed:** `routes_watchlist.py`, `routes_evaluations.py`, `routes_boards.py`, `routes_meta.py`, `routes_concepts.py`

### T-10: Fix MarketDataService Session Leak
- **File:** `src/api/dependencies.py`
- Removed singleton `_market_data_service` global
- `get_data_service()` now takes `db: Session = Depends(get_db)` and creates per-request `MarketDataService` instances

### T-11: Eliminate Direct sqlite3 Calls
- **Files:** `routes_watchlist.py`, `routes_meta.py`, `src/perception/sources/market_data_source.py`
- Replaced `import sqlite3` + `sqlite3.connect()` with SQLAlchemy `text()` queries via `SessionLocal()`
- Changed parameter placeholders from `?` to `:name` style

### T-12: Delete models_old.py
- **Deleted:** `src/models_old.py` (529 lines of dead code)
- Verified no remaining imports reference the file

### T-13: Migrate lifecycle.py to Lifespan
- **File:** `src/lifecycle.py`
- Replaced deprecated `@app.on_event("startup"/"shutdown")` with `@asynccontextmanager async def lifespan(app)`
- Eliminated global `_scheduler_manager` variable

### T-14: Fix BaseRepository.count()
- **File:** `src/repositories/base_repository.py`
- Changed from `len(list(result.scalars().all()))` to `select(func.count()).select_from(self.model_class)` — avoids loading all rows into memory

---

## Sprint 3: Code Quality (T-15 ~ T-23)

### T-15: Fix Bare Except Blocks
- **Files:** `routes_pattern.py`, `routes_concepts.py`, `news_sentiment.py`, `anomaly_monitor.py`, `daily_review_data_service.py`
- Replaced 5 bare `except:` with `except Exception as e:` + proper logging

### T-16: Unify Exception Usage
- **Files:** 12 route files (35 replacements total)
- Replaced 32 `HTTPException(status_code=500)` with `DatabaseError(operation=..., reason=...)`
- Replaced 3 `HTTPException(status_code=503)` with `ServiceUnavailableError(service=..., reason=...)`
- Removed `HTTPException` import from 5 files that no longer use it
- Custom exception handlers in `web/app.py` now consistently handle all error responses

### T-17: Unify Logging
- **Files:** 31+ files across `src/`
- Replaced `import logging; logger = logging.getLogger(__name__)` with `from src.utils.logging import get_logger; logger = get_logger(__name__)`
- Replaced inline `logging.warning(...)` with `logger.warning(...)`

### T-18: Fix SQLite pool_size
- **File:** `src/database.py`
- SQLite now uses `StaticPool` (appropriate for single-connection SQLite)
- `pool_size=20` only applied to non-SQLite databases

### T-19: Rename TimeoutError
- **File:** `src/exceptions.py`
- Renamed `TimeoutError` to `OperationTimeoutError` to avoid shadowing Python's built-in `TimeoutError`

### T-20: Fix Perception Hardcoded Paths
- **Files:** `src/perception/pipeline.py`, `src/perception/sources/market_data_source.py`
- `PipelineConfig.db_path` now resolves from `get_settings().data_dir` via `__post_init__`
- `DEFAULT_DB_PATH` replaced with lazy `_get_default_db_path()` function

### T-21: Extract WatchlistService
- **New file:** `src/services/watchlist_service.py`
- Extracted `get_watchlist_items()`, `calculate_portfolio_history()`, `calculate_analytics()` from `routes_watchlist.py`
- Route handlers now delegate to `WatchlistService(db)`

### T-22: Fix routes_status.py Fake Timestamps
- **File:** `src/api/routes_status.py`
- `get_update_times()` now queries real `func.max(Kline.trade_time)` from DB instead of returning `datetime.now()`

### T-23: Merge Ticker Normalization
- **File:** `src/schemas/normalized.py` — added `VALID_PATTERNS`, `is_valid_ashare()`, `identify_market()` to `NormalizedTicker`
- **File:** `src/utils/ticker_utils.py` — rewritten as thin proxy delegating to `NormalizedTicker`

---

## Sprint 4: Testing (T-24 ~ T-29)

### T-24: Create Shared conftest.py
- **New file:** `tests/conftest.py`
- Three core fixtures:
  - `db_engine` — in-memory SQLite with `StaticPool`, all tables created via `Base.metadata.create_all()`
  - `db_session` — SQLAlchemy session, closed after each test
  - `client` — FastAPI `TestClient` with test DB injected via `dependency_overrides`, minimal app (no lifespan/scheduler)

### T-25: Test simulated_service
- **New file:** `tests/services/test_simulated_service.py`
- **24 tests** across 9 test classes
- Covers: account auto-creation, buy/sell, PnL calculation, position tracking, trade history with pagination, insufficient funds errors
- `simulated_service.py` coverage: **89%**

### T-26: Test data_pipeline
- **New file:** `tests/services/test_data_pipeline.py`
- **7 tests** across 3 test classes
- Covers: `list_symbols()`, `last_refresh_time()`, `refresh_metadata()` with mocked Tushare provider
- `data_pipeline.py` coverage: **69%**

### T-27: Test Uncovered API Routes
- **New files:** `tests/api/__init__.py`, `tests/api/test_routes_watchlist.py`
- **20 tests** across 8 test classes
- Covers all watchlist endpoints: GET list, POST add, DELETE remove/clear, GET check, PATCH focus/positioning, GET portfolio/history, GET analytics
- Includes `_ensure_stock_basic_table` fixture for the raw SQL table fallback

### T-28: Enable pytest-cov
- **File:** `pytest.ini`
- Enabled `--cov=src --cov-report=term-missing --cov-report=html:htmlcov --cov-fail-under=5`
- Installed `pytest-cov` (already in `requirements-dev.txt`)

### T-29: Clean Up Problem Test Files
- **`tests/test_momentum_signals.py`** — Rewrote: removed hardcoded paths to `/Users/park/`, replaced print-driven checks with proper pytest assertions
- **`test_market_style.py`** — Moved from project root to `tests/`, added `skipif` for missing `SuperCategoryDaily` model, uses `db_session` fixture
- **`tests/test_persist_metadata_chunking.py`** — Replaced `SessionLocal()` direct connection with `db_session` fixture
- **`tests/perception/test_pipeline.py`** — Fixed 4 broken `TestMarketDataSource` tests by patching `SessionLocal` to use the temp DB file (broken by T-11's sqlite3→SQLAlchemy migration)

---

## Files Created (8)

| File | Purpose |
|------|---------|
| `src/api/auth.py` | API key authentication middleware |
| `src/api/rate_limit.py` | Shared slowapi limiter instance |
| `src/services/watchlist_service.py` | Extracted watchlist business logic |
| `tests/conftest.py` | Shared test fixtures (db_engine, db_session, client) |
| `tests/api/__init__.py` | Test package init |
| `tests/api/test_routes_watchlist.py` | Watchlist API route tests (20 tests) |
| `tests/services/test_simulated_service.py` | Simulated trading service tests (24 tests) |
| `tests/services/test_data_pipeline.py` | Data pipeline service tests (7 tests) |

## Files Deleted (1)

| File | Reason |
|------|--------|
| `src/models_old.py` | 529 lines of dead code, all definitions already migrated to `src/models/` |

## Key Metrics

| Metric | Value |
|--------|-------|
| Tasks completed | 29/29 |
| Files modified | ~60+ |
| Files created | 8 |
| Files deleted | 1 |
| Dead code removed | 529 lines |
| New tests added | 51 (24 + 7 + 20) |
| Tests fixed | 7 (3 problem files + 4 perception tests) |
| Final test suite | 816 passed, 4 skipped, 4 pre-existing failures |
