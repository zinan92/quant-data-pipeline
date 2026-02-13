#!/usr/bin/env python3
"""
A股数据采集简报 — 纯数据输出版

采集所有截面数据，输出结构化 markdown，不做分析判断。
LLM 分析由 OpenClaw 调度 Claude Code CLI 完成。

输出保存到 ~/knowledge-base/briefings/ashare/{YYYY-MM-DD}.md (append 模式)

使用方式:
    python3 scripts/full_briefing.py
"""

import json
import requests
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOT_FILE = PROJECT_ROOT / "data" / "snapshots" / "intraday" / "today_index_snapshots.json"
VOLUME_HISTORY_FILE = PROJECT_ROOT / "data" / "snapshots" / "daily_volume_history.json"
SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)

BRIEFING_DIR = Path.home() / "knowledge-base" / "briefings" / "ashare"

API_BASE = "http://127.0.0.1:8000"
PARK_INTEL_BASE = "http://127.0.0.1:8001"
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}

# 宽基/非行业概念过滤列表
BROAD_CONCEPTS_FILTER = [
    "融资融券", "深股通", "沪股通", "证金持股", "MSCI概念", "标普道琼斯",
    "富时罗素", "同花顺漂亮", "同花顺中特估", "超级品牌", "北交所",
    "创业板综", "参股银行", "参股保险", "参股券商", "社保重仓",
    "险资重仓", "基金重仓", "机构重仓", "外资重仓", "QFII重仓",
]

INDEX_CODES = [
    ("000001.SH", "上证指数"),
    ("399001.SZ", "深证成指"),
    ("399006.SZ", "创业板指"),
    ("000688.SH", "科创50"),
    ("000852.SH", "中证1000"),
]


def safe_section(section_name: str):
    """Decorator to catch section errors"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return [f"[{section_name}] 获取失败: {e}"]
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════
# Data Fetchers
# ═══════════════════════════════════════════════════════════════
def fetch_indices() -> dict:
    """Fetch current index data via Sina"""
    result = {}
    codes_str = ",".join([f"sh{c[2:] if c.startswith('0') else c[2:]}" if "SH" in c else f"sz{c[2:]}" for c, _ in INDEX_CODES])

    try:
        r = requests.get(
            f"http://hq.sinajs.cn/list={codes_str}",
            headers=SINA_HEADERS,
            timeout=8,
        )
        lines = r.text.strip().split("\n")

        for line in lines:
            if "hq_str_" in line and "=" in line and '"' in line:
                code_part = line.split("hq_str_")[1].split("=")[0]
                if code_part.startswith("sh"):
                    code = f"{code_part[2:]}.SH"
                elif code_part.startswith("sz"):
                    code = f"{code_part[2:]}.SZ"
                else:
                    continue

                data = line.split('"')[1].split(",")
                if len(data) > 5 and data[3] and data[2]:
                    try:
                        current_price = float(data[3])
                        prev_close = float(data[2])
                        pct_change = (current_price - prev_close) / prev_close * 100
                        amount = float(data[9]) if data[9] else 0

                        name = next((n for c, n in INDEX_CODES if c == code), code)

                        result[code] = {
                            "name": name,
                            "price": current_price,
                            "pct": pct_change,
                            "amount": amount,
                        }
                    except (ValueError, IndexError, ZeroDivisionError):
                        continue
    except Exception:
        pass

    return result


def get_volume_context() -> dict:
    """Get yesterday's and 5-day avg volume for comparison."""
    try:
        if not VOLUME_HISTORY_FILE.exists():
            return {}
        data = json.loads(VOLUME_HISTORY_FILE.read_text())
        history = data.get("history", [])
        if not history:
            return {}

        yesterday = history[-1] if history else {}
        recent_5 = history[-5:] if len(history) >= 5 else history
        avg_5_total = sum(h.get("total", 0) for h in recent_5) / len(recent_5) if recent_5 else 0

        return {
            "yesterday_total": yesterday.get("total", 0),
            "avg_5_total": avg_5_total,
        }
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════
# 1. A股指数
# ═══════════════════════════════════════════════════════════════
@safe_section("A股指数")
def section_indices(index_data: dict) -> list[str]:
    lines = ["### 指数"]
    if not index_data:
        return lines + ["数据暂无"]

    lines.append("| 指数 | 现价 | 涨跌% | 成交额(亿) |")
    lines.append("|------|------|--------|------------|")

    total_amount = 0
    for code, _ in INDEX_CODES:
        if code not in index_data:
            continue
        d = index_data[code]
        amt_yi = d["amount"] / 1e4 if d["amount"] else 0
        total_amount += amt_yi
        lines.append(
            f"| {d['name']} | {d['price']:.2f} | {d['pct']:+.2f}% | {amt_yi:.0f} |"
        )

    # Volume comparison
    vol_ctx = get_volume_context()
    if vol_ctx and total_amount > 0:
        yesterday = vol_ctx.get("yesterday_total", 0)
        avg_5 = vol_ctx.get("avg_5_total", 0)
        vs_yesterday = f"{(total_amount - yesterday) / yesterday * 100:+.0f}%" if yesterday > 0 else "-"
        vs_avg5 = f"{(total_amount - avg_5) / avg_5 * 100:+.0f}%" if avg_5 > 0 else "-"
        lines.append("")
        lines.append(f"两市合计: {total_amount:.0f}亿 | vs昨日: {vs_yesterday} | vs5日均: {vs_avg5}")

    return lines


