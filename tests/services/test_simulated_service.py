"""
Tests for SimulatedService

Uses the db_session fixture from tests/conftest.py which provides
an in-memory SQLite session with all tables created.
"""

import pytest

from src.models import SymbolMetadata
from src.models.simulated import SimulatedAccount, SimulatedPosition, SimulatedTrade
from src.models.enums import TradeType
from src.services.simulated_service import SimulatedService, DEFAULT_INITIAL_CAPITAL


@pytest.fixture
def symbol_maotai(db_session):
    """Insert a SymbolMetadata record for 贵州茅台 so buy/sell can resolve stock names."""
    meta = SymbolMetadata(ticker="600519", name="贵州茅台")
    db_session.add(meta)
    db_session.commit()
    return meta


@pytest.fixture
def service(db_session):
    """Create a SimulatedService backed by the in-memory test database."""
    return SimulatedService.create_with_session(db_session)


# ---------------------------------------------------------------------------
# 1. Account auto-creation
# ---------------------------------------------------------------------------

class TestAccountAutoCreated:
    def test_account_auto_created(self, db_session, service):
        """Constructing the service auto-creates a SimulatedAccount row."""
        account = db_session.query(SimulatedAccount).first()
        assert account is not None
        assert account.initial_capital == DEFAULT_INITIAL_CAPITAL
        assert account.created_at is not None

    def test_account_not_duplicated(self, db_session, service):
        """Creating a second service instance does not duplicate the account."""
        _ = SimulatedService.create_with_session(db_session)
        count = db_session.query(SimulatedAccount).count()
        assert count == 1


# ---------------------------------------------------------------------------
# 2. get_account (initial state)
# ---------------------------------------------------------------------------

class TestGetAccountInitial:
    def test_get_account_initial(self, service):
        """Initial account has full capital, zero positions, zero PnL."""
        acct = service.get_account()
        assert acct["initial_capital"] == DEFAULT_INITIAL_CAPITAL
        assert acct["cash"] == DEFAULT_INITIAL_CAPITAL
        assert acct["position_count"] == 0
        assert acct["total_pnl"] == 0
        assert acct["total_pnl_pct"] == 0
        assert acct["position_value"] == 0
        assert acct["total_value"] == DEFAULT_INITIAL_CAPITAL


# ---------------------------------------------------------------------------
# 3. buy() - success
# ---------------------------------------------------------------------------

class TestBuySuccess:
    def test_buy_creates_trade_and_position(self, db_session, service, symbol_maotai):
        """A successful buy creates a trade record and a position."""
        result = service.buy(
            ticker="600519",
            price=1800.0,
            position_pct=10,
            note="test buy",
        )

        assert result["success"] is True
        assert result["ticker"] == "600519"
        assert result["stock_name"] == "贵州茅台"
        assert result["shares"] > 0
        assert result["shares"] % 100 == 0  # rounded to lot size
        assert result["price"] == 1800.0
        assert result["amount"] == result["shares"] * 1800.0

        # Verify trade record in DB
        trade = db_session.query(SimulatedTrade).first()
        assert trade is not None
        assert trade.ticker == "600519"
        assert trade.trade_type == TradeType.BUY
        assert trade.trade_price == 1800.0
        assert trade.shares == result["shares"]
        assert trade.note == "test buy"

        # Verify position in DB
        pos = db_session.query(SimulatedPosition).filter_by(ticker="600519").first()
        assert pos is not None
        assert pos.shares == result["shares"]
        assert pos.cost_price == 1800.0
        assert pos.stock_name == "贵州茅台"

    def test_buy_reduces_cash(self, service, symbol_maotai):
        """After buying, available cash decreases."""
        service.buy(ticker="600519", price=1800.0, position_pct=10)
        acct = service.get_account()
        assert acct["cash"] < DEFAULT_INITIAL_CAPITAL

    def test_buy_add_to_existing_position(self, db_session, service, symbol_maotai):
        """Buying the same stock twice increases shares and recalculates average cost."""
        service.buy(ticker="600519", price=1800.0, position_pct=10)
        first_pos = db_session.query(SimulatedPosition).filter_by(ticker="600519").first()
        first_shares = first_pos.shares

        service.buy(ticker="600519", price=1900.0, position_pct=10)
        db_session.refresh(first_pos)

        assert first_pos.shares > first_shares
        # Average cost should be between 1800 and 1900
        assert 1800.0 < first_pos.cost_price < 1900.0


# ---------------------------------------------------------------------------
# 4. buy() - insufficient funds
# ---------------------------------------------------------------------------

