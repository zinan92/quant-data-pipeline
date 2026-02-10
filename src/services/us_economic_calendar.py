"""
美国经济日历服务
提供重要经济数据发布日程（半静态 + 自动判断）
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, date

from src.utils.logging import get_logger

logger = get_logger(__name__)

# ── 2026 年重要经济事件日历 ──
# 基于历年发布节奏推算；FOMC日期来自美联储公布的2026日程
# 格式：(日期, 事件名, 事件英文名, 重要性 1-3)
CALENDAR_2026 = [
    # ── Jan 2026 ──
    ('2026-01-07', 'FOMC会议纪要 (12月)', 'FOMC Minutes Dec', 3),
    ('2026-01-10', '非农就业 (12月)', 'NFP Dec', 3),
    ('2026-01-14', 'PPI (12月)', 'PPI Dec', 2),
    ('2026-01-15', 'CPI (12月)', 'CPI Dec', 3),
    ('2026-01-29', 'FOMC利率决议', 'FOMC Rate Decision', 3),
    ('2026-01-30', 'GDP (Q4初值)', 'GDP Q4 Advance', 3),
    ('2026-01-30', 'PCE通胀 (12月)', 'PCE Dec', 3),
    # ── Feb 2026 ──
    ('2026-02-06', '非农就业 (1月)', 'NFP Jan', 3),
    ('2026-02-11', 'CPI (1月)', 'CPI Jan', 3),
    ('2026-02-12', 'PPI (1月)', 'PPI Jan', 2),
    ('2026-02-18', 'FOMC会议纪要', 'FOMC Minutes', 3),
    ('2026-02-27', 'GDP (Q4修正值)', 'GDP Q4 Second', 2),
    ('2026-02-27', 'PCE通胀 (1月)', 'PCE Jan', 3),
    # ── Mar 2026 ──
    ('2026-03-06', '非农就业 (2月)', 'NFP Feb', 3),
    ('2026-03-11', 'CPI (2月)', 'CPI Feb', 3),
    ('2026-03-12', 'PPI (2月)', 'PPI Feb', 2),
    ('2026-03-18', 'FOMC利率决议', 'FOMC Rate Decision', 3),
    ('2026-03-26', 'GDP (Q4终值)', 'GDP Q4 Final', 2),
    ('2026-03-27', 'PCE通胀 (2月)', 'PCE Feb', 3),
    # ── Apr 2026 ──
    ('2026-04-03', '非农就业 (3月)', 'NFP Mar', 3),
    ('2026-04-08', 'FOMC会议纪要', 'FOMC Minutes', 3),
    ('2026-04-14', 'CPI (3月)', 'CPI Mar', 3),
    ('2026-04-15', 'PPI (3月)', 'PPI Mar', 2),
    ('2026-04-29', 'GDP (Q1初值)', 'GDP Q1 Advance', 3),
    ('2026-04-30', 'PCE通胀 (3月)', 'PCE Mar', 3),
    # ── May 2026 ──
    ('2026-05-06', 'FOMC利率决议', 'FOMC Rate Decision', 3),
    ('2026-05-08', '非农就业 (4月)', 'NFP Apr', 3),
    ('2026-05-12', 'CPI (4月)', 'CPI Apr', 3),
    ('2026-05-13', 'PPI (4月)', 'PPI Apr', 2),
    ('2026-05-27', 'FOMC会议纪要', 'FOMC Minutes', 3),
    ('2026-05-28', 'GDP (Q1修正值)', 'GDP Q1 Second', 2),
    ('2026-05-29', 'PCE通胀 (4月)', 'PCE Apr', 3),
    # ── Jun 2026 ──
    ('2026-06-05', '非农就业 (5月)', 'NFP May', 3),
    ('2026-06-10', 'CPI (5月)', 'CPI May', 3),
    ('2026-06-11', 'PPI (5月)', 'PPI May', 2),
    ('2026-06-17', 'FOMC利率决议', 'FOMC Rate Decision', 3),
    ('2026-06-25', 'GDP (Q1终值)', 'GDP Q1 Final', 2),
    ('2026-06-26', 'PCE通胀 (5月)', 'PCE May', 3),
    # ── Jul 2026 ──
    ('2026-07-02', '非农就业 (6月)', 'NFP Jun', 3),
    ('2026-07-08', 'FOMC会议纪要', 'FOMC Minutes', 3),
    ('2026-07-14', 'CPI (6月)', 'CPI Jun', 3),
    ('2026-07-15', 'PPI (6月)', 'PPI Jun', 2),
    ('2026-07-29', 'FOMC利率决议', 'FOMC Rate Decision', 3),
    ('2026-07-30', 'GDP (Q2初值)', 'GDP Q2 Advance', 3),
    ('2026-07-31', 'PCE通胀 (6月)', 'PCE Jun', 3),
    # ── Aug 2026 ──
    ('2026-08-07', '非农就业 (7月)', 'NFP Jul', 3),
    ('2026-08-12', 'CPI (7月)', 'CPI Jul', 3),
    ('2026-08-13', 'PPI (7月)', 'PPI Jul', 2),
    ('2026-08-19', 'FOMC会议纪要', 'FOMC Minutes', 3),
    ('2026-08-27', 'GDP (Q2修正值)', 'GDP Q2 Second', 2),
    ('2026-08-28', 'PCE通胀 (7月)', 'PCE Jul', 3),
    # ── Sep 2026 ──
    ('2026-09-04', '非农就业 (8月)', 'NFP Aug', 3),
    ('2026-09-11', 'CPI (8月)', 'CPI Aug', 3),
    ('2026-09-14', 'PPI (8月)', 'PPI Aug', 2),
    ('2026-09-16', 'FOMC利率决议', 'FOMC Rate Decision', 3),
    ('2026-09-25', 'GDP (Q2终值)', 'GDP Q2 Final', 2),
    ('2026-09-25', 'PCE通胀 (8月)', 'PCE Aug', 3),
    # ── Oct 2026 ──
    ('2026-10-02', '非农就业 (9月)', 'NFP Sep', 3),
    ('2026-10-07', 'FOMC会议纪要', 'FOMC Minutes', 3),
    ('2026-10-13', 'CPI (9月)', 'CPI Sep', 3),
    ('2026-10-14', 'PPI (9月)', 'PPI Sep', 2),
    ('2026-10-28', 'FOMC利率决议', 'FOMC Rate Decision', 3),
    ('2026-10-29', 'GDP (Q3初值)', 'GDP Q3 Advance', 3),
    ('2026-10-30', 'PCE通胀 (9月)', 'PCE Sep', 3),
    # ── Nov 2026 ──
    ('2026-11-06', '非农就业 (10月)', 'NFP Oct', 3),
    ('2026-11-10', 'CPI (10月)', 'CPI Oct', 3),
    ('2026-11-12', 'PPI (10月)', 'PPI Oct', 2),
    ('2026-11-25', 'FOMC会议纪要', 'FOMC Minutes', 3),
    ('2026-11-25', 'GDP (Q3修正值)', 'GDP Q3 Second', 2),
    ('2026-11-25', 'PCE通胀 (10月)', 'PCE Oct', 3),
    # ── Dec 2026 ──
    ('2026-12-04', '非农就业 (11月)', 'NFP Nov', 3),
    ('2026-12-10', 'CPI (11月)', 'CPI Nov', 3),
    ('2026-12-11', 'PPI (11月)', 'PPI Nov', 2),
    ('2026-12-16', 'FOMC利率决议', 'FOMC Rate Decision', 3),
    ('2026-12-23', 'GDP (Q3终值)', 'GDP Q3 Final', 2),
    ('2026-12-23', 'PCE通胀 (11月)', 'PCE Nov', 3),
]


class USEconomicCalendar:
    """美国经济日历"""

    def __init__(self):
        self._events = self._parse_events()

    def _parse_events(self) -> List[Dict[str, Any]]:
        events = []
        for date_str, name_cn, name_en, importance in CALENDAR_2026:
            events.append({
                'date': date_str,
                'name': name_cn,
                'name_en': name_en,
                'importance': importance,  # 1=低, 2=中, 3=高
                'importance_label': {1: '低', 2: '中', 3: '高'}.get(importance, ''),
            })
        return events

    def get_upcoming(self, days: int = 14, importance_min: int = 1) -> List[Dict[str, Any]]:
        """
        获取未来 N 天内的经济事件

        Args:
            days: 往后看几天 (默认14)
            importance_min: 最低重要性 (1=全部, 2=中高, 3=仅高)
        """
        today = date.today()
        upcoming = []
        for evt in self._events:
            evt_date = date.fromisoformat(evt['date'])
            delta = (evt_date - today).days
            if 0 <= delta <= days and evt['importance'] >= importance_min:
                evt_copy = dict(evt)
                evt_copy['days_away'] = delta
                upcoming.append(evt_copy)
        return upcoming

    def get_all(self) -> List[Dict[str, Any]]:
        """返回全部事件"""
        return self._events


# 单例
_calendar: Optional[USEconomicCalendar] = None


def get_economic_calendar() -> USEconomicCalendar:
    global _calendar
    if _calendar is None:
        _calendar = USEconomicCalendar()
    return _calendar
