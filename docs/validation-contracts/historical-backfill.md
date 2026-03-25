## Area: Historical Backfill

### VAL-BACKFILL-001: Stock Daily Data Covers 5-Year Date Range
Each backfilled stock must have daily kline data reaching back at least 5 years. Pass: for every symbol_code in the expanded stock universe (~1000 stocks), `SELECT MIN(trade_time) FROM klines WHERE symbol_type='stock' AND symbol_code=<code> AND timeframe='DAY'` returns a date ≤ 2021-03-25. Fail: any stock's earliest record is later than 2021-06-01 (allowing a 3-month grace period for IPOs after 2021-01-01).
Evidence: Query `SELECT symbol_code, MIN(trade_time) AS min_date FROM klines WHERE symbol_type='stock' AND timeframe='DAY' GROUP BY symbol_code HAVING min_date > '2021-06-01';` — result set must be empty (or only contain stocks listed after 2021-01-01). Cross-check against `list_date` in symbol metadata to exclude recently-listed stocks.

### VAL-BACKFILL-002: Sufficient Row Count Per Stock (~1250 Trading Days)
Each stock with a listing date on or before 2021-01-01 should have approximately 1,200–1,300 daily kline rows (≈245 trading days/year × 5 years). Pass: `SELECT COUNT(*) FROM klines WHERE symbol_type='stock' AND symbol_code=<code> AND timeframe='DAY'` returns ≥ 1,100 for stocks listed before 2021. Fail: any pre-2021 stock has fewer than 1,000 rows, indicating missing data or incomplete backfill.
Evidence: Query `SELECT symbol_code, COUNT(*) AS cnt FROM klines WHERE symbol_type='stock' AND timeframe='DAY' GROUP BY symbol_code HAVING cnt < 1000;` and cross-reference results against `list_date` to filter out stocks listed after 2021-01-01.

### VAL-BACKFILL-003: No Gaps in Stock Daily Data Against Trade Calendar
Stock daily data must have no missing trading days when compared against the `trade_calendar` table. Pass: for a sample of 50 stocks, the set of `trade_time` dates matches all trading days in `trade_calendar` between the stock's `list_date` (or 2021-01-01, whichever is later) and the latest backfill date. Fail: any sampled stock is missing more than 5 trading days (allowing for suspensions).
Evidence: For each sampled stock, compute `SELECT date FROM trade_calendar WHERE is_trading_day=1 AND date >= '2021-01-01' EXCEPT SELECT trade_time FROM klines WHERE symbol_type='stock' AND symbol_code=<code> AND timeframe='DAY';` — the result set should contain ≤ 5 dates per stock (suspended days). Aggregate: `SELECT symbol_code, COUNT(*) AS gaps FROM (...) GROUP BY symbol_code HAVING gaps > 5;` must be empty or explainable by known suspensions.

### VAL-BACKFILL-004: Index Daily Data Covers 5-Year Range for All 8 Indices
All 8 tracked indices (000001.SH, 399001.SZ, 399006.SZ, 000688.SH, 899050.BJ, 000300.SH, 000905.SH, 000852.SH) must have daily kline data from 2021-01-04 (first trading day of 2021) to the latest trading day. Pass: for each index code, `MIN(trade_time) ≤ '2021-01-08'` and `MAX(trade_time)` is within the last 5 trading days. Fail: any index has a start date later than 2021-01-31 or a max date more than 5 trading days behind today.
Evidence: Query `SELECT symbol_code, MIN(trade_time) AS min_d, MAX(trade_time) AS max_d, COUNT(*) AS cnt FROM klines WHERE symbol_type='index' AND timeframe='DAY' AND symbol_code IN ('000001.SH','399001.SZ','399006.SZ','000688.SH','899050.BJ','000300.SH','000905.SH','000852.SH') GROUP BY symbol_code;` — verify 8 rows returned, each with min_d ≤ '2021-01-08' and cnt ≥ 1,100.

### VAL-BACKFILL-005: Index Daily Data Has No Significant Gaps
Index kline data should be continuous with no missing trading days. Pass: for each of the 8 indices, comparing kline dates against `trade_calendar` yields zero missing dates over the 5-year range. Fail: any index is missing more than 2 trading days.
Evidence: For each index, run `SELECT date FROM trade_calendar WHERE is_trading_day=1 AND date >= '2021-01-04' AND date <= '<latest_trade_date>' EXCEPT SELECT trade_time FROM klines WHERE symbol_type='index' AND symbol_code=<code> AND timeframe='DAY';` — result must be empty or contain at most 2 dates.

### VAL-BACKFILL-006: Concept Board Data Has Historical Coverage
The `concept_daily` table must contain historical data for concept boards spanning at least 2 years back (TuShare ths_daily() data availability may be limited). Pass: `SELECT MIN(trade_date) FROM concept_daily` returns a date ≤ 20240325 (at least 2 years of data), and `SELECT COUNT(DISTINCT code) FROM concept_daily` returns ≥ 300 concept codes. Fail: the earliest date is later than 20250101 (less than 1 year of history) or fewer than 200 distinct concepts exist.
Evidence: Query `SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT code), COUNT(*) FROM concept_daily;` and verify the date range and concept count. Note: TuShare ths_daily() historical depth varies; document the actual achievable range.

