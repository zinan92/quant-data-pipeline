#!/usr/bin/env python3
"""
自选股备份脚本
导出 watchlist 数据为 JSON 文件，便于版本控制和恢复
"""

import sys
from pathlib import Path
import json
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from sqlalchemy import text


def backup_watchlist():
    """备份自选股数据"""

    db = SessionLocal()

    try:
        # 创建备份目录
        backup_dir = project_root / "backups"
        backup_dir.mkdir(exist_ok=True)

        print("="*60)
        print("自选股备份工具")
        print("="*60)

        # 1. 获取所有自选股数据
        result = db.execute(text("""
            SELECT
                w.ticker,
                w.added_at,
                w.purchase_price,
                w.purchase_date,
                w.shares,
                w.category,
                w.is_focus,
                s.name
            FROM watchlist w
            LEFT JOIN symbol_metadata s ON w.ticker = s.ticker
            ORDER BY w.added_at DESC
        """)).fetchall()

        print(f"\n读取到 {len(result)} 只自选股")

        # 2. 转换为字典列表
        watchlist_data = []
        for r in result:
            watchlist_data.append({
                'ticker': r[0],
                'name': r[7] if r[7] else r[0],
                'added_at': r[1],
                'purchase_price': r[2],
                'purchase_date': r[3],
                'shares': r[4],
                'category': r[5],
                'is_focus': bool(r[6])
            })

        # 3. 生成备份文件
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 完整备份（包含所有信息）
        full_backup_file = backup_dir / f"watchlist_full_{timestamp}.json"
        with open(full_backup_file, 'w', encoding='utf-8') as f:
            json.dump({
                'backup_time': datetime.now().isoformat(),
                'total_count': len(watchlist_data),
                'data': watchlist_data
            }, f, ensure_ascii=False, indent=2)

        print(f"✓ 完整备份: {full_backup_file}")

        # 轻量级备份（只保留核心信息）
        lite_data = [
            {
                'ticker': item['ticker'],
                'name': item['name'],
                'category': item['category'],
                'is_focus': item['is_focus']
            }
            for item in watchlist_data
        ]

        lite_backup_file = backup_dir / "watchlist_latest.json"
        with open(lite_backup_file, 'w', encoding='utf-8') as f:
            json.dump({
                'backup_time': datetime.now().isoformat(),
                'total_count': len(lite_data),
                'data': lite_data
            }, f, ensure_ascii=False, indent=2)

        print(f"✓ 轻量备份: {lite_backup_file}")

        # 4. 统计信息
        print("\n" + "="*60)
        print("备份统计:")
        print("="*60)

        from collections import Counter
        categories = Counter([item['category'] if item['category'] else '未分类'
                            for item in watchlist_data])

        print(f"\n总数: {len(watchlist_data)} 只")
        print(f"\n分类统计:")
        for cat, count in categories.most_common(10):
            print(f"  {cat:15s}: {count:3d} 只")

        focus_count = sum(1 for item in watchlist_data if item['is_focus'])
        print(f"\n重点关注: {focus_count} 只")

        # 5. 导出为简单的 ticker 列表（用于快速恢复）
        tickers_file = backup_dir / "watchlist_tickers.txt"
        with open(tickers_file, 'w', encoding='utf-8') as f:
            for item in watchlist_data:
                focus_mark = '★' if item['is_focus'] else ''
                f.write(f"{item['ticker']}\t{item['name']}\t{item['category']}\t{focus_mark}\n")

        print(f"\n✓ Ticker列表: {tickers_file}")

        print("\n" + "="*60)
        print("✓ 备份完成")
        print("="*60)

        return 0

    except Exception as e:
        print(f"\n✗ 备份失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        db.close()


def restore_watchlist(backup_file):
    """从备份恢复自选股数据"""

    db = SessionLocal()

    try:
        print("="*60)
        print("自选股恢复工具")
        print("="*60)

        # 读取备份文件
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)

        watchlist_data = backup_data['data']
        print(f"\n备份时间: {backup_data['backup_time']}")
        print(f"记录数: {len(watchlist_data)}")

        # 询问是否继续
        print("\n⚠️  警告: 恢复操作会清空当前自选股数据！")
        confirm = input("确认恢复? (yes/no): ")

        if confirm.lower() != 'yes':
            print("取消恢复")
            return 0

        # 清空现有数据
        db.execute(text("DELETE FROM watchlist"))
        print("✓ 已清空现有自选股")

        # 恢复数据
        for item in watchlist_data:
            db.execute(text("""
                INSERT INTO watchlist
                (ticker, added_at, purchase_price, purchase_date, shares, category, is_focus)
                VALUES
                (:ticker, :added_at, :purchase_price, :purchase_date, :shares, :category, :is_focus)
            """), {
                'ticker': item['ticker'],
                'added_at': item['added_at'],
                'purchase_price': item.get('purchase_price'),
                'purchase_date': item.get('purchase_date'),
                'shares': item.get('shares'),
                'category': item.get('category'),
                'is_focus': 1 if item.get('is_focus') else 0
            })

        db.commit()

        print(f"✓ 已恢复 {len(watchlist_data)} 只自选股")

        print("\n" + "="*60)
        print("✓ 恢复完成")
        print("="*60)

        return 0

    except Exception as e:
        db.rollback()
        print(f"\n✗ 恢复失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        db.close()


def main():
    """主函数"""

    if len(sys.argv) > 1:
        if sys.argv[1] == 'restore':
            if len(sys.argv) < 3:
                print("用法: python backup_watchlist.py restore <backup_file>")
                return 1
            backup_file = sys.argv[2]
            return restore_watchlist(backup_file)
        else:
            print("未知命令，支持的命令: restore")
            return 1
    else:
        # 默认执行备份
        return backup_watchlist()


if __name__ == "__main__":
    exit(main())
