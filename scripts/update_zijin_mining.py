#!/usr/bin/env python3
"""
更新紫金矿业的分类和自选股
1. 将紫金矿业的 industry_lv1 从"工业金属"改为"贵金属"
2. 添加紫金矿业到自选股板块
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from src.models.board import BoardMapping
from src.models.symbol import SymbolMetadata
from sqlalchemy.orm import Session


def update_industry_classification(session: Session, ticker: str, new_industry: str):
    """更新股票的行业分类"""
    symbol = session.query(SymbolMetadata).filter(
        SymbolMetadata.ticker == ticker
    ).first()

    if not symbol:
        print(f"✗ 未找到股票: {ticker}")
        return False

    old_industry = symbol.industry_lv1
    symbol.industry_lv1 = new_industry
    session.commit()

    print(f"✓ {symbol.name} ({ticker})")
    print(f"  行业分类: {old_industry} → {new_industry}")
    return True


def add_to_watchlist(session: Session, ticker: str, stock_name: str):
    """添加股票到自选股板块"""
    # 查找自选股板块
    watchlist = session.query(BoardMapping).filter(
        BoardMapping.board_name == '自选股'
    ).first()

    # 如果不存在，创建自选股板块
    if not watchlist:
        print("\n创建自选股板块...")
        watchlist = BoardMapping(
            board_code='WATCHLIST',
            board_name='自选股',
            board_type='custom',
            constituents=[]
        )
        session.add(watchlist)
        session.flush()
        print(f"✓ 自选股板块已创建 (board_code: {watchlist.board_code})")

    # 检查是否已存在
    if watchlist.constituents and ticker in watchlist.constituents:
        print(f"  {stock_name} ({ticker}) - 已在自选股中")
        return False

    # 添加到自选股
    if watchlist.constituents is None:
        watchlist.constituents = []

    watchlist.constituents = list(set(watchlist.constituents + [ticker]))
    session.commit()

    print(f"✓ {stock_name} ({ticker}) - 已添加到自选股")
    return True


def update_sector_classification(session: Session, ticker: str, new_sector: str):
    """更新股票的赛道分类（stock_sectors表）"""
    from datetime import datetime
    from sqlalchemy import text

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 检查当前赛道
    result = session.execute(
        text("SELECT sector FROM stock_sectors WHERE ticker = :ticker"),
        {"ticker": ticker}
    ).fetchone()

    if result:
        old_sector = result[0]
        session.execute(
            text("UPDATE stock_sectors SET sector = :sector, updated_at = :now WHERE ticker = :ticker"),
            {"ticker": ticker, "sector": new_sector, "now": now}
        )
        session.commit()
        print(f"✓ 赛道分类: {old_sector} → {new_sector}")
        return True
    else:
        print(f"✗ stock_sectors 中未找到 {ticker}")
        return False


def main():
    """主函数"""
    db = SessionLocal()

    try:
        print("="*60)
        print("更新紫金矿业分类和自选股")
        print("="*60)

        ticker = '601899'
        stock_name = '紫金矿业'

        # 1. 更新行业分类 (symbol_metadata.industry_lv1)
        print(f"\n1. 更新行业分类 (symbol_metadata)")
        update_industry_classification(db, ticker, '贵金属')

        # 2. 更新赛道分类 (stock_sectors.sector)
        print(f"\n2. 更新赛道分类 (stock_sectors)")
        update_sector_classification(db, ticker, '贵金属')

        # 3. 添加到自选股
        print(f"\n3. 添加到自选股")
        add_to_watchlist(db, ticker, stock_name)

        # 4. 验证结果
        print("\n" + "="*60)
        print("验证结果:")
        print("="*60)

        # 检查 symbol_metadata
        symbol = db.query(SymbolMetadata).filter(
            SymbolMetadata.ticker == ticker
        ).first()
        print(f"\n1. Symbol Metadata:")
        print(f"   {symbol.name} ({symbol.ticker})")
        print(f"   Industry L1: {symbol.industry_lv1}")

        # 检查 stock_sectors
        from sqlalchemy import text
        sector_result = db.execute(
            text("SELECT sector FROM stock_sectors WHERE ticker = :ticker"),
            {"ticker": ticker}
        ).fetchone()
        print(f"\n2. Stock Sectors:")
        print(f"   Sector: {sector_result[0] if sector_result else 'N/A'}")

        # 检查贵金属板块
        precious_metal = db.query(BoardMapping).filter(
            BoardMapping.board_code == '881169.TI'
        ).first()
        print(f"\n3. 贵金属板块 (881169.TI):")
        print(f"   成分股数: {len(precious_metal.constituents) if precious_metal.constituents else 0}")
        print(f"   包含紫金矿业: {'601899' in (precious_metal.constituents or [])}")

        # 检查自选股
        watchlist = db.query(BoardMapping).filter(
            BoardMapping.board_name == '自选股'
        ).first()
        print(f"\n4. 自选股:")
        print(f"   Board Code: {watchlist.board_code}")
        print(f"   成分股数: {len(watchlist.constituents) if watchlist.constituents else 0}")
        print(f"   包含紫金矿业: {'601899' in (watchlist.constituents or [])}")
        if watchlist.constituents:
            print(f"   成分股列表: {sorted(watchlist.constituents)}")

        print("\n" + "="*60)
        print("✓ 更新完成")
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