### VAL-BACKFILL-007: Industry Board Data Has Historical Coverage
The `industry_daily` table must contain historical data from `moneyflow_ind_ths()` spanning the maximum available range. Pass: `SELECT MIN(trade_date) FROM industry_daily` returns a date ≤ 20240325 (at least 2 years), and `SELECT COUNT(DISTINCT ts_code) FROM industry_daily` returns ≥ 80 industry codes. Fail: the earliest date is later than 20250101 or fewer than 60 distinct industries exist.
Evidence: Query `SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT ts_code), COUNT(*) FROM industry_daily;` and verify. Cross-check `COUNT(DISTINCT ts_code)` against the ~90 industries listed in TuShare's ths_index(type='I').

### VAL-BACKFILL-008: Backfill Scripts Are Idempotent
Running the backfill script a second time on an already-backfilled database must not create duplicate rows or corrupt existing data. Pass: after running the backfill twice, `SELECT symbol_type, symbol_code, timeframe, trade_time, COUNT(*) FROM klines GROUP BY symbol_type, symbol_code, timeframe, trade_time HAVING COUNT(*) > 1` returns zero rows. The UniqueConstraint on `(symbol_type, symbol_code, timeframe, trade_time)` must prevent duplicates. Fail: any duplicate rows exist, or the second run raises an unhandled constraint violation error.
Evidence: Run the backfill script, record total row count via `SELECT COUNT(*) FROM klines`. Run it again. Verify the count is unchanged (or only increased by new trading days that occurred between runs). Confirm no errors in logs. Also verify for `concept_daily` and `industry_daily` tables using their respective unique constraints on `(code, trade_date)` and `(ts_code, trade_date)`.

### VAL-BACKFILL-009: Backfill Scripts Support Resume After Interruption
If a backfill script is interrupted (e.g., killed mid-run), restarting it must resume from where it left off rather than restarting from scratch. Pass: after interrupting a backfill at ~50% completion, restarting the script detects already-backfilled symbols and skips them, completing only the remaining symbols. The total runtime of the resumed run is significantly less than a fresh run. Fail: the script re-fetches data for all symbols from the beginning, wasting API calls and time.
Evidence: Instrument the backfill script to log which symbols are skipped vs. fetched. After interruption and restart, verify that logs show "skipping <symbol>, already has data through <date>" for previously-completed symbols. Alternatively, check that the script queries `MAX(trade_time)` per symbol before deciding whether to fetch.

### VAL-BACKFILL-010: TuShare Rate Limiting Is Respected
The backfill process must not exceed TuShare's rate limits (180 calls/minute for 5000+ points). Pass: throughout a full backfill run, no TuShare API errors with codes indicating rate-limiting (e.g., "exceed the limit", HTTP 429, or similar) appear in logs. The `RateLimiter` in `src/services/tushare_client.py` must enforce ≤ 180 calls per 60-second window. Fail: any rate-limit error appears in logs, or the backfill is banned/blocked by TuShare.
Evidence: Grep backfill logs for "达到调用限制", "exceed", "429", or "banned". Inspect `TushareClient.__init__()` to confirm `max_calls` is ≤ 180 for `points=5000`. Monitor API call timestamps in logs to verify no burst exceeds 180/minute.

### VAL-BACKFILL-011: Backfill Does Not Conflict With Live Update Scheduler
Running a historical backfill must not interfere with the scheduled live update jobs (`_job_daily_refresh`, `_job_30m_refresh`). Pass: if the backfill is running when a scheduled update fires, either (a) the scheduler gracefully skips the overlapping update with a log message, or (b) both run concurrently without data corruption (SQLite WAL mode supports concurrent reads). Fail: a deadlock occurs, data is corrupted, or the scheduler crashes with a "database is locked" error.
Evidence: Review the scheduler's locking/guard mechanism in `src/services/kline_scheduler.py`. Check for `_running` flags or mutex usage. Verify SQLite WAL mode is enabled in `src/database.py` (PRAGMA journal_mode=WAL). Simulate by starting a backfill and triggering a manual scheduler job simultaneously; confirm no errors in either log stream.

### VAL-BACKFILL-012: All ~1000 Stocks Have Been Backfilled
The backfill must cover the full expanded stock universe (CSI 300 + CSI 500 + CSI 1000 constituents merged with existing watchlist). Pass: `SELECT COUNT(DISTINCT symbol_code) FROM klines WHERE symbol_type='stock' AND timeframe='DAY'` returns ≥ 800. Fail: the count is below 600, indicating the backfill did not process the full universe.
Evidence: Query `SELECT COUNT(DISTINCT symbol_code) FROM klines WHERE symbol_type='stock' AND timeframe='DAY';`. Compare against the expected symbol count from the constituent merge. Check backfill logs for any symbols that were skipped due to errors.

