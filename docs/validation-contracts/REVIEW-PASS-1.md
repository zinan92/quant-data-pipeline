# Validation Contract Review — Pass 1 (Adversarial)

**Reviewer:** Automated critical review  
**Date:** 2026-03-25  
**Scope:** All 4 contract files (59 total assertions: 15 infra + 20 backfill + 16 health + 8 cross-area)

---

## 🔴 CRITICAL: SQL Case Mismatch in Evidence Queries

**This affects almost every assertion in the backfill and cross-area contracts.**

The database stores enum values in **UPPERCASE** (`STOCK`, `INDEX`, `DAY`, `MINS_30`), verified directly:
```
sqlite3> SELECT DISTINCT symbol_type FROM klines;
→ INDEX, STOCK

sqlite3> SELECT COUNT(*) FROM klines WHERE symbol_type='stock';  → 0
sqlite3> SELECT COUNT(*) FROM klines WHERE symbol_type='STOCK';  → 255753
sqlite3> SELECT COUNT(*) FROM klines WHERE timeframe='day';      → 0
sqlite3> SELECT COUNT(*) FROM klines WHERE timeframe='DAY';      → 63617
```

Yet the contracts use **lowercase** `symbol_type='stock'` and mixed `timeframe='day'`/`timeframe='DAY'` in their SQL evidence queries. **Every validator who copy-pastes the evidence SQL will get zero results and a false pass/fail.**

**Affected assertions (lowercase `symbol_type='stock'`):**
- VAL-BACKFILL-001, 002, 003, 012 — all use `symbol_type='stock'`
- VAL-CROSS-001, 002, 004, 006, 007 — all use `symbol_type='stock'`

**Affected assertions (lowercase `timeframe='day'`):**
- VAL-INFRA-005 (evidence query uses `timeframe='day'`)
- VAL-INFRA-014 (evidence query uses `timeframe='day'`)

**Fix:** Replace all `symbol_type='stock'` with `symbol_type='STOCK'`, `symbol_type='index'` with `symbol_type='INDEX'`, and `timeframe='day'` with `timeframe='DAY'` in evidence queries.

---

## 🟡 MISSING ASSERTIONS

### MISS-001: Backfill Script CLI Invocability
**Draft ID:** VAL-BACKFILL-021  
**Title:** Backfill Scripts Are Executable from Command Line  
**Description:** There is no assertion verifying the backfill scripts can actually be invoked from the command line. VAL-BACKFILL-008/009 assume scripts exist and run, but never assert they have a proper entry point, argument parsing, or even that `python scripts/backfill_stock_daily.py` works without error. Should verify: `python scripts/<backfill_script>.py --help` (or equivalent) exits 0, and the script name/path is documented.

### MISS-002: Backfill Writes to Klines Table (Not Just Fetches)
**Draft ID:** VAL-BACKFILL-022  
**Title:** Backfill Persists Data to Klines Table  
**Description:** Multiple assertions check for data _presence_ in the klines table post-backfill (e.g., VAL-BACKFILL-001, 002, 012), but none explicitly assert the backfill code contains a _write path_ to the klines table. A backfill could fetch data from TuShare and silently drop it. Should verify the code contains an explicit `INSERT` or `session.add()` for klines, and that a small-scope test run (e.g., 1 stock) actually increases the klines row count.

### MISS-003: Concept/Industry Daily Table Schema vs ths_daily() Response Compatibility
**Draft ID:** VAL-BACKFILL-023  
**Title:** ConceptDaily and IndustryDaily Schemas Are Compatible with TuShare Response  
**Description:** The `ConceptDaily` model has fields like `code`, `name`, `close`, `pct_change`, `volume`, `amount`, `leader_symbol`, etc. But TuShare `ths_daily()` returns columns like `ts_code`, `close`, `pct_change`, `turnover_rate`, etc. There's no assertion that verifies the column mapping between TuShare's response format and the ORM models. A field mismatch would cause silent data loss. Similarly, `IndustryDaily` has fields like `net_buy_amount`, `net_sell_amount`, `industry_pe` — these must be validated against `moneyflow_ind_ths()` response columns. The existing `ConceptDaily.code` vs TuShare's `ts_code` is a known mapping that must be explicitly tested.

