"""Test market style index endpoint to see the actual error"""

import sys
import traceback
from src.database import SessionLocal
from src.models import SuperCategoryDaily
from sqlalchemy import func

def test_market_style_index():
    """Test the market style index calculation"""
    session = SessionLocal()

    try:
        # Get latest date
        latest_date_subq = session.query(
            func.max(SuperCategoryDaily.trade_date)
        ).scalar_subquery()

        trade_date = session.query(SuperCategoryDaily.trade_date).filter(
            SuperCategoryDaily.trade_date == latest_date_subq
        ).scalar()

        print(f"Latest trade date: {trade_date}")

        # Get all super categories
        super_categories = session.query(SuperCategoryDaily).filter(
            SuperCategoryDaily.trade_date == trade_date
        ).all()

        print(f"Found {len(super_categories)} super categories")

        # Test calculation
        rising_categories = []
        numerator = 0
        denominator = 0

        for cat in super_categories:
            print(f"{cat.super_category_name}: pct_change={cat.pct_change}, total_mv={cat.total_mv}")

            if cat.pct_change is None:
                continue

            money_flow = cat.total_mv * cat.pct_change

            if cat.pct_change > 0:
                rising_categories.append({
                    "name": cat.super_category_name,
                    "score": cat.score,
                    "pct_change": cat.pct_change,
                    "total_mv": cat.total_mv,
                    "money_flow": money_flow
                })

                weight = money_flow
                numerator += cat.score * weight
                denominator += weight

        if denominator > 0:
            index = numerator / denominator
            print(f"\nCalculated index: {index}")
            print(f"Rising categories: {len(rising_categories)}")
        else:
            print("No rising categories found!")

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    test_market_style_index()
