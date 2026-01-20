#!/usr/bin/env python3
"""
获取同花顺概念板块前10涨幅数据
包含字段：涨幅、主力净量、主力净流入、涨停数、涨家数、跌家数、量比、总市值
"""

import akshare as ak
import pandas as pd
import time
from datetime import datetime

def get_top_concept_sectors(top_n=10):
    """获取涨幅前N的概念板块数据"""

    print(f"开始获取同花顺概念板块数据...")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. 获取所有概念板块列表
    df_names = ak.stock_board_concept_name_ths()
    print(f"✓ 获取到 {len(df_names)} 个概念板块")

    results = []
    failed_count = 0

    # 2. 遍历所有板块获取详细数据
    for idx, row in df_names.iterrows():
        concept_name = row['name']
        concept_code = row['code']

        try:
            # 获取板块详细信息
            df_info = ak.stock_board_concept_info_ths(symbol=concept_name)

            # 解析数据为字典
            data = {}
            for i, info_row in df_info.iterrows():
                data[info_row['项目']] = info_row['值']

            # 解析涨跌家数
            up_down = data.get('涨跌家数', '0/0')
            up_count, down_count = map(int, up_down.split('/'))

            # 提取数据
            change_pct_str = data.get('板块涨幅', '0%').replace('%', '')
            money_inflow = float(data.get('资金净流入(亿)', 0))  # 主力净流入(亿元)
            turnover = float(data.get('成交额(亿)', 0))
            volume = float(data.get('成交量(万手)', 0))

            # 计算主力净量 (亿元 -> 万手，需要根据平均价格估算)
            # 简化计算：净流入金额(亿) / 成交额(亿) * 成交量(万手)
            if turnover > 0:
                main_volume = (money_inflow / turnover) * volume
            else:
                main_volume = 0

            # 计算量比 (当前成交量 / 过去5日平均)
            # 注：同花顺接口未直接提供量比，这里用占位符
            volume_ratio = 0  # 需要历史数据计算

            # 计算总市值
            # 注：同花顺接口未直接提供总市值，需要通过成分股计算
            total_market_cap = 0  # 占位符

            results.append({
                '板块代码': concept_code,
                '板块名称': concept_name,
                '涨幅': float(change_pct_str),
                '主力净流入': money_inflow,  # 亿元
                '主力净量': round(main_volume, 2),  # 万手
                '涨停数': 0,  # 需要单独统计
                '涨家数': up_count,
                '跌家数': down_count,
                '量比': volume_ratio,  # 占位
                '总市值': total_market_cap,  # 占位
                '成交额': turnover,
                '成交量': volume,
                '今开': float(data.get('今开', 0)),
                '最高': float(data.get('最高', 0)),
                '最低': float(data.get('最低', 0)),
                '昨收': float(data.get('昨收', 0)),
            })

            print(f"✓ [{idx+1}/{len(df_names)}] {concept_name} - 涨幅: {change_pct_str}%")

        except Exception as e:
            failed_count += 1
            print(f"✗ [{idx+1}/{len(df_names)}] {concept_name} - 失败: {str(e)[:50]}")
            continue

        # 限流，避免请求过快
        time.sleep(0.3)

    print("\n" + "=" * 80)
    print(f"✓ 成功获取 {len(results)} 个板块，失败 {failed_count} 个")

    # 3. 转换为DataFrame并排序
    df_result = pd.DataFrame(results)
    df_result = df_result.sort_values('涨幅', ascending=False)

    # 4. 获取前N名
    df_top = df_result.head(top_n).copy()
    df_top['排名'] = range(1, len(df_top) + 1)

    return df_top

def save_to_csv(df, filename=None):
    """保存数据到CSV文件"""
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'/Users/park/a-share-data/docs/top_sectors_{timestamp}.csv'

    # 选择需要的字段
    columns = [
        '排名', '板块代码', '板块名称', '涨幅', '主力净流入', '主力净量',
        '涨停数', '涨家数', '跌家数', '量比', '总市值', '成交额', '成交量'
    ]

    df_output = df[columns]
    df_output.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"\n✓ 数据已保存到: {filename}")
    return filename

def display_results(df):
    """格式化显示结果"""
    print("\n" + "=" * 80)
    print("📊 今日涨幅前10概念板块")
    print("=" * 80)

    for idx, row in df.iterrows():
        print(f"\n🏆 第{row['排名']}名: {row['板块名称']} ({row['板块代码']})")
        print(f"   涨幅: {row['涨幅']:.2f}%")
        print(f"   主力净流入: {row['主力净流入']:.2f}亿元")
        print(f"   主力净量: {row['主力净量']:.2f}万手")
        print(f"   涨家数/跌家数: {row['涨家数']}/{row['跌家数']}")
        print(f"   成交额: {row['成交额']:.2f}亿元")

if __name__ == '__main__':
    # 获取前10涨幅板块
    df_top = get_top_concept_sectors(top_n=10)

    # 显示结果
    display_results(df_top)

    # 保存到CSV
    filename = save_to_csv(df_top)

    print("\n" + "=" * 80)
    print("✅ 任务完成！")
    print("=" * 80)
