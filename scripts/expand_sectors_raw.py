#!/usr/bin/env python3
"""
扩充赛道库存 + 新增金融赛道 (纯SQLite版本)
根据 2026-02-05 Park确认的方案执行
"""
import sqlite3
from datetime import datetime, timezone
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
        ("601398", "工商银行"),
        ("600036", "招商银行"),
        ("601838", "成都银行"),
        ("601128", "常熟银行"),
        ("601318", "中国平安"),
        ("601628", "中国人寿"),
        ("601319", "中国人保"),
        ("600030", "中信证券"),
        ("300059", "东方财富"),
        ("601995", "中金公司"),
    ],
}

def now_str():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

def main():
    print("=" * 70)
    print("🚀 赛道库存扩充 + 新增金融赛道")
    print("=" * 70)
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 1. 确保"金融"赛道存在
    cursor = conn.execute("SELECT id FROM available_sectors WHERE name = '金融'")
    if not cursor.fetchone():
        cursor = conn.execute("SELECT MAX(display_order) FROM available_sectors")
        max_order = cursor.fetchone()[0] or 0
        conn.execute(
            "INSERT INTO available_sectors (name, display_order, created_at) VALUES (?, ?, ?)",
            ("金融", max_order + 1, now_str())
        )
        print("\n✅ 新增赛道: 金融")
    else:
        print("\n📋 赛道已存在: 金融")
    
    # 2. 逐赛道添加股票
    stats = {"meta_new": 0, "wl_new": 0, "wl_updated": 0, "sector_new": 0, "skipped": 0}
    
    for sector, stocks in STOCKS_TO_ADD.items():
        print(f"\n{'─' * 50}")
        print(f"📂 {sector} (+{len(stocks)})")
        print(f"{'─' * 50}")
        
        for ticker, name in stocks:
            # symbol_metadata
            cursor = conn.execute("SELECT ticker FROM symbol_metadata WHERE ticker = ?", (ticker,))
            if not cursor.fetchone():
                conn.execute(
                    "INSERT INTO symbol_metadata (ticker, name, last_sync) VALUES (?, ?, ?)",
                    (ticker, name, now_str())
                )
                stats["meta_new"] += 1
            
            # watchlist
            cursor = conn.execute("SELECT category FROM watchlist WHERE ticker = ?", (ticker,))
            row = cursor.fetchone()
            if row:
                if row[0] != sector:
                    conn.execute(
                        "UPDATE watchlist SET category = ? WHERE ticker = ?",
                        (sector, ticker)
                    )
                    print(f"  🔄 {ticker} {name} [watchlist: {row[0]} → {sector}]")
                    stats["wl_updated"] += 1
                else:
                    print(f"  ⏭️  {ticker} {name} [exists]")
                    stats["skipped"] += 1
            else:
                conn.execute(
                    "INSERT INTO watchlist (ticker, added_at, category, is_focus) VALUES (?, ?, ?, 0)",
                    (ticker, now_str(), sector)
                )
                print(f"  ✅ {ticker} {name} [added]")
                stats["wl_new"] += 1
            
            # stock_sectors
            cursor = conn.execute("SELECT sector FROM stock_sectors WHERE ticker = ?", (ticker,))
            row = cursor.fetchone()
            if row:
                if row[0] != sector:
                    conn.execute(
                        "UPDATE stock_sectors SET sector = ?, updated_at = ? WHERE ticker = ?",
                        (sector, now_str(), ticker)
                    )
            else:
                conn.execute(
                    "INSERT INTO stock_sectors (ticker, sector, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (ticker, sector, now_str(), now_str())
                )
                stats["sector_new"] += 1
    
    conn.commit()
    
    # 3. 最终统计
    print(f"\n{'=' * 70}")
    print("📊 执行结果")
    print(f"{'=' * 70}")
    print(f"新增元数据: {stats['meta_new']}")
    print(f"新增自选:   {stats['wl_new']}")
    print(f"更新分类:   {stats['wl_updated']}")
    print(f"新增赛道:   {stats['sector_new']}")
    print(f"已存在跳过: {stats['skipped']}")
    
    # 赛道库存总览
    print(f"\n{'─' * 40}")
    print("赛道库存 (更新后)")
    print(f"{'─' * 40}")
    cursor = conn.execute("""
        SELECT sector, COUNT(*) as cnt
        FROM stock_sectors 
        GROUP BY sector 
        ORDER BY cnt DESC
    """)
    total = 0
    for sector, count in cursor.fetchall():
        indicator = "🟢" if count >= 20 else ("🟡" if count >= 10 else "🔴")
        print(f"  {indicator} {sector}: {count}")
        total += count
    print(f"  {'─' * 30}")
    print(f"  总计: {total} 只")
    
    conn.close()
    print(f"\n✅ Done!")


if __name__ == "__main__":
    main()
