"""Decision Loop V1 — Pydantic schemas for input, analysis, output, and review."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Input Package (V1 Schema) ──


class MarketSnapshot(BaseModel):
    """Single market/asset snapshot."""
    symbol: str
    name: str
    price: float = 0.0
    change_pct: float = 0.0
    extra: Dict[str, Any] = Field(default_factory=dict)


class InputPackage(BaseModel):
    """V1 daily input package — assembled from existing API endpoints."""

    timestamp: str = Field(default="", description="Snapshot time ISO format")

    # 1.1 Cross-sectional snapshot
    ashare_indexes: List[MarketSnapshot] = Field(default_factory=list)
    us_market: List[MarketSnapshot] = Field(default_factory=list)
    commodities: List[MarketSnapshot] = Field(default_factory=list)
    crypto: List[MarketSnapshot] = Field(default_factory=list)

    # 1.2 Time-series summary (short text)
    short_term_trend: str = ""
    medium_term_trend: str = ""
    regime_change_flags: str = ""

    # 1.3 Event context
    intel_signals: Dict[str, Any] = Field(default_factory=dict)
    perception_context: Dict[str, Any] = Field(default_factory=dict)

    # 1.4 Completeness
    missing_fields: List[str] = Field(default_factory=list)
    is_low_confidence: bool = False


# ── Analysis Contract ──


class AnalysisContract(BaseModel):
    """V1 analysis contract — risk regime, consistency, drivers."""

    risk_regime: str = Field(description="e.g. 'Risk On', 'Risk Off', 'Mild Risk On with divergence'")
    confidence: str = Field(default="medium", description="low / medium / high")
    cross_market_consistent: bool = True
    contradiction_detail: str = ""
    main_drivers: List[str] = Field(default_factory=list)
    counter_drivers: List[str] = Field(default_factory=list)
    regime_rationale: str = ""


# ── Decision Output (V1 required fields) ──


class DecisionOutput(BaseModel):
    """V1 output schema — the 6 required fields."""

    risk_on_off: str = Field(description="Risk On / Risk Off / Risk On (cautious)")
    top_3_assets: List[str] = Field(min_length=3, max_length=3)
    position_sizing: Dict[str, Any] = Field(description="Asset allocation map")
    rationale: str = Field(description="One-sentence rationale")
    key_risks: List[str] = Field(min_length=1)
    invalidation_conditions: List[str] = Field(min_length=1)


# ── Full Run Result ──


class DecisionRunResult(BaseModel):
    """Complete decision loop run result."""

    run_id: str
    timestamp: str
    input_package: InputPackage
    analysis: AnalysisContract
    output: DecisionOutput
    execution_notes: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0


# ── Review (23:00) ──


class ReviewEntry(BaseModel):
    """Daily 23:00 review — 5 dimensions, all required (non-empty)."""

    judgment_error: str = Field(min_length=1, description="What was wrong in market interpretation?")
    signal_bias: str = Field(min_length=1, description="What signal was overweighted/underweighted?")
    communication_error: str = Field(min_length=1, description="Where was ambiguity?")
    sop_update_rule: str = Field(min_length=1, description="What rule changes tomorrow?")
    sop_update_location: str = Field(min_length=1, description="Where is the rule documented?")
