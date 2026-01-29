#!/usr/bin/env python3
"""
计算技术指标并保存到数据库
MA, MACD, RSI, 布林带
使用 tushare 获取日线数据
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import tushare as ts
from src.config import get_settings
from src.database import SessionLocal
from src.models import Watchlist
from sqlalchemy import text, select


def calculate_ma(closes: pd.Series, period: int) -> pd.Series:
    return closes.rolling(window=period).mean()


def calculate_macd(closes: pd.Series, fast=12, slow=26, signal=9):
    exp1 = closes.ewm(span=fast, adjust=False).mean()
    exp2 = closes.ewm(span=slow, adjust=False).mean()
    dif = exp1 - exp2
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = 2 * (dif - dea)
    return dif, dea, hist


def calculate_rsi(closes: pd.Series, period: int) -> pd.Series:
    delta = closes.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_bollinger(closes: pd.Series, period=20, std_dev=2):
    mid = closes.rolling(window=period).mean()
    std = closes.rolling(window=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower


def get_stock_daily(pro, ticker: str) -> pd.DataFrame:
    """从 tushare 获取日线数据"""
    try:
        # 转换代码格式
        if ticker.startswith('6'):
            ts_code = f"{ticker}.SH"
        elif ticker.startswith('0') or ticker.startswith('3'):
            ts_code = f"{ticker}.SZ"
        else:
            ts_code = f"{ticker}.BJ"
        
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=180)).strftime('%Y%m%d')
        
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        
        if df is None or df.empty:
            return pd.DataFrame()
        
        df = df.rename(columns={
            'trade_date': 'date',
            'vol': 'volume'
        })
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        return df[['date', 'open', 'high', 'low', 'close', 'volume']]
        
    except Exception as e:
        return pd.DataFrame()


def calculate_and_save(pro, ticker: str, session) -> bool:
    """计算单只股票的技术指标并保存"""
    df = get_stock_daily(pro, ticker)
    
    if len(df) < 60:
        return False
    
    # 计算各项指标
    df['ma5'] = calculate_ma(df['close'], 5)
    df['ma10'] = calculate_ma(df['close'], 10)
    df['ma20'] = calculate_ma(df['close'], 20)
    df['ma60'] = calculate_ma(df['close'], 60)
    
    df['macd_dif'], df['macd_dea'], df['macd_hist'] = calculate_macd(df['close'])
    
    df['rsi6'] = calculate_rsi(df['close'], 6)
    df['rsi12'] = calculate_rsi(df['close'], 12)
    df['rsi24'] = calculate_rsi(df['close'], 24)
    
    df['boll_upper'], df['boll_mid'], df['boll_lower'] = calculate_bollinger(df['close'])
    
    # 只保存最近10天
    df = df.tail(10)
    
    for _, row in df.iterrows():
        trade_date = row['date'].strftime('%Y%m%d')
        
        session.execute(text("""
            INSERT OR REPLACE INTO technical_indicators 
            (ticker, trade_date, ma5, ma10, ma20, ma60, 
             macd_dif, macd_dea, macd_hist, 
             rsi6, rsi12, rsi24,
             boll_upper, boll_mid, boll_lower)
            VALUES (:ticker, :trade_date, :ma5, :ma10, :ma20, :ma60,
                    :macd_dif, :macd_dea, :macd_hist,
                    :rsi6, :rsi12, :rsi24,
                    :boll_upper, :boll_mid, :boll_lower)
        """), {
            'ticker': ticker,
            'trade_date': trade_date,
            'ma5': None if pd.isna(row['ma5']) else float(row['ma5']),
            'ma10': None if pd.isna(row['ma10']) else float(row['ma10']),
            'ma20': None if pd.isna(row['ma20']) else float(row['ma20']),
            'ma60': None if pd.isna(row['ma60']) else float(row['ma60']),
            'macd_dif': None if pd.isna(row['macd_dif']) else float(row['macd_dif']),
            'macd_dea': None if pd.isna(row['macd_dea']) else float(row['macd_dea']),
            'macd_hist': None if pd.isna(row['macd_hist']) else float(row['macd_hist']),
            'rsi6': None if pd.isna(row['rsi6']) else float(row['rsi6']),
            'rsi12': None if pd.isna(row['rsi12']) else float(row['rsi12']),
            'rsi24': None if pd.isna(row['rsi24']) else float(row['rsi24']),
            'boll_upper': None if pd.isna(row['boll_upper']) else float(row['boll_upper']),
            'boll_mid': None if pd.isna(row['boll_mid']) else float(row['boll_mid']),
            'boll_lower': None if pd.isna(row['boll_lower']) else float(row['boll_lower']),
        })
    
    return True


def main():
    print("=" * 60, flush=True)
    print("  技术指标计算 (tushare)", flush=True)
    print(f"  时间: {datetime.now().strftime('%H:%M:%S')}", flush=True)
    print("=" * 60, flush=True)
    
    settings = get_settings()
    pro = ts.pro_api(settings.tushare_token)
    session = SessionLocal()
    
    try:
        watchlist = session.execute(select(Watchlist.ticker)).fetchall()
        tickers = [w[0] for w in watchlist]
        
        print(f"\n处理 {len(tickers)} 只股票...", flush=True)
        
        success = 0
        failed = 0
        
        for i, ticker in enumerate(tickers, 1):
            try:
                if calculate_and_save(pro, ticker, session):
                    success += 1
                else:
                    failed += 1
                
                if i % 20 == 0:
                    session.commit()
                    print(f"  [{i}/{len(tickers)}] 成功:{success} 失败:{failed}", flush=True)
                
                time.sleep(0.12)  # tushare 限流
                    
            except Exception as e:
                failed += 1
                continue
        
        session.commit()
        
        print(f"\n✅ 完成！成功: {success}, 失败: {failed}", flush=True)
        
        # 显示示例数据
        result = session.execute(text("""
            SELECT ticker, trade_date, ma5, ma20, rsi6, macd_hist
            FROM technical_indicators
            ORDER BY trade_date DESC, ticker
            LIMIT 5
        """)).fetchall()
        
        print("\n示例数据:", flush=True)
        for r in result:
            print(f"  {r[0]} {r[1]}: MA5={r[2]:.2f}, MA20={r[3]:.2f}, RSI={r[4]:.1f}, MACD={r[5]:.2f}", flush=True)
        
    finally:
        session.close()


if __name__ == '__main__':
    main()
