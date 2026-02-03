#!/usr/bin/env python3
"""
概念板块资金流简报 — Cron集成
===============================
为 HEARTBEAT.md 定时简报提供概念板块资金流分析数据。

用法:
  python scripts/concept_briefing_cron.py                # 盘中简报 (basic + compare)
  python scripts/concept_briefing_cron.py --full         # 收盘简报 (compare + trend)
  python scripts/concept_briefing_cron.py --rotation     # 含轮动检测
  python scripts/concept_briefing_cron.py --json         # JSON输出

设计:
  - 9:35~14:30 盘中: basic flow + yesterday compare
  - 15:05 收盘: full (compare + 5-day trend)
  - 自动检查 member cache 是否过期，过期则更新
  - 输出干净的格式化文本到 stdout，供 cron 调用方拼接进简报
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import from concept_flow_analysis
from scripts.concept_flow_analysis import (
    get_pro,
    load_member_cache,
    update_member_cache,
    fetch_concept_flow,
    save_flow_snapshot,
    load_flow_snapshot,
    compare_days,
    compute_multi_day_trend,
    format_analysis,
    get_prev_trade_date,
    FLOW_THRESHOLD,
    MEMBER_CACHE_FILE,
)


def ensure_member_cache(pro) -> dict:
    """
    Check member cache freshness. Auto-update if stale (not updated today).
    Returns the member cache dict.
    """
    cache = load_member_cache()
    today = datetime.now().strftime('%Y%m%d')

    if cache and cache.get('_updated') == today and cache.get('_count', 0) > 0:
        return cache

    # Cache is stale or empty — update
    print(f"🔄 Member cache stale (last: {cache.get('_updated', 'never')}), updating...",
          file=sys.stderr, flush=True)
    return update_member_cache(pro, force=True)


def get_latest_trade_date(pro) -> str:
    """Get the most recent trade date up to today."""
    today = datetime.now().strftime('%Y%m%d')
    cal = pro.trade_cal(exchange='SSE', start_date='20260101')
    open_dates = cal[
        (cal['is_open'] == 1) & (cal['cal_date'] <= today)
    ]['cal_date'].sort_values(ascending=False)
    return open_dates.iloc[0] if len(open_dates) > 0 else today


def is_market_hours() -> bool:
    """Check if we're within A-share market hours (9:30-15:00 CST)."""
    now = datetime.now()
    hour, minute = now.hour, now.minute
    t = hour * 100 + minute
    return 930 <= t <= 1500


def is_closing_briefing() -> bool:
    """Check if this is the 15:05 closing briefing slot."""
    now = datetime.now()
    hour, minute = now.hour, now.minute
    # Within the 15:00-15:15 window
    return hour == 15 and 0 <= minute <= 15


