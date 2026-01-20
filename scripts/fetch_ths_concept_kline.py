#!/usr/bin/env python3
"""
同花顺概念板块K线数据下载脚本
数据源: d.10jqka.com.cn
支持: 分时(1分钟)、30分钟、日线
"""

import os
import re
import json
import time
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

# 配置
BASE_URL = "http://d.10jqka.com.cn/v4"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "http://q.10jqka.com.cn/",
}

# 数据目录
DATA_DIR = Path(__file__).parent.parent / "data"
KLINE_DIR = DATA_DIR / "concept_klines"


def load_concept_mapping() -> dict:
    """加载概念名称到板块代码的映射"""
    concept_file = DATA_DIR / "concept_to_tickers.csv"
    df = pd.read_csv(concept_file)

    # 创建 概念名称 -> 板块代码 的映射
    mapping = {}
    for _, row in df.iterrows():
        code = row['板块代码'].replace('.TI', '')  # 885556.TI -> 885556
        name = row['板块名称']
        mapping[name] = code

    return mapping


def load_hot_concepts() -> list:
    """加载热门概念列表"""
    hot_file = DATA_DIR / "hot_concept_categories.csv"
    df = pd.read_csv(hot_file)
    return df['概念名称'].tolist()


def fetch_kline_data(code: str, period: str = "30") -> dict:
    """
    获取K线数据

    Args:
        code: 板块代码 (如 885556)
        period: K线周期
            - "01": 日线
            - "30": 30分钟
            - "time": 分时(当天1分钟)

    Returns:
        解析后的数据字典
    """
    if period == "time":
        url = f"{BASE_URL}/time/bk_{code}/last.js"
    else:
        url = f"{BASE_URL}/line/bk_{code}/{period}/last.js"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()

        # 解析JSONP响应
        text = resp.text
        # 提取JSON部分: quotebridge_v4_xxx({...})
        match = re.search(r'\((\{.*\})\)', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return None

    except Exception as e:
        print(f"  获取 {code} 数据失败: {e}")
        return None


def parse_kline_data(raw_data: dict, code: str, period: str) -> pd.DataFrame:
    """
    解析K线数据为DataFrame

    Args:
        raw_data: 原始数据字典
        code: 板块代码
        period: K线周期
    """
    if not raw_data:
        return pd.DataFrame()

    # 获取数据键 (格式如 bk_885556)
    data_key = f"bk_{code}"

    if period == "time":
        # 分时数据格式不同
        if data_key not in raw_data:
            return pd.DataFrame()

        info = raw_data[data_key]
        data_str = info.get('data', '')
        if not data_str:
            return pd.DataFrame()

        # 分时数据格式: 时间,价格,成交量,换手率,成交额;...
        records = []
        for item in data_str.split(';'):
            parts = item.split(',')
            if len(parts) >= 5:
                records.append({
                    'time': parts[0],
                    'price': float(parts[1]),
                    'volume': int(parts[2]),
                    'turnover_rate': float(parts[3]),
                    'amount': float(parts[4]),
                })

        df = pd.DataFrame(records)
        df['date'] = info.get('date', '')
        df['name'] = info.get('name', '')
        return df

    else:
        # K线数据 (日线/30分钟)
        data_str = raw_data.get('data', '')
        if not data_str:
            return pd.DataFrame()

        # K线数据格式: 时间,开盘,最高,最低,收盘,成交量,成交额,...;...
        records = []
        for item in data_str.split(';'):
            parts = item.split(',')
            if len(parts) >= 7 and parts[1]:  # 确保数据有效
                try:
                    records.append({
                        'datetime': parts[0],
                        'open': float(parts[1]),
                        'high': float(parts[2]),
                        'low': float(parts[3]),
                        'close': float(parts[4]),
                        'volume': int(parts[5]),
                        'amount': float(parts[6]),
                    })
                except (ValueError, IndexError):
                    continue  # 跳过无效数据

        df = pd.DataFrame(records)
        df['code'] = code
        df['name'] = raw_data.get('name', '')
        return df


def download_concept_klines(concepts: list = None, period: str = "30"):
    """
    下载概念板块K线数据

    Args:
        concepts: 概念名称列表，None则下载所有热门概念
        period: K线周期 ("01"=日线, "30"=30分钟, "time"=分时)
    """
    # 创建输出目录
    KLINE_DIR.mkdir(parents=True, exist_ok=True)

    # 加载映射
    concept_mapping = load_concept_mapping()

    if concepts is None:
        concepts = load_hot_concepts()

    print(f"准备下载 {len(concepts)} 个概念板块的K线数据 (周期: {period})")
    print("-" * 50)

    all_data = []
    success_count = 0
    fail_count = 0

    for i, concept_name in enumerate(concepts, 1):
        code = concept_mapping.get(concept_name)

        if not code:
            print(f"[{i}/{len(concepts)}] {concept_name}: 未找到板块代码")
            fail_count += 1
            continue

        print(f"[{i}/{len(concepts)}] {concept_name} ({code})...", end=" ")

        raw_data = fetch_kline_data(code, period)
        if raw_data:
            df = parse_kline_data(raw_data, code, period)
            if not df.empty:
                all_data.append(df)
                print(f"✓ {len(df)} 条数据")
                success_count += 1
            else:
                print("✗ 数据为空")
                fail_count += 1
        else:
            print("✗ 请求失败")
            fail_count += 1

        # 请求间隔，避免被封
        time.sleep(0.3)

    print("-" * 50)
    print(f"完成: 成功 {success_count}, 失败 {fail_count}")

    # 合并并保存数据
    if all_data:
        result_df = pd.concat(all_data, ignore_index=True)

        # 根据周期设置文件名
        period_name = {
            "01": "daily",
            "30": "30min",
            "time": "minute",
        }.get(period, period)

        output_file = KLINE_DIR / f"concept_klines_{period_name}.csv"
        result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"数据已保存: {output_file}")
        print(f"共 {len(result_df)} 条记录")

        return result_df

    return pd.DataFrame()


def update_daily():
    """每日更新任务"""
    print(f"\n{'='*50}")
    print(f"同花顺概念板块K线数据更新")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    # 下载30分钟K线
    print("\n[1] 下载30分钟K线数据...")
    download_concept_klines(period="30")

    # 下载日线
    print("\n[2] 下载日线数据...")
    download_concept_klines(period="01")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="同花顺概念板块K线数据下载")
    parser.add_argument(
        "--period", "-p",
        choices=["30", "01", "time"],
        default="30",
        help="K线周期: 30=30分钟, 01=日线, time=分时"
    )
    parser.add_argument(
        "--update", "-u",
        action="store_true",
        help="执行每日更新 (下载30分钟和日线)"
    )

    args = parser.parse_args()

    if args.update:
        update_daily()
    else:
        download_concept_klines(period=args.period)
