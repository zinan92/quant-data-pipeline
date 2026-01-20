#!/usr/bin/env python3
"""
板块监控API服务
为前端面板提供实时数据接口
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import akshare as ak
import pandas as pd
import time
from datetime import datetime
from threading import Thread, Lock
import json

app = Flask(__name__)
CORS(app)  # 允许跨域访问

# 全局缓存
cache = {
    'all_concepts': None,
    'last_update': None,
    'is_updating': False
}
cache_lock = Lock()

# 自选热门概念
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


def calculate_limit_up_count(concept_name):
    """计算涨停数"""
    try:
        df_stocks = ak.stock_board_concept_cons_em(symbol=concept_name)
        if df_stocks is not None and len(df_stocks) > 0:
            limit_up_count = 0
            for _, stock in df_stocks.iterrows():
                change_pct = stock.get('涨跌幅', 0)
                code = stock.get('代码', '')

                # 科创板/创业板 20%，主板 10%
                if code.startswith('688') or code.startswith('300'):
                    if change_pct >= 19.9:
                        limit_up_count += 1
                else:
                    if change_pct >= 9.9:
                        limit_up_count += 1

            return limit_up_count, len(df_stocks)
    except:
        pass
    return 0, 0


def fetch_all_concepts():
    """获取所有概念板块数据"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始更新板块数据...")

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

            # 解析数据
            up_down = data.get('涨跌家数', '0/0')
            up_count, down_count = map(int, up_down.split('/'))

            change_pct_str = data.get('板块涨幅', '0%').replace('%', '')
            money_inflow = float(data.get('资金净流入(亿)', 0))
            turnover = float(data.get('成交额(亿)', 0))
            volume = float(data.get('成交量(万手)', 0))

            # 主力净量
            if turnover > 0:
                main_volume = (money_inflow / turnover) * volume
            else:
                main_volume = 0

            results.append({
                'code': concept_code,
                'name': concept_name,
                'change_pct': float(change_pct_str),
                'change_value': 0,  # 占位
                'main_volume': round(main_volume, 2),
                'money_inflow': money_inflow,
                'volume_ratio': 0,  # 占位，需要历史数据
                'up_count': up_count,
                'down_count': down_count,
                'limit_up': 0,  # 稍后计算
                'total_stocks': up_count + down_count,
                'turnover': turnover,
                'volume': volume,
                'market_cap': 0,  # 占位
                'circulating_cap': 0,  # 占位
                'day5_change': 0,  # 占位
                'day10_change': 0,  # 占位
                'day20_change': 0,  # 占位
            })

            time.sleep(0.25)  # 限流

        except Exception as e:
            print(f"  ✗ {concept_name}: {str(e)[:50]}")
            continue

    df = pd.DataFrame(results)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 获取到 {len(df)} 个板块")

    return df


def enhance_top_concepts_with_limit_up(df, top_n=20):
    """为涨幅前N的板块补充涨停数"""
    df_top = df.nlargest(top_n, 'change_pct').copy()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 计算涨停数...")

    for idx, row in df_top.iterrows():
        concept_name = row['name']
        limit_up, total = calculate_limit_up_count(concept_name)
        df.at[idx, 'limit_up'] = limit_up
        print(f"  {concept_name}: {limit_up}/{total}")
        time.sleep(0.3)

    return df


