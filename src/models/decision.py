"""Decision Loop V1 — persistence model."""

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from src.database import Base


class DecisionRun(Base):
    """Persisted decision loop run."""

    __tablename__ = "decision_runs"

    id = Column(Integer, primary_key=True)
    run_id = Column(String, unique=True, index=True)
    timestamp = Column(DateTime, index=True)
    risk_regime = Column(String)
    confidence = Column(String)
    risk_on_off = Column(String)
    top_assets = Column(Text)          # JSON list
    position_sizing = Column(Text)     # JSON dict
    rationale = Column(Text)
    key_risks = Column(Text)           # JSON list
    invalidation = Column(Text)        # JSON list
    input_json = Column(Text)          # full InputPackage JSON
    analysis_json = Column(Text)       # full AnalysisContract JSON
    output_json = Column(Text)         # full DecisionOutput JSON
    duration_ms = Column(Float, default=0.0)
    # Review fields (filled later at 23:00)
    review_json = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
