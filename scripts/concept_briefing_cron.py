#!/usr/bin/env python3
"""
统一简报入口 — Cron 调度器
============================
整合指数快照、市场简报、概念资金流分析，生成完整的盘中/盘后简报。

Cron 时间表:
  9:35, 10:00, 10:30, 11:00, 11:30, 13:00, 13:30, 14:00, 14:30, 15:05

用法:
  python scripts/concept_briefing_cron.py --time 10:00           # 盘中常规
  python scripts/concept_briefing_cron.py --time 11:30 --midday  # 午盘总结
  python scripts/concept_briefing_cron.py --time 15:05 --closing # 收盘总结
  python scripts/concept_briefing_cron.py --time 9:35            # 开盘快照

流程:
  1. 捕获盘中指数快照 (intraday_snapshot)
  2. 市场简报: 指数 + 异动 + 新闻 (market_briefing)
  3. 概念资金流分析 (concept_flow_analysis)
  4. 行情复盘表 (intraday_snapshot.format_session_review)
  5. 组合输出

模式:
  - 常规 (9:35~14:30): 指数快照 + 市场简报 + 基础资金流 + 复盘表
  - 午盘 (11:30 --midday): 上午全部 + 上午复盘
  - 收盘 (15:05 --closing): 全量分析 (含 --compare --trend) + 全日复盘
"""

import sys
import os
import argparse
import traceback
from pathlib import Path
from datetime import datetime
from io import StringIO

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================
# 惰性导入 — 按需加载模块，避免不必要的初始化开销
# ============================================================
def _import_intraday():
    from scripts.intraday_snapshot import capture_snapshot, format_session_review
    return capture_snapshot, format_session_review


def _import_market_briefing():
    from scripts.market_briefing import format_briefing
    return format_briefing


def _import_concept_flow():
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
    )
    return {
        'get_pro': get_pro,
        'load_member_cache': load_member_cache,
        'update_member_cache': update_member_cache,
        'fetch_concept_flow': fetch_concept_flow,
        'save_flow_snapshot': save_flow_snapshot,
        'load_flow_snapshot': load_flow_snapshot,
        'compare_days': compare_days,
        'compute_multi_day_trend': compute_multi_day_trend,
        'format_analysis': format_analysis,
        'get_prev_trade_date': get_prev_trade_date,
        'FLOW_THRESHOLD': FLOW_THRESHOLD,
    }


# ============================================================
# 辅助函数
# ============================================================
def _get_latest_trade_date(pro) -> str:
    """获取最近的交易日 (≤今天)"""
    today = datetime.now().strftime('%Y%m%d')
    cal = pro.trade_cal(exchange='SSE', start_date='20260101')
    open_dates = cal[
        (cal['is_open'] == 1) & (cal['cal_date'] <= today)
    ]['cal_date'].sort_values(ascending=False)
    return open_dates.iloc[0] if len(open_dates) > 0 else today


def _ensure_members(cf):
    """确保概念成分股缓存是最新的"""
    cache = cf['load_member_cache']()
    today = datetime.now().strftime('%Y%m%d')
    if cache and cache.get('_updated') == today and cache.get('_count', 0) > 0:
        return cache
    print(f"🔄 成分股缓存过期 (上次: {cache.get('_updated', 'never')}), 更新中...",
          file=sys.stderr, flush=True)
    pro = cf['get_pro']()
    return cf['update_member_cache'](pro, force=True)


