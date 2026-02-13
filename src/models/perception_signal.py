"""Perception signal and scan report persistence models."""

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from src.database import Base


class PerceptionSignal(Base):
    """Persisted perception signal from a scan cycle."""

    __tablename__ = "perception_signals"

    id = Column(Integer, primary_key=True)
    signal_id = Column(String, unique=True, index=True)
    scan_id = Column(String, index=True)
    asset = Column(String, index=True)
    market = Column(String)
    direction = Column(String)
    signal_type = Column(String)
    source = Column(String)
    strength = Column(Float)
    confidence = Column(Float)
    metadata_json = Column(Text)
    created_at = Column(DateTime, default=func.now(), index=True)
    expires_at = Column(DateTime, nullable=True)


class PerceptionScanReport(Base):
    """Persisted scan report summary."""

    __tablename__ = "perception_scan_reports"

    id = Column(Integer, primary_key=True)
    scan_id = Column(String, unique=True, index=True)
    timestamp = Column(DateTime, index=True)
    duration_ms = Column(Float)
    events_fetched = Column(Integer)
    signals_detected = Column(Integer)
    signals_ingested = Column(Integer)
    market_bias = Column(String)
    market_bias_score = Column(Float)
    top_longs_json = Column(Text)
    top_shorts_json = Column(Text)
    source_health_json = Column(Text)
    errors_json = Column(Text)
    created_at = Column(DateTime, default=func.now())