def update_cache_background():
    """后台定时更新缓存"""
    while True:
        try:
            with cache_lock:
                if cache['is_updating']:
                    print("更新中，跳过本轮")
                    time.sleep(60)
                    continue

                cache['is_updating'] = True

            print(f"\n{'='*60}")
            print(f"开始后台更新 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")

            # 获取所有板块数据
            df_all = fetch_all_concepts()

            # 计算涨幅前20的涨停数
            df_all = enhance_top_concepts_with_limit_up(df_all, top_n=20)

            with cache_lock:
                cache['all_concepts'] = df_all
                cache['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cache['is_updating'] = False

            print(f"✅ 更新完成 - {cache['last_update']}")

            # 等待2.5分钟
            time.sleep(150)

        except Exception as e:
            print(f"❌ 更新失败: {e}")
            with cache_lock:
                cache['is_updating'] = False
            time.sleep(30)


@app.route('/api/concepts/top', methods=['GET'])
def get_top_concepts():
    """获取涨幅前N的概念板块"""
    n = request.args.get('n', default=20, type=int)

    with cache_lock:
        if cache['all_concepts'] is None:
            return jsonify({'error': '数据未就绪，请稍后重试'}), 503

        df = cache['all_concepts']

    df_top = df.nlargest(n, 'change_pct')

    # 转换为前端需要的格式
    data = []
    for idx, row in df_top.iterrows():
        data.append({
            'rank': len(data) + 1,
            'name': row['name'],
            'code': row['code'],
            'changePct': round(row['change_pct'], 2),
            'changeValue': round(row['change_value'], 2),
            'mainVolume': round(row['main_volume'], 2),
            'moneyInflow': round(row['money_inflow'], 2),
            'volumeRatio': round(row['volume_ratio'], 2),
            'upCount': int(row['up_count']),
            'downCount': int(row['down_count']),
            'limitUp': int(row['limit_up']),
            'day5Change': round(row['day5_change'], 2),
            'day10Change': round(row['day10_change'], 2),
            'day20Change': round(row['day20_change'], 2),
            'volume': round(row['volume'], 2),
            'turnover': round(row['turnover'], 2),
            'marketCap': round(row['market_cap'], 2),
            'circulatingCap': round(row['circulating_cap'], 2),
        })

    return jsonify({
        'success': True,
        'timestamp': cache['last_update'],
        'total': len(data),
        'data': data
    })


@app.route('/api/concepts/watch', methods=['GET'])
def get_watch_concepts():
    """获取自选概念板块"""
    with cache_lock:
        if cache['all_concepts'] is None:
            return jsonify({'error': '数据未就绪，请稍后重试'}), 503

        df = cache['all_concepts']

    df_watch = df[df['name'].isin(WATCH_LIST)].copy()
    df_watch = df_watch.sort_values('change_pct', ascending=False)

    # 为自选概念也计算涨停数
    for idx, row in df_watch.iterrows():
        if row['limit_up'] == 0:  # 如果还没计算
            concept_name = row['name']
            limit_up, _ = calculate_limit_up_count(concept_name)
            df_watch.at[idx, 'limit_up'] = limit_up

    data = []
    for idx, row in df_watch.iterrows():
        data.append({
            'rank': len(data) + 1,
            'name': row['name'],
            'code': row['code'],
            'changePct': round(row['change_pct'], 2),
            'changeValue': round(row['change_value'], 2),
            'mainVolume': round(row['main_volume'], 2),
            'moneyInflow': round(row['money_inflow'], 2),
            'volumeRatio': round(row['volume_ratio'], 2),
            'upCount': int(row['up_count']),
            'downCount': int(row['down_count']),
            'limitUp': int(row['limit_up']),
            'day5Change': round(row['day5_change'], 2),
            'day10Change': round(row['day10_change'], 2),
            'day20Change': round(row['day20_change'], 2),
            'volume': round(row['volume'], 2),
            'turnover': round(row['turnover'], 2),
            'marketCap': round(row['market_cap'], 2),
            'circulatingCap': round(row['circulatingCap'], 2),
        })

    return jsonify({
        'success': True,
        'timestamp': cache['last_update'],
        'total': len(data),
        'data': data
    })


@app.route('/api/concepts/all', methods=['GET'])
def get_all_concepts():
    """获取所有概念板块（支持排序和筛选）"""
    with cache_lock:
        if cache['all_concepts'] is None:
            return jsonify({'error': '数据未就绪，请稍后重试'}), 503

        df = cache['all_concepts'].copy()

    # 排序
    sort_by = request.args.get('sort', default='changePct', type=str)
    order = request.args.get('order', default='desc', type=str)

    sort_map = {
        'changePct': 'change_pct',
        'moneyInflow': 'money_inflow',
        'mainVolume': 'main_volume',
        'volumeRatio': 'volume_ratio',
        'upCount': 'up_count',
        'limitUp': 'limit_up'
    }

    sort_col = sort_map.get(sort_by, 'change_pct')
    ascending = (order == 'asc')
    df = df.sort_values(sort_col, ascending=ascending)

    # 分页
    page = request.args.get('page', default=1, type=int)
    page_size = request.args.get('pageSize', default=50, type=int)

    start = (page - 1) * page_size
    end = start + page_size
    df_page = df.iloc[start:end]

    data = []
    for idx, row in df_page.iterrows():
        data.append({
            'rank': start + len(data) + 1,
            'name': row['name'],
            'code': row['code'],
            'changePct': round(row['change_pct'], 2),
            'changeValue': round(row['change_value'], 2),
            'mainVolume': round(row['main_volume'], 2),
            'moneyInflow': round(row['money_inflow'], 2),
            'volumeRatio': round(row['volume_ratio'], 2),
            'upCount': int(row['up_count']),
            'downCount': int(row['down_count']),
            'limitUp': int(row['limit_up']),
            'day5Change': round(row['day5_change'], 2),
            'day10Change': round(row['day10_change'], 2),
            'day20Change': round(row['day20_change'], 2),
            'volume': round(row['volume'], 2),
            'turnover': round(row['turnover'], 2),
            'marketCap': round(row['market_cap'], 2),
            'circulatingCap': round(row['circulating_cap'], 2),
        })

    return jsonify({
        'success': True,
        'timestamp': cache['last_update'],
        'total': len(df),
        'page': page,
        'pageSize': page_size,
        'data': data
    })


@app.route('/api/status', methods=['GET'])
def get_status():
    """获取系统状态"""
    with cache_lock:
        status = {
            'is_ready': cache['all_concepts'] is not None,
            'last_update': cache['last_update'],
            'is_updating': cache['is_updating'],
            'total_concepts': len(cache['all_concepts']) if cache['all_concepts'] is not None else 0
        }

    return jsonify(status)


@app.route('/api/config/watch-list', methods=['GET', 'POST'])
def manage_watch_list():
    """管理自选列表"""
    global WATCH_LIST

    if request.method == 'GET':
        return jsonify({
            'success': True,
            'watchList': WATCH_LIST
        })

    elif request.method == 'POST':
        data = request.get_json()
        new_list = data.get('watchList', [])

        if isinstance(new_list, list):
            WATCH_LIST = new_list
            return jsonify({
                'success': True,
                'message': '自选列表已更新',
                'watchList': WATCH_LIST
            })
        else:
            return jsonify({
                'success': False,
                'message': '无效的数据格式'
            }), 400


def init_cache():
    """初始化缓存"""
    print("正在初始化数据...")
    df_all = fetch_all_concepts()
    df_all = enhance_top_concepts_with_limit_up(df_all, top_n=20)

    with cache_lock:
        cache['all_concepts'] = df_all
        cache['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"✅ 初始化完成 - {cache['last_update']}")


if __name__ == '__main__':
    # 初始化数据
    init_cache()

    # 启动后台更新线程
    update_thread = Thread(target=update_cache_background, daemon=True)
    update_thread.start()

    # 启动Flask服务
    print("\n" + "="*60)
    print("🚀 板块监控API服务已启动")
    print("="*60)
    print("API端点:")
    print("  - GET  /api/concepts/top        涨幅前N板块")
    print("  - GET  /api/concepts/watch      自选板块")
    print("  - GET  /api/concepts/all        所有板块（分页）")
    print("  - GET  /api/status              系统状态")
    print("  - GET  /api/config/watch-list   自选列表管理")
    print("="*60)

    app.run(host='0.0.0.0', port=5000, debug=False)
