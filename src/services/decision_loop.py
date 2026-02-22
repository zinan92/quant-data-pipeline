"""
Decision Loop V1 — daily repeatable trading decision protocol.

Three components:
  1. InputAssembler  — gathers data from existing API endpoints
  2. AnalysisEngine  — Claude API call with structured prompt
  3. DecisionLoopService — orchestrates the full cycle
"""

import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from src.schemas.decision import (
    AnalysisContract,
    DecisionOutput,
    DecisionRunResult,
    InputPackage,
    MarketSnapshot,
    ReviewEntry,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

_TZ_SHANGHAI = timezone(timedelta(hours=8))
_TIMEOUT = 15.0  # seconds per API call


class InputAssembler:
    """Gathers data from existing quant-data-pipeline endpoints."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("API_KEY", "")
        self._headers = {"X-API-Key": self.api_key} if self.api_key else {}

    async def assemble(self) -> InputPackage:
        """Assemble the full V1 input package from existing API endpoints."""
        t0 = time.monotonic()
        missing: List[str] = []

        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self._headers) as client:
            ashare = await self._fetch_ashare_indexes(client, missing)
            us = await self._fetch_us_market(client, missing)
            commodities = await self._fetch_commodities(client, missing)
            crypto = await self._fetch_crypto(client, missing)
            intel = await self._fetch_intel_signals(client, missing)
            perception = await self._fetch_perception_context(client, missing)

        now = datetime.now(_TZ_SHANGHAI)
        # Only flag low confidence when core quantitative data is missing
        _core_prefixes = ("ashare_index:", "us_market:", "commodities", "crypto")
        core_missing = [f for f in missing if any(f.startswith(p) for p in _core_prefixes)]
        return InputPackage(
            timestamp=now.isoformat(),
            ashare_indexes=ashare,
            us_market=us,
            commodities=commodities,
            crypto=crypto,
            short_term_trend="(derived from data above by analysis engine)",
            medium_term_trend="(not yet standardized — pending data pipeline)",
            regime_change_flags="(derived by analysis engine)",
            intel_signals=intel,
            perception_context=perception,
            missing_fields=missing,
            is_low_confidence=len(core_missing) > 0,
        )

    # ── Data fetchers ──

    async def _fetch_ashare_indexes(
        self, client: httpx.AsyncClient, missing: List[str]
    ) -> List[MarketSnapshot]:
        """Fetch A-share core indexes via /api/index/realtime."""
        indexes = [
            ("000001.SH", "上证指数"),
            ("399001.SZ", "深证成指"),
            ("000300.SH", "沪深300"),
            ("399006.SZ", "创业板指"),
        ]
        results = []
        for code, name in indexes:
            data = await self._get(client, f"/api/index/realtime/{code}")
            if data:
                results.append(MarketSnapshot(
                    symbol=code,
                    name=name,
                    price=data.get("price", 0),
                    change_pct=data.get("change_pct", 0),
                    extra={
                        "volume": data.get("volume", 0),
                        "amount": data.get("amount", 0),
                    },
                ))
            else:
                missing.append(f"ashare_index:{code}")
        return results

    async def _fetch_us_market(
        self, client: httpx.AsyncClient, missing: List[str]
    ) -> List[MarketSnapshot]:
        """Fetch US market quotes via /api/us-stock/quote."""
        symbols = [
            ("^GSPC", "S&P 500"),
            ("^IXIC", "Nasdaq"),
            ("^NDX", "Nasdaq 100"),
            ("^VIX", "VIX"),
            ("^TNX", "10Y Treasury"),
            ("DX-Y.NYB", "DXY"),
        ]
        results = []
        for sym, name in symbols:
            data = await self._get(client, f"/api/us-stock/quote/{sym}")
            if data:
                results.append(MarketSnapshot(
                    symbol=sym,
                    name=name,
                    price=data.get("price", 0),
                    change_pct=data.get("change_pct", 0),
                    extra={
                        "volume": data.get("volume", 0),
                        "market_cap": data.get("market_cap", 0),
                    },
                ))
            else:
                missing.append(f"us_market:{sym}")
        return results

    async def _fetch_commodities(
        self, client: httpx.AsyncClient, missing: List[str]
    ) -> List[MarketSnapshot]:
        """Fetch commodities via /api/commodities/realtime."""
        data = await self._get(client, "/api/commodities/realtime")
        if not data or "commodities" not in data:
            missing.append("commodities")
            return []
        return [
            MarketSnapshot(
                symbol=c["symbol"],
                name=c.get("name_cn", c.get("name", "")),
                price=c.get("price", 0),
                change_pct=c.get("change_pct", 0),
            )
            for c in data["commodities"]
        ]

    async def _fetch_crypto(
        self, client: httpx.AsyncClient, missing: List[str]
    ) -> List[MarketSnapshot]:
        """Fetch crypto prices via /api/crypto/prices."""
        data = await self._get(client, "/api/crypto/prices")
        if not data or "prices" not in data:
            missing.append("crypto")
            return []
        return [
            MarketSnapshot(
                symbol=c["symbol"],
                name=c.get("name", c["symbol"]),
                price=c.get("price", 0),
                change_pct=c.get("change_24h", 0),
                extra={
                    "volume_24h": c.get("volume_24h", 0),
                    "market_cap": c.get("market_cap", 0),
                },
            )
            for c in data["prices"][:10]  # top 10
        ]

    async def _fetch_intel_signals(
        self, client: httpx.AsyncClient, missing: List[str]
    ) -> Dict[str, Any]:
        """Fetch qualitative intel via /api/intel/signals."""
        data = await self._get(client, "/api/intel/signals", params={"hours": 24})
        if not data:
            missing.append("intel_signals")
            return {}
        return data

    async def _fetch_perception_context(
        self, client: httpx.AsyncClient, missing: List[str]
    ) -> Dict[str, Any]:
        """Fetch perception market context via /api/perception/market-context."""
        data = await self._get(client, "/api/perception/market-context")
        if not data:
            missing.append("perception_context")
            return {}
        return data

    async def _get(
        self, client: httpx.AsyncClient, path: str, params: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """GET helper with error handling."""
        url = f"{self.base_url}{path}"
        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("GET %s returned %d", path, resp.status_code)
            return None
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning("GET %s failed: %s", path, exc)
            return None


# ── Analysis Engine ──


_ANALYSIS_SYSTEM_PROMPT = """You are a senior multi-market trading analyst producing a daily decision briefing.

You will receive a structured market data snapshot. Your job:

1. Assess the RISK REGIME (Risk On / Risk Off) with confidence level.
2. Check CROSS-MARKET CONSISTENCY — do equities, rates, commodities, and crypto tell the same story?
3. Identify MAIN DRIVERS and COUNTER-DRIVERS.
4. Produce a DECISION OUTPUT with exactly these 6 fields:
   - risk_on_off: "Risk On" / "Risk Off" / "Risk On (cautious)"
   - top_3_assets: list of 3 assets to focus on, with brief reason each
   - position_sizing: allocation map (asset → percentage), total risk budget, cash percentage
   - rationale: ONE sentence explaining the overall positioning logic
   - key_risks: 2-4 specific risks ranked by impact
   - invalidation_conditions: 2-3 observable conditions that would invalidate the thesis

Rules:
- Be specific — name assets, give numbers, cite data from the snapshot.
- If cross-market signals contradict, mark low confidence and reduce position sizing.
- If data is missing, note it and widen your uncertainty.
- Output MUST be valid JSON matching the schema below. No markdown, no commentary outside the JSON.
"""

_ANALYSIS_USER_TEMPLATE = """## Market Data Snapshot ({timestamp})

{snapshot_json}

## Required Output (JSON only)

Return a single JSON object with these exact keys:

{{
  "analysis": {{
    "risk_regime": "string",
    "confidence": "low|medium|high",
    "cross_market_consistent": true/false,
    "contradiction_detail": "string or empty",
    "main_drivers": ["driver1", "driver2"],
    "counter_drivers": ["counter1"],
    "regime_rationale": "string"
  }},
  "output": {{
    "risk_on_off": "string",
    "top_3_assets": ["asset1 (reason)", "asset2 (reason)", "asset3 (reason)"],
    "position_sizing": {{"asset1": 15, "asset2": 15, "cash": 70, "total_risk_budget": 30}},
    "rationale": "one sentence",
    "key_risks": ["risk1", "risk2"],
    "invalidation_conditions": ["condition1", "condition2"]
  }},
  "execution_notes": {{
    "do_immediately": "string",
    "avoid_today": "string",
    "monitor_intraday": "string"
  }}
}}
"""


class AnalysisEngine:
    """Calls Claude via CLI (`claude -p`) to produce analysis + decision.

    Uses the existing Claude Code CLI auth — no separate API key needed.
    Falls back to Anthropic SDK if ANTHROPIC_API_KEY is set.
    """

    def __init__(self, model: str = "claude-sonnet-4-5-20250929", temperature: float = 0.3):
        self.model = model
        self.temperature = temperature

    async def analyze(self, input_pkg: InputPackage) -> tuple[AnalysisContract, DecisionOutput, Dict[str, Any]]:
        """Run the analysis. Returns (analysis, output, execution_notes)."""
        snapshot_json = json.dumps(input_pkg.model_dump(), ensure_ascii=False, indent=2)
        user_msg = _ANALYSIS_USER_TEMPLATE.format(
            timestamp=input_pkg.timestamp,
            snapshot_json=snapshot_json,
        )
        full_prompt = _ANALYSIS_SYSTEM_PROMPT + "\n\n" + user_msg

        # Try CLI first, fallback to SDK if ANTHROPIC_API_KEY is set
        raw_text = await self._call(full_prompt)

        # Parse with single retry on format failure
        try:
            parsed = self._parse_response(raw_text)
        except ValueError:
            logger.warning("First JSON parse failed, retrying with schema enforcement...")
            retry_prompt = full_prompt + "\n\nPREVIOUS RESPONSE WAS INVALID JSON. Return ONLY valid JSON, no markdown."
            raw_text = await self._call(retry_prompt)
            parsed = self._parse_response(raw_text)

        analysis = AnalysisContract(**parsed.get("analysis", {}))
        output = DecisionOutput(**parsed.get("output", {}))
        execution_notes = parsed.get("execution_notes", {})

        return analysis, output, execution_notes

    async def _call(self, prompt: str) -> str:
        """Route to CLI or SDK based on environment."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            return await self._call_sdk(api_key, prompt)
        return await self._call_cli(prompt)

    async def _call_cli(self, prompt: str) -> str:
        """Call Claude via `claude -p` CLI — uses existing Claude Code auth.

        Passes prompt via stdin to avoid OS argument length limits.
        """
        claude_path = shutil.which("claude") or "/Users/wendy/.local/bin/claude"
        if not os.path.isfile(claude_path):
            raise RuntimeError("claude CLI not found. Install Claude Code or set ANTHROPIC_API_KEY.")

        logger.info("Calling Claude CLI (model=%s)...", self.model)

        proc = await asyncio.create_subprocess_exec(
            claude_path, "-p", "-", "--model", self.model, "--output-format", "text",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")), timeout=120
        )

        if proc.returncode != 0:
            err_msg = stderr.decode().strip()[:500] if stderr else "unknown error"
            raise RuntimeError(f"Claude CLI failed (exit {proc.returncode}): {err_msg}")

        raw_text = stdout.decode().strip()
        logger.info("Claude CLI response received (%d chars)", len(raw_text))
        return raw_text

    async def _call_sdk(self, api_key: str, prompt: str) -> str:
        """Call Claude via Anthropic SDK (async) — needs ANTHROPIC_API_KEY."""
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        logger.info("Calling Anthropic SDK (model=%s)...", self.model)

        message = await client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=self.temperature,
            system=_ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt.replace(_ANALYSIS_SYSTEM_PROMPT + "\n\n", "")}],
        )

        raw_text = message.content[0].text
        logger.info("Anthropic SDK response received (%d chars)", len(raw_text))
        return raw_text

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """Parse LLM response, handling potential markdown wrapping."""
        text = raw.strip()
        # Strip only the first and last markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].strip().startswith("```"):
                lines = lines[1:]  # remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]  # remove closing fence
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM response as JSON: %s", exc)
            logger.debug("Raw response: %s", raw[:500])
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc


