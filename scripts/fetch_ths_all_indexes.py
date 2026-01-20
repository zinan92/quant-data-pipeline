#!/usr/bin/env python
"""
获取同花顺所有板块指数数据
包括：概念指数、行业指数、地域指数、特色指数、风格指数、主题指数、宽基指数
保存到CSV文件
"""

import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.tushare_client import TushareClient
from src.config import get_settings

def main():
    print("=" * 60)
    print("  获取同花顺所有板块指数数据")
    print("=" * 60)

    settings = get_settings()
    client = TushareClient(
        token=settings.tushare_token,
        points=settings.tushare_points
    )

    # 板块类型定义
    board_types = {
        'N': '概念指数',
        'I': '行业指数',
        'R': '地域指数',
        'S': '同花顺特色指数',
        'ST': '同花顺风格指数',
        'TH': '同花顺主题指数',
        'BB': '同花顺宽基指数'
    }

    all_data = []

    print("\n开始获取数据...\n")

    # 遍历所有板块类型
    for type_code, type_name in board_types.items():
        try:
            print(f"正在获取 {type_name} ({type_code})...")
            df = client.fetch_ths_index(exchange='A', type=type_code)

            if not df.empty:
                # 添加板块类型名称列
                df['板块类型'] = type_name
                all_data.append(df)
                print(f"  ✓ 获取到 {len(df)} 个{type_name}")
            else:
                print(f"  ⚠ {type_name} 暂无数据")

        except Exception as e:
            print(f"  ❌ 获取 {type_name} 失败: {e}")

    # 合并所有数据
    if all_data:
        result_df = pd.concat(all_data, ignore_index=True)

        # 重新排列列顺序，使其更易读
        columns = ['ts_code', 'name', '板块类型', 'type', 'count', 'exchange', 'list_date']
        result_df = result_df[columns]

        # 重命名列为中文
        result_df.rename(columns={
            'ts_code': '指数代码',
            'name': '指数名称',
            'type': '类型代码',
            'count': '成分个数',
            'exchange': '交易所',
            'list_date': '上市日期'
        }, inplace=True)

        # 保存到CSV
        output_file = project_root / 'data' / 'ths_all_indexes.csv'
        result_df.to_csv(output_file, index=False, encoding='utf-8-sig')

        print("\n" + "=" * 60)
        print("  ✅ 完成！")
        print("=" * 60)
        print(f"\n总板块指数数: {len(result_df)}")
        print("\n各类型统计:")
        type_counts = result_df['板块类型'].value_counts()
        for type_name, count in type_counts.items():
            print(f"  {type_name}: {count}个")

        print(f"\n前10个板块指数:")
        print(result_df.head(10).to_string(index=False))
        print(f"\n已保存到: {output_file}")

        return 0
    else:
        print("\n❌ 未获取到任何数据")
        return 1


if __name__ == "__main__":
    sys.exit(main())
