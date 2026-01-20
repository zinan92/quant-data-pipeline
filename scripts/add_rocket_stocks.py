#!/usr/bin/env python3
"""批量添加可回收火箭概念股到自选列表"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from sqlalchemy import desc as sql_desc
from src.database import session_scope
from src.models import SymbolMetadata, Watchlist, Candle, Timeframe


# 12只可回收火箭概念股
ROCKET_STOCKS = [
    ("688722", "同益中", "国内超高分子量聚乙烯纤维龙头，为可回收火箭网系回收方案提供拦截网阵绳缆、火箭挂钩缓冲绳缆材料"),
    ("688592", "司南导航", "导航定位核心供应商，为火箭回收系统提供箭载高精度北斗/GNSS组合测量系统"),
    ("688539", "高华科技", "传感器隐形冠军，为朱雀三号等可回收火箭型号提供配套传感器，是回收系统的\"感知核心\""),
    ("301522", "上大股份", "国内高温合金循环再生领域龙头，为朱雀三号可回收火箭提供固体发动机壳体材料、液体发动机热端部件锻件"),
    ("688102", "斯瑞新材", "国内唯一量产3000℃耐高温难熔合金的企业，为可回收火箭发动机提供推力室内壁部件"),
    ("301005", "超捷股份", "朱雀三号独家核心供应商，为可回收火箭提供一级尾段、整流罩等关键结构件，同时切入箭体回收后的修复服务环节"),
    ("000825", "太钢不锈", "航天级不锈钢材料龙头，是箭元科技不锈钢箭体的核心潜在供应商，提供304L宽幅冷轧等航天级材料"),
    ("600477", "杭萧钢构", "国内钢结构行业龙头，已参与海南文昌航天发射场、箭元科技海上回收复用火箭基地等重大项目"),
    ("002342", "巨力索具", "国内索具行业绝对龙头，为可回收火箭系统提供捕获臂装置、试验拉索装置及回收网关键索具"),
    ("300129", "泰胜风能", "国内风电装备龙头，为可回收火箭提供着陆支架、蜂窝式吸能缓冲装置、箭体主结构、燃料贮箱等核心部件"),
    ("600343", "航天动力", "A股唯一液体火箭发动机上市平台，背靠航天科技六院，为可回收火箭提供具备多次启动、变推力能力的动力系统"),
    ("000738", "航发控制", "高精度伺服控制系统龙头，为可回收火箭提供动力控制方案，保障回收过程中箭体姿态的精准调整"),
]


def add_stocks_to_watchlist():
    """批量添加股票到自选列表"""
    added = []
    skipped = []
    failed = []

    with session_scope() as session:
        for ticker, name, desc in ROCKET_STOCKS:
            # 检查股票是否存在
            symbol = session.query(SymbolMetadata).filter(
                SymbolMetadata.ticker == ticker
            ).first()

            if not symbol:
                failed.append((ticker, name, "股票不存在于数据库"))
                continue

            # 检查是否已在自选中
            existing = session.query(Watchlist).filter(
                Watchlist.ticker == ticker
            ).first()

            if existing:
                skipped.append((ticker, name, "已在自选列表中"))
                continue

            # 获取最新收盘价作为买入价格
            latest_candle = session.query(Candle).filter(
                Candle.ticker == ticker,
                Candle.timeframe == Timeframe.DAY
            ).order_by(sql_desc(Candle.timestamp)).first()

            purchase_price = None
            shares = None
            purchase_date = datetime.now()

            if latest_candle and latest_candle.close:
                purchase_price = float(latest_candle.close)
                shares = 10000.0 / purchase_price if purchase_price > 0 else None

            # 添加到自选
            watchlist_item = Watchlist(
                ticker=ticker,
                purchase_price=purchase_price,
                purchase_date=purchase_date,
                shares=shares
            )
            session.add(watchlist_item)
            added.append((ticker, name, purchase_price, shares))

    # 打印结果
    print("\n" + "=" * 60)
    print("可回收火箭概念股添加结果")
    print("=" * 60)

    if added:
        print(f"\n✅ 成功添加 {len(added)} 只股票:")
        for ticker, name, price, shares in added:
            price_str = f"¥{price:.2f}" if price else "未知"
            shares_str = f"{shares:.2f}股" if shares else "未知"
            print(f"   {ticker} {name} - 买入价: {price_str}, 股数: {shares_str}")

    if skipped:
        print(f"\n⏭️  跳过 {len(skipped)} 只股票 (已在自选中):")
        for ticker, name, reason in skipped:
            print(f"   {ticker} {name}")

    if failed:
        print(f"\n❌ 失败 {len(failed)} 只股票:")
        for ticker, name, reason in failed:
            print(f"   {ticker} {name} - {reason}")

    print("\n" + "=" * 60)
    print(f"总计: 添加 {len(added)}, 跳过 {len(skipped)}, 失败 {len(failed)}")
    print("=" * 60 + "\n")

    return added, skipped, failed


if __name__ == "__main__":
    add_stocks_to_watchlist()
