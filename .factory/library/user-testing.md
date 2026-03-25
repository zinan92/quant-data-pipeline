# User Testing

Testing surface, required testing skills/tools, resource cost classification per surface.

---

## Validation Surface

### Browser (React Frontend)
- **URL**: http://localhost:5173
- **Tool**: agent-browser
- **Key pages**: `/health` (Health Dashboard — primary validation target)
- **Navigation**: Top nav bar with buttons (市场, 我的自选, Dashboard, 健康, etc.)
- **Important**: Use `wait 3000` instead of `networkidle` — WebSocket connections keep the page "loading"
- **Browser Notification API**: Available but permission may be "denied" initially

### Backend API
- **URL**: http://localhost:8000
- **Tool**: curl
- **Key endpoints**: `/api/health/gaps`, `/api/health/consistency`, `/api/health/failures`, `/api/health/unified`
- **Swagger**: http://localhost:8000/docs

### Database
- **Path**: `/Users/wendy/work/trading-co/ashare/data/market.db`
- **Tool**: sqlite3
- **Important**: Values are UPPERCASE — use `symbol_type='STOCK'`, `timeframe='DAY'`

## Validation Concurrency

**Machine**: 16 GB RAM, 10 CPU cores, ~13 GB baseline usage

**agent-browser surface**:
- Each agent-browser instance: ~937 MB overhead
- Available headroom: ~3 GB * 0.7 = ~2.1 GB
- **Max concurrent validators: 2** (2 × 937 MB = ~1.9 GB, within budget)
- Services (backend + frontend) already running, no additional startup cost

**curl/sqlite3 surface**:
- Negligible resource cost
- **Max concurrent validators: 5**

## Testing Notes

- Backend and frontend are already running (PID 43943 and 1048) — do NOT restart
- The frontend proxies `/api/` to localhost:8000 via Vite
- A-share stock suspensions are common — allow up to 30 missing trading days per stock
- Concept/industry data from TuShare may have < 5 years of history — 2 years minimum acceptable
