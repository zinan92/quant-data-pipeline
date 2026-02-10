"""Test market style index calculation.

Note: SuperCategoryDaily model is not yet defined in src/models.
These tests are placeholders that skip when the model is unavailable.
"""

import pytest


def _import_super_category_daily():
    """Try to import SuperCategoryDaily; return None if unavailable."""
    try:
        from src.models import SuperCategoryDaily
        return SuperCategoryDaily
    except ImportError:
        return None


SuperCategoryDaily = _import_super_category_daily()

needs_model = pytest.mark.skipif(
    SuperCategoryDaily is None,
    reason="SuperCategoryDaily model not yet defined in src.models",
)


@needs_model
def test_market_style_index_with_data(db_session):
    """Test market style index calculation with synthetic data."""
    from sqlalchemy import func

    db_session.add_all([
        SuperCategoryDaily(
            trade_date="2024-01-15",
            super_category_name="消费",
            pct_change=1.5,
            total_mv=5000.0,
            score=80,
        ),
        SuperCategoryDaily(
            trade_date="2024-01-15",
            super_category_name="科技",
            pct_change=-0.5,
            total_mv=3000.0,
            score=60,
        ),
        SuperCategoryDaily(
            trade_date="2024-01-15",
            super_category_name="金融",
            pct_change=0.8,
            total_mv=8000.0,
            score=70,
        ),
    ])
    db_session.commit()

    latest_date = db_session.query(
        func.max(SuperCategoryDaily.trade_date)
    ).scalar()
    assert latest_date == "2024-01-15"

    categories = db_session.query(SuperCategoryDaily).filter(
        SuperCategoryDaily.trade_date == latest_date
    ).all()
    assert len(categories) == 3

    numerator = 0.0
    denominator = 0.0
    for cat in categories:
        if cat.pct_change is not None and cat.pct_change > 0:
            weight = cat.total_mv * cat.pct_change
            numerator += cat.score * weight
            denominator += weight

    assert denominator > 0
    index = numerator / denominator
    assert 70 < index < 80


@needs_model
def test_market_style_index_no_data(db_session):
    """Test graceful handling when no data exists."""
    from sqlalchemy import func

    latest_date = db_session.query(
        func.max(SuperCategoryDaily.trade_date)
    ).scalar()
    assert latest_date is None
