# Architecture

Architectural decisions, patterns discovered, and conventions.

**What belongs here:** Patterns used in the codebase, architectural decisions, module responsibilities.

---

## Data Flow

```
TuShare Pro / Sina / THS / AKShare
        ↓
  Services (kline_updater, index_updater, concept_updater, stock_updater)
        ↓
  SQLite market.db (klines, concept_daily, industry_daily)
        ↓
  FastAPI API (routes_*.py)
        ↓
  React Frontend (components/, hooks/)
```

## Service Architecture

- **KlineScheduler**: APScheduler-based, runs in-process with FastAPI
- **KlineUpdater**: Coordinator that delegates to IndexUpdater, ConceptUpdater, StockUpdater, CalendarUpdater
- **TushareClient**: Centralized TuShare API client with RateLimiter
- **DataConsistencyValidator**: Compares daily vs 30-min prices for consistency

## Key Patterns

- Services are class-based with constructor dependency injection
- Database operations use SQLAlchemy ORM with session management
- Config via Pydantic Settings with env var overrides
- Scripts in `scripts/` are standalone CLI tools
- Frontend data fetching: TanStack Query (preferred) or raw fetch+useEffect
