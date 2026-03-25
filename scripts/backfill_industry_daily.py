#!/usr/bin/env python3
"""
Backfill historical industry board daily data from TuShare

Gets industry list from TuShare `pro.ths_index(exchange='A', type='I')`,
then iterates over trading dates and fetches `pro.moneyflow_ind_ths(trade_date=date)`.

Uses INSERT OR IGNORE for idempotency and supports resume.

Usage:
    python scripts/backfill_industry_daily.py              # Full backfill
    python scripts/backfill_industry_daily.py --dry-run    # Dry run mode
    python scripts/backfill_industry_daily.py --start-date 20220101  # Custom start date
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.tushare_client import TushareClient
from src.config import get_settings
from src.database import SessionLocal
from src.models import IndustryDaily
from sqlalchemy import select, func


def parse_args():
    parser = argparse.ArgumentParser(description='Backfill industry board historical data')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no database writes)')
    parser.add_argument('--start-date', type=str, default='20210101', help='Start date YYYYMMDD (default: 20210101)')
    parser.add_argument('--end-date', type=str, help='End date YYYYMMDD (default: latest trade date)')
    parser.add_argument('--batch-size', type=int, default=50, help='Number of dates to process in one batch')
    return parser.parse_args()


def get_trading_dates(client: TushareClient, start_date: str, end_date: str) -> list[str]:
    """Get list of trading dates from trade calendar"""
    print(f"  获取交易日历 ({start_date} - {end_date})...")
    
    cal_df = client.fetch_trade_calendar(
        exchange='SSE',
        start_date=start_date,
        end_date=end_date
    )
    
    if cal_df.empty:
        return []
    
    # Filter for trading days only
    trading_days = sorted(
        cal_df[cal_df['is_open'] == 1]['cal_date'].tolist()
    )
    
    return trading_days


def main():
    args = parse_args()
    settings = get_settings()
    
    # Determine end date
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = datetime.now().strftime('%Y%m%d')
    
    print("=" * 80)
    print(f"  行业板块历史数据回填")
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  日期范围: {args.start_date} - {end_date}")
    print(f"  模式: {'DRY RUN (不写入数据库)' if args.dry_run else '正常模式'}")
    print("=" * 80)
    
    # Initialize TuShare client
    client = TushareClient(
        token=settings.tushare_token,
        points=settings.tushare_points,
        delay=0.35  # Slightly longer delay for historical data fetching
    )
    
    session = SessionLocal()
    
    try:
        # Step 1: Get industry board list
        print("\n[1/4] 获取行业板块列表...")
        industries_df = client.fetch_ths_index(exchange='A', type='I')
        
        if industries_df.empty:
            print("❌ 未获取到行业板块列表")
            return 1
        
        print(f"✓ 共找到 {len(industries_df)} 个行业板块")
        
        # Create industry lookup map
        industry_map = {row['ts_code']: row['name'] for _, row in industries_df.iterrows()}
        
        # Step 2: Get trading dates
        print("\n[2/4] 获取交易日历...")
        trading_dates = get_trading_dates(client, args.start_date, end_date)
        
        if not trading_dates:
            print("❌ 未获取到交易日期")
            return 1
        
        print(f"✓ 共 {len(trading_dates)} 个交易日")
        
        # Step 3: Check existing data
        print("\n[3/4] 检查已有数据...")
        existing_stats = session.execute(
            select(
                func.count(IndustryDaily.id).label('total_rows'),
                func.count(func.distinct(IndustryDaily.ts_code)).label('distinct_codes'),
                func.min(IndustryDaily.trade_date).label('min_date'),
                func.max(IndustryDaily.trade_date).label('max_date')
            )
        ).first()
        
        print(f"  现有数据: {existing_stats.total_rows} 行, {existing_stats.distinct_codes} 个行业")
        if existing_stats.min_date:
            print(f"  日期范围: {existing_stats.min_date} - {existing_stats.max_date}")
        
        # Find dates that need backfilling
        existing_dates = set(
            session.execute(
                select(func.distinct(IndustryDaily.trade_date))
            ).scalars().all()
        )
        
        dates_to_process = [d for d in trading_dates if d not in existing_dates]
        
        if not dates_to_process:
            print("  ✓ 所有日期数据已存在，无需回填")
            return 0
        
        print(f"  需要回填: {len(dates_to_process)} 个交易日")
        
        # Step 4: Backfill by date
        print(f"\n[4/4] 开始回填历史数据...")
        print(f"  方法: 遍历交易日，使用 moneyflow_ind_ths(trade_date=date)")
        print()
        
        total_dates = len(dates_to_process)
        success_count = 0
        error_count = 0
        total_new_rows = 0
        
        start_time = time.time()
        
        for idx, trade_date in enumerate(dates_to_process, 1):
            print(f"[{idx}/{total_dates}] {trade_date}")
            
            try:
                # Fetch industry money flow for this date
                df = client.fetch_ths_industry_moneyflow(trade_date=trade_date)
                
                if df is None or df.empty:
                    print(f"  ⚠️ 未获取到数据 (可能非交易日或数据未发布)")
                    error_count += 1
                    continue
                
                print(f"  获取到 {len(df)} 个行业数据")
                
                # Process and insert data
                new_rows = 0
                
                if not args.dry_run:
                    for _, data_row in df.iterrows():
                        ts_code = data_row['ts_code']
                        industry_name = industry_map.get(ts_code, data_row.get('name', ''))
                        
                        # Check if record already exists (INSERT OR IGNORE logic)
                        existing = session.execute(
                            select(IndustryDaily)
                            .where(IndustryDaily.ts_code == ts_code)
                            .where(IndustryDaily.trade_date == trade_date)
                        ).first()
                        
                        if existing:
                            continue
                        
                        # Create new record
                        industry_record = IndustryDaily(
                            trade_date=trade_date,
                            ts_code=ts_code,
                            industry=industry_name,
                            close=float(data_row.get('close', 0) or 0),
                            pct_change=float(data_row.get('pct_change', 0) or 0),
                            company_num=int(data_row.get('count', 0) or 0),
                            # Money flow fields
                            net_amount=float(data_row.get('net_amount', 0) or 0),
                            net_buy_amount=float(data_row.get('buy_elg_amount', 0) or 0),
                            net_sell_amount=float(data_row.get('sell_elg_amount', 0) or 0),
                            # Additional fields from response
                            close_price=float(data_row.get('close', 0) or 0),
                            industry_pe=float(data_row.get('pe', 0) or 0) if 'pe' in data_row else None,
                            pe_median=float(data_row.get('pe_median', 0) or 0) if 'pe_median' in data_row else None,
                            total_mv=float(data_row.get('total_mv', 0) or 0) if 'total_mv' in data_row else None,
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        
                        session.add(industry_record)
                        new_rows += 1
                    
                    # Commit after each date to enable resume
                    session.commit()
                    print(f"  ✓ 新增 {new_rows} 条记录")
                else:
                    print(f"  (DRY RUN: 将新增 ~{len(df)} 条记录)")
                
                total_new_rows += new_rows
                success_count += 1
                
            except Exception as e:
                print(f"  ❌ 失败: {e}")
                error_count += 1
                session.rollback()
                
                # Don't stop on error, continue with next date
                continue
            
            # Progress indicator every 50 dates
            if idx % 50 == 0:
                elapsed = time.time() - start_time
                avg_time = elapsed / idx
                remaining = avg_time * (total_dates - idx)
                print(f"  进度: {idx}/{total_dates} ({100*idx/total_dates:.1f}%), 预计剩余: {remaining/60:.1f} 分钟")
        
        elapsed = time.time() - start_time
        
        # Summary
        print()
        print("=" * 80)
        print(f"回填完成")
        print(f"  总耗时: {elapsed/60:.1f} 分钟")
        print(f"  成功: {success_count} 个交易日")
        print(f"  失败: {error_count} 个交易日")
        if not args.dry_run:
            print(f"  新增记录: {total_new_rows} 条")
        print()
        
        # Final verification
        if not args.dry_run:
            final_stats = session.execute(
                select(
                    func.count(IndustryDaily.id).label('total_rows'),
                    func.count(func.distinct(IndustryDaily.ts_code)).label('distinct_codes'),
                    func.min(IndustryDaily.trade_date).label('min_date'),
                    func.max(IndustryDaily.trade_date).label('max_date')
                )
            ).first()
            
            print("回填后数据统计:")
            print(f"  总记录数: {final_stats.total_rows}")
            print(f"  行业板块数: {final_stats.distinct_codes}")
            print(f"  日期范围: {final_stats.min_date} - {final_stats.max_date}")
            
            # Check if we meet the 2-year minimum requirement
            if final_stats.min_date and final_stats.min_date <= '20240325':
                print(f"  ✓ 满足最低要求 (最早日期 <= 20240325)")
            else:
                print(f"  ⚠️ 未满足最低要求 (最早日期应 <= 20240325, 实际: {final_stats.min_date})")
        
        print("=" * 80)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断，数据已保存至最后一次提交")
        return 1
    except Exception as e:
        print(f"\n❌ 致命错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()


if __name__ == '__main__':
    sys.exit(main())
