#!/usr/bin/env python
"""
获取同花顺90个行业板块数据并保存到数据库
包括行情数据和加权平均PE

重要：
1. 上涨/下跌家数直接使用同花顺成分股关系计算
2. 同时更新 SymbolMetadata.industry_lv1 为同花顺行业名称
   （这是 industry_lv1 的唯一数据来源，不再从中信行业写入）
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
import csv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.tushare_client import TushareClient
from src.config import get_settings
from src.database import SessionLocal
from src.models import IndustryDaily, SymbolMetadata, Candle, Timeframe
from sqlalchemy import func


def load_super_category_map() -> dict[str, str]:
    """加载行业 -> 超级行业组映射"""
    mapping_path = project_root / "data" / "super_category_mapping.csv"
    if not mapping_path.exists():
        return {}

    lookup = {}
    with mapping_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            industry = row.get("行业名称")
            super_category = row.get("超级行业组")
            if industry and super_category:
                lookup[industry] = super_category
    return lookup


def get_latest_candles_map(session, tickers: list[str]) -> dict[str, list]:
    """
    获取指定股票的最新两根K线（用于计算涨跌）

    Args:
        session: 数据库会话
        tickers: 股票代码列表

    Returns:
        {ticker: [latest_candle, prev_candle]}
    """
    ticker_candles_map = {}
    if not tickers:
        return ticker_candles_map

    CHUNK_SIZE = 500
    for i in range(0, len(tickers), CHUNK_SIZE):
        ticker_chunk = tickers[i:i + CHUNK_SIZE]

        subq = session.query(
            Candle,
            func.row_number().over(
                partition_by=Candle.ticker,
                order_by=Candle.timestamp.desc()
            ).label('rn')
        ).filter(
            Candle.ticker.in_(ticker_chunk),
            Candle.timeframe == Timeframe.DAY
        ).subquery()

        latest_candles = session.query(
            subq.c.ticker,
            subq.c.close,
            subq.c.rn
        ).filter(
            subq.c.rn <= 2
        ).all()

        for row in latest_candles:
            if row.ticker not in ticker_candles_map:
                ticker_candles_map[row.ticker] = []
            ticker_candles_map[row.ticker].append(row)

    return ticker_candles_map


def calculate_industry_stats_from_ths_members(
    client: TushareClient,
    session,
    industry_ts_code: str,
    industry_name: str,
    ticker_candles_map: dict[str, list],
    ticker_metadata_map: dict[str, SymbolMetadata]
) -> dict:
    """
    使用同花顺成分股直接计算行业的上涨/下跌家数和PE

    Args:
        client: TushareClient
        session: 数据库会话
        industry_ts_code: 行业板块代码（如 885800.TI）
        industry_name: 行业名称
        ticker_candles_map: {ticker: [candles]} K线数据
        ticker_metadata_map: {ticker: SymbolMetadata} 元数据

    Returns:
        {"up": int, "down": int, "pe": float|None, "total_mv": float, "member_tickers": set}
    """
    stats = {"up": 0, "down": 0, "pe": None, "total_mv": 0, "member_tickers": set()}

    # 获取该行业的同花顺成分股
    try:
        members_df = client.fetch_ths_member(ts_code=industry_ts_code)
    except Exception as e:
        print(f"    ⚠️ 获取 {industry_name} 成分股失败: {e}")
        return stats

    if members_df.empty:
        return stats

    # 提取成分股代码
    code_field = 'con_code' if 'con_code' in members_df.columns else 'code'
    member_tickers = set()
    for stock_code in members_df[code_field].dropna():
        # 标准化股票代码（去掉交易所后缀）
        if '.' in str(stock_code):
            ticker = str(stock_code).split('.')[0]
        else:
            ticker = str(stock_code)
        member_tickers.add(ticker)

    stats["member_tickers"] = member_tickers

    # 计算涨跌家数
    weighted_pe_sum = 0
    weighted_mv_sum = 0
    total_mv = 0

    for ticker in member_tickers:
        # 计算涨跌
        candles = ticker_candles_map.get(ticker, [])
        if len(candles) >= 2:
            latest = candles[0]
            prev = candles[1]
            if prev.close and prev.close > 0:
                change_pct = ((latest.close - prev.close) / prev.close) * 100
                if change_pct > 0:
                    stats["up"] += 1
                elif change_pct < 0:
                    stats["down"] += 1

        # 计算PE（使用元数据）
        metadata = ticker_metadata_map.get(ticker)
        if metadata:
            if metadata.total_mv:
                total_mv += metadata.total_mv
            if metadata.pe_ttm and metadata.pe_ttm > 0 and metadata.total_mv:
                weighted_pe_sum += metadata.pe_ttm * metadata.total_mv
                weighted_mv_sum += metadata.total_mv

    # 计算加权平均PE
    if weighted_mv_sum > 0:
        stats["pe"] = round(weighted_pe_sum / weighted_mv_sum, 2)
    stats["total_mv"] = total_mv

    return stats


def main():
    print("=" * 60)
    print("  更新同花顺90个行业板块数据")
    print("  (使用同花顺成分股计算涨跌家数)")
    print("  (同时更新股票的 industry_lv1 为同花顺行业)")
    print("=" * 60)

    settings = get_settings()
    client = TushareClient(
        token=settings.tushare_token,
        points=settings.tushare_points
    )

    session = SessionLocal()

    try:
        # 1. 获取最新交易日
        print("\n1. 获取最新交易日...")
        latest_date = client.get_latest_trade_date()
        print(f"   最新交易日: {latest_date}")

        # 2. 获取同花顺行业资金流向数据
        print("\n2. 获取同花顺行业资金流向数据...")
        df = client.fetch_ths_industry_moneyflow(trade_date=latest_date)

        if df.empty:
            print("❌ 未获取到数据")
            return 1

        print(f"   ✓ 获取到 {len(df)} 个行业板块")

        # 3. 预加载数据
        print("\n3. 预加载股票数据...")

        # 获取所有股票元数据
        all_symbols = session.query(SymbolMetadata).all()
        ticker_metadata_map = {s.ticker: s for s in all_symbols}
        print(f"   ✓ 加载 {len(ticker_metadata_map)} 只股票元数据")

        # 获取所有股票的K线数据
        all_tickers = list(ticker_metadata_map.keys())
        ticker_candles_map = get_latest_candles_map(session, all_tickers)
        print(f"   ✓ 加载 {len(ticker_candles_map)} 只股票K线数据")

        # 加载超级行业组映射
        super_category_map = load_super_category_map()
        print(f"   ✓ 加载 {len(super_category_map)} 个超级行业组映射")

        # 4. 遍历每个行业，获取成分股并计算涨跌
        print("\n4. 计算每个行业的涨跌家数和PE（使用同花顺成分股）...")

        saved_count = 0
        updated_count = 0
        stock_industry_updated = 0  # 记录更新了多少只股票的行业

        for idx, row in df.iterrows():
            ts_code = row['ts_code']
            industry_name = row.get('industry', row.get('name', ''))

            # 使用同花顺成分股计算统计数据
            stats = calculate_industry_stats_from_ths_members(
                client=client,
                session=session,
                industry_ts_code=ts_code,
                industry_name=industry_name,
                ticker_candles_map=ticker_candles_map,
                ticker_metadata_map=ticker_metadata_map
            )

            # 更新成分股的 industry_lv1 和 super_category
            super_category = super_category_map.get(industry_name)
            for ticker in stats["member_tickers"]:
                metadata = ticker_metadata_map.get(ticker)
                if metadata:
                    # 只有当行业发生变化时才更新
                    if metadata.industry_lv1 != industry_name:
                        metadata.industry_lv1 = industry_name
                        metadata.super_category = super_category
                        metadata.last_sync = datetime.now(timezone.utc)
                        stock_industry_updated += 1

            # 检查是否已存在
            existing = session.query(IndustryDaily).filter(
                IndustryDaily.ts_code == ts_code,
                IndustryDaily.trade_date == latest_date
            ).first()

            if existing:
                # 更新
                existing.industry = industry_name
                existing.close = float(row['close'])
                existing.pct_change = float(row['pct_change'])
                existing.company_num = int(row['company_num'])
                existing.up_count = stats["up"]
                existing.down_count = stats["down"]
                existing.lead_stock = row.get('lead_stock')
                existing.pct_change_stock = row.get('pct_change_stock')
                existing.close_price = row.get('close_price')
                existing.net_buy_amount = row.get('net_buy_amount')
                existing.net_sell_amount = row.get('net_sell_amount')
                existing.net_amount = row.get('net_amount')
                existing.industry_pe = stats["pe"]
                existing.total_mv = stats["total_mv"]
                updated_count += 1
            else:
                # 新增
                record = IndustryDaily(
                    trade_date=latest_date,
                    ts_code=ts_code,
                    industry=industry_name,
                    close=float(row['close']),
                    pct_change=float(row['pct_change']),
                    company_num=int(row['company_num']),
                    up_count=stats["up"],
                    down_count=stats["down"],
                    lead_stock=row.get('lead_stock'),
                    pct_change_stock=row.get('pct_change_stock'),
                    close_price=row.get('close_price'),
                    net_buy_amount=row.get('net_buy_amount'),
                    net_sell_amount=row.get('net_sell_amount'),
                    net_amount=row.get('net_amount'),
                    industry_pe=stats["pe"],
                    total_mv=stats["total_mv"]
                )
                session.add(record)
                saved_count += 1

            # 打印进度（每10个打印一次）
            if (idx + 1) % 10 == 0 or idx < 5:
                pe_str = f"PE: {stats['pe']}" if stats['pe'] else "PE: N/A"
                print(f"  [{idx+1}/{len(df)}] {industry_name}: {row['pct_change']:.2f}%, ↑{stats['up']} ↓{stats['down']}, {pe_str}")

        session.commit()

        print("\n" + "=" * 60)
        print("  ✅ 完成！")
        print("=" * 60)
        print(f"\n总行业数: {len(df)}")
        print(f"新增记录: {saved_count}")
        print(f"更新记录: {updated_count}")
        print(f"股票行业更新: {stock_industry_updated} 只")
        print(f"数据日期: {latest_date}")

        return 0

    except Exception as e:
        session.rollback()
        print(f"\n❌ 更新失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
