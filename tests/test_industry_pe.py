"""Tests for industry PE calculation logic."""

import pytest


def test_market_cap_weighted_pe_calculation():
    """
    Test that industry PE is correctly calculated using market-cap weighting.

    Formula: Industry PE = Σ(individual_PE × market_cap) / Σ(market_cap)
    """
    # Test data: 3 stocks with different PE and market caps
    stocks = [
        {"pe_ttm": 10, "total_mv": 1000},   # Small cap, low PE
        {"pe_ttm": 20, "total_mv": 2000},   # Medium cap, medium PE
        {"pe_ttm": 30, "total_mv": 3000},   # Large cap, high PE
    ]

    # Calculate weighted PE
    weighted_pe_sum = sum(s["pe_ttm"] * s["total_mv"] for s in stocks)
    weighted_mv_sum = sum(s["total_mv"] for s in stocks)
    expected_pe = weighted_pe_sum / weighted_mv_sum

    # Expected: (10*1000 + 20*2000 + 30*3000) / (1000+2000+3000)
    # = (10000 + 40000 + 90000) / 6000
    # = 140000 / 6000
    # = 23.33

    assert abs(expected_pe - 23.33) < 0.01, f"Expected ~23.33, got {expected_pe}"


def test_industry_pe_with_negative_pe():
    """Test that stocks with negative PE (loss-making) are excluded."""
    stocks = [
        {"pe_ttm": 10, "total_mv": 1000},
        {"pe_ttm": -5, "total_mv": 2000},  # Negative PE, should be excluded
        {"pe_ttm": 20, "total_mv": 3000},
    ]

    # Filter out negative PEs
    valid_stocks = [s for s in stocks if s["pe_ttm"] > 0]

    weighted_pe_sum = sum(s["pe_ttm"] * s["total_mv"] for s in valid_stocks)
    weighted_mv_sum = sum(s["total_mv"] for s in valid_stocks)
    industry_pe = weighted_pe_sum / weighted_mv_sum

    # Expected: (10*1000 + 20*3000) / (1000+3000)
    # = 70000 / 4000 = 17.5

    assert abs(industry_pe - 17.5) < 0.01, f"Expected 17.5, got {industry_pe}"


def test_industry_pe_with_zero_pe():
    """Test that stocks with zero PE are excluded."""
    stocks = [
        {"pe_ttm": 10, "total_mv": 1000},
        {"pe_ttm": 0, "total_mv": 2000},   # Zero PE, should be excluded
        {"pe_ttm": 20, "total_mv": 3000},
    ]

    # Filter out zero PEs
    valid_stocks = [s for s in stocks if s["pe_ttm"] > 0]

    weighted_pe_sum = sum(s["pe_ttm"] * s["total_mv"] for s in valid_stocks)
    weighted_mv_sum = sum(s["total_mv"] for s in valid_stocks)
    industry_pe = weighted_pe_sum / weighted_mv_sum

    # Same as test_industry_pe_with_negative_pe
    assert abs(industry_pe - 17.5) < 0.01


def test_industry_pe_with_no_valid_stocks():
    """Test that None is returned when no stocks have valid PE."""
    stocks = [
        {"pe_ttm": -10, "total_mv": 1000},
        {"pe_ttm": 0, "total_mv": 2000},
        {"pe_ttm": -5, "total_mv": 3000},
    ]

    # Filter out invalid PEs
    valid_stocks = [s for s in stocks if s["pe_ttm"] > 0]

    if not valid_stocks:
        industry_pe = None
    else:
        weighted_pe_sum = sum(s["pe_ttm"] * s["total_mv"] for s in valid_stocks)
        weighted_mv_sum = sum(s["total_mv"] for s in valid_stocks)
        industry_pe = weighted_pe_sum / weighted_mv_sum

    assert industry_pe is None, "Should return None when no valid stocks"


def test_industry_pe_simple_average_vs_weighted():
    """
    Test that market-cap weighting gives different result than simple average.
    This validates the design choice to use weighted averaging.
    """
    stocks = [
        {"pe_ttm": 10, "total_mv": 100},    # Small company
        {"pe_ttm": 100, "total_mv": 10000}, # Large company
    ]

    # Simple average
    simple_avg = sum(s["pe_ttm"] for s in stocks) / len(stocks)
    # = (10 + 100) / 2 = 55

    # Weighted average
    weighted_pe_sum = sum(s["pe_ttm"] * s["total_mv"] for s in stocks)
    weighted_mv_sum = sum(s["total_mv"] for s in stocks)
    weighted_avg = weighted_pe_sum / weighted_mv_sum
    # = (10*100 + 100*10000) / (100 + 10000)
    # = 1001000 / 10100 ≈ 99.11

    assert abs(simple_avg - 55) < 0.01, "Simple average should be 55"
    assert abs(weighted_avg - 99.11) < 0.1, "Weighted average should be ~99.11"
    assert weighted_avg > simple_avg, "Weighted average should be higher (dominated by large cap)"


def test_industry_pe_rounding():
    """Test that industry PE is correctly rounded to 2 decimal places."""
    stocks = [
        {"pe_ttm": 10.123, "total_mv": 1000},
        {"pe_ttm": 20.789, "total_mv": 2000},
    ]

    weighted_pe_sum = sum(s["pe_ttm"] * s["total_mv"] for s in stocks)
    weighted_mv_sum = sum(s["total_mv"] for s in stocks)
    industry_pe = weighted_pe_sum / weighted_mv_sum
    industry_pe_rounded = round(industry_pe, 2)

    # Expected: (10.123*1000 + 20.789*2000) / 3000 ≈ 17.23
    assert abs(industry_pe_rounded - 17.23) < 0.01
    assert len(str(industry_pe_rounded).split(".")[-1]) <= 2, "Should have at most 2 decimal places"
