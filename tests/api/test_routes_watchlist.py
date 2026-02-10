"""
Tests for watchlist API routes (/api/watchlist).

Covers CRUD operations, focus toggling, positioning updates,
portfolio history, and analytics endpoints.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from src.models import SymbolMetadata, Watchlist


@pytest.fixture(autouse=True)
def _ensure_stock_basic_table(db_session):
    """Create the raw ``stock_basic`` table expected by the POST handler's
    fallback query.  The table is not an ORM model, so it is absent from
    ``Base.metadata.create_all`` and must be created manually.
    """
    db_session.execute(text(
        "CREATE TABLE IF NOT EXISTS stock_basic ("
        "  symbol TEXT PRIMARY KEY,"
        "  name TEXT,"
        "  industry TEXT,"
        "  market TEXT"
        ")"
    ))
    db_session.commit()


def _add_symbol(db_session, ticker="600519", name="贵州茅台"):
    """Helper: insert a SymbolMetadata row so POST can find the ticker."""
    symbol = SymbolMetadata(ticker=ticker, name=name)
    db_session.add(symbol)
    db_session.commit()
    return symbol


def _add_to_watchlist_via_db(db_session, ticker="600519"):
    """Helper: insert a Watchlist row directly (bypasses POST logic)."""
    item = Watchlist(ticker=ticker)
    db_session.add(item)
    db_session.commit()
    return item


def _post_watchlist(client, ticker="600519"):
    """Helper: POST to /api/watchlist with KlineUpdater mocked out."""
    with patch("src.services.kline_updater.KlineUpdater") as mock_kline:
        mock_updater = mock_kline.create_with_session.return_value
        mock_updater.update_single_stock_klines = AsyncMock(
            return_value={"status": "ok"}
        )
        resp = client.post("/api/watchlist", json={"ticker": ticker})
    return resp


class TestGetWatchlist:
    """GET /api/watchlist"""

    def test_empty(self, client):
        """Returns an empty list when no items in watchlist."""
        resp = client.get("/api/watchlist")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_items_after_add(self, client, db_session):
        """Returns watchlist items with full metadata after adding a ticker."""
        _add_symbol(db_session)
        _add_to_watchlist_via_db(db_session, "600519")

        resp = client.get("/api/watchlist")
        assert resp.status_code == 200

        data = resp.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "600519"
        assert data[0]["name"] == "贵州茅台"


class TestCheckWatchlist:
    """GET /api/watchlist/check/{ticker}"""

    def test_not_in_watchlist(self, client):
        """Returns in_watchlist=false when ticker is absent."""
        resp = client.get("/api/watchlist/check/600519")
        assert resp.status_code == 200
        assert resp.json()["in_watchlist"] is False

    def test_in_watchlist(self, client, db_session):
        """Returns in_watchlist=true when ticker is present."""
        _add_to_watchlist_via_db(db_session, "600519")

        resp = client.get("/api/watchlist/check/600519")
        assert resp.status_code == 200
        assert resp.json()["in_watchlist"] is True


class TestAddToWatchlist:
    """POST /api/watchlist"""

    def test_add_success(self, client, db_session):
        """Successfully adds a ticker that exists in SymbolMetadata."""
        _add_symbol(db_session)

        resp = _post_watchlist(client, "600519")
        assert resp.status_code == 201

        body = resp.json()
        assert "成功添加" in body["message"]
        assert "贵州茅台" in body["message"]

    def test_add_duplicate_returns_400(self, client, db_session):
        """Adding the same ticker twice returns 400."""
        _add_symbol(db_session)

        resp1 = _post_watchlist(client, "600519")
        assert resp1.status_code == 201

        resp2 = _post_watchlist(client, "600519")
        assert resp2.status_code == 400
        assert "已在自选列表中" in resp2.json()["detail"]

    def test_add_unknown_ticker_returns_404(self, client):
        """Adding a ticker that does not exist anywhere returns 404."""
        resp = _post_watchlist(client, "999999")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]


class TestRemoveFromWatchlist:
    """DELETE /api/watchlist/{ticker}"""

    def test_remove_existing(self, client, db_session):
        """Removing an existing ticker succeeds."""
        _add_to_watchlist_via_db(db_session, "600519")

        resp = client.delete("/api/watchlist/600519")
        assert resp.status_code == 200
        assert "600519" in resp.json()["message"]

        # Verify it is actually gone
        check = client.get("/api/watchlist/check/600519")
        assert check.json()["in_watchlist"] is False

    def test_remove_nonexistent_returns_404(self, client):
        """Removing a ticker not in watchlist returns 404."""
        resp = client.delete("/api/watchlist/600519")
        assert resp.status_code == 404
        assert "不在自选列表中" in resp.json()["detail"]


class TestClearWatchlist:
    """DELETE /api/watchlist"""

    def test_clear_empty(self, client):
        """Clearing an empty watchlist returns deleted_count=0."""
        resp = client.delete("/api/watchlist")
        assert resp.status_code == 200
        assert resp.json()["deleted_count"] == 0

    def test_clear_with_items(self, client, db_session):
        """Clearing removes all items and reports count."""
        _add_to_watchlist_via_db(db_session, "600519")
        _add_to_watchlist_via_db(db_session, "000001")

        resp = client.delete("/api/watchlist")
        assert resp.status_code == 200
        assert resp.json()["deleted_count"] == 2

        # Verify empty
        get_resp = client.get("/api/watchlist")
        assert get_resp.json() == []


class TestToggleFocus:
    """PATCH /api/watchlist/{ticker}/focus"""

    def test_toggle_on(self, client, db_session):
        """Toggling focus on a non-focused item sets is_focus=true."""
        _add_to_watchlist_via_db(db_session, "600519")

        resp = client.patch("/api/watchlist/600519/focus")
        assert resp.status_code == 200

        body = resp.json()
        assert body["ticker"] == "600519"
        assert body["is_focus"] is True

    def test_toggle_off(self, client, db_session):
        """Toggling twice returns is_focus back to false."""
        _add_to_watchlist_via_db(db_session, "600519")

        # First toggle: false -> true
        resp1 = client.patch("/api/watchlist/600519/focus")
        assert resp1.json()["is_focus"] is True

        # Second toggle: true -> false
        resp2 = client.patch("/api/watchlist/600519/focus")
        assert resp2.json()["is_focus"] is False

    def test_toggle_nonexistent_returns_404(self, client):
        """Toggling focus on an absent ticker returns 404."""
        resp = client.patch("/api/watchlist/600519/focus")
        assert resp.status_code == 404


class TestUpdatePositioning:
    """PATCH /api/watchlist/{ticker}/positioning"""

    def test_update_positioning(self, client, db_session):
        """Sets the positioning text for a watchlist item."""
        _add_to_watchlist_via_db(db_session, "600519")

        resp = client.patch(
            "/api/watchlist/600519/positioning",
            json={"positioning": "高端白酒龙头"},
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["ticker"] == "600519"
        assert body["positioning"] == "高端白酒龙头"

    def test_update_positioning_overwrite(self, client, db_session):
        """Updating positioning replaces the previous value."""
        _add_to_watchlist_via_db(db_session, "600519")

        client.patch(
            "/api/watchlist/600519/positioning",
            json={"positioning": "旧定位"},
        )
        resp = client.patch(
            "/api/watchlist/600519/positioning",
            json={"positioning": "新定位：高端白酒龙头"},
        )
        assert resp.status_code == 200
        assert resp.json()["positioning"] == "新定位：高端白酒龙头"

    def test_update_positioning_nonexistent_returns_404(self, client):
        """Updating positioning on an absent ticker returns 404."""
        resp = client.patch(
            "/api/watchlist/600519/positioning",
            json={"positioning": "任意文字"},
        )
        assert resp.status_code == 404

    def test_update_positioning_missing_body_returns_422(self, client, db_session):
        """Omitting the positioning field returns 422 validation error."""
        _add_to_watchlist_via_db(db_session, "600519")

        resp = client.patch("/api/watchlist/600519/positioning", json={})
        assert resp.status_code == 422


class TestPortfolioHistory:
    """GET /api/watchlist/portfolio/history"""

    def test_empty_portfolio(self, client):
        """Empty watchlist returns zeroed-out portfolio history."""
        resp = client.get("/api/watchlist/portfolio/history")
        assert resp.status_code == 200

        body = resp.json()
        assert body["dates"] == []
        assert body["initial_investment"] == 0
        assert body["current_value"] == 0


class TestAnalytics:
    """GET /api/watchlist/analytics"""

    def test_empty_analytics(self, client):
        """Empty watchlist returns zeroed-out analytics overview."""
        resp = client.get("/api/watchlist/analytics")
        assert resp.status_code == 200

        body = resp.json()
        assert body["overview"]["total_stocks"] == 0
        assert body["industry_allocation"] == []
        assert body["top_gainers"] == []
        assert body["top_losers"] == []
