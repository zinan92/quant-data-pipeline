"""生成测试数据：创建昨天和今天的超级行业组数据，用于测试涨跌幅和进攻防守指数"""

import random
from datetime import datetime, timedelta
from src.database import SessionLocal
from src.models import SuperCategoryDaily

# 14个超级行业组配置
SUPER_CATEGORIES = [
    {"name": "半导体与硬件", "score": 95, "industries": 5},
    {"name": "软件与互联网", "score": 90, "industries": 5},
    {"name": "新能源产业链", "score": 85, "industries": 5},
    {"name": "消费电子", "score": 80, "industries": 1},
    {"name": "通信与5G", "score": 75, "industries": 2},
    {"name": "汽车产业链", "score": 70, "industries": 3},
    {"name": "智能制造", "score": 65, "industries": 6},
    {"name": "军工航天", "score": 55, "industries": 2},
    {"name": "资源能源", "score": 50, "industries": 17},
    {"name": "基建地产链", "score": 45, "industries": 7},
    {"name": "大消费", "score": 40, "industries": 21},
    {"name": "医药健康", "score": 35, "industries": 6},
    {"name": "金融地产", "score": 25, "industries": 5},
    {"name": "公用事业", "score": 10, "industries": 5},
]


def generate_category_data(category, trade_date, yesterday_mv=None):
    """生成单个超级组的数据"""
    # 基础市值（根据行业数量生成）
    if yesterday_mv is None:
        base_mv = category["industries"] * random.uniform(10000, 50000)  # 万元
    else:
        base_mv = yesterday_mv

    # 生成涨跌幅：进攻性越强，波动越大
    volatility = (category["score"] / 100) * 0.05  # 5%基础波动
    pct_change = random.uniform(-volatility, volatility)

    # 偏向：进攻性板块更容易上涨
    if category["score"] > 70:
        pct_change += random.uniform(0, 0.02)  # 额外0-2%的上涨倾向
    elif category["score"] < 30:
        pct_change -= random.uniform(0, 0.01)  # 额外0-1%的下跌倾向

    # 今天市值 = 昨天市值 × (1 + 涨跌幅)
    total_mv = base_mv * (1 + pct_change)

    # 上涨/下跌行业数
    up_ratio = random.uniform(0.3, 0.7) if pct_change > 0 else random.uniform(0.2, 0.4)
    up_count = int(category["industries"] * up_ratio)
    down_count = category["industries"] - up_count

    # 平均PE
    avg_pe = random.uniform(15, 40)

    return {
        "super_category_name": category["name"],
        "score": category["score"],
        "trade_date": trade_date,
        "total_mv": total_mv,
        "pct_change": pct_change if yesterday_mv is not None else None,
        "industry_count": category["industries"],
        "up_count": up_count,
        "down_count": down_count,
        "avg_pe": avg_pe,
        "leading_industry": None,
    }


def generate_test_data():
    """生成昨天和今天的测试数据"""
    session = SessionLocal()

    try:
        # 交易日期
        today = datetime.now()
        today_str = today.strftime("%Y%m%d")
        yesterday = today - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y%m%d")

        print(f"Generating test data for {yesterday_str} and {today_str}...")

        # 清空现有数据
        session.query(SuperCategoryDaily).filter(
            SuperCategoryDaily.trade_date.in_([yesterday_str, today_str])
        ).delete()

        # 1. 生成昨天的数据
        print(f"\nGenerating data for {yesterday_str} (yesterday)...")
        yesterday_data = {}
        for category in SUPER_CATEGORIES:
            data = generate_category_data(category, yesterday_str)
            record = SuperCategoryDaily(**data)
            session.add(record)
            yesterday_data[category["name"]] = data["total_mv"]
            print(f"  {category['name']:20s} | 市值: {data['total_mv']/1e4:>10.0f}亿")

        session.commit()

        # 2. 生成今天的数据（基于昨天市值）
        print(f"\nGenerating data for {today_str} (today)...")
        for category in SUPER_CATEGORIES:
            yesterday_mv = yesterday_data[category["name"]]
            data = generate_category_data(category, today_str, yesterday_mv)
            record = SuperCategoryDaily(**data)
            session.add(record)
            print(f"  {category['name']:20s} | 市值: {data['total_mv']/1e4:>10.0f}亿 | "
                  f"涨跌幅: {data['pct_change']*100:>6.2f}%")

        session.commit()
        print(f"\n✓ Test data generated successfully!")
        print(f"\nYou can now test:")
        print(f"  - API: GET /api/boards/super-categories/daily")
        print(f"  - API: GET /api/boards/market-style-index")
        print(f"  - Frontend: SuperCategoryView with MarketStyleIndicator")

    except Exception as e:
        session.rollback()
        print(f"✗ Error generating test data: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    generate_test_data()