class TestBuyInsufficientFunds:
    def test_buy_insufficient_funds(self, db_session, service, symbol_maotai):
        """Buying when cash is zero returns an error."""
        # Drain all cash by setting initial_capital to 0
        account = db_session.query(SimulatedAccount).first()
        account.initial_capital = 0
        db_session.commit()

        result = service.buy(ticker="600519", price=1800.0, position_pct=10)
        assert result["success"] is False
        assert "不足" in result["error"]

    def test_buy_too_expensive(self, db_session, service, symbol_maotai):
        """When position_pct is too small to afford 100 shares, returns error."""
        # Very expensive stock with tiny position percentage
        result = service.buy(
            ticker="600519",
            price=999999.0,
            position_pct=0.001,
        )
        assert result["success"] is False


# ---------------------------------------------------------------------------
# 5. sell() - success with PnL
# ---------------------------------------------------------------------------

class TestSellSuccess:
    def test_sell_full_position(self, db_session, service, symbol_maotai):
        """Selling 100% of a position removes it and records PnL."""
        buy_result = service.buy(ticker="600519", price=1800.0, position_pct=10)
        shares_bought = buy_result["shares"]

        sell_result = service.sell(
            ticker="600519",
            price=2000.0,
            sell_pct=100,
            note="take profit",
        )

        assert sell_result["success"] is True
        assert sell_result["shares"] == shares_bought
        assert sell_result["price"] == 2000.0

        # PnL should be positive (sold higher than cost)
        assert sell_result["pnl"] > 0
        assert sell_result["pnl_pct"] > 0

        # Position should be removed after full sell
        pos = db_session.query(SimulatedPosition).filter_by(ticker="600519").first()
        assert pos is None

        # Trade record should exist with realized PnL
        sell_trade = (
            db_session.query(SimulatedTrade)
            .filter_by(trade_type=TradeType.SELL)
            .first()
        )
        assert sell_trade is not None
        assert sell_trade.realized_pnl > 0
        assert sell_trade.note == "take profit"

    def test_sell_partial_position(self, db_session, service, symbol_maotai):
        """Selling a partial position keeps the remaining shares."""
        buy_result = service.buy(ticker="600519", price=1800.0, position_pct=20)
        initial_shares = buy_result["shares"]

        # Sell 50%
        sell_result = service.sell(ticker="600519", price=2000.0, sell_pct=50)
        assert sell_result["success"] is True

        # Position should still exist with reduced shares
        pos = db_session.query(SimulatedPosition).filter_by(ticker="600519").first()
        assert pos is not None
        assert pos.shares < initial_shares
        assert pos.shares > 0

    def test_sell_at_loss(self, db_session, service, symbol_maotai):
        """Selling below cost price produces negative PnL."""
        service.buy(ticker="600519", price=1800.0, position_pct=10)
        sell_result = service.sell(ticker="600519", price=1500.0, sell_pct=100)

        assert sell_result["success"] is True
        assert sell_result["pnl"] < 0
        assert sell_result["pnl_pct"] < 0

    def test_sell_pnl_calculation(self, db_session, service, symbol_maotai):
        """Verify the exact PnL math: pnl = sell_amount - cost_of_sold."""
        service.buy(ticker="600519", price=1800.0, position_pct=10)
        pos = db_session.query(SimulatedPosition).filter_by(ticker="600519").first()
        shares = pos.shares
        cost = pos.cost_amount

        sell_price = 2000.0
        sell_result = service.sell(ticker="600519", price=sell_price, sell_pct=100)

        expected_pnl = (shares * sell_price) - cost
        assert sell_result["pnl"] == pytest.approx(round(expected_pnl, 2), abs=0.01)


# ---------------------------------------------------------------------------
# 6. sell() - no position
# ---------------------------------------------------------------------------

class TestSellNoPosition:
    def test_sell_no_position(self, service):
        """Selling a stock not held returns an error."""
        result = service.sell(ticker="600519", price=2000.0, sell_pct=100)
        assert result["success"] is False
        assert "未持有" in result["error"]


# ---------------------------------------------------------------------------
# 7. get_positions()
# ---------------------------------------------------------------------------

