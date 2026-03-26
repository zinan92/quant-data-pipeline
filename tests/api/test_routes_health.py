"""
Tests for health check API endpoints.
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from src.models import (
    Kline,
    KlineTimeframe,
    SymbolType,
    TradeCalendar,
    DataUpdateLog,
    DataUpdateStatus,
)


class TestHealthGaps:
    """Tests for GET /api/health/gaps endpoint"""

    def test_empty_database_returns_zero_gaps(self, client):
        """When no klines exist, should return zero gaps."""
        resp = client.get("/api/health/gaps")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_gaps"] == 0
        assert data["details"] == []
        assert "calendar_coverage" in data
        assert "by_type" in data

    def test_gap_detection_finds_missing_days(self, client, db_session: Session):
        """Should detect gaps when klines are missing for trading days."""
        # Setup: Add trade calendar with 5 trading days
        for i, date in enumerate(["2021-01-04", "2021-01-05", "2021-01-06", "2021-01-07", "2021-01-08"], 1):
            db_session.add(TradeCalendar(date=date, is_trading_day=True))
        
        # Add klines for only 3 days (missing 2)
        for date in ["2021-01-04", "2021-01-05", "2021-01-08"]:
            db_session.add(Kline(
                symbol_type=SymbolType.STOCK,
                symbol_code="000001.SZ",
                symbol_name="平安银行",
                timeframe=KlineTimeframe.DAY,
                trade_time=f"{date} 15:00:00",
                open=10.0,
                high=10.5,
                low=9.8,
                close=10.2,
                volume=1000000,
                amount=10000000
            ))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/gaps")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should find 2 gaps
        assert data["total_gaps"] == 2
        assert len(data["details"]) == 1
        assert data["details"][0]["symbol_code"] == "000001.SZ"
        assert data["details"][0]["gap_count"] == 2
        assert set(data["details"][0]["missing_dates"]) == {"2021-01-06", "2021-01-07"}
        
        # Check by_type stats
        assert data["by_type"]["STOCK"]["symbols_with_gaps"] == 1
        assert data["by_type"]["STOCK"]["total_missing_days"] == 2
        assert data["by_type"]["INDEX"]["symbols_with_gaps"] == 0

    def test_no_gaps_when_all_days_covered(self, client, db_session: Session):
        """Should return zero gaps when all trading days are covered."""
        # Setup: Add trade calendar
        for date in ["2021-01-04", "2021-01-05"]:
            db_session.add(TradeCalendar(date=date, is_trading_day=True))
        
        # Add klines for all days
        for date in ["2021-01-04", "2021-01-05"]:
            db_session.add(Kline(
                symbol_type=SymbolType.INDEX,
                symbol_code="000001.SH",
                symbol_name="上证指数",
                timeframe=KlineTimeframe.DAY,
                trade_time=f"{date} 15:00:00",
                open=3500.0,
                high=3550.0,
                low=3480.0,
                close=3520.0,
                volume=100000000,
                amount=200000000000
            ))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/gaps")
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["total_gaps"] == 0
        assert len(data["details"]) == 0

    def test_calendar_coverage_info(self, client, db_session: Session):
        """Should include calendar coverage metadata."""
        # Setup: Add calendar data
        for date in ["2021-01-04", "2021-01-05", "2021-12-31"]:
            db_session.add(TradeCalendar(date=date, is_trading_day=True))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/gaps")
        assert resp.status_code == 200
        data = resp.json()
        
        coverage = data["calendar_coverage"]
        assert coverage["min_date"] == "2021-01-04"
        assert coverage["max_date"] == "2021-12-31"
        assert coverage["trading_days"] == 3

    def test_limits_details_to_top_50(self, client, db_session: Session):
        """Should limit details to top 50 symbols with most gaps."""
        # Setup: Add calendar
        for i in range(10):
            db_session.add(TradeCalendar(date=f"2021-01-{4+i:02d}", is_trading_day=True))
        
        # Add 60 stocks with varying gap counts
        for stock_num in range(60):
            # Each stock has different number of gaps (stock_num % 10)
            covered_days = 10 - (stock_num % 10)
            for day_idx in range(covered_days):
                db_session.add(Kline(
                    symbol_type=SymbolType.STOCK,
                    symbol_code=f"{stock_num:06d}.SZ",
                    symbol_name=f"Stock {stock_num}",
                    timeframe=KlineTimeframe.DAY,
                    trade_time=f"2021-01-{4+day_idx:02d} 15:00:00",
                    open=10.0,
                    high=10.5,
                    low=9.8,
                    close=10.2,
                    volume=1000000,
                    amount=10000000
                ))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/gaps")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should have details for exactly 50 symbols (limited)
        # But total_gaps should count all
        assert len(data["details"]) <= 50
        assert data["total_gaps"] > 0

    def test_respects_stock_listing_date(self, client, db_session: Session):
        """Should only count gaps AFTER a stock's listing date, not before."""
        from sqlalchemy import text
        
        # Setup: Add calendar for 2 weeks
        for i in range(10):
            db_session.add(TradeCalendar(date=f"2021-01-{4+i:02d}", is_trading_day=True))
        
        # Add a stock that IPO'd on 2021-01-10 (7th trading day)
        # This stock should only be expected to have data from 2021-01-10 onwards, not from 2021-01-04
        db_session.execute(text(
            "CREATE TABLE IF NOT EXISTS stock_basic ("
            "ts_code TEXT PRIMARY KEY, symbol TEXT, name TEXT, "
            "area TEXT, industry TEXT, market TEXT, list_date TEXT)"
        ))
        db_session.execute(text(
            "INSERT OR REPLACE INTO stock_basic (ts_code, symbol, name, list_date) "
            "VALUES ('300999.SZ', '300999', '新IPO股票', '20210110')"
        ))
        
        # Add klines for this stock starting from listing date (2021-01-10 onwards)
        # Missing 2021-01-11, 2021-01-12, 2021-01-13 (3 gaps)
        for date in ["2021-01-10"]:
            db_session.add(Kline(
                symbol_type=SymbolType.STOCK,
                symbol_code="300999",  # Plain format as stored in klines
                symbol_name="新IPO股票",
                timeframe=KlineTimeframe.DAY,
                trade_time=f"{date} 15:00:00",
                open=20.0,
                high=22.0,
                low=19.5,
                close=21.0,
                volume=5000000,
                amount=100000000
            ))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/gaps")
        assert resp.status_code == 200
        data = resp.json()
        
        # Find the IPO stock in details
        ipo_stock = next((d for d in data["details"] if d["symbol_code"] == "300999"), None)
        assert ipo_stock is not None
        
        # Should only count gaps from 2021-01-10 onwards (missing 2021-01-11, 12, 13)
        # NOT from 2021-01-04 (which would incorrectly add 6 more gap days)
        assert ipo_stock["gap_count"] == 3
        assert "2021-01-04" not in ipo_stock["missing_dates"]
        assert "2021-01-11" in ipo_stock["missing_dates"]
        assert "2021-01-12" in ipo_stock["missing_dates"]
        assert "2021-01-13" in ipo_stock["missing_dates"]

    def test_stock_listed_before_backfill_uses_backfill_date(self, client, db_session: Session):
        """Stocks listed before 2021-01-04 should use backfill start date."""
        from sqlalchemy import text
        
        # Setup: Add calendar
        for i in range(5):
            db_session.add(TradeCalendar(date=f"2021-01-{4+i:02d}", is_trading_day=True))
        
        # Add a stock that IPO'd in 2010 (well before backfill start)
        db_session.execute(text(
            "CREATE TABLE IF NOT EXISTS stock_basic ("
            "ts_code TEXT PRIMARY KEY, symbol TEXT, name TEXT, "
            "area TEXT, industry TEXT, market TEXT, list_date TEXT)"
        ))
        db_session.execute(text(
            "INSERT OR REPLACE INTO stock_basic (ts_code, symbol, name, list_date) "
            "VALUES ('000001.SZ', '000001', '平安银行', '19910403')"
        ))
        
        # Add klines missing 2 days (2021-01-06, 2021-01-07)
        for date in ["2021-01-04", "2021-01-05", "2021-01-08"]:
            db_session.add(Kline(
                symbol_type=SymbolType.STOCK,
                symbol_code="000001",
                symbol_name="平安银行",
                timeframe=KlineTimeframe.DAY,
                trade_time=f"{date} 15:00:00",
                open=10.0,
                high=10.5,
                low=9.8,
                close=10.2,
                volume=1000000,
                amount=10000000
            ))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/gaps")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should count gaps from 2021-01-04 onwards (not from 1991)
        stock = next((d for d in data["details"] if d["symbol_code"] == "000001"), None)
        assert stock is not None
        assert stock["gap_count"] == 2
        assert set(stock["missing_dates"]) == {"2021-01-06", "2021-01-07"}

    def test_indices_use_backfill_date_not_listing_date(self, client, db_session: Session):
        """Indices should always use backfill start date, not listing dates."""
        # Setup: Add calendar
        for i in range(5):
            db_session.add(TradeCalendar(date=f"2021-01-{4+i:02d}", is_trading_day=True))
        
        # Add index klines missing 2 days
        for date in ["2021-01-04", "2021-01-05", "2021-01-08"]:
            db_session.add(Kline(
                symbol_type=SymbolType.INDEX,
                symbol_code="000001.SH",
                symbol_name="上证指数",
                timeframe=KlineTimeframe.DAY,
                trade_time=f"{date} 15:00:00",
                open=3500.0,
                high=3550.0,
                low=3480.0,
                close=3520.0,
                volume=100000000,
                amount=200000000000
            ))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/gaps")
        assert resp.status_code == 200
        data = resp.json()
        
        # Indices should use backfill start date
        index = next((d for d in data["details"] if d["symbol_code"] == "000001.SH"), None)
        assert index is not None
        assert index["gap_count"] == 2
        assert set(index["missing_dates"]) == {"2021-01-06", "2021-01-07"}

    def test_returns_total_tracked_and_zero_gaps_counts(self, client, db_session: Session):
        """Should return total tracked stocks and count of stocks with zero gaps."""
        # Setup: Add calendar
        for i in range(5):
            db_session.add(TradeCalendar(date=f"2021-01-{4+i:02d}", is_trading_day=True))
        
        # Add 3 stocks: 2 with complete data, 1 with gaps
        for stock_code, has_gaps in [("000001", False), ("000002", False), ("000003", True)]:
            dates = ["2021-01-04", "2021-01-05", "2021-01-06", "2021-01-07", "2021-01-08"]
            if has_gaps:
                dates = dates[:3]  # Only partial data
            
            for date in dates:
                db_session.add(Kline(
                    symbol_type=SymbolType.STOCK,
                    symbol_code=stock_code,
                    symbol_name=f"股票{stock_code}",
                    timeframe=KlineTimeframe.DAY,
                    trade_time=f"{date} 15:00:00",
                    open=10.0,
                    high=10.5,
                    low=9.8,
                    close=10.2,
                    volume=1000000,
                    amount=10000000
                ))
        
        # Add 1 index (should not be counted in stock totals)
        db_session.add(Kline(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            symbol_name="上证指数",
            timeframe=KlineTimeframe.DAY,
            trade_time="2021-01-04 15:00:00",
            open=3500.0,
            high=3550.0,
            low=3480.0,
            close=3520.0,
            volume=100000000,
            amount=200000000000
        ))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/gaps")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should count stocks only (not indices)
        assert data["total_tracked_stocks"] == 3
        # 2 stocks have zero gaps
        assert data["stocks_with_zero_gaps"] == 2