### VAL-BACKFILL-013: Backfill Uses pro.daily() for Stocks (Not Sina/AkShare)
Stock daily backfill must use TuShare `pro.daily()` (via `TushareClient.fetch_daily()`) as the data source, not Sina or AkShare, to ensure consistent 5-year history. Pass: the backfill code calls `TushareClient.fetch_daily()` or `self.pro.daily()` for stock data. Fail: the backfill falls back to Sina or AkShare APIs for historical daily data.
Evidence: Inspect the backfill script/function for stock daily data. Verify it uses `TushareClient.fetch_daily(ts_code=..., start_date='20210101', end_date=...)`. Grep for any references to `httpx`, `akshare`, or `sina` in the backfill code path.

### VAL-BACKFILL-014: Backfill Uses pro.index_daily() for Indices
Index daily backfill must use TuShare `pro.index_daily()` (via `TushareClient.fetch_index_daily()`) instead of the current Sina API source in `IndexUpdater`, since Sina only provides recent data. Pass: the backfill code for indices calls `TushareClient.fetch_index_daily()`. Fail: index backfill still uses Sina `_fetch_kline()` for historical data.
Evidence: Inspect the index backfill code path. Verify it calls `fetch_index_daily(ts_code=..., start_date='20210101', ...)` for each of the 8 indices.

### VAL-BACKFILL-015: OHLCV Fields Are Non-Null and Valid
All backfilled kline rows must have valid, non-null OHLCV data. Pass: `SELECT COUNT(*) FROM klines WHERE (open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL) AND timeframe='DAY'` returns 0. Additionally, `high >= low` and `high >= open` and `high >= close` for every row. Fail: any NULL OHLCV fields or price violations (high < low) exist.
Evidence: Run `SELECT COUNT(*) FROM klines WHERE open IS NULL OR close IS NULL OR high < low;` — must return 0. Sample-check: `SELECT * FROM klines WHERE high < low LIMIT 10;` must return empty.

### VAL-BACKFILL-016: Backfill Progress Is Logged and Trackable
The backfill process must log progress at regular intervals so operators can monitor completion. Pass: logs contain periodic progress messages (e.g., "Backfilled 100/1000 stocks", "Progress: 10%") at least every 50 symbols. Fail: the backfill runs silently with no progress indication, or only logs at start and end.
Evidence: Grep backfill logs for progress indicators. Verify the code contains logging statements inside the per-symbol loop. Check that `DataUpdateLog` entries are created in the database for backfill operations.

### VAL-BACKFILL-017: Backfill Handles Delisted and Suspended Stocks Gracefully
When the backfill encounters a stock that was delisted or suspended for extended periods, it must not crash. Pass: if TuShare returns empty data for a symbol, the backfill logs a warning and continues to the next symbol. The overall backfill completes even if some symbols have no data. Fail: the backfill raises an unhandled exception and aborts when encountering an empty response.
Evidence: Check the backfill code for try/except handling around the per-symbol fetch. Verify logs contain warnings like "No data for <symbol>, skipping" rather than stack traces. Confirm the final completion log shows the total successfully backfilled count vs. skipped count.

### VAL-BACKFILL-018: Concept Backfill Uses TuShare ths_daily()
Concept board historical data must be fetched via TuShare's `ths_daily()` API. Pass: the concept backfill code calls `pro.ths_daily(ts_code=..., start_date=..., end_date=...)` for each concept board. Fail: concept backfill uses only AkShare or scrapes data from web sources.
Evidence: Inspect the concept backfill script (likely `scripts/update_concept_daily.py` or a new backfill module). Verify it contains calls to `pro.ths_daily()` with historical date ranges.

### VAL-BACKFILL-019: Industry Backfill Uses TuShare moneyflow_ind_ths()
Industry board historical data must be fetched via TuShare's `moneyflow_ind_ths()` API (via `TushareClient.fetch_ths_industry_moneyflow()`). Pass: the industry backfill code iterates over trading dates and calls `moneyflow_ind_ths(trade_date=...)` for each date. Fail: industry backfill uses a different API or only fetches the latest day.
Evidence: Inspect the industry backfill script (likely `scripts/update_industry_daily.py` or a new backfill module). Verify it loops over historical trade dates and calls `fetch_ths_industry_moneyflow(trade_date=...)` for each.

### VAL-BACKFILL-020: Total Backfill API Calls Are Within Budget
The total number of TuShare API calls for a full backfill must be estimated and documented, and must be completable within a reasonable time given the 180 calls/min rate limit. Pass: stock backfill (~1000 calls for daily, one per stock) + index backfill (8 calls) + concept backfill (~400 calls or date-iterated) + industry backfill (~1250 date-iterated calls) are documented with estimated total time. The entire backfill completes within 24 hours. Fail: the backfill takes more than 48 hours or the API call count is not documented.
Evidence: Check backfill documentation or comments for API call budget. Calculate: 1000 stock calls + 8 index calls ≈ 1008 calls ≈ 6 minutes at 180/min. For date-iterated APIs: ~1250 trading days × 1 call/day = 1250 calls ≈ 7 minutes. Total ≈ 15-30 minutes for the primary backfill. Verify actual runtime from logs.