def _safe_run(name: str, fn, *args, **kwargs) -> str:
    """安全执行并捕获输出，失败时返回错误提示"""
    try:
        result = fn(*args, **kwargs)
        return result if isinstance(result, str) else ""
    except Exception as e:
        print(f"⚠️ {name} 失败: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return f"⚠️ {name}: {e}"


# ============================================================
# 核心：概念资金流获取与格式化
# ============================================================
def run_concept_flow(mode: str = 'basic') -> str:
    """
    运行概念资金流分析。

    Args:
        mode:
          'basic'   — 仅今日 TOP 排名
          'compare' — 今日 + 日度对比
          'full'    — 今日 + 日度对比 + 5日趋势

    Returns:
        格式化文本
    """
    cf = _import_concept_flow()
    pro = cf['get_pro']()
    members = _ensure_members(cf)
    trade_date = _get_latest_trade_date(pro)

    # 今日资金流
    today_df = cf['load_flow_snapshot'](trade_date)
    if today_df.empty:
        today_df = cf['fetch_concept_flow'](pro, trade_date, members)
        if not today_df.empty:
            cf['save_flow_snapshot'](today_df, trade_date)

    if today_df.empty:
        # 回退到前一交易日
        prev = cf['get_prev_trade_date'](pro, trade_date)
        if prev:
            trade_date = prev
            today_df = cf['load_flow_snapshot'](trade_date)
            if today_df.empty:
                today_df = cf['fetch_concept_flow'](pro, trade_date, members)
                if not today_df.empty:
                    cf['save_flow_snapshot'](today_df, trade_date)

    if today_df.empty:
        return f"⚠️ 无概念资金流数据 ({trade_date})"

    # 日度对比
    comparisons = None
    if mode in ('compare', 'full'):
        prev_date = cf['get_prev_trade_date'](pro, trade_date)
        if prev_date:
            ydf = cf['load_flow_snapshot'](prev_date)
            if ydf.empty:
                ydf = cf['fetch_concept_flow'](pro, prev_date, members)
                if not ydf.empty:
                    cf['save_flow_snapshot'](ydf, prev_date)
            if not ydf.empty:
                comparisons = cf['compare_days'](today_df, ydf)

    # 多日趋势
    trend_df = None
    if mode == 'full':
        trend_df = cf['compute_multi_day_trend'](pro, members, trade_date, days=5)

    now_str = datetime.now().strftime('%H:%M')
    label = f"{trade_date} {'收盘' if mode == 'full' else now_str}"

    return cf['format_analysis'](
        today_df, comparisons, trend_df,
        trade_date=trade_date,
        label=label,
    )


# ============================================================
# 组合简报生成
# ============================================================
def generate_briefing(time_label: str, closing: bool = False, midday: bool = False) -> str:
    """
    生成完整简报。

    Args:
        time_label: 时间标签 (如 "10:00", "15:05")
        closing: 是否收盘模式 (15:05)
        midday: 是否午盘模式 (11:30)

    Returns:
        拼接好的完整简报文本
    """
    sections = []
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')

    # ── 标题 ──
    if closing:
        title = f"📋 收盘简报 ({date_str} {time_label})"
    elif midday:
        title = f"📋 午盘简报 ({date_str} {time_label})"
    else:
        title = f"📋 盘中简报 ({date_str} {time_label})"
    sections.append(title)
    sections.append("=" * 36)

    # ── Step 1: 捕获盘中指数快照 ──
    capture_snapshot, format_session_review = _import_intraday()
    snap = _safe_run("指数快照", capture_snapshot, label=time_label)
    # capture_snapshot 打印到 stdout，不返回文本；我们需要它写入文件的副作用

    # ── Step 2: 市场简报 (指数 + 异动 + 新闻) ──
    format_market = _import_market_briefing()
    market_text = _safe_run("市场简报", format_market, time_label)
    if market_text:
        sections.append(market_text)

    # ── Step 3: 概念资金流 ──
    if closing:
        flow_mode = 'full'  # 日度对比 + 5日趋势
    elif midday:
        flow_mode = 'compare'  # 日度对比
    else:
        flow_mode = 'basic'  # 仅排名
    
    flow_text = _safe_run("概念资金流", run_concept_flow, flow_mode)
    if flow_text:
        sections.append("")
        sections.append(flow_text)

    # ── Step 4: 行情复盘表 ──
    # 午盘和收盘时生成复盘表；常规盘中有≥2个快照也生成
    review_text = _safe_run("行情复盘", format_session_review)
    if review_text and "无快照数据" not in review_text:
        sections.append("")
        sections.append(review_text)

    return '\n'.join(sections)


# ============================================================
# CLI 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='统一简报入口 (Cron调度)')
    parser.add_argument('--time', default=None,
                        help='时间标签 (如 10:00, 15:05)，默认当前时间')
    parser.add_argument('--closing', action='store_true',
                        help='收盘模式 (完整分析: compare + trend + 全日复盘)')
    parser.add_argument('--midday', action='store_true',
                        help='午盘模式 (上午复盘 + 日度对比)')
    parser.add_argument('--auto', action='store_true',
                        help='自动判断模式: 11:30→midday, 15:05→closing, 其他→常规')

    # 兼容旧版参数
    parser.add_argument('--full', action='store_true',
                        help='(兼容旧版) 等同于 --closing')
    parser.add_argument('--rotation', action='store_true',
                        help='(兼容旧版) 包含轮动检测')
    parser.add_argument('--json', action='store_true',
                        help='(兼容旧版) JSON输出')

    args = parser.parse_args()

    # 兼容旧版
    if args.full:
        args.closing = True

    # 时间标签
    time_label = args.time or datetime.now().strftime('%H:%M')

    # 自动模式判断
    if args.auto:
        if time_label in ('11:30',):
            args.midday = True
        elif time_label in ('15:05', '15:00'):
            args.closing = True

    try:
        result = generate_briefing(
            time_label=time_label,
            closing=args.closing,
            midday=args.midday,
        )
        print(result)
        return 0
    except Exception as e:
        print(f"❌ 简报生成失败: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
