# Environment

Environment variables, external dependencies, and setup notes.

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `.factory/services.yaml`).

---

## Environment Variables

- `TUSHARE_TOKEN` — TuShare Pro API token (required, in `.env`). Account has 5000+ points.
- `CANDLE_LOOKBACK` — Number of kline bars to fetch per symbol (default: 1250, set in `.env`)

## Data Universe (post historical-backfill milestone)

- **Stocks**: ~1000 A-share stocks (CSI 300 + CSI 500 + CSI 1000 constituents merged with original watchlist)
- **Indices**: 8 indices: 上证指数(000001.SH), 深证成指(399001.SZ), 创业板指(399006.SZ), 科创50(000688.SH), 北证50(899050.BJ), 沪深300(000300.SH), 中证500(000905.SH), 中证1000(000852.SH)
- **Data range**: ~2021-01-04 to present (5 years) for daily klines. 北证50 (899050.BJ) starts from 2022-12-19 (index established late 2022).
- **Concept boards**: ~360+ concepts with historical data from TuShare ths_daily()
- **Industry boards**: ~80+ industries with historical moneyflow data

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
