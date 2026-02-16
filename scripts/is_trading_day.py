#!/usr/bin/env python3
"""Check if today is an A-share trading day. Exit 0 = trading day, exit 1 = not."""

import sys
import datetime

# 2026 A-share holidays (SSE official)
# Format: (month, day) for non-weekend holidays
HOLIDAYS_2026 = {
    # 元旦 1/1-1/3
    (1, 1), (1, 2), (1, 3),
    # 春节 2/15-2/23 (includes weekends)
    (2, 15), (2, 16), (2, 17), (2, 18), (2, 19), (2, 20), (2, 21), (2, 22), (2, 23),
    # 清明节 4/4-4/6
    (4, 4), (4, 5), (4, 6),
    # 劳动节 5/1-5/5
    (5, 1), (5, 2), (5, 3), (5, 4), (5, 5),
    # 端午节 5/31-6/2
    (5, 31), (6, 1), (6, 2),
    # 中秋节 9/25-9/27
    (9, 25), (9, 26), (9, 27),
    # 国庆节 10/1-10/8
    (10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7), (10, 8),
}

# 调休补班日（周末但要开市）
EXTRA_TRADING_DAYS_2026 = {
    (2, 14),  # 春节调休
    (2, 28),  # 春节调休 — actually SSE says this is 周末休市, so NOT a trading day
}
# Correction: 2/14 (Sat) and 2/28 (Sat) are both weekend 休市 per SSE announcement
# Remove them
EXTRA_TRADING_DAYS_2026 = set()


def is_trading_day(d: datetime.date = None) -> bool:
    if d is None:
        d = datetime.date.today()
    
    # Weekend check
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        if (d.month, d.day) in EXTRA_TRADING_DAYS_2026:
            return True
        return False
    
    # Holiday check
    if (d.month, d.day) in HOLIDAYS_2026:
        return False
    
    return True


if __name__ == "__main__":
    today = datetime.date.today()
    trading = is_trading_day(today)
    if trading:
        print(f"{today} is a trading day ✅")
        sys.exit(0)
    else:
        print(f"{today} is NOT a trading day (holiday/weekend) ❌")
        sys.exit(1)
