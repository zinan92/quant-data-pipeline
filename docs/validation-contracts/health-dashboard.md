## Area: Health Dashboard

### VAL-HEALTH-001: Gap Detection Section Visible on Health Page
The `/health` page must display a "Gap Detection" (数据缺口检测) section that shows trading days with missing kline data. The section must be populated by calling `GET /api/health/gaps`. Pass: navigating to `/health` shows a clearly labeled gap detection section containing either a table/list of detected gaps (symbol, missing dates, count) or an explicit "no gaps found" message. Fail: the section is absent, renders an empty container with no indication of state, or the `/api/health/gaps` endpoint returns a non-200 status.
Evidence: Use agent-browser to navigate to `/health` and screenshot. Verify the gap detection section heading is visible. Inspect network requests to confirm `/api/health/gaps` was called and returned 200. Check that at least a summary row or "no gaps" message appears.

### VAL-HEALTH-002: Gap Detection Backend Cross-References Trade Calendar with Klines
The `GET /api/health/gaps` endpoint must cross-reference the `trade_calendar` table (trading days) with actual kline data to identify missing trading days per symbol. Pass: when a trading day exists in `trade_calendar` but no corresponding kline row exists for a tracked symbol, that date appears in the gap results. Fail: the endpoint returns an empty list despite known missing data, or it does not consult `trade_calendar` at all.
Evidence: Query `trade_calendar` for a recent trading day. Verify the endpoint logic joins or cross-references calendar dates against klines. If a test symbol has a known missing day, confirm it appears in the response. Inspect the route handler code to verify `trade_calendar` is queried.

### VAL-HEALTH-003: Per-Stock Drill-Down Shows Individual Symbol Freshness
The health page must include a per-stock drill-down view that lists individual stock symbols with their freshness status and gap count. Pass: the UI displays a list or table where each row contains at minimum: symbol code, symbol name, freshness indicator (green/yellow/red), and gap count. The data comes from a dedicated backend endpoint. Fail: only aggregate freshness is shown (current behavior) with no per-symbol breakdown available.
Evidence: Use agent-browser to navigate to `/health` and locate the per-stock section. Verify at least 5 individual stock rows are visible with symbol codes, names, and status indicators. Confirm the associated API endpoint returns per-symbol data with freshness and gap fields.

### VAL-HEALTH-004: Per-Stock Drill-Down Supports Filtering or Scrolling
Given the expanded stock universe (~1000 symbols), the per-stock drill-down must handle large lists gracefully — either via pagination, virtual scrolling, search/filter, or a summary-with-expand pattern. Pass: the UI does not attempt to render 1000+ rows simultaneously without any performance mitigation, and the user can locate a specific stock. Fail: the page becomes unresponsive or takes >5 seconds to render the per-stock section, or there is no way to find a specific symbol.
Evidence: Use agent-browser to load `/health` and measure render time. If >100 stocks, verify pagination controls, a search input, or virtual scroll is present. Attempt to filter/search for a known stock symbol.

### VAL-HEALTH-005: Recent Failures Section Shows DataUpdateLog Entries
The health page must display a "Recent Failures" (最近失败记录) section populated from `DataUpdateLog` entries with `status = 'failed'` or `status = 'error'`. Pass: the section shows a table/list with columns for update type, error message, and timestamp. When failures exist in the database, they appear in the UI. When no failures exist, an explicit "no recent failures" message is shown. Fail: the section is missing, or it never displays failure entries even when `data_update_log` contains rows with failed status.
Evidence: Use agent-browser to navigate to `/health` and look for the recent failures section. Check the backend endpoint that serves this data returns `DataUpdateLog` rows filtered by failure status. If the database has failure records, confirm at least one row renders with error details.

### VAL-HEALTH-006: Recent Failures Are Limited and Ordered by Recency
The recent failures display must show a bounded number of entries (e.g., last 20-50) ordered by most recent first, to avoid overwhelming the UI. Pass: failures are sorted by `started_at` descending, and no more than a reasonable limit (20-50) are returned per page/request. Fail: all historical failures are returned without limit, or they are shown in ascending (oldest-first) order.
Evidence: Inspect the backend query for `DataUpdateLog` failures to verify `ORDER BY started_at DESC` and a `LIMIT` clause. Verify the UI shows the most recent failure at the top.

### VAL-HEALTH-007: Data Consistency Section Shows Validation Results
The health page must display a "Data Consistency" (数据一致性) section that surfaces results from `DataConsistencyValidator`. This section must show the consistency rate, total items validated, and a list of any inconsistencies found. Pass: the section renders with at least: consistency rate percentage, count of validated items, and an inconsistencies list (or "all consistent" message). Fail: the `DataConsistencyValidator` remains unwired from the UI, or the section shows no data.
Evidence: Use agent-browser to navigate to `/health` and look for the data consistency section. Verify it shows a summary (e.g., "98.5% consistent, 200 items validated") and, if inconsistencies exist, a list with symbol names and details. Confirm the backend endpoint invokes `DataConsistencyValidator.validate_all()` or returns cached results.

### VAL-HEALTH-008: Data Consistency Validation Does Not Block Page Load
Since `DataConsistencyValidator.validate_all()` queries many symbols and may be slow, it must not block the initial health page render. Pass: the health page loads and shows other sections (aggregate freshness, gap detection) while the consistency section shows a loading indicator, then populates asynchronously. Fail: the entire health page is blank or frozen until consistency validation completes.
Evidence: Use agent-browser to load `/health` and observe load sequence. The aggregate freshness section should appear first; the consistency section may show a spinner/skeleton before data arrives. Network tab should show the consistency API call as a separate request from the unified health call.