# ── Decision Loop Service ──


class DecisionLoopService:
    """Orchestrates the full Decision Loop V1 cycle."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        api_key: str = "",
        model: str = "claude-sonnet-4-5-20250929",
    ):
        self.assembler = InputAssembler(base_url=base_url, api_key=api_key)
        self.engine = AnalysisEngine(model=model)

    async def run(self) -> DecisionRunResult:
        """Execute the full decision loop: gather → analyze → format → persist."""
        t0 = time.monotonic()
        run_id = f"{datetime.now(_TZ_SHANGHAI).strftime('%Y-%m-%d')}-{uuid4().hex[:6]}"

        # Step 1: Assemble input
        logger.info("[%s] Step 1: Assembling input package...", run_id)
        input_pkg = await self.assembler.assemble()
        logger.info(
            "[%s] Input assembled: %d A-share, %d US, %d commodities, %d crypto, missing=%s",
            run_id,
            len(input_pkg.ashare_indexes),
            len(input_pkg.us_market),
            len(input_pkg.commodities),
            len(input_pkg.crypto),
            input_pkg.missing_fields or "none",
        )

        # Refuse to run if all core data blocks are empty
        core_blocks = [input_pkg.ashare_indexes, input_pkg.us_market,
                       input_pkg.commodities, input_pkg.crypto]
        empty_cores = sum(1 for b in core_blocks if not b)
        if empty_cores >= 3:
            raise ValueError(
                f"Insufficient data: {empty_cores}/4 core blocks empty "
                f"(missing: {input_pkg.missing_fields}). Refusing to generate decision."
            )

        # Step 2: Analyze
        logger.info("[%s] Step 2: Running analysis engine...", run_id)
        analysis, output, exec_notes = await self.engine.analyze(input_pkg)
        logger.info("[%s] Analysis: regime=%s, confidence=%s", run_id, analysis.risk_regime, analysis.confidence)

        duration_ms = (time.monotonic() - t0) * 1000

        result = DecisionRunResult(
            run_id=run_id,
            timestamp=input_pkg.timestamp,
            input_package=input_pkg,
            analysis=analysis,
            output=output,
            execution_notes=exec_notes,
            duration_ms=round(duration_ms, 1),
        )

        # Step 3: Persist (run in thread to avoid blocking event loop)
        await asyncio.to_thread(self._persist, result)
        logger.info("[%s] Decision loop complete in %.0fms", run_id, duration_ms)

        return result

    def _persist(self, result: DecisionRunResult) -> None:
        """Save run to database."""
        from src.database import session_scope
        from src.models.decision import DecisionRun

        with session_scope() as session:
            record = DecisionRun(
                run_id=result.run_id,
                timestamp=datetime.fromisoformat(result.timestamp),
                risk_regime=result.analysis.risk_regime,
                confidence=result.analysis.confidence,
                risk_on_off=result.output.risk_on_off,
                top_assets=json.dumps(result.output.top_3_assets, ensure_ascii=False),
                position_sizing=json.dumps(result.output.position_sizing, ensure_ascii=False),
                rationale=result.output.rationale,
                key_risks=json.dumps(result.output.key_risks, ensure_ascii=False),
                invalidation=json.dumps(result.output.invalidation_conditions, ensure_ascii=False),
                input_json=result.input_package.model_dump_json(),
                analysis_json=result.analysis.model_dump_json(),
                output_json=result.output.model_dump_json(),
                duration_ms=result.duration_ms,
            )
            session.add(record)
        logger.info("[%s] Persisted to decision_runs table", result.run_id)

    def save_review(self, run_id: str, review: ReviewEntry) -> bool:
        """Attach a 23:00 review to an existing run."""
        from src.database import session_scope
        from src.models.decision import DecisionRun

        with session_scope() as session:
            record = session.query(DecisionRun).filter_by(run_id=run_id).first()
            if not record:
                return False
            record.review_json = review.model_dump_json()
            record.reviewed_at = datetime.now(_TZ_SHANGHAI)
        return True

    def get_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent decision runs."""
        from src.database import session_scope
        from src.models.decision import DecisionRun

        cutoff = datetime.now(_TZ_SHANGHAI) - timedelta(days=days)
        with session_scope() as session:
            rows = (
                session.query(DecisionRun)
                .filter(DecisionRun.timestamp >= cutoff)
                .order_by(DecisionRun.timestamp.desc())
                .all()
            )
            return [
                {
                    "run_id": r.run_id,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                    "risk_regime": r.risk_regime,
                    "confidence": r.confidence,
                    "risk_on_off": r.risk_on_off,
                    "top_assets": json.loads(r.top_assets) if r.top_assets else [],
                    "rationale": r.rationale,
                    "duration_ms": r.duration_ms,
                    "reviewed": r.review_json is not None,
                }
                for r in rows
            ]

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get 7-day stats for V1 acceptance criteria."""
        from src.database import session_scope
        from src.models.decision import DecisionRun

        cutoff = datetime.now(_TZ_SHANGHAI) - timedelta(days=days)
        with session_scope() as session:
            rows = (
                session.query(DecisionRun)
                .filter(DecisionRun.timestamp >= cutoff)
                .order_by(DecisionRun.timestamp.desc())
                .all()
            )

        total_runs = len(rows)
        reviewed = sum(1 for r in rows if r.review_json)
        avg_duration = sum(r.duration_ms or 0 for r in rows) / total_runs if total_runs else 0

        return {
            "period_days": days,
            "total_runs": total_runs,
            "reviewed_runs": reviewed,
            "review_completion_pct": round(reviewed / total_runs * 100, 1) if total_runs else 0,
            "avg_duration_ms": round(avg_duration, 1),
            "acceptance_criteria": {
                "valid_output_7_of_7": total_runs >= 7,
                "reviews_completed": reviewed >= 5 if total_runs >= 7 else False,
            },
        }
