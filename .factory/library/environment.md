# Environment

Environment variables, external dependencies, and setup notes.

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `.factory/services.yaml`).

---

## Environment Variables

- `TUSHARE_TOKEN` — TuShare Pro API token (required, in `.env`). Account has 5000+ points.
- `CANDLE_LOOKBACK` — Number of kline bars to fetch per symbol (default: 1250, set in `.env`)

## External APIs

- **TuShare Pro**: Rate limit 180 calls/min for 5000+ points. Use `TushareClient` in `src/services/tushare_client.py`.
- **Sina Finance**: Used for realtime index/stock klines. Rate limit ~3s delay between requests.
- **TongHuaShun (10jqka)**: Used for concept board klines. Batch of 10 with 0.5s delay.
- **AKShare**: Used in scripts for supplemental data (concept info, ETF, news).

## Database

- SQLite at `data/market.db` (~121 MB + WAL)
- WAL mode enabled for concurrent reads
- Key tables: `klines`, `concept_daily`, `industry_daily`, `trade_calendar`, `watchlist`, `stock_basic`, `symbol_metadata`, `stock_sectors`, `data_update_log`
- Database values are UPPERCASE: `symbol_type='STOCK'/'INDEX'`, `timeframe='DAY'/'MINS_30'`

## Known Issues

- TuShare IP rate limit errors for concept/industry updates ("您的IP数量超限") — pre-existing, not caused by this mission
- `technical_indicators` table stale (Dec 2025 - Jan 2026)
