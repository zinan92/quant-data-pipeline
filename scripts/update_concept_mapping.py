#!/usr/bin/env python
"""
更新股票的概念板块映射

从同花顺获取406个概念指数的成分股，并更新 symbol_metadata.concepts 字段
"""

import sys
import time
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict

import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.tushare_client import TushareClient
from src.database import SessionLocal
from src.models import SymbolMetadata
from src.config import get_settings
from sqlalchemy import select


def load_concept_indexes() -> pd.DataFrame:
    """加载同花顺概念指数列表（只要类型代码为 N 的）"""
    csv_path = project_root / 'data' / 'ths_all_indexes.csv'
    df = pd.read_csv(csv_path)

    # 只筛选类型代码为 'N' 的概念指数
    concept_df = df[df['类型代码'] == 'N'].copy()

    print(f"📊 加载了 {len(concept_df)} 个概念指数（类型代码=N）")
    print(f"   排除了以下类型: I-行业, R-地域, S-特色, ST-风格, TH-主题, BB-宽基")
    return concept_df


def fetch_all_concept_members(client: TushareClient, concept_df: pd.DataFrame) -> Dict[str, Set[str]]:
    """
    获取所有概念的成分股

    Returns:
        Dict[concept_name, Set[ticker]]: 概念名称 -> 成分股集合
    """
    concept_members = {}
    total = len(concept_df)

    print(f"\n🔄 开始获取 {total} 个概念的成分股...")
    print("=" * 80)

    for idx, row in concept_df.iterrows():
        ts_code = row['指数代码']
        concept_name = row['指数名称']

        try:
            # 获取成分股
            members_df = client.fetch_ths_member(ts_code=ts_code)

            if not members_df.empty:
                # 提取股票代码（去掉 .SH/.SZ 后缀）
                tickers = set()
                for con_code in members_df['con_code'].tolist():
                    # con_code 格式: '000001.SZ'
                    ticker = con_code.split('.')[0] if '.' in str(con_code) else str(con_code)
                    tickers.add(ticker)

                concept_members[concept_name] = tickers
                print(f"[{idx + 1}/{total}] ✅ {concept_name}: {len(tickers)} 只股票")
            else:
                concept_members[concept_name] = set()
                print(f"[{idx + 1}/{total}] ⚠️  {concept_name}: 无成分股")

            # API 限流保护：每次调用后休息0.3秒
            time.sleep(0.3)

        except Exception as e:
            print(f"[{idx + 1}/{total}] ❌ {concept_name}: 获取失败 - {e}")
            concept_members[concept_name] = set()

    print("=" * 80)
    print(f"✅ 成功获取 {len(concept_members)} 个概念的成分股\n")

    return concept_members


def build_ticker_concept_mapping(concept_members: Dict[str, Set[str]]) -> Dict[str, List[str]]:
    """
    建立股票 -> 概念列表的反向映射

    Args:
        concept_members: 概念名称 -> 成分股集合

    Returns:
        Dict[ticker, List[concept_name]]: 股票代码 -> 概念列表
    """
    ticker_concepts = defaultdict(list)

    for concept_name, tickers in concept_members.items():
        for ticker in tickers:
            ticker_concepts[ticker].append(concept_name)

    print(f"📋 建立了 {len(ticker_concepts)} 只股票的概念映射")

    # 统计信息
    concept_counts = [len(concepts) for concepts in ticker_concepts.values()]
    if concept_counts:
        print(f"   - 平均每只股票属于 {sum(concept_counts) / len(concept_counts):.1f} 个概念")
        print(f"   - 最多概念数: {max(concept_counts)}")
        print(f"   - 最少概念数: {min(concept_counts)}")

    return dict(ticker_concepts)


def update_database(ticker_concepts: Dict[str, List[str]]) -> None:
    """更新数据库中的 concepts 字段"""
    session = SessionLocal()

    try:
        print(f"\n💾 开始更新数据库...")
        print("=" * 80)

        # 获取所有股票
        symbols = session.query(SymbolMetadata).all()

        updated_count = 0
        no_concept_count = 0

        for symbol in symbols:
            ticker = symbol.ticker

            # 获取该股票的概念列表
            concepts = ticker_concepts.get(ticker, [])

            if concepts:
                symbol.concepts = concepts
                updated_count += 1
            else:
                symbol.concepts = []
                no_concept_count += 1

        # 提交更改
        session.commit()

        print(f"✅ 数据库更新完成!")
        print(f"   - 有概念的股票: {updated_count} 只")
        print(f"   - 无概念的股票: {no_concept_count} 只")
        print("=" * 80)

    except Exception as e:
        session.rollback()
        print(f"❌ 数据库更新失败: {e}")
        raise
    finally:
        session.close()


def show_sample_results(session) -> None:
    """显示部分结果样例"""
    print(f"\n📖 数据样例（前10只有概念的股票）:")
    print("=" * 80)

    # 查询有概念的股票
    stmt = select(SymbolMetadata).where(
        SymbolMetadata.concepts != None,
        SymbolMetadata.concepts != '[]'
    ).limit(10)

    samples = session.execute(stmt).scalars().all()

    for symbol in samples:
        concepts_str = ', '.join(symbol.concepts[:5])  # 只显示前5个
        if len(symbol.concepts) > 5:
            concepts_str += f" ... (共{len(symbol.concepts)}个)"
        print(f"{symbol.ticker} {symbol.name}")
        print(f"  行业: {symbol.industry_lv1}")
        print(f"  概念: {concepts_str}")
        print()

    print("=" * 80)


def main():
    print("=" * 80)
    print("  同花顺概念板块映射更新")
    print("=" * 80)

    # 1. 加载概念指数列表
    concept_df = load_concept_indexes()

    # 2. 获取所有概念的成分股
    settings = get_settings()
    client = TushareClient(
        token=settings.tushare_token,
        points=settings.tushare_points
    )
    concept_members = fetch_all_concept_members(client, concept_df)

    # 3. 建立股票 -> 概念的映射
    ticker_concepts = build_ticker_concept_mapping(concept_members)

    # 4. 更新数据库
    update_database(ticker_concepts)

    # 5. 显示样例结果
    session = SessionLocal()
    try:
        show_sample_results(session)
    finally:
        session.close()

    print("\n✅ 全部完成!\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
