"""
创建赛道管理表
"""
from src.database import SessionLocal
from sqlalchemy import text

def create_sectors_table():
    """创建 available_sectors 表"""
    session = SessionLocal()
    try:
        # 创建表
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS available_sectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(name)
            )
        """))

        # 插入默认赛道
        default_sectors = [
            'AI应用', '芯片', 'PCB', '机器人', '军工',
            '新能源汽车', '可控核聚变', '发电', '金属',
            '创新药', '脑机接口', '消费', '其他'
        ]

        from datetime import datetime
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for idx, sector in enumerate(default_sectors):
            session.execute(
                text("""
                    INSERT OR IGNORE INTO available_sectors (name, display_order, created_at)
                    VALUES (:name, :order, :created_at)
                """),
                {"name": sector, "order": idx, "created_at": now}
            )

        session.commit()
        print(f"✓ 成功创建 available_sectors 表并插入 {len(default_sectors)} 个默认赛道")

    except Exception as e:
        print(f"✗ 创建表失败: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    create_sectors_table()
