#!/usr/bin/env python3
"""
概念板块资金流分析器 v2
=============================
数据源: Tushare (moneyflow_ths + ths_member + ths_daily)
口径: Tushare主力 ≈ 同花顺 × 0.6
门槛: ≥30亿净流入

功能:
1. 概念板块成分股缓存 (board_mapping表，每天更新)
2. 概念板块资金流聚合 (个股moneyflow → 概念聚合)
3. 日度对比 (yesterday vs today，加速/减速判断)
4. 多日趋势 (3日/5日累计，趋势方向)
5. 盘中30分钟轮动快照对比 (价格变动排名轮动检测)

用法:
  python scripts/concept_flow_analysis.py                    # 完整分析 (今日)
  python scripts/concept_flow_analysis.py --date 20260203    # 指定日期
  python scripts/concept_flow_analysis.py --update-members   # 仅更新成分股缓存
  python scripts/concept_flow_analysis.py --trend            # 含多日趋势
  python scripts/concept_flow_analysis.py --json             # JSON输出 (供API/cron使用)
  python scripts/concept_flow_analysis.py --rotation         # 盘中轮动检测
  python scripts/concept_flow_analysis.py --rotation --snapshot  # 保存轮动快照
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import tushare as ts
import pandas as pd
from src.config import get_settings

# ============================================================
# Configuration
# ============================================================
FLOW_THRESHOLD = 30  # 亿元, 概念板块资金净流入门槛
TUSHARE_THS_COEFF = 0.6  # Tushare ≈ 同花顺 × 0.6
MEMBER_CACHE_FILE = project_root / "data" / "cache" / "concept_members.json"
FLOW_SNAPSHOT_DIR = project_root / "data" / "snapshots" / "concept_flow"
INTRADAY_SNAPSHOT_DIR = project_root / "data" / "snapshots" / "intraday"
ANALYSIS_OUTPUT_DIR = project_root / "data" / "analysis"

# Rotation detection thresholds
ROTATION_RANK_JUMP = 20       # 排名跳升≥20位视为显著轮动
ROTATION_TOP_N = 50           # 只关注排名前50的概念

# Ensure dirs exist
MEMBER_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
FLOW_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
INTRADAY_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_pro():
    settings = get_settings()
    return ts.pro_api(settings.tushare_token)


# ============================================================
# 1. Concept Membership Cache
# ============================================================
def load_member_cache() -> dict:
    """Load cached concept → stock mapping"""
    if MEMBER_CACHE_FILE.exists():
        with open(MEMBER_CACHE_FILE, 'r') as f:
            data = json.load(f)
        return data
    return {}


def save_member_cache(data: dict):
    """Save concept → stock mapping to cache"""
    with open(MEMBER_CACHE_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_member_cache(pro, force=False) -> dict:
    """
    Fetch concept members from Tushare and cache.
    Takes ~80 seconds for 395 concepts. Only run once daily.
    """
    cache = load_member_cache()
    today = datetime.now().strftime('%Y%m%d')

    if not force and cache.get('_updated') == today:
        print(f"✅ 成分股缓存已是最新 ({today}), 跳过更新", flush=True)
        return cache

    print(f"🔄 更新概念板块成分股缓存...", flush=True)

    # Get all concept boards
    df_concepts = pro.ths_index(exchange='A', type='N')
    concept_codes = df_concepts['ts_code'].tolist()
    name_map = dict(zip(df_concepts['ts_code'], df_concepts['name']))

    members = {}
    errors = 0
    total = len(concept_codes)

    for i, code in enumerate(concept_codes):
        try:
            df = pro.ths_member(ts_code=code)
            if df is not None and len(df) > 0:
                members[code] = {
                    'name': name_map.get(code, ''),
                    'stocks': df['con_code'].tolist()
                }
            time.sleep(0.12)
        except Exception:
            errors += 1
            time.sleep(0.5)

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{total}] 失败{errors}", flush=True)

    members['_updated'] = today
    members['_count'] = len([k for k in members if not k.startswith('_')])
    save_member_cache(members)

    print(f"✅ 成分股缓存更新完成: {members['_count']}个概念, 失败{errors}", flush=True)
    return members


# ============================================================
# 2. Concept Flow Aggregation
# ============================================================
def fetch_concept_flow(pro, trade_date: str, members: dict) -> pd.DataFrame:
    """
    Aggregate stock-level moneyflow to concept-level.
    
    Returns DataFrame with columns:
        ts_code, name, net_inflow (亿), pct_change, member_count, vol
    """
    # Get stock moneyflow (all stocks, one call)
    df_flow = pro.moneyflow_ths(trade_date=trade_date)
    if df_flow is None or len(df_flow) == 0:
        print(f"⚠️ 无个股资金流数据: {trade_date}", flush=True)
        return pd.DataFrame()
    
    flow_map = dict(zip(df_flow['ts_code'], df_flow['net_amount']))  # 万元

    # Get concept daily prices
    df_daily = pro.ths_daily(trade_date=trade_date)
    if df_daily is None or len(df_daily) == 0:
        print(f"⚠️ 无概念日线数据: {trade_date}", flush=True)
        return pd.DataFrame()

    # Get concept list for filtering
    df_concepts = pro.ths_index(exchange='A', type='N')
    concept_codes = set(df_concepts['ts_code'])
    name_map_ts = dict(zip(df_concepts['ts_code'], df_concepts['name']))

    # Filter daily to concepts only
    df_cd = df_daily[df_daily['ts_code'].isin(concept_codes)].copy()

    # Aggregate moneyflow by concept
    results = []
    for _, row in df_cd.iterrows():
        code = row['ts_code']
        member_info = members.get(code)
        if not member_info or isinstance(member_info, str):
            continue

        stocks = member_info.get('stocks', [])
        total_net = sum(flow_map.get(s, 0) for s in stocks) / 10000  # 万元 → 亿元

        results.append({
            'ts_code': code,
            'name': member_info.get('name', name_map_ts.get(code, '')),
            'net_inflow': round(total_net, 1),
            'pct_change': round(row['pct_change'], 2),
            'member_count': len(stocks),
            'vol': row.get('vol', 0),
            'trade_date': trade_date,
        })

    df = pd.DataFrame(results)
    if len(df) > 0:
        df = df.sort_values('net_inflow', ascending=False).reset_index(drop=True)
    return df


def save_flow_snapshot(df: pd.DataFrame, trade_date: str, label: str = "close"):
    """Save a flow snapshot to disk for later comparison"""
    filepath = FLOW_SNAPSHOT_DIR / f"{trade_date}_{label}.json"
    records = df.to_dict(orient='records')
    with open(filepath, 'w') as f:
        json.dump({
            'trade_date': trade_date,
            'label': label,
            'timestamp': datetime.now().isoformat(),
            'count': len(records),
            'data': records
        }, f, ensure_ascii=False, indent=2)
    return filepath


def load_flow_snapshot(trade_date: str, label: str = "close") -> pd.DataFrame:
    """Load a previously saved snapshot"""
    filepath = FLOW_SNAPSHOT_DIR / f"{trade_date}_{label}.json"
    if not filepath.exists():
        return pd.DataFrame()
    with open(filepath, 'r') as f:
        data = json.load(f)
    return pd.DataFrame(data['data'])


# ============================================================
# 3. Day-over-Day Comparison
# ============================================================
def compare_days(today_df: pd.DataFrame, yesterday_df: pd.DataFrame) -> list[dict]:
    """
    Compare two days of concept flow data.
    Detect acceleration/deceleration in moneyflow.
    
    Returns list of dicts with:
        name, today_flow, yesterday_flow, flow_delta, flow_trend,
        today_pct, yesterday_pct, pct_delta
    """
    if today_df.empty or yesterday_df.empty:
        return []

    # Merge on ts_code
    merged = today_df.merge(
        yesterday_df[['ts_code', 'net_inflow', 'pct_change']],
        on='ts_code',
        how='left',
        suffixes=('_today', '_yesterday')
    )

    comparisons = []
    for _, row in merged.iterrows():
        today_flow = row.get('net_inflow_today', row.get('net_inflow', 0))
        yesterday_flow = row.get('net_inflow_yesterday', 0)

        if pd.isna(yesterday_flow):
            yesterday_flow = 0

        flow_delta = today_flow - yesterday_flow
        today_pct = row.get('pct_change_today', row.get('pct_change', 0))
        yesterday_pct = row.get('pct_change_yesterday', 0)

        if pd.isna(yesterday_pct):
            yesterday_pct = 0

        # Determine trend
        if today_flow >= FLOW_THRESHOLD:
            if yesterday_flow > 0 and today_flow > yesterday_flow * 1.3:
                trend = "🚀加速"
            elif yesterday_flow > 0 and today_flow > yesterday_flow:
                trend = "📈增长"
            elif yesterday_flow <= 0 and today_flow > 0:
                trend = "🔄转正"
            elif yesterday_flow > 0 and today_flow < yesterday_flow * 0.7:
                trend = "⚠️减速"
            elif yesterday_flow > 0:
                trend = "➡️持平"
            else:
                trend = "🆕新进"
        else:
            if yesterday_flow >= FLOW_THRESHOLD and today_flow < FLOW_THRESHOLD:
                trend = "📉跌出"
            else:
                trend = ""

        comparisons.append({
            'ts_code': row['ts_code'],
            'name': row['name'],
            'today_flow': today_flow,
            'yesterday_flow': yesterday_flow,
            'flow_delta': round(flow_delta, 1),
            'trend': trend,
            'today_pct': today_pct,
            'yesterday_pct': yesterday_pct,
            'member_count': row.get('member_count', 0),
        })

    # Sort by today's flow
    comparisons.sort(key=lambda x: x['today_flow'], reverse=True)
    return comparisons


# ============================================================
# 4. Multi-day Trend (3-day / 5-day)
# ============================================================
def compute_multi_day_trend(pro, members: dict, target_date: str, days: int = 5) -> pd.DataFrame:
    """
    Compute multi-day flow trend for concept boards.
    Fetches data for last N trading days and computes:
    - Cumulative flow
    - Trend direction (accelerating/decelerating/stable)
    - Consecutive days of inflow/outflow
    """
    # Get trading calendar
    cal = pro.trade_cal(exchange='SSE', start_date='20260101', end_date=target_date)
    trade_dates = cal[cal['is_open'] == 1]['cal_date'].sort_values(ascending=False).head(days + 1).tolist()
    
    if len(trade_dates) < 2:
        return pd.DataFrame()

    # Load or fetch data for each date
    all_data = {}
    for date in trade_dates[:days]:
        # Try loading snapshot first
        df = load_flow_snapshot(date)
        if df.empty:
            print(f"  📥 获取 {date} 数据...", flush=True)
            df = fetch_concept_flow(pro, date, members)
            if not df.empty:
                save_flow_snapshot(df, date)
            time.sleep(0.5)
        if not df.empty:
            all_data[date] = df

    if len(all_data) < 2:
        return pd.DataFrame()

    # Build trend for each concept
    dates_sorted = sorted(all_data.keys())
    all_concepts = set()
    for df in all_data.values():
        all_concepts.update(df['ts_code'].tolist())

    trends = []
    for code in all_concepts:
        daily_flows = []
        daily_pcts = []
        name = ''
        member_count = 0

        for date in dates_sorted:
            df = all_data[date]
            row = df[df['ts_code'] == code]
            if len(row) > 0:
                daily_flows.append(row.iloc[0]['net_inflow'])
                daily_pcts.append(row.iloc[0]['pct_change'])
                name = row.iloc[0]['name']
                member_count = row.iloc[0].get('member_count', 0)
            else:
                daily_flows.append(0)
                daily_pcts.append(0)

        cum_flow = sum(daily_flows)
        avg_flow = cum_flow / len(daily_flows) if daily_flows else 0
        cum_pct = sum(daily_pcts)

        # Trend direction: compare recent half vs older half
        mid = len(daily_flows) // 2
        recent_avg = sum(daily_flows[mid:]) / max(len(daily_flows[mid:]), 1)
        older_avg = sum(daily_flows[:mid]) / max(len(daily_flows[:mid]), 1)

        if recent_avg > older_avg * 1.3 and cum_flow > 0:
            direction = "📈加速"
        elif recent_avg < older_avg * 0.7 and older_avg > 0:
            direction = "📉减速"
        elif cum_flow > 0:
            direction = "➡️稳定"
        else:
            direction = "🔻流出"

        # Consecutive inflow days
        consec = 0
        for f in reversed(daily_flows):
            if f > 0:
                consec += 1
            else:
                break

        trends.append({
            'ts_code': code,
            'name': name,
            'cum_flow': round(cum_flow, 1),
            'avg_flow': round(avg_flow, 1),
            'cum_pct': round(cum_pct, 2),
            'direction': direction,
            'consec_inflow_days': consec,
            'daily_flows': [round(f, 1) for f in daily_flows],
            'dates': dates_sorted,
            'member_count': member_count,
        })

    df_trend = pd.DataFrame(trends)
    df_trend = df_trend.sort_values('cum_flow', ascending=False).reset_index(drop=True)
    return df_trend


# ============================================================
# 5. Intraday Rotation Detection (30-min snapshots)
# ============================================================
# NOTE: Tushare moneyflow is daily-only. Intraday rotation uses
# PRICE CHANGE rankings from ths_daily (概念指数涨跌幅排名).
# Also tries the local API concept-monitor for realtime data.

def fetch_concept_price_rankings(pro, trade_date: str = None) -> pd.DataFrame:
    """
    Get concept board price change rankings.
    Uses ths_daily for all concept boards.
    
    Returns DataFrame: ts_code, name, pct_change, close, vol, rank
    """
    if trade_date is None:
        trade_date = datetime.now().strftime('%Y%m%d')

    # Try local API first (realtime during market hours)
    try:
        import requests
        r = requests.get(
            'http://127.0.0.1:8000/api/concept-monitor/top',
            params={'limit': 500},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            items = data.get('data', [])
            # Filter to concept boards only (exclude industry boards)
            concepts = [x for x in items if x.get('boardType') == '概念']
            if len(concepts) >= 10:
                df = pd.DataFrame(concepts)
                df = df.rename(columns={'code': 'ts_code', 'changePct': 'pct_change'})
                df = df.sort_values('pct_change', ascending=False).reset_index(drop=True)
                df['rank'] = range(1, len(df) + 1)
                return df[['ts_code', 'name', 'pct_change', 'rank',
                           'volume', 'upCount', 'downCount', 'limitUp']]
    except Exception:
        pass

    # Fallback: Tushare ths_daily (all concept boards)
    df_daily = pro.ths_daily(trade_date=trade_date)
    if df_daily is None or len(df_daily) == 0:
        return pd.DataFrame()

    # Filter to concept boards (N type)
    df_concepts = pro.ths_index(exchange='A', type='N')
    concept_codes = set(df_concepts['ts_code'])
    name_map = dict(zip(df_concepts['ts_code'], df_concepts['name']))

    df = df_daily[df_daily['ts_code'].isin(concept_codes)].copy()
    df['name'] = df['ts_code'].map(name_map)
    df = df.sort_values('pct_change', ascending=False).reset_index(drop=True)
    df['rank'] = range(1, len(df) + 1)
    return df[['ts_code', 'name', 'pct_change', 'close', 'vol', 'rank']]


def save_intraday_snapshot(df: pd.DataFrame, label: str = None) -> Path:
    """
    Save an intraday price ranking snapshot.
    Label format: YYYYMMDD_HHMM (e.g., 20260203_1030)
    """
    if label is None:
        label = datetime.now().strftime('%Y%m%d_%H%M')

    filepath = INTRADAY_SNAPSHOT_DIR / f"rotation_{label}.json"
    records = df.to_dict(orient='records')
    with open(filepath, 'w') as f:
        json.dump({
            'label': label,
            'timestamp': datetime.now().isoformat(),
            'count': len(records),
            'data': records,
        }, f, ensure_ascii=False, indent=2)
    return filepath


def load_intraday_snapshot(label: str) -> pd.DataFrame:
    """Load a previously saved intraday snapshot."""
    filepath = INTRADAY_SNAPSHOT_DIR / f"rotation_{label}.json"
    if not filepath.exists():
        return pd.DataFrame()
    with open(filepath, 'r') as f:
        data = json.load(f)
    return pd.DataFrame(data['data'])


def get_previous_snapshot_label() -> str | None:
    """Find the most recent intraday snapshot for today."""
    today_prefix = datetime.now().strftime('%Y%m%d')
    snapshots = sorted(INTRADAY_SNAPSHOT_DIR.glob(f"rotation_{today_prefix}_*.json"),
                       reverse=True)
    if not snapshots:
        return None
    # Extract label from filename: rotation_YYYYMMDD_HHMM.json → YYYYMMDD_HHMM
    return snapshots[0].stem.replace('rotation_', '')


def detect_rotation(current_df: pd.DataFrame, previous_df: pd.DataFrame,
                    top_n: int = ROTATION_TOP_N,
                    rank_jump: int = ROTATION_RANK_JUMP) -> dict:
    """
    Compare two snapshots and detect rotation signals.
    
    A rotation signal is a concept that jumped significantly in rank,
    indicating capital is rotating into/out of it.
    
    Args:
        current_df: Current snapshot with 'ts_code', 'name', 'pct_change', 'rank'
        previous_df: Previous snapshot with same columns
        top_n: Only consider concepts in current top N
        rank_jump: Minimum rank improvement to flag as rotation
        
    Returns:
        dict with 'rising' (moved up), 'falling' (moved down), 'new_entrants', 'summary'
    """
    if current_df.empty or previous_df.empty:
        return {'rising': [], 'falling': [], 'new_entrants': [], 'summary': {}}

    # Build rank maps
    curr_ranks = dict(zip(current_df['ts_code'], current_df['rank']))
    prev_ranks = dict(zip(previous_df['ts_code'], previous_df['rank']))
    curr_names = dict(zip(current_df['ts_code'], current_df['name']))
    curr_pcts = dict(zip(current_df['ts_code'], current_df['pct_change']))
    prev_pcts = dict(zip(previous_df['ts_code'], previous_df['pct_change']))

    rising = []
    falling = []
    new_entrants = []

    for code, curr_rank in curr_ranks.items():
        if curr_rank > top_n:
            continue

        name = curr_names.get(code, '')
        curr_pct = curr_pcts.get(code, 0)
        prev_pct = prev_pcts.get(code, 0)

        if code not in prev_ranks:
            # New entrant to the rankings
            new_entrants.append({
                'ts_code': code,
                'name': name,
                'rank': curr_rank,
                'pct_change': curr_pct,
            })
            continue

        prev_rank = prev_ranks[code]
        rank_delta = prev_rank - curr_rank  # positive = moved up

        if rank_delta >= rank_jump:
            rising.append({
                'ts_code': code,
                'name': name,
                'prev_rank': prev_rank,
                'curr_rank': curr_rank,
                'rank_delta': rank_delta,
                'pct_change': curr_pct,
                'prev_pct': prev_pct,
                'pct_delta': round(curr_pct - prev_pct, 2),
            })
        elif rank_delta <= -rank_jump:
            falling.append({
                'ts_code': code,
                'name': name,
                'prev_rank': prev_rank,
                'curr_rank': curr_rank,
                'rank_delta': rank_delta,
                'pct_change': curr_pct,
                'prev_pct': prev_pct,
                'pct_delta': round(curr_pct - prev_pct, 2),
            })

    # Sort by magnitude of rank change
    rising.sort(key=lambda x: x['rank_delta'], reverse=True)
    falling.sort(key=lambda x: x['rank_delta'])

    return {
        'rising': rising,
        'falling': falling,
        'new_entrants': new_entrants,
        'summary': {
            'current_snapshot_count': len(current_df),
            'previous_snapshot_count': len(previous_df),
            'rising_count': len(rising),
            'falling_count': len(falling),
            'new_entrant_count': len(new_entrants),
        },
    }


def format_rotation(rotation: dict, label: str = '') -> str:
    """Format rotation detection results for Telegram."""
    lines = []
    now_str = label or datetime.now().strftime('%H:%M')
    lines.append(f"🔄 **盘中轮动检测** ({now_str})")

    rising = rotation.get('rising', [])
    falling = rotation.get('falling', [])
    new_entrants = rotation.get('new_entrants', [])
    summary = rotation.get('summary', {})

    if not rising and not falling and not new_entrants:
        lines.append("无显著轮动信号")
        return '\n'.join(lines)

    lines.append(f"排名跳升≥{ROTATION_RANK_JUMP}位 | "
                 f"🔺{summary.get('rising_count', 0)} "
                 f"🔻{summary.get('falling_count', 0)} "
                 f"🆕{summary.get('new_entrant_count', 0)}")
    lines.append("")

    if rising:
        lines.append("**🔺 资金轮入（排名大幅上升）:**")
        for r in rising[:8]:
            lines.append(f"• {r['name']} "
                         f"#{r['prev_rank']}→#{r['curr_rank']} (↑{r['rank_delta']}位) "
                         f"{r['pct_change']:+.2f}%")
        lines.append("")

    if falling:
        lines.append("**🔻 资金轮出（排名大幅下降）:**")
        for f in falling[:5]:
            lines.append(f"• {f['name']} "
                         f"#{f['prev_rank']}→#{f['curr_rank']} (↓{abs(f['rank_delta'])}位) "
                         f"{f['pct_change']:+.2f}%")
        lines.append("")

    if new_entrants:
        top_new = sorted(new_entrants, key=lambda x: x['rank'])[:5]
        lines.append("**🆕 新进前50:**")
        for n in top_new:
            lines.append(f"• {n['name']} #{n['rank']} ({n['pct_change']:+.2f}%)")
        lines.append("")

    return '\n'.join(lines)


def run_rotation_detection(pro, save_snapshot: bool = True) -> tuple[dict, str]:
    """
    Run a full rotation detection cycle:
    1. Fetch current concept price rankings
    2. Load previous snapshot (if any)
    3. Compare and detect rotation
    4. Save current snapshot
    
    Returns: (rotation_dict, formatted_text)
    """
    # 1. Get current rankings
    current_df = fetch_concept_price_rankings(pro)
    if current_df.empty:
        return {}, "⚠️ 无法获取概念排名数据"

    # 2. Load previous snapshot
    prev_label = get_previous_snapshot_label()
    previous_df = pd.DataFrame()
    if prev_label:
        previous_df = load_intraday_snapshot(prev_label)

    # 3. Save current snapshot
    current_label = datetime.now().strftime('%Y%m%d_%H%M')
    if save_snapshot:
        save_intraday_snapshot(current_df, current_label)

    # 4. Detect rotation
    if previous_df.empty:
        return {
            'rising': [], 'falling': [], 'new_entrants': [],
            'summary': {'note': '首次快照，无对比数据'},
        }, f"📸 首次轮动快照已保存 ({current_label}), 共{len(current_df)}个概念"

    rotation = detect_rotation(current_df, previous_df)
    text = format_rotation(rotation, label=f"{prev_label.split('_')[-1]}→{current_label.split('_')[-1]}")
    return rotation, text


# ============================================================
# 6. Formatted Output
# ============================================================
def format_analysis(
    flow_df: pd.DataFrame,
    comparisons: list[dict] = None,
    trend_df: pd.DataFrame = None,
    trade_date: str = "",
    label: str = ""
) -> str:
    """Generate formatted analysis text for Telegram"""
    lines = []
    
    if not label:
        label = trade_date

    # Header
    passed = flow_df[flow_df['net_inflow'] >= FLOW_THRESHOLD] if not flow_df.empty else pd.DataFrame()
    total = len(flow_df)
    lines.append(f"📊 **概念板块资金流分析** ({label})")
    lines.append(f"Tushare聚合 | ≥{FLOW_THRESHOLD}亿门槛 | **{len(passed)}/{total}** 通过")
    lines.append("")

    # === Section 1: Top by flow ===
    # Filter out index-like concepts (融资融券, 深股通, etc.)
    index_keywords = ['融资融券', '深股通', '沪股通', '成份股', '样本股', '中特估', '同花顺漂亮', '同花顺果', '同花顺出海']
    
    def is_thematic(name):
        return not any(kw in name for kw in index_keywords)
    
    thematic = passed[passed['name'].apply(is_thematic)] if not passed.empty else pd.DataFrame()
    
    lines.append(f"**🔥 资金 TOP 20（主题概念）:**")
    for i, (_, row) in enumerate(thematic.head(20).iterrows(), 1):
        lines.append(f"{i}. **{row['name']}** +{row['net_inflow']:.0f}亿 | {row['pct_change']:+.2f}% | {row['member_count']}只")
    lines.append("")

    # === Section 2: 涨幅+资金双强 ===
    if not passed.empty:
        dual_strong = passed[(passed['pct_change'] >= 4) & passed['name'].apply(is_thematic)]
        if not dual_strong.empty:
            dual_strong = dual_strong.sort_values('pct_change', ascending=False)
            lines.append("**🎯 涨幅+资金双强（涨幅>4% 且 ≥30亿）:**")
            for _, row in dual_strong.iterrows():
                lines.append(f"• {row['name']} {row['pct_change']:+.2f}% / {row['net_inflow']:.0f}亿")
            lines.append("")

    # === Section 3: Day-over-Day Comparison ===
    if comparisons:
        # Show accelerating concepts
        accel = [c for c in comparisons if '加速' in c.get('trend', '') and c['today_flow'] >= FLOW_THRESHOLD]
        if accel:
            lines.append("**🚀 资金加速流入（今日>昨日×1.3）:**")
            for c in accel[:10]:
                lines.append(f"• {c['name']}: {c['yesterday_flow']:+.0f}亿→{c['today_flow']:+.0f}亿 ({c['flow_delta']:+.0f})")
            lines.append("")

        # Show reversals (turned positive)
        turns = [c for c in comparisons if '转正' in c.get('trend', '')]
        if turns:
            lines.append("**🔄 资金转正（昨日流出→今日流入）:**")
            for c in turns[:5]:
                lines.append(f"• {c['name']}: {c['yesterday_flow']:+.0f}亿→{c['today_flow']:+.0f}亿")
            lines.append("")

        # Show decelerating
        decel = [c for c in comparisons if '减速' in c.get('trend', '') and c['today_flow'] >= FLOW_THRESHOLD]
        if decel:
            lines.append("**⚠️ 资金减速（今日<昨日×0.7）:**")
            for c in decel[:5]:
                lines.append(f"• {c['name']}: {c['yesterday_flow']:+.0f}亿→{c['today_flow']:+.0f}亿 ({c['flow_delta']:+.0f})")
            lines.append("")

    # === Section 4: Multi-day Trend ===
    if trend_df is not None and not trend_df.empty:
        n_days = len(trend_df.iloc[0]['dates']) if len(trend_df) > 0 else 0
        thematic_trends = trend_df[trend_df['name'].apply(is_thematic)]

        # 4a: Accelerating concepts (recent half > older half by 30%+)
        accel_trends = thematic_trends[
            thematic_trends['direction'].str.contains('加速')
        ].nlargest(10, 'cum_flow')
        
        if not accel_trends.empty:
            lines.append(f"**📊 {n_days}日趋势 — 资金加速:**")
            for _, row in accel_trends.iterrows():
                flow_str = '→'.join([f"{f:+.0f}" for f in row['daily_flows']])
                lines.append(f"• {row['name']} {row['direction']} 累计{row['cum_flow']:+.0f}亿 ({flow_str})")
            lines.append("")

        # 4b: Sustained inflow (consecutive days >= 2)
        sustained = thematic_trends[
            (thematic_trends['consec_inflow_days'] >= 2) &
            (thematic_trends['cum_flow'] > 0)
        ].nlargest(10, 'cum_flow')

        if not sustained.empty:
            lines.append(f"**🔄 连续流入（≥2日）:**")
            for _, row in sustained.iterrows():
                flow_str = '→'.join([f"{f:+.0f}" for f in row['daily_flows']])
                lines.append(f"• {row['name']} 连续{row['consec_inflow_days']}日 累计{row['cum_flow']:+.0f}亿 ({flow_str})")
            lines.append("")

        # 4c: Decelerating - were strong, now weakening
        decel_trends = thematic_trends[
            thematic_trends['direction'].str.contains('减速')
        ].nlargest(5, 'cum_flow')

        if not decel_trends.empty:
            lines.append(f"**⚠️ {n_days}日趋势 — 资金减速:**")
            for _, row in decel_trends.iterrows():
                flow_str = '→'.join([f"{f:+.0f}" for f in row['daily_flows']])
                lines.append(f"• {row['name']} {row['direction']} 累计{row['cum_flow']:+.0f}亿 ({flow_str})")
            lines.append("")

    # === Section 5: Net outflow ===
    outflow = flow_df[flow_df['net_inflow'] < 0] if not flow_df.empty else pd.DataFrame()
    if not outflow.empty:
        lines.append(f"**🔻 净流出 ({len(outflow)}个):**")
        for _, row in outflow.head(5).iterrows():
            lines.append(f"• {row['name']} {row['net_inflow']:+.1f}亿 ({row['pct_change']:+.2f}%)")
        lines.append("")

    # === Section 6: Summary stats ===
    if not flow_df.empty:
        total_pass_flow = passed['net_inflow'].sum() if not passed.empty else 0
        n_outflow = len(outflow)
        lines.append(f"📈 **汇总:** {len(passed)}概念过门槛 | 净流出{n_outflow}个 | 过门槛总计{total_pass_flow:.0f}亿")

    return '\n'.join(lines)


# ============================================================
# 6. Main Logic
# ============================================================
def get_prev_trade_date(pro, date: str) -> str:
    """Get the previous trading date"""
    cal = pro.trade_cal(exchange='SSE', start_date='20250101', end_date=date)
    trade_dates = cal[(cal['is_open'] == 1) & (cal['cal_date'] < date)]['cal_date'].sort_values(ascending=False)
    return trade_dates.iloc[0] if len(trade_dates) > 0 else ''


def main():
    parser = argparse.ArgumentParser(description='概念板块资金流分析')
    parser.add_argument('--date', default=None, help='交易日期 YYYYMMDD')
    parser.add_argument('--update-members', action='store_true', help='强制更新成分股缓存')
    parser.add_argument('--trend', action='store_true', help='包含多日趋势分析')
    parser.add_argument('--trend-days', type=int, default=5, help='趋势天数 (默认5)')
    parser.add_argument('--json', action='store_true', help='JSON格式输出')
    parser.add_argument('--compare', action='store_true', help='包含日度对比')
    parser.add_argument('--full', action='store_true', help='完整分析 (对比+趋势)')
    parser.add_argument('--save', action='store_true', help='保存快照到文件')
    parser.add_argument('--rotation', action='store_true', help='盘中轮动检测')
    parser.add_argument('--snapshot', action='store_true', help='保存轮动快照 (配合--rotation)')
    args = parser.parse_args()

    if args.full:
        args.compare = True
        args.trend = True

    pro = get_pro()

    # Handle rotation detection (standalone mode)
    if args.rotation:
        rotation_result, rotation_text = run_rotation_detection(pro, save_snapshot=args.snapshot)
        print(rotation_text)
        if args.json:
            print(json.dumps(rotation_result, ensure_ascii=False, indent=2))
        return 0

    # Determine trade date
    if args.date:
        trade_date = args.date
    else:
        # Latest trade date
        cal = pro.trade_cal(exchange='SSE', start_date='20260101')
        today = datetime.now().strftime('%Y%m%d')
        open_dates = cal[(cal['is_open'] == 1) & (cal['cal_date'] <= today)]['cal_date'].sort_values(ascending=False)
        trade_date = open_dates.iloc[0] if len(open_dates) > 0 else today

    print(f"📅 分析日期: {trade_date}", flush=True)

    # Step 1: Ensure member cache
    members = load_member_cache()
    if not members or members.get('_count', 0) == 0 or args.update_members:
        members = update_member_cache(pro, force=args.update_members)
    else:
        print(f"✅ 使用成分股缓存 (更新于: {members.get('_updated', 'unknown')}, {members.get('_count', 0)}个概念)", flush=True)

    # Step 2: Fetch today's flow
    print(f"📊 获取 {trade_date} 资金流...", flush=True)
    today_df = load_flow_snapshot(trade_date)
    if today_df.empty:
        today_df = fetch_concept_flow(pro, trade_date, members)
        if not today_df.empty and args.save:
            save_flow_snapshot(today_df, trade_date)
            print(f"💾 快照已保存", flush=True)

    if today_df.empty:
        print(f"❌ 无法获取 {trade_date} 数据", flush=True)
        return 1

    # Step 3: Day-over-day comparison
    comparisons = None
    if args.compare:
        prev_date = get_prev_trade_date(pro, trade_date)
        if prev_date:
            print(f"📊 获取 {prev_date} 数据做对比...", flush=True)
            yesterday_df = load_flow_snapshot(prev_date)
            if yesterday_df.empty:
                yesterday_df = fetch_concept_flow(pro, prev_date, members)
                if not yesterday_df.empty:
                    save_flow_snapshot(yesterday_df, prev_date)
            
            if not yesterday_df.empty:
                comparisons = compare_days(today_df, yesterday_df)
                print(f"✅ 日度对比完成 ({prev_date} vs {trade_date})", flush=True)

    # Step 4: Multi-day trend
    trend_df = None
    if args.trend:
        print(f"📊 计算 {args.trend_days} 日趋势...", flush=True)
        trend_df = compute_multi_day_trend(pro, members, trade_date, args.trend_days)
        if trend_df is not None and not trend_df.empty:
            print(f"✅ 趋势分析完成 ({len(trend_df)} 概念)", flush=True)

    # Step 5: Output
    if args.json:
        output = {
            'trade_date': trade_date,
            'timestamp': datetime.now().isoformat(),
            'threshold': FLOW_THRESHOLD,
            'total_concepts': len(today_df),
            'passed_threshold': len(today_df[today_df['net_inflow'] >= FLOW_THRESHOLD]),
            'flow_data': today_df.to_dict(orient='records'),
        }
        if comparisons:
            output['comparisons'] = comparisons
        if trend_df is not None and not trend_df.empty:
            output['trends'] = trend_df.to_dict(orient='records')
        
        output_file = ANALYSIS_OUTPUT_DIR / f"concept_flow_{trade_date}.json"
        with open(output_file, 'w') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"💾 JSON输出: {output_file}", flush=True)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        text = format_analysis(
            today_df, comparisons, trend_df,
            trade_date=trade_date,
            label=trade_date
        )
        print("\n" + text)

    return 0


if __name__ == '__main__':
    sys.exit(main())
