#!/usr/bin/env python3
"""
板块监控 - 无需Flask版本
定时更新数据到JSON文件，前端直接读取
包含动量信号检测功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import akshare as ak
import pandas as pd
import json
import time
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Optional
from src.database import SessionLocal
from src.models import Kline, SymbolType, KlineTimeframe
from sqlalchemy import and_, desc

# 配置
WATCH_LIST = [
    "先进封装",
    "存储芯片",
    "光刻机",
    "第三代半导体",
    "国家大基金持股",
    "汽车芯片",
    "MCU芯片",
    "中芯国际概念",
    "人形机器人",
    "特高压"
]

UPDATE_INTERVAL = 60  # 更新间隔（秒）
TOP_N = 20  # 监控前N个板块

# 输出目录
OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'monitor'
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / 'latest.json'
SIGNALS_FILE = OUTPUT_DIR / 'momentum_signals.json'

# 数据目录
DATA_DIR = Path('/Users/park/a-share-data/data')

# 快照历史（保留最近10次，用于检测动量变化）
SNAPSHOT_HISTORY: deque = deque(maxlen=10)


def build_concept_code_mapping():
    """
    建立新旧概念代码映射
    新系统代码(AKShare) -> 旧系统代码(数据库)
    通过概念名称作为桥梁
    """
    # 读取旧系统映射文件
    concept_file = DATA_DIR / 'concept_to_tickers.csv'
    df_old = pd.read_csv(concept_file)

    # 创建名称 -> 旧代码映射
    old_mapping = {}
    for _, row in df_old.iterrows():
        name = row['板块名称']
        code = row['板块代码'].replace('.TI', '')  # 886042.TI -> 886042
        old_mapping[name] = code

    return old_mapping


def calculate_n_day_change(old_code: str, n_days: int) -> float:
    """
    从数据库K线数据计算N日涨幅

    Args:
        old_code: 旧系统代码 (如 886042)
        n_days: 天数 (5, 10, 20)

    Returns:
        N日涨幅百分比，如果数据不足返回0
    """
    session = SessionLocal()
    try:
        # 获取最近的 n_days+1 条日K线（需要多一条用于计算）
        klines = session.query(Kline).filter(
            and_(
                Kline.symbol_type == SymbolType.CONCEPT,
                Kline.symbol_code == old_code,
                Kline.timeframe == KlineTimeframe.DAY
            )
        ).order_by(desc(Kline.trade_time)).limit(n_days + 1).all()

        if len(klines) < n_days + 1:
            return 0.0

        # 最新收盘价
        latest_close = klines[0].close
        # N天前的收盘价
        n_days_ago_close = klines[n_days].close

        if n_days_ago_close > 0:
            change_pct = ((latest_close - n_days_ago_close) / n_days_ago_close) * 100
            return round(change_pct, 2)

        return 0.0

    except Exception as e:
        print(f"  ⚠️  计算{old_code}的{n_days}日涨幅失败: {e}")
        return 0.0
    finally:
        session.close()


def calculate_limit_up_count(concept_name):
    """计算涨停数"""
    try:
        df_stocks = ak.stock_board_concept_cons_em(symbol=concept_name)
        if df_stocks is not None and len(df_stocks) > 0:
            limit_up_count = 0
            for _, stock in df_stocks.iterrows():
                change_pct = stock.get('涨跌幅', 0)
                code = stock.get('代码', '')

                if code.startswith('688') or code.startswith('300'):
                    if change_pct >= 19.9:
                        limit_up_count += 1
                else:
                    if change_pct >= 9.9:
                        limit_up_count += 1

            return limit_up_count
    except:
        pass
    return 0


def fetch_all_concepts():
    """获取所有概念板块数据"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 开始获取板块数据...")

    df_names = ak.stock_board_concept_name_ths()
    results = []

    for idx, row in df_names.iterrows():
        concept_name = row['name']
        concept_code = row['code']

        try:
            df_info = ak.stock_board_concept_info_ths(symbol=concept_name)

            data = {}
            for i, info_row in df_info.iterrows():
                data[info_row['项目']] = info_row['值']

            up_down = data.get('涨跌家数', '0/0')
            up_count, down_count = map(int, up_down.split('/'))

            change_pct_str = data.get('板块涨幅', '0%').replace('%', '')
            money_inflow = float(data.get('资金净流入(亿)', 0))
            turnover = float(data.get('成交额(亿)', 0))
            volume = float(data.get('成交量(万手)', 0))

            results.append({
                'code': concept_code,
                'name': concept_name,
                'changePct': float(change_pct_str),
                'changeValue': 0,
                'moneyInflow': money_inflow,
                'volumeRatio': 0,
                'upCount': up_count,
                'downCount': down_count,
                'limitUp': 0,
                'totalStocks': up_count + down_count,
                'turnover': turnover,
                'volume': volume,
                'day5Change': 0,
                'day10Change': 0,
                'day20Change': 0,
            })

            time.sleep(0.25)

        except Exception as e:
            print(f"  ✗ {concept_name}: {str(e)[:50]}")
            continue

    df = pd.DataFrame(results)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 成功获取 {len(df)} 个板块")
    return df


