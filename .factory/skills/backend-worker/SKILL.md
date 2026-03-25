---
name: backend-worker
description: Python backend worker for data pipeline features (services, scripts, API endpoints, tests)
---

# Backend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features involving Python backend code: data services, scripts, API endpoints, database operations, TuShare/AKShare integrations, pytest tests.

## Required Skills

None.

## Work Procedure

1. **Read the feature description thoroughly.** Understand preconditions, expected behavior, and verification steps.

2. **Investigate existing code first.** Before writing any code, read the relevant existing files to understand patterns:
   - Services: `src/services/` — class-based, use dependency injection
   - Models: `src/models/` — SQLAlchemy with UPPERCASE enum values (`SymbolType.STOCK`, `KlineTimeframe.DAY`)
   - API routes: `src/api/routes_*.py` — registered in `router.py`
   - Scripts: `scripts/` — standalone with `if __name__ == '__main__':` entry point
   - Tests: `tests/` — pytest with `db_session` fixture from `conftest.py`
   - Config: `src/config.py` — Settings class with env var overrides

3. **Write tests first (RED).** Create or modify test files following existing patterns:
   - Use `db_session` fixture for database tests
   - Use `TestClient` for API endpoint tests
   - Cover: happy path, edge cases, error handling
   - Run `.venv/bin/python -m pytest tests/ -v --tb=short -x` — tests should FAIL

4. **Implement the feature (GREEN).** Write the minimum code to make tests pass:
   - Follow existing naming and patterns
   - Use UPPERCASE for database values: `symbol_type='STOCK'`, `timeframe='DAY'`
   - Use existing `TushareClient` for TuShare API calls (respect RateLimiter)
   - Use existing `DataUpdateLog` for tracking operations
   - Scripts must have progress logging and error handling
   - Database operations must be idempotent (INSERT OR IGNORE / INSERT OR REPLACE)

5. **Run all tests.** `.venv/bin/python -m pytest tests/ -v --tb=short` — all must pass.

6. **Manual verification.** Execute the verification steps from the feature description:
   - For scripts: run them (with --dry-run if available, or limited scope)
   - For API endpoints: curl them against the running backend (localhost:8000)
   - For database changes: query with sqlite3
   - Record EVERY command and its output in the handoff

7. **Commit.** Stage and commit all changes with a descriptive message.

## Example Handoff

```json
{
  "salientSummary": "Created scripts/backfill_index_daily.py using TuShare pro.index_daily() for 8 indices from 2021-01-04. All 8 indices backfilled with >= 1,200 rows each, no gaps. 14 tests added covering field mapping, idempotency, and resume logic.",
  "whatWasImplemented": "Backfill script for index daily data. Iterates INDEX_LIST (8 indices), fetches 5-year history via pro.index_daily(), maps to klines table with symbol_type='INDEX'/timeframe='DAY'. UPSERT for idempotency. Resume support via MAX(trade_time) check. Progress logging every index. DataUpdateLog tracking.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": ".venv/bin/python -m pytest tests/ -v --tb=short", "exitCode": 0, "observation": "47 tests passed, 0 failed" },
      { "command": "python scripts/backfill_index_daily.py", "exitCode": 0, "observation": "Backfilled 8 indices, 9,823 total rows inserted" },
      { "command": "sqlite3 data/market.db \"SELECT symbol_code, MIN(trade_time), COUNT(*) FROM klines WHERE symbol_type='INDEX' AND timeframe='DAY' GROUP BY symbol_code;\"", "exitCode": 0, "observation": "8 rows, all with min_date 2021-01-04 and count >= 1,200" }
    ],
    "interactiveChecks": []
  },
  "tests": {
    "added": [
      { "file": "tests/test_backfill_index.py", "cases": [
        { "name": "test_backfill_all_indices", "verifies": "All 8 indices get data from 2021" },
        { "name": "test_idempotent_rerun", "verifies": "Running twice doesn't create duplicates" },
        { "name": "test_resume_from_checkpoint", "verifies": "Skips already-backfilled indices" },
        { "name": "test_field_mapping", "verifies": "TuShare fields map correctly to klines columns" }
      ]}
    ],
    "coverage": "14 new tests for index backfill"
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- TuShare API returns unexpected errors (rate limit, auth failure, endpoint changed)
- Database schema doesn't match expectations (missing columns, different types)
- Existing code has bugs that block the feature
- Feature depends on data/services not yet available
