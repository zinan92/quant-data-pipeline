#!/usr/bin/env python
"""
导出概念板块映射为CSV文件

生成两个映射文件：
1. concept_to_tickers.csv - 板块代码 -> 股票列表
2. ticker_to_concepts.csv - 股票代码 -> 概念列表
"""

import sys
import csv
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import SessionLocal
from src.models import SymbolMetadata
import pandas as pd


def load_concept_index_mapping() -> Dict[str, str]:
    """
    加载概念名称到板块代码的映射

    Returns:
        Dict[concept_name, board_code]: 概念名称 -> 板块代码
    """
    csv_path = project_root / 'data' / 'ths_all_indexes.csv'
    df = pd.read_csv(csv_path)

    # 只筛选类型代码为 'N' 的概念指数
    concept_df = df[df['类型代码'] == 'N'].copy()

    # 创建映射：指数名称 -> 指数代码
    mapping = {}
    for _, row in concept_df.iterrows():
        concept_name = row['指数名称']
        board_code = row['指数代码']
        mapping[concept_name] = board_code

    print(f"📊 加载了 {len(mapping)} 个概念板块的代码映射")
    return mapping


def build_concept_to_tickers() -> Dict[str, List[str]]:
    """
    从数据库构建 概念 -> 股票列表 的映射

    Returns:
        Dict[concept_name, List[ticker]]: 概念名称 -> 股票代码列表
    """
    session = SessionLocal()

    try:
        # 获取所有有概念的股票
        symbols = session.query(SymbolMetadata).filter(
            SymbolMetadata.concepts != None,
            SymbolMetadata.concepts != '[]'
        ).all()

        # 构建反向映射
        concept_tickers = defaultdict(list)

        for symbol in symbols:
            ticker = symbol.ticker
            for concept in symbol.concepts:
                concept_tickers[concept].append(ticker)

        print(f"📋 构建了 {len(concept_tickers)} 个概念的股票映射")

        # 统计信息
        ticker_counts = [len(tickers) for tickers in concept_tickers.values()]
        if ticker_counts:
            print(f"   - 平均每个概念包含 {sum(ticker_counts) / len(ticker_counts):.1f} 只股票")
            print(f"   - 最多股票数: {max(ticker_counts)}")
            print(f"   - 最少股票数: {min(ticker_counts)}")

        return dict(concept_tickers)

    finally:
        session.close()


def export_concept_to_tickers_csv(
    concept_tickers: Dict[str, List[str]],
    concept_codes: Dict[str, str],
    output_path: Path
):
    """
    导出 概念板块 -> 股票列表 的CSV文件

    CSV格式：
    板块代码,板块名称,股票代码列表,股票数量
    """
    print(f"\n💾 导出概念 -> 股票映射到: {output_path}")

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['板块代码', '板块名称', '股票代码列表', '股票数量'])

        # 按板块名称排序
        sorted_concepts = sorted(concept_tickers.items(), key=lambda x: x[0])

        exported_count = 0
        missing_code_count = 0

        for concept_name, tickers in sorted_concepts:
            # 获取板块代码
            board_code = concept_codes.get(concept_name, '')

            if not board_code:
                missing_code_count += 1
                # 如果没有找到代码，使用概念名称作为代码
                board_code = f"UNKNOWN_{concept_name}"

            # 股票列表用逗号分隔
            ticker_list = ','.join(sorted(tickers))

            writer.writerow([
                board_code,
                concept_name,
                ticker_list,
                len(tickers)
            ])

            exported_count += 1

        print(f"✅ 导出了 {exported_count} 个概念板块")
        if missing_code_count > 0:
            print(f"⚠️  {missing_code_count} 个概念没有找到板块代码")


def export_ticker_to_concepts_csv(output_path: Path):
    """
    导出 股票 -> 概念列表 的CSV文件

    CSV格式：
    股票代码,股票名称,概念列表,概念数量
    """
    print(f"\n💾 导出股票 -> 概念映射到: {output_path}")

    session = SessionLocal()

    try:
        # 获取所有有概念的股票
        symbols = session.query(SymbolMetadata).filter(
            SymbolMetadata.concepts != None,
            SymbolMetadata.concepts != '[]'
        ).order_by(SymbolMetadata.ticker).all()

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['股票代码', '股票名称', '概念列表', '概念数量'])

            exported_count = 0

            for symbol in symbols:
                # 概念列表用分号分隔
                concept_list = ';'.join(symbol.concepts)

                writer.writerow([
                    symbol.ticker,
                    symbol.name,
                    concept_list,
                    len(symbol.concepts)
                ])

                exported_count += 1

            print(f"✅ 导出了 {exported_count} 只股票")

    finally:
        session.close()


def main():
    print("=" * 80)
    print("  导出概念板块映射为CSV")
    print("=" * 80)

    data_dir = project_root / 'data'

    # 1. 加载概念代码映射
    concept_codes = load_concept_index_mapping()

    # 2. 构建概念 -> 股票映射
    concept_tickers = build_concept_to_tickers()

    # 3. 导出第一个CSV: 概念 -> 股票列表
    output1 = data_dir / 'concept_to_tickers.csv'
    export_concept_to_tickers_csv(concept_tickers, concept_codes, output1)

    # 4. 导出第二个CSV: 股票 -> 概念列表
    output2 = data_dir / 'ticker_to_concepts.csv'
    export_ticker_to_concepts_csv(output2)

    print("\n" + "=" * 80)
    print("✅ 全部完成!")
    print(f"   文件1: {output1}")
    print(f"   文件2: {output2}")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