def enhance_with_limit_up(df, concepts):
    """为指定板块补充涨停数"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 计算涨停数...")

    for idx, row in df[df['name'].isin(concepts)].iterrows():
        concept_name = row['name']
        limit_up = calculate_limit_up_count(concept_name)
        df.at[idx, 'limitUp'] = limit_up
        print(f"  {concept_name}: {limit_up}只涨停")
        time.sleep(0.3)

    return df


def enhance_with_historical_changes(df, concepts):
    """
    为指定板块补充历史涨幅数据
    从本地数据库K线表读取
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 计算历史涨幅...")

    # 建立新旧代码映射
    code_mapping = build_concept_code_mapping()

    for idx, row in df[df['name'].isin(concepts)].iterrows():
        concept_name = row['name']

        # 获取旧系统代码
        old_code = code_mapping.get(concept_name)

        if not old_code:
            print(f"  ⚠️  {concept_name}: 未找到旧代码映射")
            continue

        # 计算5日、10日、20日涨幅
        day5_change = calculate_n_day_change(old_code, 5)
        day10_change = calculate_n_day_change(old_code, 10)
        day20_change = calculate_n_day_change(old_code, 20)

        df.at[idx, 'day5Change'] = day5_change
        df.at[idx, 'day10Change'] = day10_change
        df.at[idx, 'day20Change'] = day20_change

        print(f"  {concept_name}: 5日{day5_change:+.2f}% 10日{day10_change:+.2f}% 20日{day20_change:+.2f}%")

    return df


def check_kline_pattern(old_code: str) -> Optional[Dict]:
    """
    检测30分钟K线形态 (Criterion 3)
    阳线且无上影线: close > open 且 (high - close) / (close - open) < 0.05

    Args:
        old_code: 旧系统代码 (如 886042)

    Returns:
        如果符合条件返回形态信息，否则返回None
    """
    session = SessionLocal()
    try:
        # 获取最新的30分钟K线
        latest_kline = session.query(Kline).filter(
            and_(
                Kline.symbol_type == SymbolType.CONCEPT,
                Kline.symbol_code == old_code,
                Kline.timeframe == KlineTimeframe.MINS_30
            )
        ).order_by(desc(Kline.trade_time)).first()

        if not latest_kline:
            return None

        # 检查是否为阳线
        is_yang = latest_kline.close > latest_kline.open
        if not is_yang:
            return None

        # 检查上影线比例
        body_size = latest_kline.close - latest_kline.open
        if body_size <= 0:
            return None

        upper_shadow_ratio = (latest_kline.high - latest_kline.close) / body_size

        # 上影线小于5%视为无上影线
        if upper_shadow_ratio < 0.05:
            return {
                'trade_time': latest_kline.trade_time,
                'open': latest_kline.open,
                'high': latest_kline.high,
                'low': latest_kline.low,
                'close': latest_kline.close,
                'upper_shadow_ratio': round(upper_shadow_ratio * 100, 2)
            }

        return None

    except Exception as e:
        print(f"  ⚠️  检测{old_code}的K线形态失败: {e}")
        return None
    finally:
        session.close()


