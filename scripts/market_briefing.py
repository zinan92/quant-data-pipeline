#!/usr/bin/env python3
"""
市场简报生成器
整合指数、快讯、异动等信息生成简报
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import datetime
from typing import Dict, Any, List

# 初始化
def get_index_data() -> Dict[str, Any]:
    """获取主要指数数据"""
    try:
        import akshare as ak
        
        indices = {}
        
        # 上证指数
        try:
            df = ak.stock_zh_index_spot_sina(symbol="sh000001")
            if not df.empty:
                row = df.iloc[0]
                indices['上证指数'] = {
                    'price': float(row.get('最新价', 0)),
                    'change': float(row.get('涨跌额', 0)),
                    'change_pct': float(row.get('涨跌幅', 0)),
                }
        except:
            pass
        
        # 深证成指
        try:
            df = ak.stock_zh_index_spot_sina(symbol="sz399001")
            if not df.empty:
                row = df.iloc[0]
                indices['深证成指'] = {
                    'price': float(row.get('最新价', 0)),
                    'change': float(row.get('涨跌额', 0)),
                    'change_pct': float(row.get('涨跌幅', 0)),
                }
        except:
            pass
        
        # 创业板指
        try:
            df = ak.stock_zh_index_spot_sina(symbol="sz399006")
            if not df.empty:
                row = df.iloc[0]
                indices['创业板指'] = {
                    'price': float(row.get('最新价', 0)),
                    'change': float(row.get('涨跌额', 0)),
                    'change_pct': float(row.get('涨跌幅', 0)),
                }
        except:
            pass
        
        return indices
        
    except Exception as e:
        print(f"获取指数数据失败: {e}")
        return {}


def get_news_summary() -> List[Dict[str, Any]]:
    """获取快讯摘要"""
    try:
        from src.services.news import get_news_aggregator
        
        aggregator = get_news_aggregator()
        news = aggregator.fetch_latest(sources=['cls', 'ths'], limit=10)
        
        return [
            {
                'source': n.get('source_name', ''),
                'title': n.get('title', '')[:60],
                'time': n.get('time', ''),
            }
            for n in news
        ]
    except Exception as e:
        print(f"获取快讯失败: {e}")
        return []


def get_alerts_summary() -> Dict[str, Any]:
    """获取异动摘要"""
    try:
        from src.services.news import get_alerts_service
        
        service = get_alerts_service()
        summary = service.fetch_summary()
        
        result = {}
        for alert_type, data in summary.items():
            result[alert_type] = {
                'count': data.get('count', 0),
                'top': [
                    f"{a.get('code', '')} {a.get('name', '')}"
                    for a in data.get('top', [])[:3]
                ]
            }
        
        return result
    except Exception as e:
        print(f"获取异动失败: {e}")
        return {}


def format_briefing(indices: Dict, news: List, alerts: Dict) -> str:
    """格式化简报"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    lines = [
        f"📊 **市场简报** ({now})",
        "",
        "**📈 主要指数**",
    ]
    
    # 指数
    for name, data in indices.items():
        price = data.get('price', 0)
        change_pct = data.get('change_pct', 0)
        emoji = '🔴' if change_pct < 0 else '🟢' if change_pct > 0 else '⚪'
        lines.append(f"{emoji} {name}: {price:.2f} ({change_pct:+.2f}%)")
    
    # 异动
    if alerts:
        lines.extend(["", "**⚡ 异动提醒**"])
        for alert_type, data in alerts.items():
            count = data.get('count', 0)
            if count > 0:
                top = ', '.join(data.get('top', []))
                lines.append(f"• {alert_type}: {count}只 ({top})")
    
    # 快讯
    if news:
        lines.extend(["", "**📰 最新快讯**"])
        for n in news[:5]:
            source = n.get('source', '')
            title = n.get('title', '')
            lines.append(f"• [{source}] {title}")
    
    return '\n'.join(lines)


def main():
    """生成并输出市场简报"""
    print("正在生成市场简报...\n")
    
    # 获取数据
    indices = get_index_data()
    news = get_news_summary()
    alerts = get_alerts_summary()
    
    # 格式化
    briefing = format_briefing(indices, news, alerts)
    
    print(briefing)
    
    # 也输出 JSON 格式（便于程序处理）
    print("\n--- JSON ---")
    print(json.dumps({
        'timestamp': datetime.now().isoformat(),
        'indices': indices,
        'news_count': len(news),
        'alerts': alerts,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