# ═══════════════════════════════════════════════════════════════
# 2. 涨跌停统计
# ═══════════════════════════════════════════════════════════════
@safe_section("涨跌停")
def section_alerts() -> list[str]:
    lines = ["### 涨跌停"]
    try:
        r = requests.get(f"{API_BASE}/api/anomaly/alerts", timeout=20)
        if r.status_code != 200:
            return lines + ["API请求失败"]

        alerts = r.json()
        if not alerts:
            return lines + ["暂无异动数据"]

        up_count = alerts.get("封涨停板", {}).get("count", 0)
        down_count = alerts.get("封跌停板", {}).get("count", 0)
        bomb_count = alerts.get("炸板", {}).get("count", 0)
        lines.append(f"- 涨停: {up_count} | 跌停: {down_count} | 炸板: {bomb_count}")

        # Rapid movers
        categories = ["急速拉升", "急速下跌", "量比放大"]
        for category in categories:
            if category in alerts:
                data = alerts[category]
                count = data.get("count", 0)
                stocks = data.get("stocks", [])
                if count > 0:
                    top_names = ", ".join(
                        f"{s.get('name', '')}({s.get('code', '')}){s.get('change_pct', 0):+.2f}%"
                        for s in stocks[:3]
                    )
                    lines.append(f"- {category}: {count}只 | {top_names}")

        return lines
    except Exception as e:
        return lines + [f"获取失败: {e}"]


# ═══════════════════════════════════════════════════════════════
# 3. 盘中路径快照
# ═══════════════════════════════════════════════════════════════
@safe_section("盘中路径")
def section_intraday() -> list[str]:
    lines = ["### 盘中路径"]
    if not SNAPSHOT_FILE.exists():
        return lines + ["暂无快照数据"]

    data = json.loads(SNAPSHOT_FILE.read_text())
    snapshots = data.get("snapshots", [])
    if len(snapshots) < 2:
        return lines + ["快照不足"]

    # Analyze 上证指数 path (000001.SH)
    sh_data = []
    for snap in snapshots:
        idx = snap.get("indexes", {}).get("000001.SH", {})
        price = idx.get("price", 0)
        pct = idx.get("pct", 0)
        if price > 0:
            sh_data.append({"time": snap["time"], "price": price, "pct": pct})

    if len(sh_data) < 2:
        return lines + ["数据不足"]

    open_pct = sh_data[0]["pct"]
    current_pct = sh_data[-1]["pct"]
    current_price = sh_data[-1]["price"]
    current_time = sh_data[-1]["time"]
    high_point = max(sh_data, key=lambda x: x["price"])
    low_point = min(sh_data, key=lambda x: x["price"])
    amplitude = high_point["pct"] - low_point["pct"]

    lines.append(f"- 上证 开盘: {open_pct:+.2f}% | 当前: {current_price:.2f} ({current_pct:+.2f}%) @{current_time}")
    lines.append(f"- 最高: {high_point['price']:.2f} ({high_point['pct']:+.2f}%) @{high_point['time']} | 最低: {low_point['price']:.2f} ({low_point['pct']:+.2f}%) @{low_point['time']}")
    lines.append(f"- 振幅: {amplitude:.2f}%")

    return lines