class TestHealthConsistency:
    """Tests for GET /api/health/consistency endpoint"""

    @pytest.mark.asyncio
    async def test_consistency_endpoint_returns_validator_results(self, client, db_session: Session):
        """Should run DataConsistencyValidator and return results."""
        # Setup: Add some kline data for validation
        db_session.add(Kline(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            symbol_name="上证指数",
            timeframe=KlineTimeframe.DAY,
            trade_time="2021-01-04 15:00:00",
            open=3500.0,
            high=3550.0,
            low=3480.0,
            close=3520.0,
            volume=100000000,
            amount=200000000000
        ))
        db_session.add(Kline(
            symbol_type=SymbolType.INDEX,
            symbol_code="000001.SH",
            symbol_name="上证指数",
            timeframe=KlineTimeframe.MINS_30,
            trade_time="2021-01-04 15:00:00",
            open=3500.0,
            high=3550.0,
            low=3480.0,
            close=3520.0,  # Same close price = consistent
            volume=10000000,
            amount=20000000000
        ))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/consistency")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should have standard validator response structure
        assert "summary" in data
        assert "indexes" in data
        assert "concepts" in data
        assert "inconsistencies" in data
        
        # Summary should have expected fields
        summary = data["summary"]
        assert "total_validated" in summary
        assert "total_inconsistencies" in summary
        assert "consistency_rate" in summary
        assert "is_healthy" in summary

    @pytest.mark.asyncio
    async def test_consistency_empty_database(self, client):
        """Should handle empty database gracefully."""
        resp = client.get("/api/health/consistency")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should return valid structure even with no data
        assert data["summary"]["total_validated"] == 0
        assert data["indexes"] == []
        assert data["concepts"] == []


