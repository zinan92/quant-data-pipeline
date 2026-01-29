#!/usr/bin/env python3
"""
美股简报脚本
生成格式化的美股市场简报
"""
import sys
import argparse
import requests
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"


def get_indexes():
    """获取美股指数"""
    try:
        resp = requests.get(f"{BASE_URL}/api/us-stock/indexes", timeout=30)
        resp.raise_for_status()
        return resp.json().get('quotes', [])
    except Exception as e:
        print(f"获取指数失败: {e}", file=sys.stderr)
        return []


def get_china_adr():
    """获取中概股"""
    try:
        resp = requests.get(f"{BASE_URL}/api/us-stock/china-adr", timeout=30)
        resp.raise_for_status()
        return resp.json().get('quotes', [])
    except Exception as e:
        print(f"获取中概股失败: {e}", file=sys.stderr)
        return []


def get_tech():
    """获取科技股"""
    try:
        resp = requests.get(f"{BASE_URL}/api/us-stock/tech", timeout=30)
        resp.raise_for_status()
        return resp.json().get('quotes', [])
    except Exception as e:
        print(f"获取科技股失败: {e}", file=sys.stderr)
        return []


def get_ai():
    """获取AI概念股"""
    try:
        resp = requests.get(f"{BASE_URL}/api/us-stock/ai", timeout=30)
        resp.raise_for_status()
        return resp.json().get('quotes', [])
    except Exception as e:
        print(f"获取AI概念股失败: {e}", file=sys.stderr)
        return []


def format_change(change_pct):
    """格式化涨跌幅"""
    if change_pct > 0:
        return f"🟢 +{change_pct:.2f}%"
    elif change_pct < 0:
        return f"🔴 {change_pct:.2f}%"
    else:
        return f"⚪ {change_pct:.2f}%"


def format_quote(quote, show_price=True):
    """格式化单个报价"""
    name = quote.get('cn_name') or quote.get('name', quote['symbol'])
    change_pct = quote.get('change_pct', 0)
    
    if show_price:
        price = quote.get('price', 0)
        return f"{name}: ${price:.2f} ({format_change(change_pct)})"
    else:
        return f"{name} {format_change(change_pct)}"


def generate_briefing(mode='full'):
    """
    生成美股简报
    
    Args:
        mode: 'full' 完整版, 'quick' 快速版, 'open' 开盘版, 'close' 收盘版
    """
    now = datetime.now()
    lines = []
    
    # 标题
    if mode == 'open':
        lines.append(f"🇺🇸 美股开盘 ({now.strftime('%H:%M')})")
    elif mode == 'close':
        lines.append(f"🇺🇸 美股收盘 ({now.strftime('%H:%M')})")
    else:
        lines.append(f"🇺🇸 美股简报 ({now.strftime('%H:%M')})")
    lines.append("")
    
    # 三大指数
    indexes = get_indexes()
    if indexes:
        lines.append("📈 三大指数")
        # 只显示主要的三个
        main_indexes = {'^GSPC': 'S&P 500', '^DJI': '道琼斯', '^IXIC': '纳斯达克'}
        for idx in indexes:
            symbol = idx.get('symbol', '')
            if symbol in main_indexes:
                name = main_indexes[symbol]
                price = idx.get('price', 0)
                change_pct = idx.get('change_pct', 0)
                emoji = "🟢" if change_pct > 0 else "🔴" if change_pct < 0 else "⚪"
                sign = "+" if change_pct > 0 else ""
                lines.append(f"{emoji} {name}: {price:,.2f} ({sign}{change_pct:.2f}%)")
        
        # VIX 恐慌指数
        for idx in indexes:
            if idx.get('symbol') == '^VIX':
                vix = idx.get('price', 0)
                vix_change = idx.get('change_pct', 0)
                vix_emoji = "😨" if vix > 20 else "😰" if vix > 15 else "😌"
                lines.append(f"{vix_emoji} VIX恐慌指数: {vix:.2f} ({vix_change:+.2f}%)")
        lines.append("")
    
    # 中概股
    if mode in ['full', 'open', 'close']:
        china_adr = get_china_adr()
        if china_adr:
            lines.append("🇨🇳 中概股")
            # 按涨跌幅排序
            sorted_adr = sorted(china_adr, key=lambda x: x.get('change_pct', 0), reverse=True)
            for stock in sorted_adr:
                name = stock.get('cn_name', stock.get('symbol', ''))
                price = stock.get('price', 0)
                change_pct = stock.get('change_pct', 0)
                emoji = "🟢" if change_pct > 0 else "🔴" if change_pct < 0 else "⚪"
                sign = "+" if change_pct > 0 else ""
                lines.append(f"{emoji} {name}: ${price:.2f} ({sign}{change_pct:.2f}%)")
            lines.append("")
    
    # 科技股 (完整版和收盘版)
    if mode in ['full', 'close']:
        tech = get_tech()
        if tech:
            lines.append("💻 科技股")
            sorted_tech = sorted(tech, key=lambda x: x.get('change_pct', 0), reverse=True)
            for stock in sorted_tech[:5]:  # 只显示前5
                name = stock.get('cn_name', stock.get('symbol', ''))
                price = stock.get('price', 0)
                change_pct = stock.get('change_pct', 0)
                emoji = "🟢" if change_pct > 0 else "🔴" if change_pct < 0 else "⚪"
                sign = "+" if change_pct > 0 else ""
                lines.append(f"{emoji} {name}: ${price:.2f} ({sign}{change_pct:.2f}%)")
            lines.append("")
    
    # AI概念 (完整版)
    if mode == 'full':
        ai = get_ai()
        if ai:
            lines.append("🤖 AI概念")
            # 去重 (有些股票既在tech又在ai)
            seen = set()
            for stock in sorted(ai, key=lambda x: x.get('change_pct', 0), reverse=True):
                symbol = stock.get('symbol', '')
                if symbol in seen:
                    continue
                seen.add(symbol)
                name = stock.get('cn_name', stock.get('symbol', ''))
                change_pct = stock.get('change_pct', 0)
                emoji = "🟢" if change_pct > 0 else "🔴" if change_pct < 0 else "⚪"
                sign = "+" if change_pct > 0 else ""
                lines.append(f"{emoji} {name} ({sign}{change_pct:.2f}%)")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='美股简报生成器')
    parser.add_argument('--mode', '-m', 
                        choices=['full', 'quick', 'open', 'close'],
                        default='full',
                        help='简报模式: full(完整), quick(快速), open(开盘), close(收盘)')
    parser.add_argument('--json', '-j', action='store_true',
                        help='输出JSON格式')
    
    args = parser.parse_args()
    
    if args.json:
        import json
        data = {
            'indexes': get_indexes(),
            'china_adr': get_china_adr(),
            'tech': get_tech(),
            'ai': get_ai(),
            'timestamp': datetime.now().isoformat(),
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(generate_briefing(mode=args.mode))


if __name__ == '__main__':
    main()
