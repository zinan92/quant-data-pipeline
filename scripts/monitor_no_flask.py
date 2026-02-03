#!/usr/bin/env python3
"""
板块监控 — 同花顺数据源版本
使用 TuShare Pro 的同花顺行业资金流向接口获取板块涨跌数据。
定时更新数据到 data/monitor/latest.json，前端 API 直接读取。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import time
from datetime import datetime
from typing import Dict, List

import pandas as pd

from src.config import get_settings
from src.services.tushare_client import TushareClient
from src.services.tonghuashun_service import (
    TonghuashunService,
    CATEGORY_TO_THS_CONCEPTS,
)

# ── 配置 ──
UPDATE_INTERVAL = 300  # 更新间隔（秒）— 同花顺数据非实时，5分钟足够
TOP_N = 20  # 监控前 N 个板块

# 输出目录
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "monitor"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "latest.json"

# ── 自选热门概念名称（从 CATEGORY_TO_THS_CONCEPTS 汇总） ──
# 取每个赛道最核心的概念名称，确保与行业资金流向数据能匹配
WATCH_NAMES: List[str] = [
    "光伏设备",
    "半导体",
    "小金属",
    "通信设备",
    "电力",
    "汽车零部件",
    "消费电子",
    "计算机设备",
    "化学制药",
    "军工电子",
    "电池",
    "贵金属",
    "电网设备",
    "白酒",
    "游戏",
    "自动化设备",
    "软件开发",
    "能源金属",
]


def _fetch_historical_changes(client: TushareClient, ts_codes: List[str]) -> Dict[str, Dict]:
    """Fetch 5d/10d/20d historical changes and volume via ths_daily."""
    import tushare as ts
    pro = ts.pro_api(client.token)
    
    result = {}
    for code in ts_codes:
        try:
            df = pro.ths_daily(ts_code=code, start_date='20260101', end_date='20260203')
            if df.empty or len(df) < 2:
                continue
            
            today_close = df.iloc[0]["close"]
            today_vol = float(df.iloc[0].get("vol", 0) or 0)
            
            # Calculate N-day changes
            day5 = day10 = day20 = 0.0
            if len(df) >= 6:
                day5 = round((today_close - df.iloc[5]["close"]) / df.iloc[5]["close"] * 100, 2)
            if len(df) >= 11:
                day10 = round((today_close - df.iloc[10]["close"]) / df.iloc[10]["close"] * 100, 2)
            if len(df) >= 21:
                day20 = round((today_close - df.iloc[20]["close"]) / df.iloc[20]["close"] * 100, 2)
            
            result[code] = {
                "day5Change": day5,
                "day10Change": day10,
                "day20Change": day20,
                "volume": round(today_vol / 10000, 2),  # 转万手
            }
        except Exception:
            continue
    
    return result


def _row_to_concept_dict(row: pd.Series, rank: int, hist: Dict = None) -> Dict:
    """将 moneyflow DataFrame 行转为前端格式 dict。"""

    pct_change = float(row.get("pct_change", 0) or 0)
    net_amount = float(row.get("net_amount", 0) or 0)
    company_num = int(row.get("company_num", 0) or 0)
    close = float(row.get("close", 0) or 0)
    net_buy = float(row.get("net_buy_amount", 0) or 0)
    net_sell = float(row.get("net_sell_amount", 0) or 0)
    ts_code = row.get("ts_code", "")
    
    # Historical data if available
    h = (hist or {}).get(ts_code, {})

    return {
        "rank": rank,
        "name": row.get("industry", row.get("name", "")),
        "code": ts_code,
        "changePct": round(pct_change, 2),
        "changeValue": round(close, 2),
        "moneyInflow": round(net_amount, 2),
        "volumeRatio": 0,
        "upCount": 0,
        "downCount": 0,
        "limitUp": 0,
        "totalStocks": company_num,
        "turnover": round(net_buy + net_sell, 2),
        "volume": h.get("volume", 0),
        "day5Change": h.get("day5Change", 0),
        "day10Change": h.get("day10Change", 0),
        "day20Change": h.get("day20Change", 0),
    }


def update_data(service: TonghuashunService) -> None:
    """主更新逻辑：获取行业排名 → 生成 JSON。"""

    print(f"\n{'=' * 60}")
    print(f"开始更新 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    # 1. 获取行业资金流向排名
    print("\n[1/3] 获取同花顺行业资金流向...")
    df = service.get_industry_ranking()

    if df.empty:
        print("⚠️  行业资金流向数据为空，跳过本次更新")
        return

    print(f"  ✓ 获取到 {len(df)} 个行业板块")

    # 1.5. 获取历史涨跌数据（5日/10日/20日 + 成交量）
    print("\n[1.5/3] 获取历史涨跌数据...")
    all_codes = df["ts_code"].tolist()
    hist = _fetch_historical_changes(service._client, all_codes[:TOP_N + len(WATCH_NAMES)])
    print(f"  ✓ 获取到 {len(hist)} 个板块的历史数据")

    # 2. 构建 topConcepts（涨幅前 TOP_N）
    print(f"\n[2/3] 构建涨幅 TOP{TOP_N}...")
    df_top = df.head(TOP_N)
    top_data = []
    for idx, (_, row) in enumerate(df_top.iterrows(), start=1):
        top_data.append(_row_to_concept_dict(row, idx, hist))

    # 3. 构建 watchConcepts（自选热门）
    print(f"\n[3/3] 构建自选热门概念...")
    watch_data = []
    for watch_name in WATCH_NAMES:
        matched = df[df["industry"] == watch_name]
        if not matched.empty:
            row = matched.iloc[0]
            watch_data.append(_row_to_concept_dict(row, len(watch_data) + 1, hist))
        else:
            print(f"  ⚠️  自选概念 '{watch_name}' 未在行业数据中找到")

    # Re-rank watch data
    for idx, item in enumerate(watch_data, start=1):
        item["rank"] = idx

    # 4. 保存 JSON
    output = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updateInterval": UPDATE_INTERVAL,
        "dataSource": "tonghuashun_tushare",
        "topConcepts": {
            "total": len(top_data),
            "data": top_data,
        },
        "watchConcepts": {
            "total": len(watch_data),
            "data": watch_data,
        },
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 数据已写入: {OUTPUT_FILE}")
    print(f"   — 涨幅 TOP{TOP_N}: {len(top_data)} 个")
    print(f"   — 自选热门: {len(watch_data)} 个")

    # 摘要
    print(f"\n📊 涨幅前 5:")
    for item in top_data[:5]:
        print(
            f"   {item['rank']:2d}. {item['name']:10s}  "
            f"{item['changePct']:+6.2f}%  "
            f"净流入: {item['moneyInflow']:+8.2f}亿  "
            f"成分: {item['totalStocks']}只"
        )


def run_once(service: TonghuashunService) -> None:
    """单次运行。"""
    print("运行模式: 单次更新")
    update_data(service)


def run_continuous(service: TonghuashunService) -> None:
    """持续运行模式。"""
    print("=" * 60)
    print("🚀 板块监控启动（同花顺数据源）")
    print("=" * 60)
    print(f"监控配置:")
    print(f"  — 涨幅前 {TOP_N} 行业")
    print(f"  — 自选热门: {len(WATCH_NAMES)} 个")
    print(f"  — 更新间隔: {UPDATE_INTERVAL} 秒 ({UPDATE_INTERVAL / 60:.1f} 分钟)")
    print(f"  — 输出文件: {OUTPUT_FILE}")
    print("=" * 60)

    iteration = 0
    while True:
        try:
            iteration += 1
            print(f"\n第 {iteration} 轮监控")
            update_data(service)
            print(f"\n⏰ 等待 {UPDATE_INTERVAL} 秒...")
            time.sleep(UPDATE_INTERVAL)
        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断，停止监控")
            break
        except Exception as e:
            print(f"\n❌ 更新失败: {e}")
            import traceback
            traceback.print_exc()
            print("等待 30 秒后重试...")
            time.sleep(30)


if __name__ == "__main__":
    # Initialise service
    settings = get_settings()
    client = TushareClient(
        token=settings.tushare_token,
        points=settings.tushare_points,
    )
    svc = TonghuashunService(client=client)

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_once(svc)
    else:
        run_continuous(svc)
