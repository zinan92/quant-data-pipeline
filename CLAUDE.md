# quant-data-pipeline (ashare)

## Project Overview
Multi-market quantitative data platform covering A-shares, US stocks, crypto, commodities, bonds, forex. Full-stack: FastAPI backend + React frontend + SQLite DB.

## Tech Stack
- **Backend**: FastAPI 0.110, SQLAlchemy 2.0, APScheduler, Python 3.11+
- **Frontend**: React + TypeScript, Vite, TanStack Query, Lightweight Charts
- **Database**: SQLite with WAL mode at `data/market.db`
- **Data Sources**: AKShare, TuShare Pro, Yahoo Finance, Sina Finance, Tonghuashun

## Architecture
Layered: API routes (`src/api/`) → Schemas (`src/schemas/`) → Services (`src/services/`) → Repositories (`src/repositories/`) → Models (`src/models/`) → Database (`src/database.py`)

## Key Directories
- `src/api/` — FastAPI route handlers (34 modules)
- `src/services/` — Business logic (39 modules)
- `src/perception/` — Perception pipeline (detectors, sources, aggregator)
- `src/models/` — SQLAlchemy ORM models
- `src/tasks/scheduler.py` — APScheduler-based task scheduling
- `scripts/` — Briefing scripts, data loaders, utilities (120+ files)
- `frontend/` — React app
- `web/app.py` — FastAPI app factory

## Important Files
- `scripts/full_briefing.py` — A-share daily briefing
- `scripts/us_briefing_v2.py` — US stock briefing
- `src/perception/pipeline.py` — Perception pipeline orchestration
- `src/perception/aggregator.py` — Signal aggregation
- `src/services/simulated_service.py` — Paper trading service
- `src/config.py` — Pydantic settings (env-based)

## Commands
```bash
# Run backend
python -m uvicorn web.app:create_app --factory --port 8000

# Run frontend
cd frontend && npm run dev

# Run briefing
python scripts/full_briefing.py
python scripts/us_briefing_v2.py

# Run tests
pytest tests/
```

## Conventions
- Async/await throughout backend
- Custom exception hierarchy in `src/exceptions.py`
- Rate limiting on API endpoints via slowapi
- All new API routes follow pattern: `src/api/routes_{feature}.py`
- Services are injected via FastAPI Depends

## Related Project
- **qualitative-data-pipeline** (park-intel) runs on port 8001, provides qualitative signals
- Repo: https://github.com/zinan92/qualitative-data-pipeline

## Current Roadmap
See `/Users/wendy/Documents/trading-system-roadmap.md` for full 5-phase plan.
Active work: Phase 1 — integrating qualitative + quantitative data.
