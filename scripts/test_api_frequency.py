#!/usr/bin/env python3
"""
测试同花顺API的访问频率和响应时间
"""

import akshare as ak
import time
from datetime import datetime

def test_single_concept_speed():
    """测试单个板块的访问速度"""
    print("=" * 80)
    print("测试1: 单个板块访问速度")
    print("=" * 80)

    test_concepts = ["先进封装", "存储芯片", "国家大基金持股"]

    for concept in test_concepts:
        start_time = time.time()
        try:
            df_info = ak.stock_board_concept_info_ths(symbol=concept)
            elapsed = time.time() - start_time
            print(f"✓ {concept:15s} - 响应时间: {elapsed:.2f}秒")
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"✗ {concept:15s} - 失败 ({elapsed:.2f}秒): {str(e)[:50]}")

def test_concept_stocks_speed():
    """测试获取成分股的速度"""
    print("\n" + "=" * 80)
    print("测试2: 获取成分股速度（东方财富接口）")
    print("=" * 80)

    test_concepts = ["先进封装", "存储芯片", "国家大基金持股"]

    for concept in test_concepts:
        start_time = time.time()
        try:
            df_stocks = ak.stock_board_concept_cons_em(symbol=concept)
            elapsed = time.time() - start_time
            stock_count = len(df_stocks) if df_stocks is not None else 0
            print(f"✓ {concept:15s} - {stock_count:3d}只成分股 - 响应时间: {elapsed:.2f}秒")
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"✗ {concept:15s} - 失败 ({elapsed:.2f}秒): {str(e)[:50]}")

def test_batch_access_speed(num_concepts=20):
    """测试批量访问速度"""
    print("\n" + "=" * 80)
    print(f"测试3: 批量访问{num_concepts}个板块的速度")
    print("=" * 80)

    # 获取所有板块
    df_names = ak.stock_board_concept_name_ths()
    test_concepts = df_names.head(num_concepts)

    total_start = time.time()
    success_count = 0
    fail_count = 0

    for idx, row in test_concepts.iterrows():
        concept_name = row['name']
        start_time = time.time()

        try:
            df_info = ak.stock_board_concept_info_ths(symbol=concept_name)
            elapsed = time.time() - start_time
            success_count += 1
            print(f"✓ [{idx+1}/{num_concepts}] {concept_name:20s} - {elapsed:.2f}秒")
        except Exception as e:
            elapsed = time.time() - start_time
            fail_count += 1
            print(f"✗ [{idx+1}/{num_concepts}] {concept_name:20s} - {elapsed:.2f}秒")

        # 可选：添加延迟避免被封
        # time.sleep(0.1)

    total_elapsed = time.time() - total_start
    avg_time = total_elapsed / num_concepts

    print("\n" + "=" * 80)
    print(f"总耗时: {total_elapsed:.2f}秒")
    print(f"成功: {success_count}, 失败: {fail_count}")
    print(f"平均每个板块: {avg_time:.2f}秒")
    print(f"理论最高频率: {60/total_elapsed:.2f}次/分钟 (单线程)")
    print("=" * 80)

def test_rate_limit():
    """测试访问频率限制"""
    print("\n" + "=" * 80)
    print("测试4: 访问频率限制（快速连续访问）")
    print("=" * 80)

    concept = "先进封装"
    num_requests = 10

    print(f"连续访问 {num_requests} 次，无延迟...")

    times = []
    for i in range(num_requests):
        start_time = time.time()
        try:
            df_info = ak.stock_board_concept_info_ths(symbol=concept)
            elapsed = time.time() - start_time
            times.append(elapsed)
            status = "✓"
        except Exception as e:
            elapsed = time.time() - start_time
            times.append(elapsed)
            status = f"✗ {str(e)[:30]}"

        print(f"  第{i+1}次: {elapsed:.2f}秒 - {status}")

    print(f"\n平均响应时间: {sum(times)/len(times):.2f}秒")
    print(f"最快: {min(times):.2f}秒, 最慢: {max(times):.2f}秒")

def calculate_monitoring_strategy():
    """计算监控策略"""
    print("\n" + "=" * 80)
    print("监控策略分析")
    print("=" * 80)

    scenarios = [
        {"boards": 10, "stocks_per_board": 50},
        {"boards": 15, "stocks_per_board": 100},
        {"boards": 20, "stocks_per_board": 120},
        {"boards": 30, "stocks_per_board": 100},
    ]

    # 假设参数
    board_info_time = 2.0  # 秒/板块信息
    stock_list_time = 1.5  # 秒/成分股列表

    print("\n方案对比：")
    print(f"{'板块数':<8} {'平均成分股':<10} {'单轮耗时':<12} {'最高频率':<15} {'推荐更新间隔'}")
    print("-" * 80)

    for scenario in scenarios:
        num_boards = scenario['boards']
        stocks_per = scenario['stocks_per_board']

        # 方案1: 只获取板块信息
        time_board_only = num_boards * board_info_time
        freq_board_only = 60 / time_board_only

        # 方案2: 板块信息 + 成分股
        time_with_stocks = num_boards * (board_info_time + stock_list_time)
        freq_with_stocks = 60 / time_with_stocks

        print(f"{num_boards:<8} {stocks_per:<10} {time_board_only:.1f}秒 ({time_with_stocks:.1f}秒)  "
              f"{freq_board_only:.2f}次/分钟     {time_board_only:.0f}-{time_board_only*2:.0f}秒")

    print("\n" + "=" * 80)
    print("💡 建议监控策略：")
    print("=" * 80)
    print("""
1. 【快速监控】- 只获取板块级别数据
   - 监控板块：15-20个热门板块
   - 更新频率：30-60秒/轮
   - 数据内容：涨幅、资金流向、涨跌家数
   - 适用场景：快速捕捉板块轮动

2. 【深度监控】- 板块 + 成分股涨停统计
   - 监控板块：10-15个重点板块
   - 更新频率：60-120秒/轮
   - 数据内容：板块数据 + 成分股列表 + 涨停统计
   - 适用场景：精确捕捉涨停股票

3. 【混合策略】（推荐⭐）
   - 第一层：快速监控30个板块（30秒/轮）
   - 第二层：深度监控涨幅前10板块（60秒/轮）
   - 优势：兼顾覆盖面和精度

4. 【风险控制】
   - 添加请求间隔：0.3-0.5秒（避免IP被封）
   - 错误重试机制：失败后等待5秒重试
   - 异常检测：连续失败3次则暂停监控
    """)

if __name__ == '__main__':
    print("同花顺API频率测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 测试1: 单个板块速度
    test_single_concept_speed()
    time.sleep(1)

    # 测试2: 成分股速度
    test_concept_stocks_speed()
    time.sleep(1)

    # 测试3: 批量访问速度
    test_batch_access_speed(num_concepts=20)
    time.sleep(1)

    # 测试4: 频率限制
    test_rate_limit()

    # 监控策略分析
    calculate_monitoring_strategy()

    print("\n✅ 测试完成！")