# ═══════════════════════════════════════════════════════════════
# 4. 概念资金流 TOP20
# ═══════════════════════════════════════════════════════════════
@safe_section("概念资金流")
def section_flow_top20() -> list[str]:
    lines = ["### 概念资金流 TOP20"]
    try:
        r = requests.get(f"{API_BASE}/api/rotation/top-inflow", timeout=10)
        if r.status_code != 200:
            return lines + ["API请求失败"]

        data = r.json()
        if not data:
            return lines + ["数据为空"]
    except Exception as e:
        return lines + [f"获取失败: {e}"]

    import pandas as pd
    df = pd.DataFrame(data)

    # Remap API column names
    col_map = {"name": "行业", "net_inflow": "净额", "pct_change": "涨跌幅"}
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    df_sorted = df.sort_values("净额", ascending=False).reset_index(drop=True)

    # Filter broad concepts for sector table
    sector_df = df_sorted[~df_sorted["行业"].apply(
        lambda x: any(b in x for b in BROAD_CONCEPTS_FILTER)
    )].reset_index(drop=True)

    total = len(df_sorted)
    net_in = len(df_sorted[df_sorted["净额"] > 0])
    net_out = total - net_in

    lines.append(f"共{total}个概念 | {net_in}个净流入 | {net_out}个净流出")
    lines.append("")

    # TOP10 inflow table
    lines.append("| 排名 | 概念 | 净流入(亿) | 板块涨跌% |")
    lines.append("|------|------|-----------|----------|")
    top10 = sector_df.head(10)
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        pct = row.get("涨跌幅", 0)
        pct_str = f"{pct:+.2f}%" if pct else "-"
        lines.append(f"| {i} | {row['行业']} | {row['净额']:+.0f} | {pct_str} |")

    # Bottom 5 outflow
    bot5 = sector_df.tail(5).iloc[::-1]
    lines.append("")
    lines.append("**流出前5:**")
    for _, row in bot5.iterrows():
        pct = row.get("涨跌幅", 0)
        pct_str = f"{pct:+.2f}%" if pct else "-"
        lines.append(f"- {row['行业']} {row['净额']:.0f}亿 | {pct_str}")

    return lines


