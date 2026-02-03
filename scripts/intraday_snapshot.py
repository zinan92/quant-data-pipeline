#!/usr/bin/env python3
"""
盘中指数快照 + 全程回顾
===========================
每次 cron 触发时捕获A股指数数据，存为日内快照序列。
收盘后可生成全日走势回顾表 + 自动识别行情模式。

子命令模式 (推荐):
  python scripts/intraday_snapshot.py capture --label "10:00"
  python scripts/intraday_snapshot.py capture              # 自动label
  python scripts/intraday_snapshot.py review               # 今日复盘
  python scripts/intraday_snapshot.py review --date 20260204

旧版flag模式 (向后兼容):
  python scripts/intraday_snapshot.py                  # 拍快照 + 生成回顾
  python scripts/intraday_snapshot.py --snapshot-only  # 仅拍快照
  python scripts/intraday_snapshot.py --review-only    # 仅生成回顾
  python scripts/intraday_snapshot.py --json           # JSON输出

检查点标签 (与 cron 对齐):
  9:35开盘 | 10:00 | 10:30 | 11:00 | 11:30午间收盘
  13:00午后开盘 | 13:30 | 14:00 | 14:30 | 15:05收盘

数据源: Sina Finance 实时行情 API
存储: data/snapshots/intraday/index_YYYYMMDD.json
"""

import sys
import os
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime

# ============================================================
# Configuration
# ============================================================
project_root = Path(__file__).parent.parent
INTRADAY_DIR = project_root / "data" / "snapshots" / "intraday"
INTRADAY_DIR.mkdir(parents=True, exist_ok=True)

SINA_HEADERS = {
    'Referer': 'https://finance.sina.com.cn',
    'User-Agent': 'Mozilla/5.0',
}

# Indices to track: (sina_code, display_name, short_name)
INDICES = [
    ('sh000001', '上证指数', '上证'),
    ('sz399001', '深证成指', '深成指'),
    ('sz399006', '创业板指', '创业板'),
    ('sh000688', '科创50',   '科创50'),
]

# Checkpoint labels for display
CHECKPOINT_LABELS = {
    '0935': '9:35开盘',
    '1000': '10:00',
    '1030': '10:30',
    '1100': '11:00',
    '1130': '11:30午间',
    '1300': '13:00午后',
    '1330': '13:30',
    '1400': '14:00',
    '1430': '14:30',
    '1505': '15:05收盘',
}


