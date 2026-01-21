#!/usr/bin/env python3
"""
批量重构 kline_updater.py 的辅助脚本
将所有 session = SessionLocal() 替换为使用 repository
"""

import re

def refactor_kline_updater():
    """重构 kline_updater.py"""
    file_path = "/Users/park/a-share-data/src/services/kline_updater.py"

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 移除所有方法中的 "session = SessionLocal()"
    content = re.sub(
        r'(\n\s+)(session = SessionLocal\(\))',
        r'\1# session = SessionLocal()  # 已迁移到使用 repository',
        content
    )

    # 2. 移除所有 "session.close()"
    content = re.sub(
        r'(\n\s+)(finally:\s+session\.close\(\))',
        r'\1# finally: session.close()  # 已迁移到使用 repository',
        content
    )

    content = re.sub(
        r'(\n\s+)(session\.close\(\))',
        r'\1# session.close()  # 已迁移到使用 repository',
        content
    )

    # 3. 替换 session.query 为使用 repository
    # 这个需要手动处理，因为每个查询都不同

    # 4. 替换 KlineService(session) 为 KlineService.create_with_session(session)
    # 实际上我们应该直接使用 repository

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ kline_updater.py 重构完成")
    print("⚠️  请手动检查以下内容:")
    print("   1. session.query() 调用")
    print("   2. KlineService 使用")
    print("   3. 数据库事务管理")

if __name__ == "__main__":
    refactor_kline_updater()
