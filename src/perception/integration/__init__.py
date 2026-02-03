"""Perception → Trading-Agents integration layer.

Bridges perception signals into formats consumable by the trading-agents
decision pipeline, publishes signals to an event bus, and builds market
context objects for injection into trading analysis.
"""

from src.perception.integration.trading_bridge import (
    TradingAction,
    TradingSignal,
    BridgeConfig,
    TradingBridge,
)
from src.perception.integration.signal_publisher import (
    SignalPublisher,
    PublisherConfig,
    SignalEnvelope,
)
from src.perception.integration.market_context import (
    MarketSentiment,
    SectorSignal,
    RiskFactor,
    MarketContext,
    MarketContextBuilder,
)

__all__ = [
    # Bridge
    "TradingAction",
    "TradingSignal",
    "BridgeConfig",
    "TradingBridge",
    # Publisher
    "SignalPublisher",
    "PublisherConfig",
    "SignalEnvelope",
    # Market Context
    "MarketSentiment",
    "SectorSignal",
    "RiskFactor",
    "MarketContext",
    "MarketContextBuilder",
]
