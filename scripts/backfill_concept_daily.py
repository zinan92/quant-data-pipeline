#!/usr/bin/env python3
"""
Backfill historical concept board daily data from TuShare

Gets concept board list from TuShare `pro.ths_index(exchange='A', type='N')`,
then fetches historical daily data via `pro.ths_daily(ts_code=code, start_date='20210101')`.

Uses INSERT OR IGNORE for idempotency and supports resume.

Usage:
    python scripts/backfill_concept_daily.py              # Full backfill
    python scripts/backfill_concept_daily.py --dry-run    # Dry run mode
    python scripts/backfill_concept_daily.py --start-date 20220101  # Custom start date
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.tushare_client import TushareClient
from src.config import get_settings
from src.database import SessionLocal
from src.models import ConceptDaily
from sqlalchemy import select, func


def parse_args():
    parser = argparse.ArgumentParser(description='Backfill concept board historical data')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no database writes)')
    parser.add_argument('--start-date', type=str, default='20210101', help='Start date YYYYMMDD (default: 20210101)')
    parser.add_argument('--limit', type=int, help='Limit number of concepts to process (for testing)')
    return parser.parse_args()


def main():
    args = parse_args()
    settings = get_settings()
    
    print("=" * 80)
    print(f"  概念板块历史数据回填")
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  起始日期: {args.start_date}")
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
        # Step 1: Get concept board list
        print("\n[1/3] 获取概念板块列表...")
        concepts_df = client.fetch_ths_index(exchange='A', type='N')
        
        if concepts_df.empty:
            print("❌ 未获取到概念板块列表")
            return 1
        
        print(f"✓ 共找到 {len(concepts_df)} 个概念板块")
        
        # Apply limit if specified
        if args.limit:
            concepts_df = concepts_df.head(args.limit)
            print(f"  (测试模式：仅处理前 {args.limit} 个)")
        
        # Step 2: Check existing data and determine resume point
        print("\n[2/3] 检查已有数据...")
        existing_stats = session.execute(
            select(
                func.count(ConceptDaily.id).label('total_rows'),
                func.count(func.distinct(ConceptDaily.code)).label('distinct_codes'),
                func.min(ConceptDaily.trade_date).label('min_date'),
                func.max(ConceptDaily.trade_date).label('max_date')
            )
        ).first()
        
        print(f"  现有数据: {existing_stats.total_rows} 行, {existing_stats.distinct_codes} 个板块")
        if existing_stats.min_date:
            print(f"  日期范围: {existing_stats.min_date} - {existing_stats.max_date}")
        
        # Step 3: Backfill each concept
        print(f"\n[3/3] 开始回填历史数据 (从 {args.start_date})...")
        print(f"  注意: ths_daily() 需要 5000+ 积分，历史深度可能有限")
        print()
        
        total_concepts = len(concepts_df)
        success_count = 0
        skip_count = 0
        error_count = 0
        total_new_rows = 0
        
        start_time = time.time()
        
        for idx, row in concepts_df.iterrows():
            ts_code = row['ts_code']
            name = row['name']
            
            print(f"[{idx+1}/{total_concepts}] {name} ({ts_code})")
            
            # Check if we already have data for this concept
            existing_max_date = session.execute(
                select(func.max(ConceptDaily.trade_date))
                .where(ConceptDaily.code == ts_code)
            ).scalar()
            
            if existing_max_date and existing_max_date >= args.start_date:
                # Already have some data, check if complete
                existing_count = session.execute(
                    select(func.count(ConceptDaily.id))
                    .where(ConceptDaily.code == ts_code)
                    .where(ConceptDaily.trade_date >= args.start_date)
                ).scalar()
                
                print(f"  已有 {existing_count} 条数据 (最新: {existing_max_date}), 跳过")
                skip_count += 1
                continue
            
            try:
                # Fetch historical daily data using pro.ths_daily
                # Note: This requires 5000+ points
                df = client.pro.ths_daily(
                    ts_code=ts_code,
                    start_date=args.start_date
                )
                
                if df is None or df.empty:
                    print(f"  ⚠️ 未获取到历史数据 (可能该板块上线较晚)")
                    skip_count += 1
                    continue
                
                print(f"  获取到 {len(df)} 条历史数据")
                
                # Process and insert data
                new_rows = 0
                
                if not args.dry_run:
                    for _, data_row in df.iterrows():
                        trade_date = str(data_row['trade_date'])
                        
                        # Check if record already exists (INSERT OR IGNORE logic)
                        existing = session.execute(
                            select(ConceptDaily)
                            .where(ConceptDaily.code == ts_code)
                            .where(ConceptDaily.trade_date == trade_date)
                        ).first()
                        
                        if existing:
                            continue
                        
                        # Create new record
                        concept_record = ConceptDaily(
                            trade_date=trade_date,
                            code=ts_code,
                            name=name,
                            open=float(data_row.get('open', 0) or 0),
                            high=float(data_row.get('high', 0) or 0),
                            low=float(data_row.get('low', 0) or 0),
                            close=float(data_row.get('close', 0) or 0),
                            pct_change=float(data_row.get('pct_change', 0) or 0),
                            volume=float(data_row.get('vol', 0) or 0),
                            amount=float(data_row.get('amount', 0) or 0),
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        
                        session.add(concept_record)
                        new_rows += 1
                    
                    # Commit after each concept to enable resume
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
                
                # Don't stop on error, continue with next concept
                continue
        
        elapsed = time.time() - start_time
        
        # Summary
        print()
        print("=" * 80)
        print(f"回填完成")
        print(f"  总耗时: {elapsed/60:.1f} 分钟")
        print(f"  成功: {success_count} 个板块")
        print(f"  跳过: {skip_count} 个板块 (已有数据)")
        print(f"  失败: {error_count} 个板块")
        if not args.dry_run:
            print(f"  新增记录: {total_new_rows} 条")
        print()
        
        # Final verification
        if not args.dry_run:
            final_stats = session.execute(
                select(
                    func.count(ConceptDaily.id).label('total_rows'),
                    func.count(func.distinct(ConceptDaily.code)).label('distinct_codes'),
                    func.min(ConceptDaily.trade_date).label('min_date'),
                    func.max(ConceptDaily.trade_date).label('max_date')
                )
            ).first()
            
            print("回填后数据统计:")
            print(f"  总记录数: {final_stats.total_rows}")
            print(f"  概念板块数: {final_stats.distinct_codes}")
            print(f"  日期范围: {final_stats.min_date} - {final_stats.max_date}")
            
            # Check if we meet the 2-year minimum requirement
            if final_stats.min_date and final_stats.min_date <= '20240325':
                print(f"  ✓ 满足最低要求 (最早日期 <= 20240325)")
            else:
                print(f"  ⚠️ 未满足最低要求 (最早日期应 <= 20240325, 实际: {final_stats.min_date})")
                print(f"  注意: TuShare ths_daily() 历史深度可能受限")
        
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
