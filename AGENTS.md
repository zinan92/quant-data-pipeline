# Repository Guidelines

## Project Structure & Module Organization
- `src/` holds FastAPI services, database models, and shared utilities; align new modules with the existing domain folders.
- `web/app.py` assembles the ASGI app and lifecycle hooks; register new routers under `src/api/`.
- `frontend/` hosts the Vite + React dashboard, while `data/` and `logs/` are runtime artifacts managed via `src/config.py`.
- Keep backend tests in `tests/` and mirror package paths (e.g., `tests/services/test_data_pipeline.py`).

## Environment & Configuration
- Copy `.env.example` to `.env`, then set `DEFAULT_SYMBOLS`, `DATABASE_URL`, and any cron overrides before launching the API.
- Settings resolve through `src/config.py`; relative paths are created automatically, so avoid hard-coded user directories.
- Keep AkShare credentials and proxies outside git and surface them through environment variables consumed by `.env`.

## Build, Test & Development Commands
- `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` prepares the backend environment.
- `uvicorn web.app:app --reload` runs the API, initializes SQLite tables, and starts the scheduler with your `.env` values.
- `cd frontend && npm install` installs client dependencies; use `npm run dev` for local work and `npm run build` for production bundles.
- `python -m unittest discover tests` executes backend tests from the repo root to ensure settings import cleanly.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation, explicit type hints, and module-level `LOGGER` instances as in `src/utils/logging.py`.
- Use `snake_case` for modules, functions, and columns; reserve `PascalCase` for Pydantic schemas, SQLAlchemy models, and React components.
- Group imports as stdlib, third-party, internal, and prefer focused services or utilities over monolithic modules.

## Testing Guidelines
- Target service boundaries (`MarketDataService`, schedulers, API handlers); isolate AkShare calls with fakes or recorded fixtures.
- Name tests descriptively (`test_refresh_universe_persists_candles`) and keep reusable builders under `tests/` helpers.
- Assert scheduler outcomes via service APIs rather than APScheduler internals to keep suites stable.

## Commit & Pull Request Guidelines
- Use imperative, concise commit subjects (`Integrate industry filters`) and add body context when touching multiple layers.
- Open pull requests with a short summary, linked issues, and evidence of local runs (`unittest`, `npm run build`, UI screenshots when relevant).
- Verify API and frontend commands succeed locally before requesting review, and call out migrations or backfills in the description.