# ═══════════════════════════════════════════════════════════════
# 5. 自选股赛道汇总
# ═══════════════════════════════════════════════════════════════
@safe_section("赛道汇总")
def section_stock_sectors() -> list[str]:
    """按自定义赛道分组统计涨跌"""
    lines = ["### 自选股赛道"]

    r = requests.get(f"{API_BASE}/api/watchlist", timeout=10)
    if r.status_code != 200:
        return lines + ["获取自选股列表失败"]
    watchlist = r.json()
    if not watchlist:
        return lines + ["自选股列表为空"]

    # Build ticker -> sector mapping
    ticker_sector = {}
    ticker_name = {}
    for w in watchlist:
        ticker = w.get("ticker", "")
        sector = w.get("sector", "")
        if ticker and sector:
            ticker_sector[ticker] = sector
            ticker_name[ticker] = w.get("name", ticker)

    # Get available sectors
    sector_resp = requests.get(f"{API_BASE}/api/sectors/list/available", timeout=10)
    available_sectors = sector_resp.json().get("sectors", []) if sector_resp.status_code == 200 else []

    # Fetch prices via Sina
    tickers = list(ticker_sector.keys())
    price_data = {}

    for i in range(0, len(tickers), 50):
        batch = tickers[i:i + 50]
        codes = ",".join([f"sh{t}" if t.startswith("6") else f"sz{t}" for t in batch])
        try:
            pr = requests.get(
                f"http://hq.sinajs.cn/list={codes}",
                headers=SINA_HEADERS, timeout=10,
            )
            for line in pr.text.strip().split("\n"):
                if "hq_str_" in line and '"' in line:
                    code_part = line.split("hq_str_")[1].split("=")[0]
                    ticker = code_part[2:]
                    data = line.split('"')[1].split(",")
                    if len(data) > 4 and data[3] and data[2]:
                        try:
                            cur = float(data[3])
                            prev = float(data[2])
                            if prev > 0:
                                pct = (cur - prev) / prev * 100
                                price_data[ticker] = (cur, pct)
                        except (ValueError, ZeroDivisionError):
                            pass
        except Exception:
            pass
        time.sleep(0.1)

    # Calculate sector stats
    sector_stats = {}
    for sector in available_sectors:
        sector_stats[sector] = {
            "count": 0, "changes": [],
            "max_gainer": None, "max_loser": None,
        }

    for ticker, sector in ticker_sector.items():
        if sector not in sector_stats or ticker not in price_data:
            continue

        price, pct = price_data[ticker]
        name = ticker_name.get(ticker, ticker)
        sector_stats[sector]["count"] += 1
        sector_stats[sector]["changes"].append(pct)

        current = {"name": name, "change": pct}
        if sector_stats[sector]["max_gainer"] is None or pct > sector_stats[sector]["max_gainer"]["change"]:
            sector_stats[sector]["max_gainer"] = current
        if sector_stats[sector]["max_loser"] is None or pct < sector_stats[sector]["max_loser"]["change"]:
            sector_stats[sector]["max_loser"] = current

    # Build results
    results = []
    for sector, stats in sector_stats.items():
        if stats["count"] == 0:
            continue
        avg_change = sum(stats["changes"]) / len(stats["changes"]) if stats["changes"] else 0
        results.append({
            "sector": sector,
            "avg_change": avg_change,
            "gainer": stats["max_gainer"],
            "loser": stats["max_loser"],
        })

    results.sort(key=lambda x: x["avg_change"], reverse=True)

    if not results:
        return lines + ["无数据"]

    lines.append("| 赛道 | 涨跌% | 领涨 | 领跌 |")
    lines.append("|------|--------|------|------|")
    for r in results:
        gainer = f"{r['gainer']['name']}{r['gainer']['change']:+.1f}%" if r["gainer"] else "-"
        loser = f"{r['loser']['name']}{r['loser']['change']:+.1f}%" if r["loser"] else "-"
        lines.append(f"| {r['sector']} | {r['avg_change']:+.2f}% | {gainer} | {loser} |")

    return lines


# ═══════════════════════════════════════════════════════════════
# 6. 自选股异动
# ═══════════════════════════════════════════════════════════════
@safe_section("自选股异动")
def section_watchlist() -> list[str]:
    lines = ["### 自选股异动"]
    try:
        r = requests.get(f"{API_BASE}/api/watchlist/analytics", timeout=8)
        if r.status_code != 200:
            return lines + ["API请求失败"]

        data = r.json()
        alerts = data if isinstance(data, list) else data.get("alerts", data.get("stocks", []))

        if not alerts:
            return lines + ["暂无异动"]

        for alert in alerts[:8]:
            name = alert.get("name", "")
            code = alert.get("code", alert.get("ticker", ""))
            trigger = alert.get("trigger", alert.get("signal", ""))
            value = alert.get("value", alert.get("change_pct", 0))
            lines.append(f"- {name}({code}) {trigger} {value:+.2f}%")

        return lines
    except Exception as e:
        return lines + [f"获取失败: {e}"]


# ═══════════════════════════════════════════════════════════════
# 7. 舆情信号 (park-intel)
# ═══════════════════════════════════════════════════════════════
@safe_section("舆情信号")
def section_intel_signals() -> list[str]:
    """Fetch qualitative signals from park-intel."""
    lines = ["### 舆情 (park-intel)"]
    try:
        r = requests.get(
            f"{PARK_INTEL_BASE}/api/articles/signals",
            timeout=10,
        )
        if r.status_code != 200:
            return lines + ["park-intel 请求失败"]
        data = r.json()
    except Exception:
        return lines + ["park-intel 不可用"]

    sys.path.insert(0, str(PROJECT_ROOT))
    from src.services.narrative_mapping import format_intel_section
    lines.extend(format_intel_section(data))
    return lines


