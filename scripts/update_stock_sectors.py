#!/usr/bin/env python3
"""批量更新stock_sectors表中的赛道分类"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from datetime import datetime
from src.config import get_settings

settings = get_settings()
database_path = settings.database_url.replace("sqlite:///", "")


# AI应用概念股列表（20只）
AI_APPLICATION_STOCKS = [
    "688111",  # 金山办公
    "002602",  # 世纪华通
    "002230",  # 科大讯飞
    "002558",  # 巨人网络
    "601360",  # 三六零
    "300418",  # 昆仑万维
    "300058",  # 蓝色光标
    "301638",  # 南网数字
    "002195",  # 二三四五
    "300454",  # 深信服
    "002555",  # 三七互娱
    "002131",  # 利欧股份
    "600588",  # 用友网络
    "002517",  # 恺英网络
    "301236",  # 软通动力
    "600637",  # 东方明珠
    "600699",  # 均胜电子
    "300496",  # 中科创达
    "002624",  # 完美世界
    "301171",  # 易点天下
]


def update_sectors(tickers, sector="AI应用"):
    """
    批量更新stock_sectors表的赛道分类

    Args:
        tickers: 股票代码列表
        sector: 赛道名称（默认"AI应用"）
    """
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    updated = []
    inserted = []
    failed = []
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        for ticker in tickers:
            try:
                # 检查是否已存在
                cursor.execute("SELECT ticker FROM stock_sectors WHERE ticker = ?", (ticker,))
                existing = cursor.fetchone()

                if existing:
                    # 更新
                    cursor.execute(
                        "UPDATE stock_sectors SET sector = ?, updated_at = ? WHERE ticker = ?",
                        (sector, now, ticker)
                    )
                    updated.append(ticker)
                else:
                    # 插入
                    cursor.execute(
                        "INSERT INTO stock_sectors (ticker, sector, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (ticker, sector, now, now)
                    )
                    inserted.append(ticker)

            except Exception as e:
                failed.append((ticker, str(e)))

        conn.commit()

        # 打印结果
        print("\n" + "=" * 60)
        print(f"批量更新赛道分类: {sector}")
        print("=" * 60)

        if updated:
            print(f"\n✅ 成功更新 {len(updated)} 只股票:")
            for ticker in updated:
                print(f"   {ticker} → {sector}")

        if inserted:
            print(f"\n✅ 成功插入 {len(inserted)} 只股票:")
            for ticker in inserted:
                print(f"   {ticker} → {sector}")

        if failed:
            print(f"\n❌ 失败 {len(failed)} 只股票:")
            for ticker, error in failed:
                print(f"   {ticker} - {error}")

        print("\n" + "=" * 60)
        print(f"总计: 更新 {len(updated)}, 插入 {len(inserted)}, 失败 {len(failed)}")
        print("=" * 60 + "\n")

        return updated, inserted, failed

    except Exception as e:
        conn.rollback()
        print(f"❌ 批量更新失败: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    update_sectors(AI_APPLICATION_STOCKS, "AI应用")
