#!/usr/bin/env python3
"""
数据库迁移脚本：添加 is_focus 字段到 watchlist 表
"""

import sqlite3
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def migrate():
    """添加 is_focus 列到 watchlist 表"""

    # 查找数据库文件
    db_paths = [
        Path(__file__).parent.parent / "data" / "market.db",
        Path(__file__).parent.parent / "data" / "stocks.db",
        Path(__file__).parent.parent / "backend" / "data" / "stocks.db"
    ]

    db_path = None
    for path in db_paths:
        if path.exists() and path.stat().st_size > 0:
            db_path = path
            break

    if not db_path:
        print("❌ 未找到数据库文件")
        return False

    print(f"📁 数据库路径: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 检查 watchlist 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='watchlist'")
        if not cursor.fetchone():
            print("⚠️  watchlist 表不存在")
            conn.close()
            return False

        # 检查 is_focus 列是否已存在
        cursor.execute("PRAGMA table_info(watchlist)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'is_focus' in columns:
            print("✅ is_focus 列已存在，无需迁移")
            conn.close()
            return True

        # 添加 is_focus 列
        print("🔄 添加 is_focus 列...")
        cursor.execute("ALTER TABLE watchlist ADD COLUMN is_focus INTEGER NOT NULL DEFAULT 0")
        conn.commit()

        # 验证
        cursor.execute("PRAGMA table_info(watchlist)")
        columns_after = [row[1] for row in cursor.fetchall()]

        if 'is_focus' in columns_after:
            print("✅ 成功添加 is_focus 列")
            print(f"📊 当前 watchlist 表结构:")
            cursor.execute("PRAGMA table_info(watchlist)")
            for row in cursor.fetchall():
                print(f"   - {row[1]} ({row[2]})")
            conn.close()
            return True
        else:
            print("❌ 添加列失败")
            conn.close()
            return False

    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        conn.rollback()
        conn.close()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("数据库迁移：添加 is_focus 字段")
    print("=" * 60)

    success = migrate()

    if success:
        print("\n✅ 迁移完成！")
        print("\n下一步:")
        print("1. 重启后端: 在运行 uvicorn 的终端按 Ctrl+C，然后重新运行")
        print("2. 刷新前端浏览器")
    else:
        print("\n❌ 迁移失败")
        sys.exit(1)