def run_briefing(mode: str = 'intraday', include_rotation: bool = False,
                 output_json: bool = False) -> str:
    """
    Run the concept flow briefing.

    Args:
        mode: 'intraday' (basic+compare) or 'full' (compare+trend)
        include_rotation: include intraday rotation signals
        output_json: return JSON instead of formatted text

    Returns:
        Formatted text or JSON string
    """
    pro = get_pro()

    # 1. Ensure member cache is fresh
    members = ensure_member_cache(pro)

    # 2. Determine trade date
    trade_date = get_latest_trade_date(pro)

    # 3. Fetch today's flow (try current date, fallback to previous trading day)
    today_df = load_flow_snapshot(trade_date)
    if today_df.empty:
        today_df = fetch_concept_flow(pro, trade_date, members)
        if not today_df.empty:
            save_flow_snapshot(today_df, trade_date)

    # If no data for today (e.g., market hasn't opened yet), try previous date
    if today_df.empty:
        fallback_date = get_prev_trade_date(pro, trade_date)
        if fallback_date:
            print(f"⚠️ {trade_date}无数据, 回退到{fallback_date}", file=sys.stderr, flush=True)
            trade_date = fallback_date
            today_df = load_flow_snapshot(trade_date)
            if today_df.empty:
                today_df = fetch_concept_flow(pro, trade_date, members)
                if not today_df.empty:
                    save_flow_snapshot(today_df, trade_date)

    if today_df.empty:
        return f"⚠️ 无法获取 {trade_date} 概念资金流数据"

    # 4. Day-over-day comparison (always do this)
    comparisons = None
    prev_date = get_prev_trade_date(pro, trade_date)
    if prev_date:
        yesterday_df = load_flow_snapshot(prev_date)
        if yesterday_df.empty:
            yesterday_df = fetch_concept_flow(pro, prev_date, members)
            if not yesterday_df.empty:
                save_flow_snapshot(yesterday_df, prev_date)

        if not yesterday_df.empty:
            comparisons = compare_days(today_df, yesterday_df)

    # 5. Multi-day trend (only for closing briefing / full mode)
    trend_df = None
    if mode == 'full':
        trend_df = compute_multi_day_trend(pro, members, trade_date, days=5)

    # 6. Rotation signals (optional)
    rotation_text = ''
    if include_rotation:
        rotation_text = get_rotation_summary()

    # 7. Format output
    if output_json:
        output = {
            'trade_date': trade_date,
            'mode': mode,
            'timestamp': datetime.now().isoformat(),
            'threshold': FLOW_THRESHOLD,
            'total_concepts': len(today_df),
            'passed_threshold': int((today_df['net_inflow'] >= FLOW_THRESHOLD).sum()),
            'flow_data': today_df.head(30).to_dict(orient='records'),
        }
        if comparisons:
            # Top 20 comparisons only
            output['comparisons'] = [c for c in comparisons if c['today_flow'] >= FLOW_THRESHOLD][:20]
        if trend_df is not None and not trend_df.empty:
            output['trends'] = trend_df.head(20).to_dict(orient='records')
        return json.dumps(output, ensure_ascii=False, indent=2)

    # Formatted text
    now_str = datetime.now().strftime('%H:%M')
    label = f"{trade_date} {'收盘' if mode == 'full' else now_str}"

    text = format_analysis(
        today_df, comparisons, trend_df,
        trade_date=trade_date,
        label=label,
    )

    if rotation_text:
        text += '\n\n' + rotation_text

    return text


def get_rotation_summary() -> str:
    """Fetch rotation signals from the local API (if available)."""
    try:
        import requests
        r = requests.get('http://127.0.0.1:8000/api/rotation/signals', timeout=5)
        if r.status_code != 200:
            return ''

        data = r.json()
        inflow = data.get('inflow_accelerating', [])
        outflow = data.get('outflow_accelerating', [])

        if not inflow and not outflow:
            return ''

        lines = ['**🔄 板块轮动信号:**']
        if inflow:
            lines.append('资金加速流入:')
            for s in inflow[:5]:
                lines.append(f"  • {s['name']} 流入{s.get('net_inflow', 0):.0f}亿 "
                             f"({s.get('pct_change', 0):+.2f}%) "
                             f"强度{s.get('signal_strength', 0):.0f}")

        if outflow:
            top_outflow = sorted(outflow, key=lambda x: x.get('signal_strength', 0), reverse=True)[:3]
            lines.append('资金加速流出:')
            for s in top_outflow:
                lines.append(f"  • {s['name']} ({s.get('pct_change', 0):+.2f}%) "
                             f"强度{s.get('signal_strength', 0):.0f}")

        return '\n'.join(lines)
    except Exception:
        return ''


def main():
    parser = argparse.ArgumentParser(description='概念板块资金流简报 (Cron集成)')
    parser.add_argument('--full', action='store_true',
                        help='完整分析模式 (收盘用, 含5日趋势)')
    parser.add_argument('--auto', action='store_true',
                        help='自动判断: 15:05用full, 其他用intraday')
    parser.add_argument('--rotation', action='store_true',
                        help='包含轮动信号')
    parser.add_argument('--json', action='store_true',
                        help='JSON格式输出')
    args = parser.parse_args()

    # Auto mode: detect closing vs intraday
    if args.auto:
        mode = 'full' if is_closing_briefing() else 'intraday'
    elif args.full:
        mode = 'full'
    else:
        mode = 'intraday'

    try:
        result = run_briefing(
            mode=mode,
            include_rotation=args.rotation,
            output_json=args.json,
        )
        print(result)
        return 0
    except Exception as e:
        print(f"❌ 概念简报失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
