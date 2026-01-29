#!/usr/bin/env python3
"""
自选股分析报告
生成格式化的自选股组合分析
"""
import sys
import argparse
import requests
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"


def get_analytics():
    """获取分析数据"""
    try:
        resp = requests.get(f"{BASE_URL}/api/watchlist/analytics", timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"获取分析数据失败: {e}", file=sys.stderr)
        return None


def get_watchlist():
    """获取自选股列表"""
    try:
        resp = requests.get(f"{BASE_URL}/api/watchlist", timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"获取自选股失败: {e}", file=sys.stderr)
        return []


def generate_report(mode='full'):
    """
    生成分析报告
    
    Args:
        mode: 'full' 完整版, 'quick' 快速版, 'industry' 行业分析
    """
    analytics = get_analytics()
    if not analytics:
        return "⚠️ 获取分析数据失败"
    
    now = datetime.now()
    lines = []
    
    # 标题
    lines.append(f"📊 自选股分析 ({now.strftime('%Y-%m-%d %H:%M')})")
    lines.append("")
    
    # 概览
    overview = analytics.get('overview', {})
    total = overview.get('total_stocks', 0)
    up_count = overview.get('up_count', 0)
    down_count = overview.get('down_count', 0)
    up_pct = overview.get('up_pct', 0)
    down_pct = overview.get('down_pct', 0)
    
    lines.append(f"📈 持仓概览")
    lines.append(f"• 总数: {total} 只")
    lines.append(f"• 🟢 盈利: {up_count} ({up_pct:.1f}%)")
    lines.append(f"• 🔴 亏损: {down_count} ({down_pct:.1f}%)")
    lines.append("")
    
    # 行业分布
    industry = analytics.get('industry_allocation', [])
    if industry:
        lines.append("🏭 行业分布 (Top 10)")
        for idx, ind in enumerate(industry[:10], 1):
            name = ind.get('name', '未知')
            count = ind.get('count', 0)
            pct = ind.get('percentage', 0)
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"{idx:2d}. {name}: {count}只 ({pct:.1f}%)")
        lines.append("")
    
    # 风格分配
    style = analytics.get('style_allocation', [])
    if style and mode == 'full':
        lines.append("⚔️ 风格分配")
        for s in style:
            name = s.get('style', '')
            pct = s.get('percentage', 0)
            emoji = "🔥" if name == "进攻型" else "🛡️" if name == "防守型" else "⚖️"
            lines.append(f"{emoji} {name}: {pct:.1f}%")
        lines.append("")
    
    # 行业表现 (完整版)
    if mode == 'full':
        perf = analytics.get('industry_performance', [])
        if perf:
            lines.append("📊 行业表现")
            # 涨幅前5
            top_perf = sorted(perf, key=lambda x: x.get('return_pct', 0), reverse=True)[:5]
            for ind in top_perf:
                name = ind.get('name', '未知')
                ret = ind.get('return_pct', 0)
                emoji = "🟢" if ret > 0 else "🔴" if ret < 0 else "⚪"
                sign = "+" if ret > 0 else ""
                lines.append(f"{emoji} {name}: {sign}{ret:.2f}%")
            lines.append("")
    
    # Top 涨跌幅 (完整版)
    if mode == 'full':
        gainers = analytics.get('top_gainers', [])
        losers = analytics.get('top_losers', [])
        
        if gainers:
            lines.append("🚀 涨幅榜")
            for s in gainers[:5]:
                name = s.get('name', s.get('ticker', ''))
                pct = s.get('profit_pct', 0)
                lines.append(f"🟢 {name}: +{pct:.2f}%")
            lines.append("")
        
        if losers:
            lines.append("📉 跌幅榜")
            for s in losers[:5]:
                name = s.get('name', s.get('ticker', ''))
                pct = s.get('profit_pct', 0)
                lines.append(f"🔴 {name}: {pct:.2f}%")
            lines.append("")
    
    # 盈亏分布
    if mode == 'full':
        dist = analytics.get('profit_distribution', [])
        if dist:
            lines.append("📊 盈亏分布")
            for d in dist:
                range_str = d.get('range', '')
                count = d.get('count', 0)
                if count > 0:
                    bar = "▓" * min(count // 5, 20)
                    lines.append(f"{range_str:12s}: {count:3d} {bar}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='自选股分析报告')
    parser.add_argument('--mode', '-m', 
                        choices=['full', 'quick', 'industry'],
                        default='full',
                        help='报告模式: full(完整), quick(快速), industry(行业)')
    parser.add_argument('--json', '-j', action='store_true',
                        help='输出JSON格式')
    
    args = parser.parse_args()
    
    if args.json:
        import json
        data = get_analytics()
        if data:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print('{"error": "获取数据失败"}')
    else:
        print(generate_report(mode=args.mode))


if __name__ == '__main__':
    main()