# ============================================================
# 1. Fetch Index Data from Sina
# ============================================================
def fetch_indices() -> dict:
    """
    Fetch realtime index data from Sina Finance.
    Uses full API (not simplified) to get prev_close for pct calculation.

    Returns dict keyed by short_name:
        { '上证': { 'price': 3200.0, 'prev_close': 3184.0, 'pct': 0.50,
                    'open': 3190.0, 'high': 3210.0, 'low': 3178.0, 'vol': 5000.0 }, ... }
    """
    codes = ','.join(code for code, _, _ in INDICES)
    try:
        r = requests.get(
            f'http://hq.sinajs.cn/list={codes}',
            headers=SINA_HEADERS, timeout=5
        )
        r.encoding = 'gbk'
    except Exception as e:
        print(f"⚠️ Sina API error: {e}", file=sys.stderr)
        return {}

    results = {}
    lines = r.text.strip().split('\n')

    for i, (sina_code, full_name, short_name) in enumerate(INDICES):
        if i >= len(lines):
            continue
        line = lines[i]
        if '"' not in line:
            continue

        parts = line.split('"')[1].split(',')
        if len(parts) < 6:
            continue

        try:
            open_price = float(parts[1])
            prev_close = float(parts[2])
            current = float(parts[3])
            high = float(parts[4])
            low = float(parts[5])

            pct = ((current - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

            results[short_name] = {
                'price': round(current, 2),
                'prev_close': round(prev_close, 2),
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'pct': round(pct, 2),
                'full_name': full_name,
            }
        except (ValueError, IndexError):
            continue

    return results


# ============================================================
# 2. Snapshot Storage
# ============================================================
def get_snapshot_file(date_str: str = None) -> Path:
    """Get the snapshot file path for a given date."""
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    return INTRADAY_DIR / f"index_{date_str}.json"


def load_snapshots(date_str: str = None) -> dict:
    """
    Load all snapshots for a given date.
    Returns dict: { 'date': '20260204', 'checkpoints': { '0935': {...}, '1000': {...}, ... } }
    """
    filepath = get_snapshot_file(date_str)
    if filepath.exists():
        with open(filepath, 'r') as f:
            return json.load(f)
    return {
        'date': date_str or datetime.now().strftime('%Y%m%d'),
        'checkpoints': {},
    }


def save_snapshots(data: dict, date_str: str = None):
    """Save snapshot data to file."""
    filepath = get_snapshot_file(date_str)
    with open(filepath, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_checkpoint_label() -> str:
    """
    Determine the current checkpoint label based on time.
    Maps current time to nearest checkpoint.
    """
    now = datetime.now()
    hhmm = now.strftime('%H%M')
    t = int(hhmm)

    # Map to the closest checkpoint
    checkpoints = [935, 1000, 1030, 1100, 1130, 1300, 1330, 1400, 1430, 1505]

    # Find the closest checkpoint within ±8 minutes
    best = None
    best_dist = 999
    for cp in checkpoints:
        # Convert to minutes for comparison
        cp_mins = (cp // 100) * 60 + (cp % 100)
        t_mins = (t // 100) * 60 + (t % 100)
        dist = abs(t_mins - cp_mins)
        if dist < best_dist:
            best_dist = dist
            best = cp

    if best is not None and best_dist <= 8:
        return f"{best:04d}"

    # Not near any checkpoint — use raw time
    return hhmm


def _normalize_label(label: str) -> str:
    """
    Normalize a time label to HHMM format.
    Accepts: "10:00" → "1000", "9:35" → "0935", "1000" → "1000"
    """
    if ':' in label:
        parts = label.split(':')
        return f"{int(parts[0]):02d}{int(parts[1]):02d}"
    return label


def take_snapshot(label: str = None) -> dict | None:
    """
    Take an index snapshot and store it.
    Label can be "10:00" or "1000" format — both accepted.
    Returns the snapshot data dict, or None on failure.
    """
    if label is None:
        label = get_checkpoint_label()
    else:
        label = _normalize_label(label)

    indices = fetch_indices()
    if not indices:
        print("⚠️ Failed to fetch index data", file=sys.stderr)
        return None

    snapshot = {
        'label': label,
        'display_label': CHECKPOINT_LABELS.get(label, label),
        'timestamp': datetime.now().isoformat(),
        'indices': indices,
    }

    # Load existing snapshots for today, add this one
    today = datetime.now().strftime('%Y%m%d')
    data = load_snapshots(today)
    data['checkpoints'][label] = snapshot
    save_snapshots(data, today)

    count = len(data['checkpoints'])
    print(f"📸 快照已保存: {snapshot['display_label']} ({count}个检查点)",
          file=sys.stderr, flush=True)
    return snapshot


# Alias for cron integration (concept_briefing_cron.py imports this name)
capture_snapshot = take_snapshot


# ============================================================
# 3. Session Review Table
# ============================================================
def format_session_review(date_str: str = None) -> str:
    """
    Generate the full-session review table.

    Output format (Park's spec):
    📈 全程回顾
    | 指数 | 9:35开盘 | 10:30低点 | 当前 | 反弹幅度 |
    | ---- | ------ | ------- | ---- | ------ |
    | 上证 | -0.36% | -1.84% | -1.19% | +65bp |
    """
    data = load_snapshots(date_str)
    checkpoints = data.get('checkpoints', {})

    if not checkpoints:
        return "📈 全程回顾: 暂无快照数据"

    # Sort checkpoints chronologically
    sorted_labels = sorted(checkpoints.keys())
    index_names = [short for _, _, short in INDICES]

    # Determine session label
    last_label = sorted_labels[-1]
    try:
        last_t = int(last_label)
    except ValueError:
        last_t = 0  # 非数字标签 (如 "test") 默认盘中
    if last_t >= 1500:
        session_title = "全天回顾"
    elif last_t >= 1300:
        session_title = "午后回顾"
    elif last_t >= 1130:
        session_title = "上午全程回顾"
    else:
        session_title = "盘中回顾"

    # Build per-index time series
    index_series = {}  # { '上证': [ (label, pct), ... ] }
    for name in index_names:
        series = []
        for label in sorted_labels:
            cp = checkpoints[label]
            idx_data = cp.get('indices', {}).get(name)
            if idx_data:
                series.append((label, idx_data['pct']))
        index_series[name] = series

    # Find opening, high point, low point, current for each index
    rows = []
    for name in index_names:
        series = index_series.get(name, [])
        if not series:
            continue

        opening_label, opening_pct = series[0]
        current_label, current_pct = series[-1]

        # Find session low and high
        low_label, low_pct = min(series, key=lambda x: x[1])
        high_label, high_pct = max(series, key=lambda x: x[1])

        # Rebound = current - low (in basis points)
        rebound_bp = round((current_pct - low_pct) * 100)
        # Pullback = current - high (in basis points, negative means dropped from high)
        pullback_bp = round((current_pct - high_pct) * 100)

        rows.append({
            'name': name,
            'opening_pct': opening_pct,
            'opening_label': CHECKPOINT_LABELS.get(opening_label, opening_label),
            'low_pct': low_pct,
            'low_label': CHECKPOINT_LABELS.get(low_label, low_label),
            'high_pct': high_pct,
            'high_label': CHECKPOINT_LABELS.get(high_label, high_label),
            'current_pct': current_pct,
            'current_label': CHECKPOINT_LABELS.get(current_label, current_label),
            'rebound_bp': rebound_bp,
            'pullback_bp': pullback_bp,
        })

    if not rows:
        return "📈 全程回顾: 无指数数据"

    # Only one checkpoint? Just show current values, no table
    if len(sorted_labels) == 1:
        lines = [f"📈 {session_title} (仅1个检查点)"]
        for r in rows:
            lines.append(f"  • {r['name']}: {r['current_pct']:+.2f}%")
        return '\n'.join(lines)

    # Build the adaptive table
    # Decide which columns to show based on price action
    # Always: opening, current
    # Conditionally: low point (if different from opening & current), high point likewise

    lines = [f"📈 {session_title}"]

    # Determine the "interesting" column: is it a V-shape (low matters) or
    # inverted-V (high matters) or both?
    avg_rebound = sum(r['rebound_bp'] for r in rows) / len(rows)
    avg_pullback = sum(r['pullback_bp'] for r in rows) / len(rows)

    # Build header based on what's interesting
    # Always show: 开盘 | extreme point | 当前 | 幅度
    # If market dipped then recovered: show low point + rebound
    # If market rallied then fell: show high point + pullback
    # If both happened: show both

    show_low = any(r['low_label'] != r['opening_label'] and r['low_label'] != r['current_label']
                   for r in rows)
    show_high = any(r['high_label'] != r['opening_label'] and r['high_label'] != r['current_label']
                    for r in rows)

    # Construct the table
    # Use the format Park showed
    header_parts = ['指数', rows[0]['opening_label']]
    if show_low:
        # Use the most common low label
        low_labels = [r['low_label'] for r in rows]
        common_low = max(set(low_labels), key=low_labels.count)
        header_parts.append(f"{common_low}低点")
    if show_high and show_low:
        high_labels = [r['high_label'] for r in rows]
        common_high = max(set(high_labels), key=high_labels.count)
        header_parts.append(f"{common_high}高点")
    elif show_high:
        high_labels = [r['high_label'] for r in rows]
        common_high = max(set(high_labels), key=high_labels.count)
        header_parts.append(f"{common_high}高点")

    header_parts.append(rows[0]['current_label'])

    if show_low:
        header_parts.append('反弹幅度')
    elif show_high:
        header_parts.append('回落幅度')
    else:
        header_parts.append('变化')

    lines.append('| ' + ' | '.join(header_parts) + ' |')
    lines.append('| ' + ' | '.join(['----'] * len(header_parts)) + ' |')

    for r in rows:
        row_parts = [
            r['name'],
            f"{r['opening_pct']:+.2f}%",
        ]
        if show_low:
            row_parts.append(f"{r['low_pct']:+.2f}%")
        if show_high and show_low:
            row_parts.append(f"{r['high_pct']:+.2f}%")
        elif show_high:
            row_parts.append(f"{r['high_pct']:+.2f}%")

        row_parts.append(f"{r['current_pct']:+.2f}%")

        if show_low:
            row_parts.append(f"{r['rebound_bp']:+d}bp")
        elif show_high:
            row_parts.append(f"{r['pullback_bp']:+d}bp")
        else:
            delta = round((r['current_pct'] - r['opening_pct']) * 100)
            row_parts.append(f"{delta:+d}bp")

        lines.append('| ' + ' | '.join(row_parts) + ' |')

    # Add narrative
    narrative = generate_narrative(rows, sorted_labels, checkpoints)
    if narrative:
        lines.append('')
        lines.append(narrative)

    return '\n'.join(lines)


# ============================================================
# 4. Auto-narrative Generation
# ============================================================
def generate_narrative(rows: list[dict], sorted_labels: list[str],
                       checkpoints: dict) -> str:
    """
    Auto-generate a brief narrative describing the session pattern.
    Detects: V-shape, inverted-V, steady climb, steady decline, range-bound, divergence.
    """
    if len(sorted_labels) < 2 or not rows:
        return ""

    # Compute aggregate metrics across all indices
    avg_open = sum(r['opening_pct'] for r in rows) / len(rows)
    avg_current = sum(r['current_pct'] for r in rows) / len(rows)
    avg_low = sum(r['low_pct'] for r in rows) / len(rows)
    avg_high = sum(r['high_pct'] for r in rows) / len(rows)
    avg_rebound = sum(r['rebound_bp'] for r in rows) / len(rows)

    # Detect divergence: 创业板 vs 上证 moving in different directions
    divergent = False
    sh_row = next((r for r in rows if r['name'] == '上证'), None)
    cyb_row = next((r for r in rows if r['name'] == '创业板'), None)
    if sh_row and cyb_row:
        if (sh_row['current_pct'] > 0.3 and cyb_row['current_pct'] < -0.3) or \
           (sh_row['current_pct'] < -0.3 and cyb_row['current_pct'] > 0.3):
            divergent = True

    # Determine pattern
    dip_from_open = avg_open - avg_low      # how much it dipped below opening
    rally_from_open = avg_high - avg_open   # how much it rallied above opening
    recovery = avg_current - avg_low        # recovery from the low

    parts = []

    # V-shape reversal
    if dip_from_open > 0.5 and recovery > dip_from_open * 0.6:
        if avg_current > avg_open:
            parts.append("💪 典型V型反转，低开高走")
        else:
            parts.append("📈 探底回升，跌幅明显收窄")

    # Inverted V
    elif rally_from_open > 0.5 and (avg_high - avg_current) > rally_from_open * 0.6:
        parts.append("⚠️ 冲高回落，高位承压")

    # Steady climb
    elif avg_current > avg_open + 0.3 and dip_from_open < 0.3:
        parts.append("📈 稳步上行，做多情绪积极")

    # Steady decline
    elif avg_current < avg_open - 0.3 and rally_from_open < 0.3:
        parts.append("📉 持续下行，空头主导")

    # Range-bound
    elif abs(avg_current - avg_open) < 0.2 and (avg_high - avg_low) < 0.5:
        parts.append("➡️ 窄幅震荡，多空胶着")

    # Wide range
    elif (avg_high - avg_low) > 1.5:
        parts.append("🎢 大幅震荡，波动剧烈")

    # Divergence
    if divergent:
        if sh_row['current_pct'] > cyb_row['current_pct']:
            parts.append("权重股强于成长股，风格偏大盘")
        else:
            parts.append("成长股强于权重股，风格偏小盘")

    # Magnitude
    if avg_current > 2.0:
        parts.append("🔥 全线大涨")
    elif avg_current < -2.0:
        parts.append("💔 全线大跌")
    elif avg_rebound > 100:
        parts.append(f"反弹力度强劲 (平均{avg_rebound:.0f}bp)")

    return '💬 ' + '，'.join(parts) if parts else ""


# ============================================================
# 5. Convenience: Full-session timeline (text list)
# ============================================================
def format_timeline(date_str: str = None) -> str:
    """
    Alternative compact format: timeline list instead of table.
    Useful for platforms that don't render markdown tables well.
    """
    data = load_snapshots(date_str)
    checkpoints = data.get('checkpoints', {})

    if not checkpoints:
        return ""

    sorted_labels = sorted(checkpoints.keys())
    lines = ["📊 指数走势时间线:"]

    for label in sorted_labels:
        cp = checkpoints[label]
        display = cp.get('display_label', label)
        indices = cp.get('indices', {})
        parts = []
        for _, _, short in INDICES:
            idx = indices.get(short)
            if idx:
                parts.append(f"{short}{idx['pct']:+.2f}%")
        if parts:
            lines.append(f"  {display}: {' | '.join(parts)}")

    return '\n'.join(lines)


# ============================================================
# 6. Public API aliases (供 concept_briefing_cron 等外部模块调用)
# ============================================================
def capture_snapshot(label: str = "") -> dict | None:
    """
    捕获快照的公开接口。兼容 concept_briefing_cron 调用。
    label 接受 "10:00" 格式 (自动转为 "1000") 或 "1000" 格式。
    """
    # 将 "10:00" → "1000", "9:35" → "0935" 等格式标准化
    if label and ':' in label:
        parts = label.split(':')
        label = f"{int(parts[0]):02d}{parts[1]}"
    return take_snapshot(label=label or None)


# ============================================================
# 7. Main CLI (支持子命令和旧版flag两种模式)
# ============================================================
def main():
    # 检测子命令模式: capture / review
    if len(sys.argv) > 1 and sys.argv[1] in ('capture', 'review'):
        return _subcommand_main()
    return _flag_main()


def _subcommand_main():
    """子命令模式: capture --label "10:00" / review --date 20260204"""
    parser = argparse.ArgumentParser(description='盘中指数快照 & 全日复盘')
    subparsers = parser.add_subparsers(dest='command')

    cap = subparsers.add_parser('capture', help='捕获当前指数快照')
    cap.add_argument('--label', default='', help='快照标签 (如 "10:00", "0935")')

    rev = subparsers.add_parser('review', help='生成全日复盘')
    rev.add_argument('--date', default=None, help='日期 YYYYMMDD (默认今天)')
    rev.add_argument('--timeline', action='store_true', help='时间线格式')
    rev.add_argument('--json', action='store_true', help='JSON输出')

    args = parser.parse_args()

    if args.command == 'capture':
        result = capture_snapshot(label=args.label)
        return 0 if result else 1

    elif args.command == 'review':
        date_str = args.date or datetime.now().strftime('%Y%m%d')
        if args.json:
            data = load_snapshots(date_str)
            print(json.dumps(data, ensure_ascii=False, indent=2))
        elif args.timeline:
            print(format_timeline(date_str))
        else:
            print(format_session_review(date_str))
        return 0

    parser.print_help()
    return 1


def _flag_main():
    """旧版flag模式 (向后兼容)"""
    parser = argparse.ArgumentParser(description='盘中指数快照 + 全程回顾')
    parser.add_argument('--snapshot-only', action='store_true',
                        help='仅拍快照，不生成回顾')
    parser.add_argument('--review-only', action='store_true',
                        help='仅生成回顾，不拍新快照')
    parser.add_argument('--timeline', action='store_true',
                        help='输出时间线格式 (替代表格)')
    parser.add_argument('--date', default=None,
                        help='指定日期 YYYYMMDD (仅review模式)')
    parser.add_argument('--label', default=None,
                        help='手动指定检查点标签 (e.g., 0935)')
    parser.add_argument('--json', action='store_true',
                        help='JSON格式输出')
    args = parser.parse_args()

    # Take snapshot (unless review-only)
    if not args.review_only:
        snapshot = take_snapshot(label=args.label)
        if snapshot is None and not args.review_only:
            return 1

        if args.snapshot_only:
            if args.json and snapshot:
                print(json.dumps(snapshot, ensure_ascii=False, indent=2))
            return 0

    # Generate review
    date_str = args.date or datetime.now().strftime('%Y%m%d')

    if args.json:
        data = load_snapshots(date_str)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.timeline:
        print(format_timeline(date_str))
    else:
        print(format_session_review(date_str))

    return 0


if __name__ == '__main__':
    sys.exit(main())
