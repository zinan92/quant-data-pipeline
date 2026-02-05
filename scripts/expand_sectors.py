#!/usr/bin/env python3
"""
扩充赛道库存 + 新增金融赛道
根据 2026-02-05 Park确认的方案执行
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from datetime import datetime
from src.database import session_scope
from src.models import SymbolMetadata, Watchlist
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "market.db"

# ============================================================
# 待添加的股票清单
# ============================================================

STOCKS_TO_ADD = {
    "脑机接口": [
        ("688580", "伟思医疗"),
        ("300753", "爱朋医疗"),
        ("688626", "翔宇医疗"),
        ("300430", "诚益通"),
        ("688709", "成都华微"),
        ("688351", "微电生理"),
        ("002414", "高德红外"),
        ("300678", "中科信息"),
    ],
    "可控核聚变": [
        ("601985", "中国核电"),
        ("600875", "东方电气"),
        ("688776", "国光电气"),
        ("002318", "久立特材"),
        ("300471", "厚普股份"),
        ("600468", "百利电气"),
        ("600105", "永鼎股份"),
    ],
    "半导体": [
        ("688012", "中微公司"),
        ("688082", "盛美上海"),
        ("688396", "华润微"),
    ],
    "PCB": [
        ("300739", "明阳电路"),
        ("300814", "中富电路"),
        ("603920", "世运电路"),
    ],
    "消费": [
        ("000858", "五粮液"),
        ("000568", "泸州老窖"),
        ("600887", "伊利股份"),
        ("000895", "双汇发展"),
        ("002507", "涪陵榨菜"),
        ("600809", "山西汾酒"),
    ],
    "金融": [
        # 银行
        ("601398", "工商银行"),
        ("600036", "招商银行"),
        ("601838", "成都银行"),
        ("601128", "常熟银行"),
        # 保险
        ("601318", "中国平安"),
        ("601628", "中国人寿"),
        ("601319", "中国人保"),
        # 证券
        ("600030", "中信证券"),
        ("300059", "东方财富"),
        ("601995", "中金公司"),
    ],
}


def ensure_symbol_metadata(session, ticker, name):
    """确保 symbol_metadata 中存在该股票"""
    existing = session.query(SymbolMetadata).filter(SymbolMetadata.ticker == ticker).first()
    if existing:
        return True, "exists"
    
    meta = SymbolMetadata(
        ticker=ticker,
        name=name,
        last_sync=datetime.utcnow(),
    )
    session.add(meta)
    return True, "created"


def ensure_watchlist(session, ticker, category):
    """确保 watchlist 中存在该股票"""
    existing = session.query(Watchlist).filter(Watchlist.ticker == ticker).first()
    if existing:
        # 如果已存在但category不同，更新category
        if existing.category != category:
            old_cat = existing.category
            existing.category = category
            return "updated", f"{old_cat} → {category}"
        return "exists", existing.category
    
    item = Watchlist(
        ticker=ticker,
        added_at=datetime.utcnow(),
        category=category,
        is_focus=0,
    )
    session.add(item)
    return "created", category


def ensure_stock_sector(conn, ticker, sector):
    """确保 stock_sectors 中存在该股票"""
    cursor = conn.execute("SELECT sector FROM stock_sectors WHERE ticker = ?", (ticker,))
    row = cursor.fetchone()
    if row:
        if row[0] != sector:
            conn.execute(
                "UPDATE stock_sectors SET sector = ?, updated_at = ? WHERE ticker = ?",
                (sector, datetime.utcnow().isoformat(), ticker)
            )
            return "updated", f"{row[0]} → {sector}"
        return "exists", row[0]
    
    conn.execute(
        "INSERT INTO stock_sectors (ticker, sector, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (ticker, sector, datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
    )
    return "created", sector


def ensure_available_sector(conn, sector_name):
    """确保 available_sectors 中存在该赛道"""
    cursor = conn.execute("SELECT id FROM available_sectors WHERE name = ?", (sector_name,))
    if cursor.fetchone():
        return False
    
    # 获取最大 display_order
    cursor = conn.execute("SELECT MAX(display_order) FROM available_sectors")
    max_order = cursor.fetchone()[0] or 0
    
    conn.execute(
        "INSERT INTO available_sectors (name, display_order, created_at) VALUES (?, ?, ?)",
        (sector_name, max_order + 1, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
    )
    return True


def main():
    print("=" * 70)
    print("🚀 赛道库存扩充 + 新增金融赛道")
    print("=" * 70)
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 1. 确保"金融"赛道存在
    if ensure_available_sector(conn, "金融"):
        print("\n✅ 新增赛道: 金融")
    else:
        print("\n📋 赛道已存在: 金融")
    conn.commit()
    
    # 2. 逐赛道添加股票
    total_meta_created = 0
    total_wl_created = 0
    total_sector_created = 0
    total_updated = 0
    total_skipped = 0
    
    with session_scope() as session:
        for sector, stocks in STOCKS_TO_ADD.items():
            print(f"\n{'─' * 50}")
            print(f"📂 {sector} (+{len(stocks)})")
            print(f"{'─' * 50}")
            
            for ticker, name in stocks:
                # symbol_metadata
                _, meta_status = ensure_symbol_metadata(session, ticker, name)
                if meta_status == "created":
                    total_meta_created += 1
                
                # watchlist
                wl_status, wl_detail = ensure_watchlist(session, ticker, sector)
                if wl_status == "created":
                    total_wl_created += 1
                elif wl_status == "updated":
                    total_updated += 1
                else:
                    total_skipped += 1
                
                # stock_sectors (via raw SQL since it's not ORM)
                sec_status, sec_detail = ensure_stock_sector(conn, ticker, sector)
                if sec_status == "created":
                    total_sector_created += 1
                
                status_emoji = {"created": "✅", "updated": "🔄", "exists": "⏭️"}
                print(f"  {status_emoji.get(wl_status, '❓')} {ticker} {name} [{wl_status}]")
    
    conn.commit()
    
    # 3. 最终统计
    print(f"\n{'=' * 70}")
    print("📊 执行结果")
    print(f"{'=' * 70}")
    
    # 重新统计各赛道
    cursor = conn.execute("""
        SELECT sector, COUNT(*) 
        FROM stock_sectors 
        GROUP BY sector 
        ORDER BY COUNT(*) DESC
    """)
    
    print(f"\n新增元数据: {total_meta_created}")
    print(f"新增自选:   {total_wl_created}")
    print(f"更新分类:   {total_updated}")
    print(f"已存在跳过: {total_skipped}")
    
    print(f"\n{'─' * 40}")
    print("赛道库存 (更新后)")
    print(f"{'─' * 40}")
    for sector, count in cursor.fetchall():
        indicator = "🟢" if count >= 20 else ("🟡" if count >= 10 else "🔴")
        print(f"  {indicator} {sector}: {count}")
    
    conn.close()
    print(f"\n✅ Done!")


if __name__ == "__main__":
    main()