def detect_surge_signals(df_current: pd.DataFrame) -> List[Dict]:
    """
    检测上涨家数激增信号 (Criterion 2)
    大板块(≥50只): 60秒内新增≥5只上涨
    小板块(<50只): 60秒内新增≥3只上涨

    Args:
        df_current: 当前板块数据

    Returns:
        符合条件的信号列表
    """
    signals = []

    # 需要至少一次历史快照才能检测
    if len(SNAPSHOT_HISTORY) == 0:
        return signals

    # 获取60秒前的快照（当前间隔60秒，所以取上一次快照）
    prev_snapshot = SNAPSHOT_HISTORY[0]

    # 遍历当前所有板块
    for _, current_row in df_current.iterrows():
        concept_name = current_row['name']
        current_up_count = current_row['upCount']
        total_stocks = current_row['totalStocks']

        # 查找历史快照中对应的板块
        prev_row = prev_snapshot[prev_snapshot['name'] == concept_name]
        if prev_row.empty:
            continue

        prev_up_count = prev_row.iloc[0]['upCount']
        delta_up_count = current_up_count - prev_up_count

        # 判断是否触发信号
        is_large_board = total_stocks >= 50
        threshold = 5 if is_large_board else 3

        if delta_up_count >= threshold:
            signals.append({
                'concept_name': concept_name,
                'concept_code': current_row['code'],
                'signal_type': 'surge',
                'total_stocks': total_stocks,
                'prev_up_count': int(prev_up_count),
                'current_up_count': int(current_up_count),
                'delta_up_count': int(delta_up_count),
                'threshold': threshold,
                'board_type': 'large' if is_large_board else 'small',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'details': f"{delta_up_count}只新增上涨 (阈值: {threshold}只)"
            })

    return signals


def detect_kline_pattern_signals(df_current: pd.DataFrame) -> List[Dict]:
    """
    检测30分钟K线形态信号 (Criterion 3)

    Args:
        df_current: 当前板块数据

    Returns:
        符合条件的信号列表
    """
    signals = []
    code_mapping = build_concept_code_mapping()

    # 只检测涨幅前20的板块和自选板块
    focus_concepts = df_current.head(TOP_N)['name'].tolist() + WATCH_LIST
    focus_concepts = list(set(focus_concepts))

    for concept_name in focus_concepts:
        old_code = code_mapping.get(concept_name)
        if not old_code:
            continue

        pattern_info = check_kline_pattern(old_code)
        if pattern_info:
            # 获取当前板块数据
            concept_row = df_current[df_current['name'] == concept_name]
            if concept_row.empty:
                continue

            concept_data = concept_row.iloc[0]

            signals.append({
                'concept_name': concept_name,
                'concept_code': concept_data['code'],
                'signal_type': 'kline_pattern',
                'total_stocks': int(concept_data['totalStocks']),
                'current_change_pct': float(concept_data['changePct']),
                'kline_info': pattern_info,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'details': f"阳线无上影线 (上影{pattern_info['upper_shadow_ratio']}%)"
            })

    return signals


