# Troubleshooting: Momentum Signals Not Displaying

## Issue Detected

The frontend is showing:
- "加载中..." (Loading) on the momentum signals page
- 404 errors for `/api/concept-monitor/momentum-signals`
- 500 errors for `/api/concept-monitor/top` and `/api/concept-monitor/watch`

## Root Cause

The **backend server needs to be restarted** to pick up the new API endpoint and code changes.

## Solution

### Step 1: Stop the Current Backend Server
Press `Ctrl+C` in the terminal running `uvicorn` to stop it.

### Step 2: Restart the Backend Server
```bash
cd /Users/park/a-share-data
uvicorn src.main:app --reload --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using StatReload
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Step 3: Verify the API Endpoint
Open a new terminal and test:
```bash
curl http://localhost:8000/api/concept-monitor/momentum-signals
```

**Expected response:**
```json
{
  "success": true,
  "timestamp": "2026-01-19 09:40:13",
  "total_signals": 11,
  "surge_signals_count": 0,
  "kline_signals_count": 11,
  "signals": [...]
}
```

### Step 4: Refresh the Frontend
1. Go to http://localhost:5173
2. Click "🔔 动量信号" button
3. You should now see the momentum signals displayed

---

## Additional Fixes Applied

### Frontend Import Fix
Fixed the import error in `MomentumSignalsView.tsx`:

**Before:**
```typescript
import { API_BASE_URL } from "../utils/api";  // ❌ Does not exist
const response = await fetch(`${API_BASE_URL}/concept-monitor/momentum-signals`);
```

**After:**
```typescript
import { buildApiUrl } from "../utils/api";  // ✅ Correct
const url = buildApiUrl("/api/concept-monitor/momentum-signals");
const response = await fetch(url);
```

---

## Verification Checklist

- [ ] Backend server restarted
- [ ] API endpoint returns 200 OK
- [ ] Frontend loads without errors
- [ ] Momentum signals page displays data
- [ ] 11 K-line pattern signals visible (from last monitor run)
- [ ] Auto-refresh working (60 seconds)

---

## If Issues Persist

### Check Backend Logs
Look for any errors in the uvicorn output:
```bash
# Should show route registration
INFO:     Application startup complete.
```

### Check Monitor Process
Ensure the monitor is running:
```bash
ps aux | grep monitor_no_flask
```

If not running, start it:
```bash
python3 scripts/monitor_no_flask.py
```

### Check JSON Files
Verify the signal file exists and has content:
```bash
cat /Users/park/a-share-data/docs/monitor/momentum_signals.json | head -20
```

### Browser DevTools
1. Open browser console (F12)
2. Check for:
   - Red errors (should be none after backend restart)
   - Network tab showing 200 OK for `/api/concept-monitor/momentum-signals`

---

## Quick Test Commands

```bash
# 1. Test API directly
curl http://localhost:8000/api/concept-monitor/momentum-signals | python3 -m json.tool

# 2. Test top concepts endpoint
curl http://localhost:8000/api/concept-monitor/top?n=5 | python3 -m json.tool

# 3. Check backend health
curl http://localhost:8000/api/status

# 4. List all routes (if available)
curl http://localhost:8000/docs  # Opens API documentation
```

---

## Expected Behavior After Fix

1. **Button Appearance**: Orange pulsing "🔔 动量信号" button in top navigation
2. **Click Action**: Navigates to signals view
3. **Loading State**: Brief "加载中..." while fetching
4. **Display**: Grid of signal cards showing:
   - 上涨激增 signals (if any triggered)
   - K线形态 signals (11 from last run)
5. **Auto-refresh**: Updates every 60 seconds
6. **Manual Refresh**: Click "手动刷新" button works

---

## Contact
If the issue persists after following these steps, check:
- `docs/MOMENTUM_SIGNALS_IMPLEMENTATION.md` for full technical details
- `docs/MOMENTUM_SIGNALS_QUICK_START.md` for usage guide
- `tests/test_momentum_signals.py` for validation script
