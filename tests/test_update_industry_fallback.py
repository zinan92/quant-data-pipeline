from __future__ import annotations

import pandas as pd

from scripts.update_industry_daily import fetch_moneyflow_with_fallback


class _FakeClient:
    def __init__(self) -> None:
        self.requested_dates: list[str] = []

    def fetch_trade_calendar(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"cal_date": "20260302", "is_open": 1},
                {"cal_date": "20260303", "is_open": 1},
                {"cal_date": "20260304", "is_open": 1},
            ]
        )

    def fetch_ths_industry_moneyflow(self, trade_date: str) -> pd.DataFrame:
        self.requested_dates.append(trade_date)
        if trade_date == "20260304":
            return pd.DataFrame()
        return pd.DataFrame([{"ts_code": "881001.TI", "close": 1.0, "pct_change": 0.1, "company_num": 10}])


def test_fetch_moneyflow_with_fallback_uses_previous_trade_day() -> None:
    client = _FakeClient()
    selected_date, data = fetch_moneyflow_with_fallback(client, preferred_date="20260304", lookback_days=5)

    assert selected_date == "20260303"
    assert not data.empty
    assert client.requested_dates[:2] == ["20260304", "20260303"]


def test_fetch_moneyflow_with_fallback_returns_empty_when_all_dates_missing() -> None:
    class _EmptyClient(_FakeClient):
        def fetch_ths_industry_moneyflow(self, trade_date: str) -> pd.DataFrame:
            self.requested_dates.append(trade_date)
            return pd.DataFrame()

    client = _EmptyClient()
    selected_date, data = fetch_moneyflow_with_fallback(client, preferred_date="20260304", lookback_days=2)

    assert selected_date == "20260304"
    assert data.empty