def save_momentum_signals(surge_signals: List[Dict], kline_signals: List[Dict]):
    """
    保存动量信号到JSON文件

    Args:
        surge_signals: 上涨激增信号列表
        kline_signals: K线形态信号列表
    """
    all_signals = surge_signals + kline_signals

    output_data = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_signals': len(all_signals),
        'surge_signals_count': len(surge_signals),
        'kline_signals_count': len(kline_signals),
        'signals': all_signals
    }

    with open(SIGNALS_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    if all_signals:
        print(f"\n🔔 检测到 {len(all_signals)} 个动量信号:")
        print(f"   - 上涨激增: {len(surge_signals)}个")
        print(f"   - K线形态: {len(kline_signals)}个")
        for signal in all_signals[:5]:  # 显示前5个
            print(f"   [{signal['signal_type']}] {signal['concept_name']}: {signal['details']}")


def update_data():
    """更新数据"""
    print("\n" + "="*60)
    print(f"开始更新 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # 1. 获取所有板块数据
    df_all = fetch_all_concepts()

    # 2. 获取涨幅前20
    df_all = df_all.sort_values('changePct', ascending=False)
    top_concepts = df_all.head(TOP_N)['name'].tolist()

    # 3. 合并需要计算涨停数和历史涨幅的板块
    focus_concepts = list(set(top_concepts + WATCH_LIST))

    # 4. 计算涨停数
    df_all = enhance_with_limit_up(df_all, focus_concepts)

    # 5. 计算历史涨幅 (5日/10日/20日)
    df_all = enhance_with_historical_changes(df_all, focus_concepts)

    # 6. 按涨幅重新排序
    df_all = df_all.sort_values('changePct', ascending=False)

    # 7. 提取数据
    df_top = df_all.head(TOP_N).copy()
    df_watch = df_all[df_all['name'].isin(WATCH_LIST)].copy()

    # 8. 添加排名
    df_top['rank'] = range(1, len(df_top) + 1)
    df_watch['rank'] = range(1, len(df_watch) + 1)

    # 9. 检测动量信号
    surge_signals = detect_surge_signals(df_all)
    kline_signals = detect_kline_pattern_signals(df_all)

    # 10. 保存动量信号
    save_momentum_signals(surge_signals, kline_signals)

    # 11. 保存当前快照到历史
    SNAPSHOT_HISTORY.appendleft(df_all.copy())

    # 12. 保存为JSON
    output_data = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'updateInterval': UPDATE_INTERVAL,
        'topConcepts': {
            'total': len(df_top),
            'data': df_top.to_dict('records')
        },
        'watchConcepts': {
            'total': len(df_watch),
            'data': df_watch.to_dict('records')
        }
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 数据已更新: {OUTPUT_FILE}")
    print(f"   - 涨幅前{TOP_N}: {len(df_top)}个")
    print(f"   - 自选概念: {len(df_watch)}个")

    # 13. 打印摘要
    print(f"\n📊 涨幅前5:")
    for idx, row in df_top.head(5).iterrows():
        print(f"   {row['rank']}. {row['name']:15s} "
              f"{row['changePct']:+6.2f}% "
              f"涨停:{row['limitUp']:2d} "
              f"资金:{row['moneyInflow']:8.2f}亿")


def run_continuous():
    """持续运行"""
    print("="*60)
    print("🚀 板块监控启动（无需Flask版本）")
    print("="*60)
    print(f"监控配置:")
    print(f"  - 涨幅前{TOP_N}概念")
    print(f"  - 自选概念: {len(WATCH_LIST)}个")
    print(f"  - 更新间隔: {UPDATE_INTERVAL}秒 ({UPDATE_INTERVAL/60:.1f}分钟)")
    print(f"  - 输出文件: {OUTPUT_FILE}")
    print("="*60)
    print(f"\n💡 前端读取: {OUTPUT_FILE}")
    print(f"   或通过HTTP: http://localhost:8000/docs/monitor/latest.json")
    print("="*60)

    iteration = 0
    while True:
        try:
            iteration += 1
            print(f"\n第{iteration}轮监控")

            update_data()

            print(f"\n⏰ 等待 {UPDATE_INTERVAL}秒...")
            time.sleep(UPDATE_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断，停止监控")
            break
        except Exception as e:
            print(f"\n❌ 更新失败: {e}")
            print(f"等待30秒后重试...")
            time.sleep(30)


def run_once():
    """单次运行"""
    print("运行模式: 单次更新")
    update_data()


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        run_once()
    else:
        run_continuous()
