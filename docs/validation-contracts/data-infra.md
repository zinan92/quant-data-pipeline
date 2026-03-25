## Area: Data Infrastructure

### VAL-INFRA-001: Daily Kline Cleanup Retention Extended to 5 Years
The scheduled cleanup job must retain daily kline data for at least 1825 days (≈5 years) instead of the previous 365 days. After running the cleanup job, daily kline records older than 365 days but younger than 1825 days must survive deletion. Pass: daily klines with `trade_time` between 365 and 1825 days ago are **not** deleted by `cleanup_old_klines()`. Fail: any daily kline record younger than 1825 days is deleted.
Evidence: Inspect `src/services/calendar_updater.py` → `cleanup_old_klines()` default `days` parameter and the daily-line cutoff logic. Verify the scheduler call in `src/services/kline_scheduler.py` → `_job_cleanup()` passes `days=1825` (or the function default is changed to 1825). Insert a synthetic daily kline row dated 400 days ago, run cleanup, and confirm the row persists.

### VAL-INFRA-002: 30-Minute Kline Cleanup Retains ≤365-Day Policy
The 30-minute kline cleanup must keep its own retention window of 365 days (previously 90 days, now updated to 365). Pass: 30-min klines with `trade_time` within the last 365 days are preserved after cleanup. Fail: 30-min klines younger than 365 days are deleted, or 30-min cleanup is accidentally set to the same 1825-day window as daily.
Evidence: Inspect the `mins_cutoff` computation inside `cleanup_old_klines()` in `src/services/calendar_updater.py`. Verify it uses `timedelta(days=365)` for `KlineTimeframe.MINS_30`.

### VAL-INFRA-003: Trade Calendar Covers 2021 Through 2026
The `trade_calendar` table must contain rows spanning from 2021-01-01 to at least 2026-12-31. Pass: `SELECT MIN(date), MAX(date) FROM trade_calendar` returns a min ≤ 2021-01-04 and a max ≥ 2026-12-31. Fail: the min date is later than 2021-01-31 or the max date is earlier than 2026-12-01.
Evidence: Run `sqlite3 data/market.db "SELECT MIN(date), MAX(date) FROM trade_calendar;"` and verify the range. Also inspect `src/services/calendar_updater.py` → `update_trade_calendar()` to confirm `start_date` is hardcoded or computed to cover 2021 (previously used `current_year` only).

### VAL-INFRA-004: Trade Calendar Contains Reasonable Row Count for 2021-2026
The 6-year range should contain approximately 1,400–1,600 trading days (≈245 trading days/year × 6). Pass: `SELECT COUNT(*) FROM trade_calendar WHERE is_trading_day = 1` returns a value between 1,300 and 1,700. Fail: count is below 1,000 or above 2,000, indicating incomplete or corrupted data.
Evidence: Query `SELECT COUNT(*) FROM trade_calendar WHERE is_trading_day = 1;` against `data/market.db`.

### VAL-INFRA-005: INDEX_LIST Includes CSI 300, CSI 500, and CSI 1000
The `INDEX_LIST` constant in `src/services/index_updater.py` must include tuples for `000300.SH` (沪深300/CSI 300), `000905.SH` (中证500/CSI 500), and `000852.SH` (中证1000/CSI 1000) in addition to the original 5 indices. Pass: `INDEX_LIST` contains at least 8 entries and includes all three new codes. Fail: any of the three new index codes is missing from `INDEX_LIST`.
Evidence: Inspect `src/services/index_updater.py` line ~28. Run `grep -c "INDEX_LIST" src/services/index_updater.py` and visually confirm all 8 entries. Optionally query `SELECT DISTINCT symbol_code FROM klines WHERE symbol_code IN ('000300.SH','000905.SH','000852.SH') AND timeframe='day'` to verify data ingestion after a refresh cycle.

### VAL-INFRA-006: Original 5 Indices Remain in INDEX_LIST
Adding new indices must not remove or alter the original 5: `000001.SH`, `399001.SZ`, `399006.SZ`, `000688.SH`, `899050.BJ`. Pass: all 5 original codes are present in `INDEX_LIST`. Fail: any original index is missing or its name has been changed.
Evidence: Inspect `src/services/index_updater.py` → `INDEX_LIST` and confirm the original 5 tuples are intact.

### VAL-INFRA-007: Stock Universe Expanded to ~1000 Symbols
The watchlist or symbol_metadata table must reflect an expanded stock universe derived from merging index constituent lists (CSI 300 + CSI 500 + CSI 1000) with the existing watchlist. Pass: `SELECT COUNT(DISTINCT ticker) FROM watchlist` (or equivalent symbol_metadata query) returns ≥ 800 after the expansion process runs. Fail: count remains at ~422 or below 600.
Evidence: Query `SELECT COUNT(DISTINCT ticker) FROM watchlist;` and/or `SELECT COUNT(*) FROM symbol_metadata;` against `data/market.db`. Inspect the code that fetches constituent lists and merges them (likely in `src/services/stock_updater.py` or a new helper).

