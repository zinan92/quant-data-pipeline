"""
同花顺概念板块实时监控API
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
import akshare as ak
import time
from datetime import datetime
from threading import Lock

router = APIRouter()

# 全局缓存
_cache = {
    'all_concepts': None,
    'last_update': None,
    'is_updating': False
}
_cache_lock = Lock()

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


class ConceptData(BaseModel):
    rank: int
    name: str
    code: str
    changePct: float
    changeValue: float
    mainVolume: float
    moneyInflow: float
    volumeRatio: float
    upCount: int
    downCount: int
    limitUp: int
    totalStocks: int
    turnover: float
    volume: float
    day5Change: float
    day10Change: float
    day20Change: float


class ConceptListResponse(BaseModel):
    success: bool
    timestamp: str
    total: int
    data: list[ConceptData]


def calculate_limit_up_count(concept_name: str) -> int:
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


def fetch_all_concepts() -> list[dict]:
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

            if turnover > 0:
                main_volume = (money_inflow / turnover) * volume
            else:
                main_volume = 0

            results.append({
                'code': concept_code,
                'name': concept_name,
                'changePct': float(change_pct_str),
                'changeValue': 0,
                'mainVolume': round(main_volume, 2),
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

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 成功获取 {len(results)} 个板块")
    return results


def enhance_with_limit_up(concepts: list[dict], focus_names: list[str]) -> list[dict]:
    """为指定板块补充涨停数"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 计算涨停数...")

    for concept in concepts:
        if concept['name'] in focus_names:
            limit_up = calculate_limit_up_count(concept['name'])
            concept['limitUp'] = limit_up
            print(f"  {concept['name']}: {limit_up}只涨停")
            time.sleep(0.3)

    return concepts


async def update_cache_data():
    """后台更新缓存数据"""
    global _cache

    with _cache_lock:
        if _cache['is_updating']:
            return
        _cache['is_updating'] = True

    try:
        print("\n" + "="*60)
        print(f"开始更新板块数据 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)

        # 1. 获取所有板块数据
        all_concepts = fetch_all_concepts()

        # 2. 按涨幅排序
        all_concepts.sort(key=lambda x: x['changePct'], reverse=True)

        # 3. 获取需要计算涨停数的板块
        top_20_names = [c['name'] for c in all_concepts[:20]]
        focus_names = list(set(top_20_names + WATCH_LIST))

        # 4. 计算涨停数
        all_concepts = enhance_with_limit_up(all_concepts, focus_names)

        # 5. 更新缓存
        with _cache_lock:
            _cache['all_concepts'] = all_concepts
            _cache['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            _cache['is_updating'] = False

        print(f"✅ 更新完成 - {_cache['last_update']}")

    except Exception as e:
        print(f"❌ 更新失败: {e}")
        with _cache_lock:
            _cache['is_updating'] = False


@router.get("/top", response_model=ConceptListResponse)
async def get_top_concepts(
    n: int = 20,
    background_tasks: BackgroundTasks = None
):
    """
    获取涨幅前N的概念板块

    - n: 返回前N个板块（默认20）
    """

    # 如果缓存为空或过期（超过3分钟），触发后台更新
    with _cache_lock:
        needs_update = (
            _cache['all_concepts'] is None or
            (datetime.now() - datetime.strptime(_cache['last_update'], '%Y-%m-%d %H:%M:%S')).seconds > 180
        ) if _cache['last_update'] else True

    if needs_update and background_tasks:
        background_tasks.add_task(update_cache_data)

    # 返回缓存数据
    with _cache_lock:
        if _cache['all_concepts'] is None:
            raise HTTPException(status_code=503, detail="数据未就绪，请稍后重试")

        all_concepts = _cache['all_concepts']
        last_update = _cache['last_update']

    # 提取前N
    top_concepts = all_concepts[:n]

    # 添加排名
    data = []
    for idx, concept in enumerate(top_concepts):
        data.append(ConceptData(
            rank=idx + 1,
            **concept
        ))

    return ConceptListResponse(
        success=True,
        timestamp=last_update,
        total=len(data),
        data=data
    )


@router.get("/watch", response_model=ConceptListResponse)
async def get_watch_concepts(background_tasks: BackgroundTasks = None):
    """
    获取自选热门概念板块
    """

    # 触发更新检查
    with _cache_lock:
        needs_update = (
            _cache['all_concepts'] is None or
            (datetime.now() - datetime.strptime(_cache['last_update'], '%Y-%m-%d %H:%M:%S')).seconds > 180
        ) if _cache['last_update'] else True

    if needs_update and background_tasks:
        background_tasks.add_task(update_cache_data)

    # 返回缓存数据
    with _cache_lock:
        if _cache['all_concepts'] is None:
            raise HTTPException(status_code=503, detail="数据未就绪，请稍后重试")

        all_concepts = _cache['all_concepts']
        last_update = _cache['last_update']

    # 提取自选概念
    watch_concepts = [c for c in all_concepts if c['name'] in WATCH_LIST]
    watch_concepts.sort(key=lambda x: x['changePct'], reverse=True)

    # 添加排名
    data = []
    for idx, concept in enumerate(watch_concepts):
        data.append(ConceptData(
            rank=idx + 1,
            **concept
        ))

    return ConceptListResponse(
        success=True,
        timestamp=last_update,
        total=len(data),
        data=data
    )


@router.post("/refresh")
async def force_refresh(background_tasks: BackgroundTasks):
    """
    强制刷新板块数据
    """
    background_tasks.add_task(update_cache_data)

    return {
        "success": True,
        "message": "后台更新已触发"
    }


@router.get("/status")
async def get_status():
    """
    获取监控状态
    """
    with _cache_lock:
        return {
            "is_ready": _cache['all_concepts'] is not None,
            "last_update": _cache['last_update'],
            "is_updating": _cache['is_updating'],
            "total_concepts": len(_cache['all_concepts']) if _cache['all_concepts'] else 0,
            "watch_list": WATCH_LIST
        }
