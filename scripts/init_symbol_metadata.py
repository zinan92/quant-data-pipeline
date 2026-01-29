#!/usr/bin/env python3
"""
初始化自选股的元数据
从 Tushare 获取股票基本信息
"""
import sys
sys.path.insert(0, '.')

import tushare as ts
import pandas as pd
from datetime import datetime
from src.config import get_settings
from src.database import session_scope
from src.models import SymbolMetadata, Watchlist

settings = get_settings()


def init_symbol_metadata():
    """初始化自选股元数据"""
    pro = ts.pro_api(settings.tushare_token)
    
    with session_scope() as session:
        # 获取所有自选股ticker
        watchlist = session.query(Watchlist.ticker).all()
        tickers = [w[0] for w in watchlist]
        
        if not tickers:
            print("自选股列表为空")
            return
        
        print(f"准备获取 {len(tickers)} 只股票的元数据...")
        
        # 获取全部A股基本信息
        print("从 Tushare 获取股票基本信息...")
        df_basic = pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,symbol,name,area,industry,market,list_date,is_hs'
        )
        
        # 获取每日指标 (市值、PE等)
        print("从 Tushare 获取每日指标...")
        today = datetime.now().strftime('%Y%m%d')
        df_daily = pro.daily_basic(
            trade_date=today,
            fields='ts_code,total_mv,circ_mv,pe_ttm,pb'
        )
        
        # 合并
        df = df_basic.merge(df_daily, on='ts_code', how='left')
        
        # 筛选自选股
        df['ticker'] = df['symbol']
        df_watchlist = df[df['ticker'].isin(tickers)]
        
        print(f"找到 {len(df_watchlist)} 只股票的数据")
        
        # 插入或更新
        created = 0
        updated = 0
        
        for _, row in df_watchlist.iterrows():
            ticker = row['ticker']
            existing = session.query(SymbolMetadata).filter(SymbolMetadata.ticker == ticker).first()
            
            if existing:
                # 更新
                existing.name = row['name']
                existing.industry_lv1 = row.get('industry')
                existing.total_mv = row.get('total_mv')
                existing.circ_mv = row.get('circ_mv')
                existing.pe_ttm = row.get('pe_ttm')
                existing.pb = row.get('pb')
                updated += 1
            else:
                # 创建
                meta = SymbolMetadata(
                    ticker=ticker,
                    name=row['name'],
                    industry_lv1=row.get('industry'),
                    total_mv=row.get('total_mv'),
                    circ_mv=row.get('circ_mv'),
                    pe_ttm=row.get('pe_ttm'),
                    pb=row.get('pb'),
                    list_date=row.get('list_date'),
                )
                session.add(meta)
                created += 1
        
        print(f"\n完成:")
        print(f"  ✅ 新增: {created} 只")
        print(f"  🔄 更新: {updated} 只")
        print(f"  ❌ 未找到: {len(tickers) - created - updated} 只")


if __name__ == '__main__':
    init_symbol_metadata()
