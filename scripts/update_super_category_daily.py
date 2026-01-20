"""更新超级行业组每日数据"""

import csv
import sys
from pathlib import Path
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func
from src.database import SessionLocal
from src.models import IndustryDaily, SuperCategoryDaily


def load_super_category_mapping() -> Dict[str, Dict]:
    """从CSV加载超级分类映射

    Returns:
        Dict[category_name, {
            'score': int,
            'industries': [industry_name, ...]
        }]
    """
    csv_path = Path(__file__).parent.parent / "data" / "super_category_mapping.csv"

    categories = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            category_name = row['超级行业组']
            score = int(row['进攻性评分'])
            industry = row['行业名称']

            if category_name not in categories:
                categories[category_name] = {
                    'score': score,
                    'industries': []
                }

            categories[category_name]['industries'].append(industry)

    return categories


def get_previous_trade_date(session, current_date: str) -> str | None:
    """获取前一个交易日

    Args:
        session: 数据库会话
        current_date: 当前交易日 YYYYMMDD

    Returns:
        前一个交易日，如果不存在返回 None
    """
    result = session.query(IndustryDaily.trade_date).filter(
        IndustryDaily.trade_date < current_date
    ).order_by(IndustryDaily.trade_date.desc()).first()

    return result[0] if result else None


def get_industry_data(session, trade_date: str) -> Dict[str, IndustryDaily]:
    """获取指定日期的所有行业数据

    Args:
        session: 数据库会话
        trade_date: 交易日期 YYYYMMDD

    Returns:
        Dict[industry_name, IndustryDaily]
    """
    industries = session.query(IndustryDaily).filter(
        IndustryDaily.trade_date == trade_date
    ).all()

    return {ind.industry: ind for ind in industries}


def calculate_super_category_data(
    category_name: str,
    category_info: Dict,
    today_industries: Dict[str, IndustryDaily],
    yesterday_industries: Dict[str, IndustryDaily] | None,
    trade_date: str
) -> SuperCategoryDaily:
    """计算超级行业组的数据

    Args:
        category_name: 超级行业组名称
        category_info: 包含 score 和 industries 的字典
        today_industries: 今天的行业数据
        yesterday_industries: 昨天的行业数据（可能为空）
        trade_date: 交易日期

    Returns:
        SuperCategoryDaily 对象
    """
    score = category_info['score']
    industries = category_info['industries']

    # 计算今天总市值和统计数据
    total_mv_today = 0
    up_count = 0
    down_count = 0
    pe_values = []
    industry_changes = []

    for industry_name in industries:
        if industry_name not in today_industries:
            continue

        ind_data = today_industries[industry_name]

        # 累加市值
        if ind_data.total_mv:
            total_mv_today += ind_data.total_mv

        # 统计上涨下跌
        if ind_data.pct_change is not None:
            if ind_data.pct_change > 0:
                up_count += 1
            elif ind_data.pct_change < 0:
                down_count += 1

            industry_changes.append({
                'name': industry_name,
                'change': ind_data.pct_change
            })

        # 收集PE数据
        if ind_data.industry_pe and ind_data.industry_pe > 0:
            pe_values.append(ind_data.industry_pe)

    # 计算市值加权平均涨跌幅
    pct_change = None

    if yesterday_industries:
        # 使用市值加权平均各行业涨跌幅
        total_weight = 0
        weighted_sum = 0

        for industry_name in industries:
            if industry_name not in today_industries or industry_name not in yesterday_industries:
                continue

            today_ind = today_industries[industry_name]
            # 使用市值作为权重，涨跌幅已经在 industry_daily 中计算好了
            if today_ind.pct_change is not None and today_ind.total_mv:
                weighted_sum += today_ind.pct_change * today_ind.total_mv
                total_weight += today_ind.total_mv

        # 计算加权平均涨跌幅
        # 注意：industry_daily.pct_change 存储为百分比（2.87 = 2.87%）
        # 但 super_category_daily.pct_change 需要存储为小数（0.0287 = 2.87%）
        if total_weight > 0:
            pct_change = (weighted_sum / total_weight) / 100

    # 计算平均PE
    avg_pe = sum(pe_values) / len(pe_values) if pe_values else None

    # 找到涨幅最大的行业
    leading_industry = None
    if industry_changes:
        industry_changes.sort(key=lambda x: x['change'], reverse=True)
        leading_industry = industry_changes[0]['name']

    # 创建记录
    return SuperCategoryDaily(
        super_category_name=category_name,
        score=score,
        trade_date=trade_date,
        total_mv=total_mv_today,
        pct_change=pct_change,
        industry_count=len(industries),
        up_count=up_count,
        down_count=down_count,
        avg_pe=avg_pe,
        leading_industry=leading_industry
    )


