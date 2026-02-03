#!/usr/bin/env python3
"""
板块监控 — 同花顺数据源版本 (混排: 90行业 + ~390概念)
使用 TuShare Pro 的 ths_daily 获取所有板块涨跌数据，
moneyflow_ind_ths 补充90个行业的资金流向。
定时更新数据到 data/monitor/latest.json，前端 API 直接读取。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Set

import pandas as pd

from src.config import get_settings
from src.services.tushare_client import TushareClient
from src.services.tonghuashun_service import TonghuashunService

# ── 配置 ──
UPDATE_INTERVAL = 300  # 更新间隔（秒）— 同花顺数据非实时，5分钟足够
TOP_N = 20  # 监控前 N 个板块

# 输出目录
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "monitor"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "latest.json"

# ── 自选热门（行业 + 概念混排） ──
WATCH_NAMES: List[str] = [
    # 行业
    "光伏设备", "半导体", "电池", "贵金属", "白酒", "军工电子",
    "通信设备", "消费电子", "自动化设备", "软件开发", "能源金属",
    # 概念
    "人形机器人", "AI应用", "光刻机", "BC电池", "钙钛矿电池",
    "稀土永磁", "智能电网", "芯片概念",
]


# ── 板块代码前缀 ──
_INDUSTRY_PREFIX = "881"
_CONCEPT_PREFIXES = ("885", "886")
_ALL_PREFIXES_RE = re.compile(r"^(881|885|886)")


def _build_name_map(client: TushareClient) -> Dict[str, str]:
    """Build ts_code → name mapping from ths_index (industry + concept)."""
    import tushare as ts
    pro = ts.pro_api(client.token)
    name_map: Dict[str, str] = {}

    try:
        df_i = pro.ths_index(exchange='A', type='I')  # 行业
        if not df_i.empty:
            name_map.update(dict(zip(df_i['ts_code'], df_i['name'])))
            print(f"  ✓ 行业指数名称: {len(df_i)} 条")
        time.sleep(0.3)

        df_n = pro.ths_index(exchange='A', type='N')  # 概念
        if not df_n.empty:
            name_map.update(dict(zip(df_n['ts_code'], df_n['name'])))
            print(f"  ✓ 概念指数名称: {len(df_n)} 条")
    except Exception as e:
        print(f"  ⚠️ 获取名称映射失败: {e}")

    return name_map


def _fetch_mixed_daily(client: TushareClient, trade_date: str, name_map: Dict[str, str]) -> pd.DataFrame:
    """Fetch ths_daily for the given date, filter to 881/885/886, add name & board_type."""
    import tushare as ts
    pro = ts.pro_api(client.token)

    try:
        df = pro.ths_daily(trade_date=trade_date)
    except Exception as e:
        print(f"  ⚠️ ths_daily 获取失败: {e}")
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # Filter to industry + concept codes
    mask = df['ts_code'].str.match(_ALL_PREFIXES_RE)
    df = df[mask].copy()

    # Add name and board_type
    df['name'] = df['ts_code'].map(name_map)
    df['board_type'] = df['ts_code'].apply(
        lambda x: '行业' if x.startswith(_INDUSTRY_PREFIX) else '概念'
    )

    # Drop rows with no name mapping
    df = df.dropna(subset=['name'])

    # Sort by pct_change descending
    df = df.sort_values('pct_change', ascending=False).reset_index(drop=True)
    return df


def _fetch_moneyflow_map(client: TushareClient, trade_date: str) -> Dict[str, Dict]:
    """Fetch moneyflow for 90 industries, return {ts_code: {net_amount, turnover, company_num, ...}}."""
    try:
        df = client.fetch_ths_industry_moneyflow(trade_date=trade_date)
    except Exception as e:
        print(f"  ⚠️ moneyflow 获取失败: {e}")
        return {}

    if df.empty:
        return {}

    result: Dict[str, Dict] = {}
    for _, row in df.iterrows():
        ts_code = row.get("ts_code", "")
        net_buy = float(row.get("net_buy_amount", 0) or 0)
        net_sell = float(row.get("net_sell_amount", 0) or 0)
        result[ts_code] = {
            "net_amount": float(row.get("net_amount", 0) or 0),
            "turnover": round(net_buy + net_sell, 2),
            "company_num": int(row.get("company_num", 0) or 0),
            "lead_stock": row.get("lead_stock", ""),
        }
    return result


def _fetch_limit_counts(client: TushareClient, trade_date: str) -> Dict[str, Dict]:
    """Fetch limit-up/down counts per industry name from limit_list_d."""
    import tushare as ts
    pro = ts.pro_api(client.token)

    result: Dict[str, Dict] = {}
    try:
        df_up = pro.limit_list_d(trade_date=trade_date, limit_type='U')
        if not df_up.empty:
            counts = df_up.groupby('industry').size()
            for ind, cnt in counts.items():
                result.setdefault(ind, {})["limitUp"] = int(cnt)

        time.sleep(0.3)

        df_down = pro.limit_list_d(trade_date=trade_date, limit_type='D')
        if not df_down.empty:
            counts = df_down.groupby('industry').size()
            for ind, cnt in counts.items():
                result.setdefault(ind, {})["limitDown"] = int(cnt)
    except Exception as e:
        print(f"  ⚠️ 获取涨跌停数据失败: {e}")

    return result


def _fetch_up_down_counts(client: TushareClient, ts_codes: List[str], trade_date: str) -> Dict[str, Dict]:
    """Fetch up/down stock counts for given board ts_codes via ths_member + daily."""
    import tushare as ts
    pro = ts.pro_api(client.token)

    result: Dict[str, Dict] = {}

    # Get all A-share daily data for today in one call
    try:
        df_daily = pro.daily(trade_date=trade_date)
        if df_daily.empty:
            return result
    except Exception as e:
        print(f"  ⚠️ 获取日线数据失败: {e}")
        return result

    for code in ts_codes:
        try:
            members = pro.ths_member(ts_code=code)
            time.sleep(0.3)
            if members.empty:
                continue

            member_codes = set(members["con_code"].tolist())
            matched = df_daily[df_daily["ts_code"].isin(member_codes)]

            up_count = int((matched["pct_chg"] > 0).sum())
            down_count = int((matched["pct_chg"] < 0).sum())

            result[code] = {"upCount": up_count, "downCount": down_count}
        except Exception:
            continue

    return result


def _fetch_historical_changes(client: TushareClient, ts_codes: List[str]) -> Dict[str, Dict]:
    """Fetch 5d/10d/20d historical changes and volume via ths_daily."""
    import tushare as ts
    pro = ts.pro_api(client.token)

    result: Dict[str, Dict] = {}
    for code in ts_codes:
        try:
            df = pro.ths_daily(ts_code=code, start_date='20260101', end_date='20260630')
            time.sleep(0.3)
            if df.empty or len(df) < 2:
                continue

            today_close = df.iloc[0]["close"]
            today_vol = float(df.iloc[0].get("vol", 0) or 0)

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


def _build_item(
    row: pd.Series,
    rank: int,
    moneyflow: Dict[str, Dict],
    hist: Dict[str, Dict],
    limit_counts: Dict[str, Dict],
    up_down: Dict[str, Dict],
) -> Dict:
    """Convert a mixed-daily row into frontend-compatible dict."""
    ts_code = row.get("ts_code", "")
    name = row.get("name", "")
    board_type = row.get("board_type", "行业")
    pct_change = float(row.get("pct_change", 0) or 0)
    close = float(row.get("close", 0) or 0)
    vol = float(row.get("vol", 0) or 0)

    # Moneyflow data (only for industries)
    mf = moneyflow.get(ts_code, {})
    net_amount = mf.get("net_amount", 0)
    turnover = mf.get("turnover", 0)
    company_num = mf.get("company_num", 0)

    # Historical data
    h = hist.get(ts_code, {})

    # Limit counts (keyed by industry name, only for 881xxx)
    lc = limit_counts.get(name, {}) if board_type == "行业" else {}

    # Up/down counts (keyed by ts_code)
    ud = up_down.get(ts_code, {})

    return {
        "rank": rank,
        "name": name,
        "code": ts_code,
        "boardType": board_type,
        "changePct": round(pct_change, 2),
        "changeValue": round(close, 2),
        "moneyInflow": round(net_amount, 2),
        "volumeRatio": 0,
        "upCount": ud.get("upCount", 0),
        "downCount": ud.get("downCount", 0),
        "limitUp": lc.get("limitUp", 0),
        "totalStocks": company_num,
        "turnover": round(turnover, 2),
        "volume": h.get("volume", round(vol / 10000, 2)),
        "day5Change": h.get("day5Change", 0),
        "day10Change": h.get("day10Change", 0),
        "day20Change": h.get("day20Change", 0),
    }


def update_data(service: TonghuashunService) -> None:
    """主更新逻辑：获取行业+概念混排 → 生成 JSON。"""

    print(f"\n{'=' * 60}")
    print(f"开始更新 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    client = service.client
    trade_date = client.get_latest_trade_date()
    print(f"  交易日: {trade_date}")

    # 1. Build name mapping
    print("\n[1/6] 获取板块名称映射...")
    name_map = _build_name_map(client)
    if not name_map:
        print("⚠️  名称映射为空，跳过本次更新")
        return

    # Reverse map: name → ts_code (for watchlist lookup)
    reverse_map: Dict[str, str] = {v: k for k, v in name_map.items()}

    # 2. Fetch mixed daily (industry + concept)
    print("\n[2/6] 获取 ths_daily 混排数据...")
    df_mixed = _fetch_mixed_daily(client, trade_date, name_map)
    if df_mixed.empty:
        print("⚠️  ths_daily 数据为空，跳过本次更新")
        return

    n_industry = (df_mixed['board_type'] == '行业').sum()
    n_concept = (df_mixed['board_type'] == '概念').sum()
    print(f"  ✓ 共 {len(df_mixed)} 个板块 (行业: {n_industry}, 概念: {n_concept})")

    # 3. Fetch moneyflow for 90 industries
    print("\n[3/6] 获取行业资金流向 (90个行业)...")
    moneyflow = _fetch_moneyflow_map(client, trade_date)
    print(f"  ✓ 获取到 {len(moneyflow)} 个行业的资金数据")

    # 4. Fetch limit-up/down counts
    print("\n[4/6] 获取涨跌停统计...")
    limit_counts = _fetch_limit_counts(client, trade_date)
    print(f"  ✓ 获取到 {len(limit_counts)} 个行业的涨跌停数据")

    # 5. Determine which codes need detailed data (TOP_N + watchlist)
    top_codes: List[str] = df_mixed.head(TOP_N)["ts_code"].tolist()
    watch_codes: List[str] = [reverse_map[n] for n in WATCH_NAMES if n in reverse_map]
    detail_codes: List[str] = list(dict.fromkeys(top_codes + watch_codes))  # dedupe, preserve order

    # 5a. Historical changes
    print(f"\n[5/6] 获取历史涨跌数据 ({len(detail_codes)} 个板块)...")
    hist = _fetch_historical_changes(client, detail_codes)
    print(f"  ✓ 获取到 {len(hist)} 个板块的历史数据")

    # 5b. Up/down stock counts
    print(f"\n[6/6] 获取涨跌家数 ({len(detail_codes)} 个板块)...")
    up_down = _fetch_up_down_counts(client, detail_codes, trade_date)
    print(f"  ✓ 获取到 {len(up_down)} 个板块的涨跌家数")

    # ── Build output ──

    # Top N (mixed)
    df_top = df_mixed.head(TOP_N)
    top_data = []
    for idx, (_, row) in enumerate(df_top.iterrows(), start=1):
        top_data.append(_build_item(row, idx, moneyflow, hist, limit_counts, up_down))

    # Watch list
    watch_data = []
    for watch_name in WATCH_NAMES:
        matched = df_mixed[df_mixed["name"] == watch_name]
        if not matched.empty:
            row = matched.iloc[0]
            watch_data.append(
                _build_item(row, len(watch_data) + 1, moneyflow, hist, limit_counts, up_down)
            )
        else:
            print(f"  ⚠️  自选概念 '{watch_name}' 未在混排数据中找到")

    # Re-rank watchlist
    for idx, item in enumerate(watch_data, start=1):
        item["rank"] = idx

    # Save JSON
    output = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updateInterval": UPDATE_INTERVAL,
        "dataSource": "tonghuashun_mixed",
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

    # Summary
    print(f"\n📊 涨幅前 5:")
    for item in top_data[:5]:
        tag = f"[{item['boardType']}]"
        print(
            f"   {item['rank']:2d}. {tag:4s} {item['name']:12s}  "
            f"{item['changePct']:+6.2f}%  "
            f"净流入: {item['moneyInflow']:+8.2f}亿  "
        )


def run_once(service: TonghuashunService) -> None:
    """单次运行。"""
    print("运行模式: 单次更新")
    update_data(service)


def run_continuous(service: TonghuashunService) -> None:
    """持续运行模式。"""
    print("=" * 60)
    print("🚀 板块监控启动（同花顺混排: 行业+概念）")
    print("=" * 60)
    print(f"监控配置:")
    print(f"  — 涨幅前 {TOP_N} 行业/概念（混排）")
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