class TestGetPositions:
    def test_get_positions_empty(self, service):
        """With no buys, positions list is empty."""
        positions = service.get_positions()
        assert positions == []

    def test_get_positions_after_buy(self, service, symbol_maotai):
        """After buying, get_positions returns the held stock."""
        service.buy(ticker="600519", price=1800.0, position_pct=10)
        positions = service.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert pos["ticker"] == "600519"
        assert pos["stock_name"] == "贵州茅台"
        assert pos["shares"] > 0
        assert pos["cost_price"] == 1800.0
        assert pos["cost_amount"] > 0
        assert pos["first_buy_date"] is not None

    def test_get_positions_multiple_stocks(self, db_session, service, symbol_maotai):
        """Buying multiple stocks shows all of them in positions."""
        # Add a second stock
        db_session.add(SymbolMetadata(ticker="000858", name="五粮液"))
        db_session.commit()

        service.buy(ticker="600519", price=1800.0, position_pct=10)
        service.buy(ticker="000858", price=150.0, position_pct=10)

        positions = service.get_positions()
        assert len(positions) == 2
        tickers = {p["ticker"] for p in positions}
        assert tickers == {"600519", "000858"}


# ---------------------------------------------------------------------------
# 8. get_trades()
# ---------------------------------------------------------------------------

class TestGetTrades:
    def test_get_trades_empty(self, service):
        """With no trades, the history is empty."""
        result = service.get_trades()
        assert result["trades"] == []
        assert result["total"] == 0

    def test_get_trades_after_buy_and_sell(self, service, symbol_maotai):
        """Trade history contains both buy and sell records."""
        service.buy(ticker="600519", price=1800.0, position_pct=10)
        service.sell(ticker="600519", price=2000.0, sell_pct=100)

        result = service.get_trades()
        assert result["total"] == 2
        assert len(result["trades"]) == 2

        trade_types = {t["trade_type"] for t in result["trades"]}
        assert trade_types == {"buy", "sell"}

    def test_get_trades_pagination(self, service, symbol_maotai):
        """Pagination via limit and offset works correctly."""
        # Create 3 buy trades
        service.buy(ticker="600519", price=1800.0, position_pct=5)
        service.buy(ticker="600519", price=1810.0, position_pct=5)
        service.buy(ticker="600519", price=1820.0, position_pct=5)

        # Get first page
        page1 = service.get_trades(limit=2, offset=0)
        assert len(page1["trades"]) == 2
        assert page1["total"] == 3

        # Get second page
        page2 = service.get_trades(limit=2, offset=2)
        assert len(page2["trades"]) == 1

    def test_get_trades_filter_by_ticker(self, db_session, service, symbol_maotai):
        """Filtering trades by ticker returns only matching records."""
        db_session.add(SymbolMetadata(ticker="000858", name="五粮液"))
        db_session.commit()

        service.buy(ticker="600519", price=1800.0, position_pct=5)
        service.buy(ticker="000858", price=150.0, position_pct=5)

        result = service.get_trades(ticker="600519")
        assert result["total"] == 1
        assert result["trades"][0]["ticker"] == "600519"

    def test_get_trades_record_fields(self, service, symbol_maotai):
        """Each trade record contains the expected fields."""
        service.buy(ticker="600519", price=1800.0, position_pct=10, note="entry")
        result = service.get_trades()
        trade = result["trades"][0]

        expected_keys = {
            "id", "ticker", "stock_name", "trade_type", "trade_date",
            "trade_price", "shares", "amount", "position_pct",
            "realized_pnl", "realized_pnl_pct", "note", "created_at",
        }
        assert expected_keys.issubset(set(trade.keys()))
        assert trade["note"] == "entry"


# ---------------------------------------------------------------------------
# 9. check_position()
# ---------------------------------------------------------------------------

class TestCheckPosition:
    def test_check_position_not_held(self, service):
        """Checking a stock not held returns has_position=False."""
        result = service.check_position("600519")
        assert result["has_position"] is False
        assert result["position"] is None

    def test_check_position_held(self, service, symbol_maotai):
        """Checking a held stock returns has_position=True with details."""
        service.buy(ticker="600519", price=1800.0, position_pct=10)
        result = service.check_position("600519")

        assert result["has_position"] is True
        pos = result["position"]
        assert pos is not None
        assert pos["shares"] > 0
        assert pos["cost_price"] == 1800.0
        # current_price will be None because no kline data is inserted
        assert pos["current_price"] is None
        # pnl_pct should be 0 when current_price is None
        assert pos["pnl_pct"] == 0

    def test_check_position_after_full_sell(self, service, symbol_maotai):
        """After fully selling, check_position returns has_position=False."""
        service.buy(ticker="600519", price=1800.0, position_pct=10)
        service.sell(ticker="600519", price=2000.0, sell_pct=100)

        result = service.check_position("600519")
        assert result["has_position"] is False
        assert result["position"] is None