def update_super_category_daily(trade_date: str = None):
    """更新超级行业组每日数据

    Args:
        trade_date: 交易日期 YYYYMMDD，如果为空则使用最新日期
    """
    session = SessionLocal()

    try:
        # 如果没有指定日期，使用最新日期
        if not trade_date:
            latest = session.query(func.max(IndustryDaily.trade_date)).scalar()
            if not latest:
                print("Error: No industry data found in database")
                return
            trade_date = latest

        print(f"Updating super category data for {trade_date}...")

        # 加载超级分类映射
        categories = load_super_category_mapping()
        print(f"Loaded {len(categories)} super categories")

        # 获取今天和昨天的行业数据
        today_industries = get_industry_data(session, trade_date)
        print(f"Found {len(today_industries)} industries for {trade_date}")

        previous_date = get_previous_trade_date(session, trade_date)
        yesterday_industries = None
        if previous_date:
            yesterday_industries = get_industry_data(session, previous_date)
            print(f"Found {len(yesterday_industries)} industries for {previous_date} (previous day)")
        else:
            print("Warning: No previous trade date found, pct_change will be NULL")

        # 删除当天已存在的数据（避免重复）
        session.query(SuperCategoryDaily).filter(
            SuperCategoryDaily.trade_date == trade_date
        ).delete()

        # 计算并保存每个超级组的数据
        records_added = 0
        for category_name, category_info in categories.items():
            record = calculate_super_category_data(
                category_name=category_name,
                category_info=category_info,
                today_industries=today_industries,
                yesterday_industries=yesterday_industries,
                trade_date=trade_date
            )

            session.add(record)
            records_added += 1

            print(f"  {category_name:20s} | 市值: {record.total_mv/1e4:>10.0f}亿 | "
                  f"涨跌幅: {record.pct_change*100:>6.2f}% | "
                  f"上涨: {record.up_count}/{record.industry_count}" if record.pct_change else
                  f"  {category_name:20s} | 市值: {record.total_mv/1e4:>10.0f}亿 | "
                  f"涨跌幅: N/A       | "
                  f"上涨: {record.up_count}/{record.industry_count}")

        session.commit()
        print(f"\n✓ Successfully updated {records_added} super category records for {trade_date}")

    except Exception as e:
        session.rollback()
        print(f"✗ Error updating super category data: {e}")
        raise
    finally:
        session.close()


def backfill_historical_data(start_date: str = None, end_date: str = None):
    """回填历史数据

    Args:
        start_date: 开始日期 YYYYMMDD，如果为空则从最早的日期开始
        end_date: 结束日期 YYYYMMDD，如果为空则到最新日期
    """
    session = SessionLocal()

    try:
        # 获取所有交易日期
        query = session.query(IndustryDaily.trade_date).distinct()

        if start_date:
            query = query.filter(IndustryDaily.trade_date >= start_date)
        if end_date:
            query = query.filter(IndustryDaily.trade_date <= end_date)

        trade_dates = [row[0] for row in query.order_by(IndustryDaily.trade_date).all()]

        print(f"Backfilling {len(trade_dates)} trading days...")

        for i, date in enumerate(trade_dates, 1):
            print(f"\n[{i}/{len(trade_dates)}] Processing {date}...")
            update_super_category_daily(date)

        print(f"\n✓ Backfill complete! Processed {len(trade_dates)} days")

    finally:
        session.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "backfill":
            # 回填所有历史数据
            start = sys.argv[2] if len(sys.argv) > 2 else None
            end = sys.argv[3] if len(sys.argv) > 3 else None
            backfill_historical_data(start, end)
        else:
            # 更新指定日期
            update_super_category_daily(sys.argv[1])
    else:
        # 更新最新日期
        update_super_category_daily()