### VAL-INFRA-008: Constituent Merge Does Not Drop Existing Watchlist Stocks
Expanding the stock universe by adding index constituents must preserve all pre-existing watchlist entries. Pass: every ticker that existed in the watchlist before the expansion still exists afterward. Fail: any previously-tracked ticker is absent after the merge.
Evidence: Before expansion, capture `SELECT ticker FROM watchlist ORDER BY ticker` as a baseline. After expansion, verify `SELECT COUNT(*) FROM watchlist WHERE ticker IN (<baseline_list>)` equals the original count.

### VAL-INFRA-009: CANDLE_LOOKBACK Set to 1250
The `CANDLE_LOOKBACK` configuration value must be 1250 (previously 120) to support 5-year daily history fetching. Pass: `Settings().candle_lookback` returns 1250, whether via `.env` override or the code default. Fail: the value is anything other than 1250.
Evidence: Check `.env` for `CANDLE_LOOKBACK=1250`. Check `src/config.py` default: `Field(default=1250, alias="CANDLE_LOOKBACK")`. Run `python3 -c "from src.config import get_settings; print(get_settings().candle_lookback)"` from the project root and confirm output is `1250`.

### VAL-INFRA-010: CANDLE_LOOKBACK Default in Code Matches .env
The default value in `src/config.py` and the value in `.env` (if present) must both be 1250 to avoid silent misconfiguration. Pass: both sources agree on 1250. Fail: `.env` says one value and code default says another, or either is still the old value (120 or 200).
Evidence: Read `src/config.py` line with `candle_lookback` Field definition. Read `.env` for `CANDLE_LOOKBACK`. Both must show 1250.

### VAL-INFRA-011: Test Dependencies Installed and Discoverable
The `requirements-dev.txt` file must include `pytest`, `pytest-asyncio`, `pytest-cov`, and `httpx` (at minimum). These packages must be importable in the project virtual environment. Pass: `source .venv/bin/activate && python -c "import pytest, httpx"` succeeds with exit code 0. Fail: any import raises `ModuleNotFoundError`.
Evidence: Inspect `requirements-dev.txt`. Run `.venv/bin/python -m pytest --version` to confirm pytest is installed. Run `.venv/bin/python -c "import pytest; import httpx; import pytest_asyncio; import pytest_cov; print('OK')"`.

### VAL-INFRA-012: Pytest Suite Runs Without Import or Collection Errors
The test suite must be runnable end-to-end without crashing during collection. Individual test failures are acceptable at this stage, but collection errors or import failures are not. Pass: `.venv/bin/python -m pytest --collect-only` exits with code 0 and reports ≥1 test collected. Fail: pytest exits with a collection error or import failure.
Evidence: Run `.venv/bin/python -m pytest --collect-only 2>&1 | tail -5` and verify "X items collected" appears with no tracebacks.

### VAL-INFRA-013: Cleanup Does Not Run on Startup or During Tests
The destructive cleanup job must only run on its scheduled cron trigger (weekly), not during application startup, test runs, or manual data refresh. Pass: searching the startup and refresh code paths shows no call to `cleanup_old_klines()` outside the scheduler's `_job_cleanup` method. Fail: cleanup is invoked in `main.py`, `lifespan`, or any test fixture without explicit opt-in.
Evidence: Run `grep -rn "cleanup_old_klines" src/` and verify it only appears in `calendar_updater.py` (definition), `kline_updater.py` (delegation), and `kline_scheduler.py` (scheduled job). No calls in `main.py`, `lifespan.py`, or route handlers.

### VAL-INFRA-014: New Indices Have Corresponding Kline Data After Refresh
After a full index refresh cycle, the three new indices (000300.SH, 000905.SH, 000852.SH) must have kline data in the database. Pass: `SELECT COUNT(*) FROM klines WHERE symbol_code = '000300.SH' AND timeframe = 'day'` returns > 0 for each of the three codes. Fail: any of the three codes has zero rows.
Evidence: Run the index update job (or `scripts/` equivalent), then query `SELECT symbol_code, COUNT(*) FROM klines WHERE symbol_code IN ('000300.SH','000905.SH','000852.SH') AND timeframe='day' GROUP BY symbol_code;`.

### VAL-INFRA-015: Extended Calendar Does Not Break Date-Range Queries
API endpoints and services that use `trade_calendar` for date-range calculations must work correctly with the expanded 2021-2026 range. Pass: calling the candle API for a stock with `start_date=2021-06-01` does not error due to missing calendar entries. Fail: the API returns a 500 error or empty result because the calendar lacks entries before the current year.
Evidence: Invoke `GET /api/candles?symbol=000001.SZ&start_date=2021-06-01` (or equivalent test) and verify it returns a 200 response without calendar-related errors in the logs.