### VAL-HEALTH-009: Browser Notification Permission Requested on Health Page
When a user first visits the `/health` page, the application must request Browser Notification API permission (via `Notification.requestPermission()`). Pass: the browser shows its native permission prompt, or if permission was already granted/denied, no prompt appears but the permission state is checked. Fail: no call to `Notification.requestPermission()` is made, or the code crashes on browsers that don't support the Notification API.
Evidence: Use agent-browser to navigate to `/health` in a fresh browser context. Verify a notification permission prompt appears (or check `Notification.permission` state). Inspect the component code for a `useEffect` or equivalent that calls `Notification.requestPermission()`. Verify a `typeof Notification !== 'undefined'` guard exists for SSR/unsupported browsers.

### VAL-HEALTH-010: Browser Notification Fires on Healthy-to-Degraded Transition
When the health status transitions from `"healthy"` to `"degraded"` (or `"unhealthy"`) between auto-refresh cycles, a browser notification must be fired. Pass: after granting notification permission, if the backend status changes from healthy to degraded between two polling intervals, a desktop notification appears with a meaningful title and body (e.g., "数据健康降级" with affected source names). Fail: no notification fires on status transition, or notification fires on every poll regardless of transition.
Evidence: Inspect the component code for logic that compares previous status with current status (e.g., via `useRef` storing last status) and only fires `new Notification(...)` on a healthy→degraded/unhealthy transition. Verify notification is NOT fired on degraded→degraded (no change) or on initial load.

### VAL-HEALTH-011: Trade Calendar Health Check Section Visible
The health page must display a "Trade Calendar Health" (交易日历健康) section showing whether the calendar covers the required year range (2021-2026). Pass: the section displays the calendar's date range (min date, max date), total trading days count, and a pass/fail indicator for coverage. Fail: no trade calendar health information is shown on the health page.
Evidence: Use agent-browser to navigate to `/health` and locate the trade calendar section. Verify it shows start year, end year, trading day count, and a health indicator. Confirm the backend provides this data (either via a dedicated endpoint or as part of the unified health response).

### VAL-HEALTH-012: Existing Aggregate Freshness Remains Functional
The existing aggregate freshness display (quantitative and qualitative data source tables) must continue to function after all health dashboard upgrades. Pass: the "定量数据源" and "定性数据源" tables still render with source names, status icons, timestamps, freshness ages, and detail columns — identical to pre-upgrade behavior. Fail: the existing tables are missing, broken, or have lost columns/data after the upgrade.
Evidence: Use agent-browser to navigate to `/health` and verify both the "定量数据源" and "定性数据源" table headings are visible. Confirm at least one row renders in each table with a freshness icon (🟢/🟡/🔴/⚪). Compare against the existing `HealthDashboard.tsx` structure to ensure no regression.

### VAL-HEALTH-013: Auto-Refresh Continues to Work After Upgrade
The health page must continue to auto-refresh data every 60 seconds (existing behavior via `setInterval(fetchData, 60_000)`). New sections (gaps, per-stock, failures, consistency) must also refresh or have their own refresh mechanism. Pass: after waiting 60+ seconds on the health page, network requests fire for all health endpoints and the UI updates without a manual page reload. Fail: auto-refresh is broken for existing or new sections, or only some sections update.
Evidence: Use agent-browser to navigate to `/health`, wait 70 seconds, and verify network activity shows repeated calls to health endpoints. Confirm the displayed timestamps or data values change after a refresh cycle.

### VAL-HEALTH-014: Overall Status Banner Reflects All Health Dimensions
The overall status banner (currently "所有活跃数据源正常" / "部分数据可能过期" / "数据异常") must incorporate the new health dimensions: gap count, data consistency, and trade calendar health — not just source freshness. Pass: if gaps are detected or consistency is below threshold, the banner reflects degraded or unhealthy status even if all sources are fresh. Fail: the banner only considers source freshness and ignores gaps, consistency, and calendar health.
Evidence: Inspect the logic that determines the `status` field in the unified health response or the frontend's `overallLabel()` function. Verify that gap count > 0 or consistency rate < threshold contributes to a degraded/unhealthy status.

### VAL-HEALTH-015: Health Page Handles Backend Errors Gracefully for New Sections
If any of the new backend endpoints (`/api/health/gaps`, consistency, failures) return errors or are unavailable, the health page must not crash. Each new section should show an error state independently. Pass: if `/api/health/gaps` returns 500 while other endpoints are healthy, only the gap section shows an error message; the rest of the page renders normally. Fail: a single endpoint failure causes the entire health page to show "加载失败" or crash with a white screen.
Evidence: Use agent-browser or test by temporarily breaking one new endpoint. Verify the page loads with error indicators only in the affected section. Other sections (aggregate freshness, etc.) must render correctly.

### VAL-HEALTH-016: Gap Detection Endpoint Returns Structured Response
The `GET /api/health/gaps` endpoint must return a structured JSON response containing at minimum: a list of gaps (each with `symbol_code`, `symbol_name`, `missing_dates` or `gap_count`, and `timeframe`), plus a summary with total gap count. Pass: the response is valid JSON with the described structure and correct Content-Type header. Fail: the endpoint returns unstructured text, an empty 200 with no body, or a schema that lacks per-symbol gap details.
Evidence: Call `GET /api/health/gaps` directly (via curl or agent-browser network inspection) and verify the JSON schema. Confirm `Content-Type: application/json`. Check that the response includes both per-symbol details and a summary count.
