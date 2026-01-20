#!/usr/bin/env python3
"""
Rebuild data/etf_daily_summary_filtered.csv from the latest full summary.

The filtered list is curated to power the ETF panel. We:
1) Read the latest etf_daily_summary.csv produced by update_etf_daily_summary.py
2) Keep only the curated tickers
3) Re-attach the configured super category tags
4) Save to etf_daily_summary_filtered.csv (utf-8-sig)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FULL_FILE = DATA_DIR / "etf_daily_summary.csv"
FILTERED_FILE = DATA_DIR / "etf_daily_summary_filtered.csv"

# Fallback curated list (also used if the filtered file is missing)
DEFAULT_SELECTION: Dict[str, str] = {
    "510300.SH": "宽基指数型",  # 沪深300ETF
    "159915.SZ": "宽基指数型",  # 创业板ETF
    "588000.SH": "宽基指数型",  # 科创50ETF
    "513130.SH": "宽基指数型",  # 恒生科技ETF
    "588200.SH": "信息技术",    # 科创芯片ETF
    "512480.SH": "信息技术",    # 半导体ETF
    "515880.SH": "信息技术",    # 通信ETF
    "513120.SH": "医药医疗",    # 港股创新药ETF
    "159992.SZ": "医药医疗",    # 创新药ETF
    "512880.SH": "金融地产",    # 证券ETF
    "512800.SH": "金融地产",    # 银行ETF
    "512690.SH": "消费",       # 酒ETF
    "159869.SZ": "消费",       # 游戏ETF
    "159755.SZ": "新能源",     # 电池ETF
    "515790.SH": "新能源",     # 光伏ETF
    "562500.SH": "先进制造",    # 机器人ETF
    "512660.SH": "先进制造",    # 军工ETF
    "159870.SZ": "材料",       # 化工ETF
    "512400.SH": "材料",       # 有色金属ETF
    "515220.SH": "材料",       # 煤炭ETF
    "516150.SH": "材料",       # 稀土ETF嘉实
    "512890.SH": "红利价值",    # 红利低波ETF
}


def load_selection() -> Tuple[List[str], Dict[str, str]]:
    """
    Returns (ordered_tickers, ticker_to_category).
    Use existing filtered file ordering if present; otherwise fallback to defaults.
    """
    if FILTERED_FILE.exists():
        df = pd.read_csv(FILTERED_FILE, encoding="utf-8-sig")
        ordered = df["Ticker"].tolist()
        # Preserve any manually tweaked categories in the existing file
        categories = {
            row["Ticker"]: row.get("超级行业组", DEFAULT_SELECTION.get(row["Ticker"], ""))
            for _, row in df.iterrows()
        }
        return ordered, categories

    ordered = list(DEFAULT_SELECTION.keys())
    return ordered, DEFAULT_SELECTION


def rebuild_filtered() -> None:
    if not FULL_FILE.exists():
        raise FileNotFoundError(f"Full ETF summary not found: {FULL_FILE}")

    ordered_tickers, category_map = load_selection()
    df_full = pd.read_csv(FULL_FILE, encoding="utf-8-sig")

    # Normalize tickers to ensure matching
    df_full["Ticker"] = df_full["Ticker"].astype(str).str.strip()

    df_filtered = df_full[df_full["Ticker"].isin(ordered_tickers)].copy()

    if df_filtered.empty:
        raise ValueError("No matching tickers found for curated ETF list.")

    # Attach super categories (fallback to empty string)
    df_filtered["超级行业组"] = df_filtered["Ticker"].map(category_map).fillna("")

    # Compute 成交/市值 if missing
    if "成交/市值" not in df_filtered.columns:
        df_filtered["成交/市值"] = df_filtered.apply(
            lambda row: round(row["成交额(亿)"] / row["总市值(亿)"] * 100, 2)
            if row.get("总市值(亿)") not in (0, None, "") else None,
            axis=1,
        )

    # Keep the curated order
    df_filtered["__order"] = pd.Categorical(df_filtered["Ticker"], categories=ordered_tickers, ordered=True)
    df_filtered = df_filtered.sort_values("__order").drop(columns="__order")

    df_filtered.to_csv(FILTERED_FILE, index=False, encoding="utf-8-sig")
    print(f"Saved curated ETF snapshot to {FILTERED_FILE} (rows={len(df_filtered)})")


def main() -> None:
    try:
        rebuild_filtered()
    except Exception as exc:  # pragma: no cover - script entrypoint
        print(f"[build_etf_filtered] failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
