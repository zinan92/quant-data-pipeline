---
name: frontend-worker
description: React/TypeScript frontend worker for UI features with agent-browser verification
---

# Frontend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features involving React frontend code: components, pages, hooks, styling, browser interactions.

## Required Skills

- `agent-browser` — MUST be invoked for all UI verification. Every user-visible change must be verified in the actual browser.

## Work Procedure

1. **Read the feature description thoroughly.** Understand preconditions, expected behavior, and verification steps.

2. **Investigate existing frontend code first.** Before writing any code, read:
   - `frontend/src/App.tsx` — routes and navigation
   - `frontend/src/components/HealthDashboard.tsx` — existing component being modified
   - `frontend/src/styles/HealthDashboard.css` — existing styles
   - `frontend/src/hooks/` — data fetching patterns (TanStack Query + raw fetch)
   - `frontend/src/utils/api.ts` — API helper (`apiFetch`)

3. **Plan the changes.** For each section to add:
   - Identify the data source (which API endpoint)
   - Determine the component structure (state, effects, refs)
   - Plan the CSS classes following existing BEM-ish naming

4. **Implement the feature.** Following existing patterns:
   - Functional components with hooks, named exports
   - Data fetching: `apiFetch('/api/health/gaps')` or TanStack Query
   - Styling: plain CSS in `src/styles/HealthDashboard.css`, BEM naming (`.health-dashboard__gaps`, `.health-dashboard__per-stock`)
   - Error handling: try/catch per section, show error message in that section only
   - Browser Notification: guard with `typeof Notification !== 'undefined'`
   - For large lists: search/filter input + limited display

5. **Verify with agent-browser.** Invoke the `agent-browser` skill and:
   - Navigate to `http://localhost:5173/health`
   - Use `wait 3000` (NOT `networkidle` — WebSocket keeps connection alive)
   - Screenshot each section
   - Test search/filter functionality
   - Check for console errors
   - Verify existing sections still work (aggregate freshness tables)
   - Test navigation from main nav bar
   - Each check = one `interactiveChecks` entry with full observation

6. **Commit.** Stage and commit all changes.

## Example Handoff

```json
{
  "salientSummary": "Upgraded HealthDashboard with 6 new sections: gap detection (summary + details), per-stock drill-down with search, recent failures table, async data consistency, browser notifications on status transition, trade calendar health. All verified via agent-browser at localhost:5173/health. Existing aggregate freshness tables preserved.",
  "whatWasImplemented": "Modified HealthDashboard.tsx: added gap detection section fetching /api/health/gaps, per-stock drill-down with search input filtering ~1000 stocks, recent failures from /api/health/failures (last 50, newest first), async consistency check from /api/health/consistency (loads independently with spinner), browser Notification API with permission request + useRef for transition detection, trade calendar health display, updated overall status banner to consider all dimensions. Added styles to HealthDashboard.css. Each section has independent error handling.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [],
    "interactiveChecks": [
      { "action": "Navigated to http://localhost:5173/health via agent-browser", "observed": "Page loaded with all sections visible: aggregate freshness (existing), gap detection, per-stock drill-down, recent failures, data consistency, trade calendar health" },
      { "action": "Checked gap detection section", "observed": "Shows summary: 'STOCK: 5 symbols with gaps, 30 missing days. INDEX: 0 gaps.' Expandable details list below." },
      { "action": "Tested per-stock search", "observed": "Typed '000001' in search input, filtered to show 000001.SZ with freshness indicator and gap count" },
      { "action": "Checked recent failures section", "observed": "Table with 3 entries showing update type, error message, timestamp. Most recent at top." },
      { "action": "Checked data consistency section", "observed": "Initially showed spinner, then loaded: '98.5% consistent, 200 items validated'. No inconsistencies listed." },
      { "action": "Checked console for errors", "observed": "No errors in console. Notification permission prompt appeared." },
      { "action": "Verified existing sections unchanged", "observed": "定量数据源 and 定性数据源 tables still render with all columns and status icons" },
      { "action": "Verified auto-refresh after 70 seconds", "observed": "Network tab showed repeated requests to all health endpoints at ~60s intervals" }
    ]
  },
  "tests": {
    "added": [],
    "coverage": "No frontend tests (project has no test infrastructure). All verification via agent-browser."
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Backend API endpoints not available or returning errors
- Frontend build fails with TypeScript errors that require backend changes
- Existing component has patterns that conflict with requirements
- Browser Notification API completely blocked in testing environment
