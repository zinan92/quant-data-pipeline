#!/usr/bin/env python3
"""
全市场简报 v2 — Park框架 + 小登/中登/老登分类
=============================================
用法: python scripts/full_briefing_v2.py [--closing]
  --closing: 收盘简报模式（含盘后总结）

模块:
1. 大盘一句话      — 指数/成交量/走势/涨跌停比
2. 赛道体检        — 16赛道实时表现 + 小登/中登/老登风格判断
3. 自选 vs 大盘    — 相对表现 + alpha
4. 关键信号        — 护盘/趋势/避险 + 概念资金流亮点
5. 快讯精选        — 3-5条有价值的
6. 操作建议        — 一句话
"""

import sys
import json
import time
import traceback
import requests
import sqlite3
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "market.db"
SNAPSHOT_FILE = PROJECT_ROOT / "data" / "snapshots" / "intraday" / "today_index_snapshots.json"
SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)

API_BASE = "http://127.0.0.1:8000"
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}

INDEX_CODES = [
    ("000001.SH", "上证"),
    ("399001.SZ", "深证"),
    ("399006.SZ", "创业板"),
    ("000688.SH", "科创50"),
]

# ── 小登/中登/老登 分类 ──────────────────────────────────────
DENG_MAP = {
    "小登": ["AI应用", "芯片", "PCB", "机器人", "半导体", "脑机接口", "可控核聚变"],
    "中登": ["新能源汽车", "光伏", "发电", "创新药", "贵金属", "金属", "军工"],
    "老登": ["消费"],
}

# Reverse map: sector → deng category
SECTOR_TO_DENG = {}
for deng_cat, sectors in DENG_MAP.items():
    for s in sectors:
        SECTOR_TO_DENG[s] = deng_cat

# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════
def safe_section(name):
    """Decorator: if a section fails, print error and continue."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                traceback.print_exc(file=sys.stderr)
                return [f"⚠️ [{name}] 获取失败: {e}"]
        return wrapper
    return decorator


def fetch_sina_batch(tickers: list[str]) -> dict:
    """Fetch realtime quotes from Sina for a list of tickers.
    Returns {ticker: {name, price, prev_close, pct, volume, amount}}
    """
    results = {}
    for i in range(0, len(tickers), 50):
        batch = tickers[i:i + 50]
        codes = ",".join([
            f"sh{t}" if t.startswith("6") or t.startswith("9")
            else f"sz{t}"
            for t in batch
        ])
        try:
            r = requests.get(
                f"http://hq.sinajs.cn/list={codes}",
                headers=SINA_HEADERS, timeout=10,
            )
            for line in r.text.strip().split("\n"):
                if "hq_str_" not in line or '"' not in line:
                    continue
                code_part = line.split("hq_str_")[1].split("=")[0]
                ticker = code_part[2:]  # Remove sh/sz prefix
                data = line.split('"')[1].split(",")
                if len(data) < 9:
                    continue
                try:
                    name = data[0]
                    prev_close = float(data[2]) if data[2] else 0
                    cur = float(data[3]) if data[3] else 0
                    high = float(data[4]) if data[4] else 0
                    low = float(data[5]) if data[5] else 0
                    volume = float(data[8]) if data[8] else 0  # 成交额(元)
                    if prev_close > 0 and cur > 0:
                        pct = (cur - prev_close) / prev_close * 100
                        # Detect limit up/down (涨跌停: ≥9.8% for main board, ≥19.8% for 创业板/科创板)
                        is_cyb = ticker.startswith("3")
                        is_kcb = ticker.startswith("68")
                        limit_threshold = 19.8 if (is_cyb or is_kcb) else 9.8
                        is_limit_up = pct >= limit_threshold
                        is_limit_down = pct <= -limit_threshold
                        results[ticker] = {
                            "name": name,
                            "price": cur,
                            "prev_close": prev_close,
                            "pct": pct,
                            "high": high,
                            "low": low,
                            "amount": volume,
                            "is_limit_up": is_limit_up,
                            "is_limit_down": is_limit_down,
                        }
                except (ValueError, ZeroDivisionError, IndexError):
                    pass
        except Exception:
            pass
        if i + 50 < len(tickers):
            time.sleep(0.3)
    return results


def load_sector_stocks() -> dict:
    """Load sectors and their stocks from market.db.
    Returns {sector: [ticker1, ticker2, ...]}
    """
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT ticker, sector FROM stock_sectors")
    rows = c.fetchall()
    conn.close()

    sectors = {}
    for ticker, sector in rows:
        sectors.setdefault(sector, []).append(ticker)
    return sectors


def load_watchlist() -> list[dict]:
    """Load watchlist from market.db.
    Returns [{ticker, category, is_focus}, ...]
    """
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT ticker, category, is_focus FROM watchlist")
    rows = c.fetchall()
    conn.close()
    return [{"ticker": r[0], "category": r[1], "is_focus": r[2]} for r in rows]


# ═══════════════════════════════════════════════════════════════
# 0. Index data + snapshot
# ═══════════════════════════════════════════════════════════════
def fetch_indices() -> dict:
    """Fetch index data from local API."""
    result = {}
    for code, name in INDEX_CODES:
        try:
            r = requests.get(f"{API_BASE}/api/index/realtime/{code}", timeout=5)
            if r.ok:
                d = r.json()
                result[code] = {
                    "name": d.get("name", name),
                    "price": d.get("price", 0),
                    "pct": d.get("change_pct", 0),
                    "amount": d.get("amount", 0),
                }
        except Exception:
            pass
    return result


def save_index_snapshot(index_data: dict):
    """Save current index data as a snapshot point."""
    try:
        if SNAPSHOT_FILE.exists():
            snapshots = json.loads(SNAPSHOT_FILE.read_text())
            if snapshots.get("date") != datetime.now().strftime("%Y-%m-%d"):
                snapshots = {"date": datetime.now().strftime("%Y-%m-%d"), "snapshots": []}
        else:
            snapshots = {"date": datetime.now().strftime("%Y-%m-%d"), "snapshots": []}

        now_time = datetime.now().strftime("%H:%M")
        existing_times = {s["time"] for s in snapshots["snapshots"]}
        if now_time in existing_times:
            return

        snapshot_entry = {"time": now_time, "indexes": {}}
        for code, info in index_data.items():
            snapshot_entry["indexes"][code] = {
                "name": info["name"],
                "price": info["price"],
                "pct": info["pct"],
            }
        snapshots["snapshots"].append(snapshot_entry)
        SNAPSHOT_FILE.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2))
    except Exception:
        pass


def get_intraday_walk(index_data: dict) -> str:
    """Describe intraday walk from snapshots: 2-3 key turning points."""
    if not SNAPSHOT_FILE.exists():
        return ""
    try:
        data = json.loads(SNAPSHOT_FILE.read_text())
        snaps = data.get("snapshots", [])
        if len(snaps) < 2:
            return ""
        
        # Use 上证 as reference
        sh_code = "000001.SH"
        points = []
        for s in snaps:
            idx = s.get("indexes", {}).get(sh_code, {})
            if idx.get("pct") is not None:
                points.append((s["time"], idx["pct"]))
        
        if len(points) < 2:
            return ""
        
        # Find key turning points: open, high, low, latest
        open_pt = points[0]
        latest_pt = points[-1]
        high_pt = max(points, key=lambda x: x[1])
        low_pt = min(points, key=lambda x: x[1])
        
        # Build narrative: 2-3 nodes
        segments = []
        
        # Opening move
        if open_pt[1] > 0.1:
            segments.append(f"高开({open_pt[1]:+.1f}%)")
        elif open_pt[1] < -0.1:
            segments.append(f"低开({open_pt[1]:+.1f}%)")
        else:
            segments.append("平开")
        
        # If there's a meaningful swing, describe it
        key_events = sorted(set([open_pt, high_pt, low_pt, latest_pt]), key=lambda x: x[0])
        
        prev_pct = open_pt[1]
        for pt in key_events[1:]:
            delta = pt[1] - prev_pct
            if abs(delta) < 0.15:
                continue
            if delta > 0:
                segments.append(f"{pt[0]}反弹至{pt[1]:+.1f}%")
            else:
                segments.append(f"{pt[0]}回落至{pt[1]:+.1f}%")
            prev_pct = pt[1]
        
        if len(segments) <= 1:
            # Simple day
            if latest_pt[1] > open_pt[1] + 0.3:
                segments.append("震荡走高")
            elif latest_pt[1] < open_pt[1] - 0.3:
                segments.append("震荡走低")
            else:
                segments.append("窄幅震荡")
        
        return " → ".join(segments[:4])  # Max 4 nodes
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════
# 1. 大盘一句话
# ═══════════════════════════════════════════════════════════════
@safe_section("大盘一句话")
def section_headline(index_data: dict, alert_data: dict = None) -> list[str]:
    lines = ["━━ 1. 大盘一句话 ━━"]
    
    # Index row
    idx_parts = []
    for code, _ in INDEX_CODES:
        d = index_data.get(code)
        if d:
            idx_parts.append(f"{d['name']} {d['pct']:+.2f}%")
    lines.append(" | ".join(idx_parts))
    
    # Volume
    sh_data = index_data.get("000001.SH", {})
    amount_yi = sh_data.get("amount", 0) / 1e4 if sh_data.get("amount") else 0
    if amount_yi > 0:
        # TODO: compare to yesterday for 缩量/放量
        lines.append(f"成交 {amount_yi:.0f}亿")
    
    # Intraday walk
    walk = get_intraday_walk(index_data)
    if walk:
        lines.append(f"走势: {walk}")
    
    # Limit up/down
    up_count = 0
    down_count = 0
    if alert_data:
        up_count = alert_data.get("封涨停板", {}).get("count", 0)
        down_count = alert_data.get("封跌停板", {}).get("count", 0)
    
    if up_count + down_count > 0:
        ratio = up_count / down_count if down_count > 0 else float("inf")
        if ratio > 1.5:
            comment = "涨停多 = 多头活跃"
        elif ratio < 0.67:
            comment = "跌停多 = 弱"
        else:
            comment = "平衡"
        lines.append(f"涨停 {up_count} / 跌停 {down_count} ({ratio:.1f}x ← {comment})")
    
    return lines


# ═══════════════════════════════════════════════════════════════
# 2. 赛道体检 (16 sectors + 小登/中登/老登)
# ═══════════════════════════════════════════════════════════════
@safe_section("赛道体检")
def section_sectors(sector_stocks: dict, all_quotes: dict) -> tuple[list[str], dict]:
    """Returns (lines, sector_stats) where sector_stats = {sector: {avg_pct, up, down, total, limit_up, limit_down, best, worst}}"""
    lines = ["━━ 2. 赛道体检 ━━"]
    
    sector_stats = {}
    
    for sector, tickers in sorted(sector_stocks.items()):
        if sector == "其他":
            continue  # Skip "其他"
        
        pcts = []
        up = 0
        down = 0
        flat = 0
        limit_up = 0
        limit_down = 0
        best_stock = None
        worst_stock = None
        
        for t in tickers:
            q = all_quotes.get(t)
            if not q:
                continue
            pct = q["pct"]
            pcts.append(pct)
            
            if pct > 0.05:
                up += 1
            elif pct < -0.05:
                down += 1
            else:
                flat += 1
            
            if q["is_limit_up"]:
                limit_up += 1
            if q["is_limit_down"]:
                limit_down += 1
            
            if best_stock is None or pct > best_stock[1]:
                best_stock = (q["name"], pct)
            if worst_stock is None or pct < worst_stock[1]:
                worst_stock = (q["name"], pct)
        
        if not pcts:
            sector_stats[sector] = None
            continue
        
        avg_pct = sum(pcts) / len(pcts)
        total = len(pcts)
        
        sector_stats[sector] = {
            "avg_pct": avg_pct,
            "up": up,
            "down": down,
            "flat": flat,
            "total": total,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "best": best_stock,
            "worst": worst_stock,
        }
    
    # Sort sectors by avg_pct descending
    sorted_sectors = sorted(
        [(s, d) for s, d in sector_stats.items() if d is not None],
        key=lambda x: x[1]["avg_pct"],
        reverse=True,
    )
    
    # Display
    green_count = 0
    red_count = 0
    
    for sector, stats in sorted_sectors:
        avg = stats["avg_pct"]
        emoji = "🟢" if avg >= 0 else "🔴"
        if avg >= 0:
            green_count += 1
        else:
            red_count += 1
        
        total = stats["total"]
        up = stats["up"]
        down = stats["down"]
        
        # Build detail string
        detail = f"{total}只: {up}涨{down}跌"
        if stats["limit_up"] > 0:
            detail += f", {stats['limit_up']}涨停"
        if stats["limit_down"] > 0:
            detail += f", {stats['limit_down']}跌停"
        
        # Comment based on severity
        comment = ""
        if down > 0 and up == 0 and down >= 3:
            comment = " ← 全灭"
        elif total > 5 and down / total > 0.85:
            comment = " ← 几乎全灭"
        elif total > 5 and up / total > 0.85:
            comment = " ← 全线飘红"
        elif avg > 3:
            comment = " ← 爆发"
        elif avg < -3:
            comment = " ← 暴跌"
        
        # Show best/worst for extreme sectors
        extra = ""
        if avg > 2 and stats["best"]:
            extra = f" 最强:{stats['best'][0]}{stats['best'][1]:+.1f}%"
        elif avg < -2 and stats["worst"]:
            extra = f" 最弱:{stats['worst'][0]}{stats['worst'][1]:+.1f}%"
        
        lines.append(f"{emoji} {sector} {avg:+.1f}% ({detail}){comment}{extra}")
    
    # Summary line
    total_sectors = green_count + red_count
    lines.append(f"📊 结论: {green_count}/{total_sectors}赛道赚钱，{red_count}个亏钱")
    
    # 小登/中登/老登 风格判断
    deng_avgs = {}
    for deng_cat in ["小登", "中登", "老登"]:
        cat_sectors = DENG_MAP[deng_cat]
        cat_pcts = []
        for s in cat_sectors:
            if s in sector_stats and sector_stats[s] is not None:
                cat_pcts.append(sector_stats[s]["avg_pct"])
        if cat_pcts:
            deng_avgs[deng_cat] = sum(cat_pcts) / len(cat_pcts)
        else:
            deng_avgs[deng_cat] = 0
    
    # Determine style
    style_parts = []
    for cat in ["小登", "中登", "老登"]:
        avg = deng_avgs.get(cat, 0)
        emoji = "🟢" if avg >= 0 else "🔴"
        style_parts.append(f"{emoji}{cat} {avg:+.1f}%")
    
    lines.append(f"⚡ 风格: {' | '.join(style_parts)}")
    
    # Narrative
    xd = deng_avgs.get("小登", 0)
    zd = deng_avgs.get("中登", 0)
    ld = deng_avgs.get("老登", 0)
    
    if xd < -1 and ld > xd + 1:
        lines.append("💡 小登溃败 → 老登防御，Risk OFF")
    elif xd > 1 and ld < xd - 1:
        lines.append("💡 小登领涨 → 科技进攻，Risk ON")
    elif xd > 0.5 and zd > 0.5 and ld > 0.5:
        lines.append("💡 全线飘红，普涨格局")
    elif xd < -0.5 and zd < -0.5 and ld < -0.5:
        lines.append("💡 全线溃败，普跌格局")
    elif abs(xd - ld) < 0.5:
        lines.append("💡 风格平衡，无明显偏向")
    else:
        if xd > zd > ld:
            lines.append("💡 科技>周期>防御，成长风格占优")
        elif ld > zd > xd:
            lines.append("💡 防御>周期>科技，价值风格占优")
        else:
            lines.append("💡 风格轮动中")
    
    return lines, sector_stats


# ═══════════════════════════════════════════════════════════════
# 3. 自选 vs 大盘
# ═══════════════════════════════════════════════════════════════
@safe_section("自选 vs 大盘")
def section_watchlist_vs_index(watchlist: list[dict], all_quotes: dict, index_data: dict) -> list[str]:
    lines = ["━━ 3. 自选 vs 大盘 ━━"]
    
    # Compute watchlist average
    wl_pcts = []
    wl_stocks = []
    
    for item in watchlist:
        t = item["ticker"]
        q = all_quotes.get(t)
        if q:
            wl_pcts.append(q["pct"])
            wl_stocks.append((q["name"], t, q["pct"]))
    
    if not wl_pcts:
        lines.append("  无法获取自选股行情")
        return lines
    
    wl_avg = sum(wl_pcts) / len(wl_pcts)
    sh_pct = index_data.get("000001.SH", {}).get("pct", 0)
    alpha = wl_avg - sh_pct
    
    emoji = "🟢" if alpha >= 0 else "🔴"
    verb = "跑赢" if alpha >= 0 else "跑输"
    lines.append(f"自选均值: {wl_avg:+.2f}% vs 上证: {sh_pct:+.2f}% → {emoji} {verb}{abs(alpha):.2f}%")
    
    # Determine reason based on sector distribution
    # Count sector composition
    sector_counts = {}
    for item in watchlist:
        cat = item.get("category", "未分类")
        if cat:
            sector_counts[cat] = sector_counts.get(cat, 0) + 1
    top_sector = max(sector_counts, key=sector_counts.get) if sector_counts else "未分类"
    deng_cat = SECTOR_TO_DENG.get(top_sector, "未分类")
    lines.append(f"持仓偏{deng_cat}({top_sector}为主)")
    
    # Best and worst
    wl_stocks.sort(key=lambda x: x[2], reverse=True)
    top3 = wl_stocks[:3]
    bot3 = wl_stocks[-3:]
    
    top_str = ", ".join([f"{n}{p:+.1f}%" for n, _, p in top3])
    bot_str = ", ".join([f"{n}{p:+.1f}%" for n, _, p in bot3])
    
    lines.append(f"📈 最强: {top_str}")
    lines.append(f"📉 最弱: {bot_str}")
    
    return lines


# ═══════════════════════════════════════════════════════════════
# 4. 关键信号
# ═══════════════════════════════════════════════════════════════
def fetch_concept_flow():
    """Fetch realtime concept flow via akshare."""
    import akshare as ak
    df = ak.stock_fund_flow_concept(symbol="即时")
    return df


@safe_section("关键信号")
def section_signals(index_data: dict) -> tuple[list[str], dict]:
    """Returns (lines, signal_data)"""
    lines = ["━━ 4. 关键信号 ━━"]
    signal_data = {}
    
    flow_df = fetch_concept_flow()
    
    # ── 4a. 概念资金流亮点 (top 3 in, top 3 out — theme only) ──
    BROAD_CONCEPTS = [
        "证金持股", "同花顺漂亮", "同花顺中特估", "融资融券", "深股通",
        "沪股通", "超级品牌", "参股银行", "参股保险", "参股券商",
    ]
    theme_df = flow_df[~flow_df["行业"].apply(
        lambda x: any(b in x for b in BROAD_CONCEPTS)
    )].reset_index(drop=True)
    
    if len(theme_df) == 0:
        theme_df = flow_df
    
    top3_in = theme_df.head(3)
    top3_out = theme_df.tail(3).iloc[::-1]
    
    in_parts = []
    for _, r in top3_in.iterrows():
        in_parts.append(f"{r['行业']} {r['净额']:+.1f}亿")
    
    out_parts = []
    for _, r in top3_out.iterrows():
        out_parts.append(f"{r['行业']} {r['净额']:.1f}亿")
    
    lines.append(f"• 资金涌入: {' / '.join(in_parts)}")
    lines.append(f"• 资金撤退: {' / '.join(out_parts)}")
    
    # ── 4b. 护盘指标 ──
    hp_sectors = {"银行": "参股银行", "保险": "参股保险", "证券": "参股券商"}
    hp_data = {}
    hp_total = 0
    hp_count = 0
    
    for display_name, search_key in hp_sectors.items():
        match = flow_df[flow_df["行业"] == search_key]
        if len(match) == 0:
            match = flow_df[flow_df["行业"].str.contains(search_key, na=False)]
        if len(match) > 0:
            row = match.iloc[0]
            net = row["净额"]
            hp_data[display_name] = net
            hp_total += net
            if net > 0:
                hp_count += 1
    
    hp_parts = []
    for name in ["银行", "保险", "证券"]:
        net = hp_data.get(name)
        if net is not None:
            emoji = "🟢" if net > 0 else "🔴"
            hp_parts.append(f"{emoji}{name}{net:+.1f}亿")
    
    if hp_count == 3:
        hp_verdict = "⚠️ 三大金融全流入 → 国家护盘，科技承压"
    elif hp_count >= 2:
        hp_verdict = f"🟡 {hp_count}/3金融流入 → 有护盘迹象"
    elif hp_total < -10:
        hp_verdict = "🟢 金融流出 → 无需护盘，资金在进攻"
    else:
        hp_verdict = "⚖️ 金融中性"
    
    lines.append(f"• 护盘: {' '.join(hp_parts)} → {hp_verdict}")
    
    # ── 4c. 趋势强度 ──
    top1 = theme_df.iloc[0]
    top1_net = abs(top1["净额"])
    top1_name = top1["行业"]
    
    if top1_net >= 200:
        trend_verdict = f"🔥 强主线 {top1_name}({top1['净额']:+.0f}亿)"
    elif top1_net >= 100:
        trend_verdict = f"📊 有方向 {top1_name}({top1['净额']:+.0f}亿) 力度一般"
    else:
        trend_verdict = f"😶 无主线 (最高仅{top1_name} {top1['净额']:+.0f}亿)"
    
    lines.append(f"• 趋势: {trend_verdict}")
    
    # ── 4d. 白酒避险 ──
    baijiu_net = None
    baijiu_match = flow_df[flow_df["行业"].str.contains("白酒", na=False)]
    if len(baijiu_match) > 0:
        baijiu_net = baijiu_match.iloc[0]["净额"]
        if baijiu_net > 10 and 護盤_count >= 2:
            lines.append(f"• 避险: 🚨 白酒{baijiu_net:+.1f}亿 + 金融护盘 = 极端Risk OFF")
        elif baijiu_net > 10:
            lines.append(f"• 避险: ⚠️ 白酒{baijiu_net:+.1f}亿流入 → 防御配置")
        elif baijiu_net < -10:
            lines.append(f"• 避险: 🟢 白酒{baijiu_net:+.1f}亿流出 → 非避险，偏进攻")
        else:
            lines.append(f"• 避险: ⚖️ 白酒{baijiu_net:+.1f}亿 中性")
    
    # Collect signal data
    signal_data = {
        "flow_df": flow_df,
        "theme_df": theme_df,
        "護盘_count": 護盤_count,
        "護盤_total": 護盤_total,
        "護盤_data": 護盤_data,
        "top1_net": top1_net,
        "top1_name": top1_name,
        "baijiu_net": baijiu_net or 0,
    }
    
    return lines, signal_data


# ═══════════════════════════════════════════════════════════════
# 5. 快讯精选
# ═══════════════════════════════════════════════════════════════
@safe_section("快讯精选")
def section_news_filtered() -> list[str]:
    """Fetch and filter news to 3-5 meaningful items."""
    r = requests.get(f"{API_BASE}/api/news/latest", params={"limit": 30}, timeout=10)
    data = r.json()
    news_list = data.get("news", [])
    
    if not news_list:
        return ["━━ 5. 快讯精选 ━━", "  暂无"]
    
    # Filter: prefer news with market-moving keywords
    HIGH_VALUE_KEYWORDS = [
        "涨停", "跌停", "突破", "暴涨", "暴跌", "利好", "利空",
        "政策", "央行", "降准", "降息", "监管", "制裁", "关税",
        "业绩", "超预期", "预增", "预减", "回购", "增持", "减持",
        "IPO", "退市", "停牌", "复牌", "重组", "并购",
        "芯片", "AI", "机器人", "新能源", "光伏", "半导体",
    ]
    NOISE_KEYWORDS = [
        "盘面上", "早知道", "异动", "快讯", "播报",
    ]
    
    scored = []
    for item in news_list:
        title = item.get("title", "")
        content = item.get("content", title)
        text = title + " " + content
        
        # Skip noise
        if any(nk in title for nk in NOISE_KEYWORDS):
            continue
        
        score = 0
        for kw in HIGH_VALUE_KEYWORDS:
            if kw in text:
                score += 1
        
        # Boost if mentions specific stock names or numbers
        if any(c.isdigit() for c in title):
            score += 0.5
        
        scored.append((score, item))
    
    # Sort by score, take top 5
    scored.sort(key=lambda x: x[0], reverse=True)
    top_news = [item for _, item in scored[:5]]
    
    if not top_news:
        top_news = news_list[:5]  # Fallback
    
    lines = ["━━ 5. 快讯精选 ━━"]
    for item in top_news:
        title = item.get("title", "")[:80]
        t = item.get("time", "")
        if t and len(t) >= 16:
            t = t[11:16]
        lines.append(f"• [{t}] {title}")
    
    return lines


# ═══════════════════════════════════════════════════════════════
# 6. 操作建议 (one line)
# ═══════════════════════════════════════════════════════════════
def section_advice(index_data: dict, signal_data: dict, sector_stats: dict, alert_data: dict = None) -> list[str]:
    """One-line actionable advice based on all signals."""
    sh_pct = index_data.get("000001.SH", {}).get("pct", 0)
    cy_pct = index_data.get("399006.SZ", {}).get("pct", 0)
    
    護盘_count = signal_data.get("護盘_count", 0)
    top1_net = signal_data.get("top1_net", 0)
    baijiu_net = signal_data.get("baijiu_net", 0)
    
    # Scoring
    bull = 0
    bear = 0
    
    if sh_pct > 0.3: bull += 1
    if sh_pct < -0.3: bear += 1
    if cy_pct > 0.3: bull += 1
    if cy_pct < -0.3: bear += 1
    if top1_net >= 200: bull += 1
    if top1_net < 100: bear += 1
    if 護盘_count == 3: bear += 1
    if baijiu_net > 10 and 護盘_count >= 2: bear += 2
    if baijiu_net < -10: bull += 1
    
    # Limit up/down
    up_count = alert_data.get("封涨停板", {}).get("count", 0) if alert_data else 0
    down_count = alert_data.get("封跌停板", {}).get("count", 0) if alert_data else 0
    if up_count > down_count * 1.5: bull += 1
    if down_count > up_count * 1.5: bear += 1
    
    # Sector breadth
    green_sectors = sum(1 for s, d in sector_stats.items() if d and d["avg_pct"] >= 0)
    total_sectors = sum(1 for s, d in sector_stats.items() if d)
    if total_sectors > 0:
        if green_sectors / total_sectors > 0.7: bull += 1
        if green_sectors / total_sectors < 0.3: bear += 1
    
    # Generate advice
    if bear >= 5:
        advice = "🛑 极端弱势，建议空仓观望，不抄底"
    elif bear >= 4:
        advice = "🛑 空头占优，减仓控险，只做确定性机会"
    elif bull >= 4:
        advice = "✅ 多头占优，可积极参与强势赛道"
    elif bear >= 3 and bull <= 1:
        advice = "🟡 偏弱，轻仓操作，关注防御板块"
    elif bull >= 3 and bear <= 1:
        advice = "🟢 偏强，适当参与领涨板块"
    else:
        advice = "⚖️ 震荡格局，保持灵活，等方向确认"
    
    return [f"🧠 {advice}"]


# ═══════════════════════════════════════════════════════════════
# Main: Assemble
# ═══════════════════════════════════════════════════════════════
def main():
    is_closing = "--closing" in sys.argv
    now = datetime.now()
    time_label = now.strftime("%Y-%m-%d %H:%M")
    
    title = "📊 A股收盘简报" if is_closing else "📊 A股简报"
    output = [f"{title} ({time_label})"]
    output.append("")
    
    # ── Fetch all data ──
    
    # 1. Index data
    index_data = fetch_indices()
    if index_data:
        save_index_snapshot(index_data)
    
    # 2. Alert data
    alert_data = None
    try:
        r = requests.get(f"{API_BASE}/api/news/market-alerts", timeout=10)
        if r.ok:
            alert_data = r.json()
    except Exception:
        pass
    
    # 3. Sector stocks from DB
    sector_stocks = load_sector_stocks()
    
    # 4. Fetch ALL stock quotes (sector stocks + watchlist)
    all_tickers = set()
    for tickers in sector_stocks.values():
        all_tickers.update(tickers)
    
    watchlist = load_watchlist()
    for item in watchlist:
        all_tickers.add(item["ticker"])
    
    print(f"正在获取 {len(all_tickers)} 只股票实时行情...", file=sys.stderr)
    all_quotes = fetch_sina_batch(list(all_tickers))
    print(f"成功获取 {len(all_quotes)} 只", file=sys.stderr)
    
    # ── Assemble sections ──
    
    # 1. 大盘一句话
    output.extend(section_headline(index_data, alert_data))
    output.append("")
    
    # 2. 赛道体检
    sector_result = section_sectors(sector_stocks, all_quotes)
    sector_stats = {}
    if isinstance(sector_result, tuple):
        sector_lines, sector_stats = sector_result
        output.extend(sector_lines)
    else:
        output.extend(sector_result)
    output.append("")
    
    # 3. 自选 vs 大盘
    output.extend(section_watchlist_vs_index(watchlist, all_quotes, index_data))
    output.append("")
    
    # 4. 关键信号
    signal_result = section_signals(index_data)
    signal_data = {}
    if isinstance(signal_result, tuple):
        signal_lines, signal_data = signal_result
        output.extend(signal_lines)
    else:
        output.extend(signal_result)
    output.append("")
    
    # 5. 快讯精选
    output.extend(section_news_filtered())
    output.append("")
    
    # 6. 操作建议
    output.extend(section_advice(index_data, signal_data, sector_stats, alert_data))
    
    output.append("")
    output.append(f"⏱ {datetime.now().strftime('%H:%M:%S')} | 数据仅供参考")
    
    full_text = "\n".join(output)
    print(full_text)


if __name__ == "__main__":
    main()