# ═══════════════════════════════════════════════════════════════
# 8. 感知管线信号
# ═══════════════════════════════════════════════════════════════
@safe_section("感知管线")
def section_perception() -> list[str]:
    """Fetch latest signals from perception pipeline."""
    lines = ["### 感知管线"]

    # Fetch signals
    try:
        sig_r = requests.get(f"{API_BASE}/api/perception/signals?limit=20", timeout=10)
        if sig_r.status_code != 200:
            return lines + ["perception API 请求失败"]
        sig_data = sig_r.json()
    except Exception:
        return lines + ["perception API 不可用"]

    signals = sig_data.get("signals", [])
    count = sig_data.get("count", len(signals))

    # Separate longs and shorts
    longs = [s for s in signals if s.get("direction") == "long"]
    shorts = [s for s in signals if s.get("direction") == "short"]
    longs.sort(key=lambda s: s.get("composite_score", 0), reverse=True)
    shorts.sort(key=lambda s: s.get("composite_score", 0), reverse=True)

    # Calculate bias
    total_long = sum(s.get("composite_score", 0) for s in longs)
    total_short = sum(s.get("composite_score", 0) for s in shorts)
    net = total_long - total_short
    bias = "long" if net >= 0 else "short"
    bias_score = abs(net) / max(total_long + total_short, 0.01)

    lines.append(f"- 信号数: {count} | bias: {bias} ({bias_score:.2f})")

    if longs:
        top_longs = ", ".join(f"{s['asset']}({s.get('composite_score', 0):.2f})" for s in longs[:5])
        lines.append(f"- Top longs: {top_longs}")

    if shorts:
        top_shorts = ", ".join(f"{s['asset']}({s.get('composite_score', 0):.2f})" for s in shorts[:5])
        lines.append(f"- Top shorts: {top_shorts}")

    # Fetch health
    try:
        health_r = requests.get(f"{API_BASE}/api/perception/health", timeout=5)
        if health_r.status_code == 200:
            health = health_r.json()
            sources = health.get("sources", {})
            if sources:
                parts = []
                for src_name, src_info in sources.items():
                    status = src_info if isinstance(src_info, str) else src_info.get("status", "unknown")
                    mark = "ok" if status in ("healthy", "ok") else status
                    parts.append(f"{src_name}={mark}")
                lines.append(f"- Source: {' '.join(parts)}")
    except Exception:
        pass

    return lines


# ═══════════════════════════════════════════════════════════════
# 9. 市场快讯
# ═══════════════════════════════════════════════════════════════
@safe_section("市场快讯")
def section_news() -> list[str]:
    lines = ["### 快讯"]
    try:
        r = requests.get(f"{API_BASE}/api/news/latest", timeout=8)
        if r.status_code != 200:
            return lines + ["API请求失败"]

        data = r.json()
        news = data if isinstance(data, list) else data.get("news", data.get("data", []))

        if not news:
            return lines + ["暂无快讯"]

        for item in news[:5]:
            title = item.get("title", "")
            time_str = item.get("time", "")
            if title:
                lines.append(f"- {time_str} {title}")

        return lines
    except Exception as e:
        return lines + [f"获取失败: {e}"]


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    """采集数据 → 输出结构化 markdown → 保存到 Obsidian"""
    now = datetime.now()

    # ── Data Gathering ──
    index_data = fetch_indices()

    # ── Build Output ──
    output_lines = [
        f"## {now.strftime('%H:%M')} 数据快照",
        "",
    ]

    output_lines.extend(section_indices(index_data))
    output_lines.append("")
    output_lines.extend(section_alerts())
    output_lines.append("")
    output_lines.extend(section_intraday())
    output_lines.append("")
    output_lines.extend(section_flow_top20())
    output_lines.append("")
    output_lines.extend(section_stock_sectors())
    output_lines.append("")
    output_lines.extend(section_watchlist())
    output_lines.append("")
    output_lines.extend(section_intel_signals())
    output_lines.append("")
    output_lines.extend(section_perception())
    output_lines.append("")
    output_lines.extend(section_news())

    output_lines.append("")
    output_lines.append(f"---")
    output_lines.append(f"生成时间: {now.strftime('%H:%M:%S')}")
    output_lines.append("")

    full_text = "\n".join(output_lines)
    print(full_text)

    # ── Save to Obsidian (append mode) ──
    BRIEFING_DIR.mkdir(parents=True, exist_ok=True)
    out_file = BRIEFING_DIR / f"{now.strftime('%Y-%m-%d')}.md"
    with open(out_file, "a", encoding="utf-8") as f:
        f.write(full_text)
    print(f"\n>> 已保存到 {out_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