### MISS-004: stock_sectors Table Needs Re-population After Universe Expansion
**Draft ID:** VAL-INFRA-016  
**Title:** stock_sectors Table Updated for Expanded Stock Universe  
**Description:** The `stock_sectors` table maps watchlist stocks to sector categories (e.g., "贵金属", "消费") and is used by the health dashboard, sector rotation analysis, and the daily briefing. When the universe expands from ~422 to ~1000 stocks, newly-added stocks will have NO sector mapping. This breaks: (a) sector-based analytics, (b) the routes_sectors API, (c) category-based filtering in the watchlist view. Should assert: after expansion, `SELECT COUNT(*) FROM watchlist w LEFT JOIN stock_sectors s ON w.ticker = s.ticker WHERE s.ticker IS NULL` returns a count that is documented and has a plan (even if sectors are assigned later).

### MISS-005: Quant-Dashboard IndexFetcher Conflict/Redundancy with New CSI 300 in market.db
**Draft ID:** VAL-CROSS-009  
**Title:** Quant-Dashboard IndexFetcher Does Not Conflict with CSI 300 Now in market.db  
**Description:** The `quant-dashboard` project has an `IndexFetcher` that independently fetches CSI 300 data via AkShare into a _separate_ `index_cache.db`. After this mission, CSI 300 will exist in `market.db` (via ashare's `INDEX_LIST` and backfill). Now there are TWO sources of CSI 300 data with potentially different values (AkShare vs TuShare, different OHLCV precision). The `streamlit_app.py` uses `IndexFetcher` for CSI 300 benchmarks. Should assert: either (a) quant-dashboard is updated to use `MarketReader.get_index_klines('000300.SH')` instead of `IndexFetcher`, or (b) both sources are documented as intentionally different with an explanation of which is authoritative.

### MISS-006: Health Page Navigation from Main Nav
**Draft ID:** VAL-HEALTH-017  
**Title:** Health Page Is Accessible from Main Navigation  
**Description:** The health page already has a nav button ("❤️ 健康") in the existing `App.tsx` header. However, after the upgrade adds multiple new sections, there's no assertion verifying the page is still navigable and the route `/health` still works. While unlikely to break, the fact that this is a milestone deliverable means it should have explicit navigation coverage. **Assessment: LOW priority** — the existing App.tsx already has this, and VAL-HEALTH-001 implicitly covers it by navigating to `/health`.

### MISS-007: 30-Minute Kline Data Retention After Expansion
**Draft ID:** VAL-INFRA-016 (alt)  
**Title:** 30-Minute Kline Data for ~1000 Stocks Does Not Exceed Storage Bounds  
**Description:** Expanding from ~422 to ~1000 stocks means ~2.4x more 30-minute kline data. With 365-day retention at ~4800 bars/stock/year, that's ~4.8M rows for 30-min data alone. No assertion checks whether SQLite performance degrades or whether the database file size is tracked. Should at least document expected DB size post-backfill.

### MISS-008: Backfill Script Sources Symbol List from Expanded Watchlist
**Draft ID:** VAL-BACKFILL-024  
**Title:** Backfill Script Reads Symbol List from Watchlist Table (Post-Expansion)  
**Description:** VAL-CROSS-002 mentions this in its evidence section but it's not a standalone assertion. There's a risk the backfill script hardcodes a symbol list or reads from a file rather than the watchlist table. Should explicitly assert: the backfill code's symbol source is `SELECT ticker FROM watchlist` (or equivalent), ensuring it automatically picks up the expanded universe.

### MISS-009: Stocks That IPO'd Between 2021-2026 Are Handled Correctly
**Draft ID:** VAL-BACKFILL-025  
**Title:** Post-2021 IPO Stocks Have Data Starting from Their list_date  
**Description:** VAL-BACKFILL-001 has a grace period for post-2021 IPOs but doesn't explicitly verify these stocks have data starting from their actual `list_date`. A stock that IPO'd in 2023 should have data from 2023, not be silently skipped. Should assert: for stocks with `list_date > '2021-01-01'`, their earliest kline `trade_time` is within 5 trading days of their `list_date`.

### MISS-010: ths_daily() Historical Data Availability Fallback
**Draft ID:** VAL-BACKFILL-026  
**Title:** Concept Backfill Documents and Handles Limited TuShare Historical Depth  
**Description:** VAL-BACKFILL-006 notes "TuShare ths_daily() historical depth varies" and sets a soft threshold of 2 years. But there's no assertion about what happens if `ths_daily()` only returns 1 year of data for some concepts, or if the API returns errors for historical dates. Should assert: the backfill code logs a warning when a concept has less than the target date range and continues, and the final report shows per-concept achievable date ranges.

---

## 🟡 WEAK ASSERTIONS (Need Strengthening)

### WEAK-001: VAL-BACKFILL-006 — Concept Board Data Threshold Too Soft
The pass condition says ≥300 concept codes and data back to 2024-03-25 (2 years). But the fail condition is <200 concepts OR data only within the last year. The gap between pass (≥300) and fail (<200) leaves 200-299 concepts in an undefined state. **Fix:** Remove the gray zone — pass ≥250, fail <250.

### WEAK-002: VAL-BACKFILL-007 — Industry Board Threshold Similarly Soft
Same issue: pass ≥80, fail <60. What about 60-79? **Fix:** pass ≥70, fail <70.

### WEAK-003: VAL-BACKFILL-020 — "Completable Within 24 Hours" Is Too Generous
The evidence section estimates ~15-30 minutes for the full backfill. A 24-hour pass threshold means a broken rate limiter or API issue could go undetected (e.g., constant retries). **Fix:** Set pass threshold to "completes within 2 hours" and fail at >4 hours.

### WEAK-004: VAL-HEALTH-009 — Permission Request on First Visit Only
The assertion says "when a user first visits `/health`" but the pass condition also accepts "if permission was already granted/denied, no prompt appears." This means the assertion passes trivially on any non-first visit. **Fix:** Require testing in a fresh browser context (incognito) and asserting `Notification.requestPermission()` was actually called (via code inspection, not just runtime observation).

### WEAK-005: VAL-INFRA-007 — "≥800 After Expansion" Threshold
CSI 300 + CSI 500 + CSI 1000 overlap heavily (CSI 300 ⊂ CSI 500 universe sometimes, and many stocks appear in multiple indices). The actual unique count after deduplication might be closer to 900-1100. Setting ≥800 could pass even if the merge is buggy and drops 200 stocks. **Fix:** Assert ≥900 (with documented expected count from dry-run constituent fetch).

### WEAK-006: VAL-HEALTH-004 — "Does Not Attempt to Render 1000+ Rows Simultaneously"
This is vague. How does a validator determine this? Checking the DOM count? The assertion should specify: either pagination is present (page controls visible), OR a search/filter input exists, OR virtual scrolling is used (inspect DOM for windowed rendering). **Fix:** Require at least one concrete UI mechanism to be identified.

### WEAK-007: VAL-INFRA-003 — Trade Calendar Fail Condition Too Loose
Pass requires min ≤ 2021-01-04, but fail only triggers if min > 2021-01-31. That means a calendar starting 2021-01-05 through 2021-01-31 is in an undefined state. **Fix:** Tighten fail to min > 2021-01-08 (first trading week of 2021).

---

## 🟠 REDUNDANT ASSERTIONS (Could Be Merged)

### REDUND-001: VAL-INFRA-009 + VAL-INFRA-010 (CANDLE_LOOKBACK)
VAL-INFRA-009 asserts `CANDLE_LOOKBACK = 1250` at runtime. VAL-INFRA-010 asserts the code default and `.env` both say 1250. These are testing the same thing from two angles. **Recommendation:** Merge into one assertion with two evidence checks (code inspection + runtime verification).

### REDUND-002: VAL-BACKFILL-004 + VAL-CROSS-003 (New Indices 5-Year Data)
VAL-BACKFILL-004 asserts all 8 indices have 5-year data. VAL-CROSS-003 specifically asserts the 3 _new_ indices have 5-year data. VAL-CROSS-003 is a strict subset of VAL-BACKFILL-004. **Recommendation:** Keep VAL-CROSS-003 only if it adds a cross-area dependency check (verify backfill uses the same INDEX_LIST from milestone 1); otherwise merge.

### REDUND-003: VAL-BACKFILL-001 + VAL-BACKFILL-002 + VAL-BACKFILL-012 (Stock Coverage)
These three assertions all check different facets of "stocks have data": 001 checks date range, 002 checks row count, 012 checks distinct symbol count. While each tests something different, the overlap is significant. **Recommendation:** Keep all three but add a note that 001+002 are per-stock quality checks while 012 is a universe completeness check — they serve different purposes.

---

## 🔵 TESTABILITY CONCERNS

### TEST-001: Backfill Assertions Require Full Backfill Run (~1000 stocks × 5 years)
VAL-BACKFILL-001 through 005, 012, and 015 all require the backfill to have completed. Running a full backfill takes 15-30 minutes even at optimal rate limits. **Concern:** Validators cannot quickly re-test these assertions. **Mitigation:** Add a note that these are "post-backfill" assertions to be validated once, not on every code change. Consider a "smoke test" variant that validates 5 randomly-sampled stocks.

### TEST-002: VAL-BACKFILL-009 (Resume After Interruption) Is Hard to Automate
Testing resume requires: start backfill → wait for ~50% → kill process → restart → verify skipping. This is inherently timing-dependent and fragile. **Mitigation:** Allow code inspection as primary evidence (check for `MAX(trade_time)` query before fetch) with runtime test as secondary.

### TEST-003: VAL-HEALTH-010 (Browser Notification on Status Transition) Requires Simulated State Change
Testing this requires the backend health status to actually change between polling cycles, which means manipulating the database mid-test. **Mitigation:** Allow testing via the component's internal state management (mock status change) rather than requiring an actual backend transition.

### TEST-004: VAL-BACKFILL-011 (No Conflict with Live Scheduler) Is a Concurrency Test
Testing simultaneous backfill + scheduler requires careful orchestration and may produce non-deterministic results. SQLite locking behavior varies by OS and filesystem. **Mitigation:** Accept code review of WAL mode + locking guards as primary evidence; concurrent runtime test as secondary.

### TEST-005: Evidence SQL in Contracts Uses Inconsistent Table/Column Names
Several evidence queries reference tables or columns that may not exist yet (e.g., `symbol_metadata`, `stock_basic.list_date`). Validators need to verify these table/column names match the actual schema before running queries. **Mitigation:** Add a "prerequisite: verify schema" step or provide a schema dump for reference.

---

## 📊 OVERALL ASSESSMENT

### Strengths
1. **Comprehensive coverage** — 59 assertions spanning all 3 milestones with good cross-area integration tests
2. **Well-structured pass/fail criteria** — most assertions have clear, binary outcomes
3. **Evidence sections are detailed** — SQL queries, code inspection steps, and API calls are provided
4. **Cross-area flows are smart** — catching interactions like cleanup-vs-backfill (VAL-CROSS-004) and calendar-powering-gap-detection (VAL-CROSS-005) is excellent

### Critical Issues
1. **🔴 SQL case mismatch is a showstopper** — ~15 assertions have evidence queries that return wrong results due to `'stock'` vs `'STOCK'` and `'day'` vs `'DAY'`. Must fix before any validation run.
2. **Missing `stock_sectors` coverage** — the universe expansion will break sector-based features with no assertion to catch it
3. **No IndexFetcher conflict assertion** — two competing sources of CSI 300 data will exist with no clarity on which is authoritative
4. **No backfill CLI invocability assertion** — we assume scripts exist but never test they can actually be run

### Moderate Issues
5. Several pass/fail thresholds have gray zones (concepts 200-299, industries 60-79)
6. Backfill time budget pass condition (24 hours) is ~50-100x too generous
7. No assertion for concept/industry schema compatibility with TuShare response format
8. Post-2021 IPO stocks need explicit list_date-based validation

### Verdict
**The contracts are ~80% solid but need a revision pass** to fix the SQL case mismatch (blocks all testing), add 5-6 missing assertions for identified gaps, and tighten ~5 weak thresholds. The cross-area flows section is the strongest part. The health dashboard section is thorough but could use the navigation assertion. The backfill section has the most issues due to the case mismatch and missing edge cases.