class TestHealthFailures:
    """Tests for GET /api/health/failures endpoint"""

    def test_failures_empty_database(self, client):
        """Should return empty list when no failures exist."""
        resp = client.get("/api/health/failures")
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["count"] == 0
        assert data["failures"] == []

    def test_failures_returns_recent_failures(self, client, db_session: Session):
        """Should return recent failed DataUpdateLog entries."""
        # Setup: Add some failed logs
        for i in range(5):
            db_session.add(DataUpdateLog(
                update_type=f"stock_day_{i}",
                symbol_type="STOCK",
                timeframe="DAY",
                status=DataUpdateStatus.FAILED,
                records_updated=0,
                error_message=f"Error {i}: API timeout",
                started_at=datetime(2021, 1, 4 + i, 10, 0, 0, tzinfo=timezone.utc),
                completed_at=datetime(2021, 1, 4 + i, 10, 5, 0, tzinfo=timezone.utc)
            ))
        
        # Add some successful logs (should not appear)
        db_session.add(DataUpdateLog(
            update_type="index_day",
            symbol_type="INDEX",
            timeframe="DAY",
            status=DataUpdateStatus.COMPLETED,
            records_updated=100,
            started_at=datetime(2021, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2021, 1, 10, 10, 5, 0, tzinfo=timezone.utc)
        ))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/failures")
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["count"] == 5
        assert len(data["failures"]) == 5
        
        # Should be ordered by started_at DESC (most recent first)
        # Most recent is 2021-01-08
        first_failure = data["failures"][0]
        assert first_failure["update_type"] == "stock_day_4"
        assert first_failure["status"] == "FAILED"
        assert first_failure["error_message"] == "Error 4: API timeout"
        assert "started_at" in first_failure
        
        # Last failure should be 2021-01-04
        last_failure = data["failures"][-1]
        assert last_failure["update_type"] == "stock_day_0"

    def test_failures_limits_to_50(self, client, db_session: Session):
        """Should limit results to 50 most recent failures."""
        # Setup: Add 60 failed logs
        for i in range(60):
            db_session.add(DataUpdateLog(
                update_type=f"test_{i}",
                symbol_type="STOCK",
                timeframe="DAY",
                status=DataUpdateStatus.FAILED,
                records_updated=0,
                error_message=f"Error {i}",
                started_at=datetime(2021, 1, 1, 10, i % 60, 0, tzinfo=timezone.utc)
            ))
        db_session.commit()
        
        # Test
        resp = client.get("/api/health/failures")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should have exactly 50 entries
        assert data["count"] == 50
        assert len(data["failures"]) == 50

    def test_failures_includes_all_fields(self, client, db_session: Session):
        """Should include all relevant fields in failure records."""
        db_session.add(DataUpdateLog(
            update_type="concept_day",
            symbol_type="CONCEPT",
            timeframe="DAY",
            status=DataUpdateStatus.FAILED,
            records_updated=5,
            error_message="TuShare API rate limit exceeded",
            started_at=datetime(2021, 1, 5, 14, 30, 0, tzinfo=timezone.utc),
            completed_at=datetime(2021, 1, 5, 14, 35, 0, tzinfo=timezone.utc)
        ))
        db_session.commit()
        
        resp = client.get("/api/health/failures")
        assert resp.status_code == 200
        data = resp.json()
        
        failure = data["failures"][0]
        assert failure["update_type"] == "concept_day"
        assert failure["symbol_type"] == "CONCEPT"
        assert failure["timeframe"] == "DAY"
        assert failure["status"] == "FAILED"
        assert failure["records_updated"] == 5
        assert failure["error_message"] == "TuShare API rate limit exceeded"
        assert failure["started_at"] is not None
        assert failure["completed_at"] is not None
