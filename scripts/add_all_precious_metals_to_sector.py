#!/usr/bin/env python3
"""
批量添加贵金属股票到赛道分类
将所有贵金属板块的股票添加到 stock_sectors 表，设置 sector = '贵金属'
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from src.models.board import BoardMapping
from src.models.symbol import SymbolMetadata
from sqlalchemy import text
from sqlalchemy.orm import Session


def add_stock_to_sector(
    session: Session,
    ticker: str,
    stock_name: str,
    sector: str
) -> bool:
    """
    添加或更新股票的赛道分类

    Args:
        session: Database session
        ticker: Stock ticker (e.g., '601899')
        stock_name: Stock name for display
        sector: Sector name (e.g., '贵金属')

    Returns:
        True if added/updated, False if already exists with same sector
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 检查是否已存在
    existing = session.execute(
        text("SELECT sector FROM stock_sectors WHERE ticker = :ticker"),
        {"ticker": ticker}
    ).fetchone()

    if existing:
        old_sector = existing[0]
        if old_sector == sector:
            print(f"  {stock_name} ({ticker}) - 已是{sector}赛道")
            return False
        else:
            # 更新
            session.execute(
                text("UPDATE stock_sectors SET sector = :sector, updated_at = :now WHERE ticker = :ticker"),
                {"ticker": ticker, "sector": sector, "now": now}
            )
            session.commit()
            print(f"✓ {stock_name} ({ticker}) - 赛道更新: {old_sector} → {sector}")
            return True
    else:
        # 插入
        session.execute(
            text("INSERT INTO stock_sectors (ticker, sector, created_at, updated_at) VALUES (:ticker, :sector, :now, :now)"),
            {"ticker": ticker, "sector": sector, "now": now}
        )
        session.commit()
        print(f"✓ {stock_name} ({ticker}) - 已添加到{sector}赛道")
        return True


def main():
    """主函数"""
    db = SessionLocal()

    try:
        print("="*60)
        print("批量添加贵金属股票到赛道分类")
        print("="*60)

        # 1. 从贵金属板块获取所有成分股
        precious_board = db.query(BoardMapping).filter(
            BoardMapping.board_code == '881169.TI'
        ).first()

        if not precious_board:
            print("✗ 未找到贵金属板块 (881169.TI)")
            return 1

        if not precious_board.constituents:
            print("✗ 贵金属板块没有成分股")
            return 1

        tickers = precious_board.constituents
        print(f"\n贵金属板块 (881169.TI) 包含 {len(tickers)} 只股票")
        print(f"成分股: {sorted(tickers)}")

        # 2. 批量添加到 stock_sectors
        print(f"\n开始批量添加到 stock_sectors 表...")
        print("-"*60)

        added_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

        for ticker in sorted(tickers):
            # 获取股票名称
            symbol = db.query(SymbolMetadata).filter(
                SymbolMetadata.ticker == ticker
            ).first()

            if not symbol:
                print(f"✗ 未找到股票信息: {ticker}")
                error_count += 1
                continue

            stock_name = symbol.name

            # 检查当前赛道
            existing = db.execute(
                text("SELECT sector FROM stock_sectors WHERE ticker = :ticker"),
                {"ticker": ticker}
            ).fetchone()

            if existing and existing[0] == '贵金属':
                print(f"  {stock_name} ({ticker}) - 已是贵金属赛道")
                skipped_count += 1
            elif existing:
                # 更新
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                old_sector = existing[0]
                db.execute(
                    text("UPDATE stock_sectors SET sector = :sector, updated_at = :now WHERE ticker = :ticker"),
                    {"ticker": ticker, "sector": "贵金属", "now": now}
                )
                db.commit()
                print(f"✓ {stock_name} ({ticker}) - 赛道更新: {old_sector} → 贵金属")
                updated_count += 1
            else:
                # 插入
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                db.execute(
                    text("INSERT INTO stock_sectors (ticker, sector, created_at, updated_at) VALUES (:ticker, :sector, :now, :now)"),
                    {"ticker": ticker, "sector": "贵金属", "now": now}
                )
                db.commit()
                print(f"✓ {stock_name} ({ticker}) - 已添加到贵金属赛道")
                added_count += 1

        # 3. 显示统计
        print("\n" + "="*60)
        print("完成统计:")
        print(f"  新增: {added_count} 只")
        print(f"  更新: {updated_count} 只")
        print(f"  跳过: {skipped_count} 只 (已是贵金属赛道)")
        print(f"  错误: {error_count} 只")
        print("="*60)

        # 4. 验证结果
        print("\n验证 stock_sectors 表中的贵金属股票:")
        result = db.execute(
            text("SELECT ticker FROM stock_sectors WHERE sector = '贵金属' ORDER BY ticker")
        ).fetchall()

        precious_tickers = [row[0] for row in result]
        print(f"贵金属赛道共 {len(precious_tickers)} 只股票:")

        # 显示股票名称
        for ticker in precious_tickers:
            symbol = db.query(SymbolMetadata).filter(
                SymbolMetadata.ticker == ticker
            ).first()
            if symbol:
                print(f"  - {symbol.name} ({ticker})")

        print("\n" + "="*60)
        print("✓ 所有操作完成")
        print("="*60)

    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        db.close()

    return 0


if __name__ == "__main__":
    exit(main())
