#!/usr/bin/env python3
"""
美股简报 v3 — 完整版（模块化 + 规则引擎分析 + 盘后总结）
=============================================
用法: python scripts/us_briefing_v2.py [--time]

模块:
1.  三大指数 + VIX             — /api/us-stock/indexes
2.  板块表现（ETF + 广度）      — /api/us-stock/sectors
3.  Mag7 七巨头                — /api/us-stock/mag7
4.  中概股 ADR                 — /api/us-stock/china-adr
5.  商品（贵金属/能源/工业）     — /api/us-stock/commodities
6.  美债收益率 + 利差           — /api/us-stock/bonds
7.  美元指数 / 外汇             — /api/us-stock/forex
8.  盘中全程回顾                — 指数快照时间线
9.  📰 快讯                    — /api/news/latest
10. 🧠 Wendy分析               — 规则引擎分析
11. 📝 盘后总结                — 模板化叙事总结
12. 📅 经济日历                — /api/us-stock/calendar

数据源: ashare API http://127.0.0.1:8000
"""

import sys
import json
import argparse
import requests
import time as time_mod
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── Config ───────────────────────────────────────────────────
API_BASE = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 10  # Increased from 5
CONNECT_TIMEOUT = 3   # Increased from 2
MAX_RETRIES = 2

PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOT_FILE = PROJECT_ROOT / "data" / "snapshots" / "intraday" / "us_index_snapshots.json"
SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# Helper: safe fetch with retry
# ═══════════════════════════════════════════════════════════════
def fetch(endpoint: str) -> dict:
    """Fetch JSON from API with retry. Returns {} on failure."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.get(
                f"{API_BASE}{endpoint}",
                timeout=(CONNECT_TIMEOUT, REQUEST_TIMEOUT),
            )
            if r.ok:
                return r.json()
        except Exception:
            if attempt < MAX_RETRIES:
                time_mod.sleep(0.3)
    return {}


def safe_section(name: str):
    """Decorator: if a section fails, print error and continue."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                return [f"⚠️ [{name}] 获取失败: {e}"]
        return wrapper
    return decorator


def pct_icon(pct: float) -> str:
    return "🟢" if pct >= 0 else "🔴"


def format_price(price: float, decimals: int = 2) -> str:
    if price >= 1000:
        return f"{price:,.{decimals}f}"
    return f"{price:.{decimals}f}"


def format_market_cap(cap: float) -> str:
    if cap >= 1e12:
        return f"{cap / 1e12:.2f}T"
    elif cap >= 1e9:
        return f"{cap / 1e9:.1f}B"
    elif cap >= 1e6:
        return f"{cap / 1e6:.0f}M"
    return ""


# ═══════════════════════════════════════════════════════════════
# 0. Save index snapshot (side effect, runs every time)
# ═══════════════════════════════════════════════════════════════
def save_index_snapshot(quotes: list):
    """Save current index prices as a snapshot point."""
    try:
        if SNAPSHOT_FILE.exists():
            data = json.loads(SNAPSHOT_FILE.read_text())
            if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
                data = {"date": datetime.now().strftime("%Y-%m-%d"), "snapshots": []}
        else:
            data = {"date": datetime.now().strftime("%Y-%m-%d"), "snapshots": []}

        now_time = datetime.now().strftime("%H:%M")
        existing = {s["time"] for s in data["snapshots"]}
        if now_time in existing:
            return

        entry = {"time": now_time, "indexes": {}}
        for q in quotes:
            if q["symbol"] in ("^GSPC", "^DJI", "^IXIC", "^NDX", "^VIX"):
                entry["indexes"][q["symbol"]] = {
                    "name": q.get("cn_name") or q["name"],
                    "price": q["price"],
                    "pct": q["change_pct"],
                }
        data["snapshots"].append(entry)
        SNAPSHOT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 1. 三大指数 + VIX
# ═══════════════════════════════════════════════════════════════
@safe_section("三大指数")
def section_indexes(data: dict) -> list[str]:
    lines = ["📈 **三大指数 + VIX**"]
    quotes = data.get("quotes", [])
    if not quotes:
        return lines + ["  数据暂无"]

    main_indexes = []
    vix = None
    for q in quotes:
        if q["symbol"] == "^VIX":
            vix = q
        else:
            main_indexes.append(q)

    for q in main_indexes:
        icon = pct_icon(q["change_pct"])
        name = q.get("cn_name") or q["name"]
        price = format_price(q["price"])
        vol_str = ""
        if q.get("volume") and q["volume"] > 0:
            vol_b = q["volume"] / 1e9
            vol_str = f" 成交:{vol_b:.1f}B" if vol_b >= 1 else f" 成交:{q['volume'] / 1e6:.0f}M"
        lines.append(f"  {icon} {name}: {price} ({q['change_pct']:+.2f}%){vol_str}")

    if vix:
        vl = vix["price"]
        if vl >= 30:
            ve = "🔴🔴"
        elif vl >= 25:
            ve = "🔴"
        elif vl >= 20:
            ve = "🟡"
        else:
            ve = "🟢"
        lines.append(f"  {ve} VIX恐慌指数: {vl:.2f} ({vix['change_pct']:+.2f}%)")

    return lines


# ═══════════════════════════════════════════════════════════════
# 2. 板块表现（按涨跌排序 + 广度 + 攻防）
# ═══════════════════════════════════════════════════════════════
@safe_section("板块表现")
def section_sectors(data: dict) -> list[str]:
    lines = ["🏛️ **板块表现**"]
    sectors = data.get("sectors", [])
    if not sectors:
        return lines + ["  数据暂无"]

    etf_sectors = []
    for s in sectors:
        if s.get("etf"):
            etf_sectors.append({
                "name_cn": s["name_cn"],
                "symbol": s["etf"]["symbol"],
                "pct": s["etf"]["change_pct"],
                "price": s["etf"]["price"],
                "volume": s["etf"].get("volume", 0),
            })

    if not etf_sectors:
        return lines + ["  无ETF数据"]

    etf_sectors.sort(key=lambda x: x["pct"], reverse=True)

    # Show ALL sectors (not just top/bottom 3)
    for s in etf_sectors:
        icon = pct_icon(s["pct"])
        vol_str = ""
        if s["volume"] > 0:
            vol_m = s["volume"] / 1e6
            vol_str = f" 成交:{vol_m:.0f}M"
        lines.append(f"  {icon} {s['name_cn']}({s['symbol']}): {s['pct']:+.2f}%{vol_str}")

    # Breadth
    up_count = sum(1 for s in etf_sectors if s["pct"] > 0)
    down_count = sum(1 for s in etf_sectors if s["pct"] < 0)
    flat_count = len(etf_sectors) - up_count - down_count
    lines.append(f"  板块广度: {up_count}涨 / {down_count}跌 / {flat_count}平")

    # Offensive vs Defensive
    defensive_names = {"公用事业", "必需消费", "医疗健康", "房地产"}
    offensive_names = {"半导体", "可选消费", "通信服务", "金融"}
    def_pcts = [s["pct"] for s in etf_sectors if s["name_cn"] in defensive_names]
    off_pcts = [s["pct"] for s in etf_sectors if s["name_cn"] in offensive_names]

    if def_pcts and off_pcts:
        def_avg = sum(def_pcts) / len(def_pcts)
        off_avg = sum(off_pcts) / len(off_pcts)
        if def_avg > off_avg + 0.5:
            lines.append(f"  🛡️ 防御>进攻（{def_avg:+.2f}% vs {off_avg:+.2f}%）→ 避险情绪")
        elif off_avg > def_avg + 0.5:
            lines.append(f"  ⚔️ 进攻>防御（{off_avg:+.2f}% vs {def_avg:+.2f}%）→ 风险偏好高")
        else:
            lines.append(f"  ⚖️ 攻防均衡（进攻{off_avg:+.2f}% / 防御{def_avg:+.2f}%）")

    return lines


# ═══════════════════════════════════════════════════════════════
# 3. Mag7 七巨头
# ═══════════════════════════════════════════════════════════════
@safe_section("Mag7")
def section_mag7(data: dict) -> list[str]:
    lines = ["💎 **Mag7 科技七巨头**"]
    quotes = data.get("quotes", [])
    if not quotes:
        return lines + ["  数据暂无"]

    sorted_q = sorted(quotes, key=lambda q: q["change_pct"], reverse=True)
    avg_pct = sum(q["change_pct"] for q in sorted_q) / len(sorted_q)
    total_cap = sum(q.get("market_cap", 0) for q in sorted_q)

    for q in sorted_q:
        icon = pct_icon(q["change_pct"])
        name = q.get("cn_name") or q["symbol"]
        cap_str = format_market_cap(q.get("market_cap", 0))
        vol_str = ""
        if q.get("volume") and q["volume"] > 0:
            vol_m = q["volume"] / 1e6
            vol_str = f" 成交:{vol_m:.0f}M"
        lines.append(
            f"  {icon} {name}({q['symbol']}): ${format_price(q['price'])} "
            f"({q['change_pct']:+.2f}%) [{cap_str}]{vol_str}"
        )

    icon_avg = pct_icon(avg_pct)
    total_cap_str = format_market_cap(total_cap)
    up_count = sum(1 for q in sorted_q if q["change_pct"] > 0)
    down_count = len(sorted_q) - up_count
    lines.append(f"  {icon_avg} Mag7: {up_count}涨/{down_count}跌 均涨幅{avg_pct:+.2f}% | 总市值{total_cap_str}")

    # Spread analysis
    best = sorted_q[0]
    worst = sorted_q[-1]
    spread = best["change_pct"] - worst["change_pct"]
    if spread > 5:
        lines.append(f"  ⚠️ 内部分化{spread:.1f}%：{best.get('cn_name', best['symbol'])}领涨 vs {worst.get('cn_name', worst['symbol'])}领跌，事件驱动")
    elif avg_pct > 1:
        lines.append(f"  🟢 巨头整体强势，科技牛市基调不变")
    elif avg_pct < -1:
        lines.append(f"  🔴 巨头整体疲弱，拖累指数权重")

    return lines


# ═══════════════════════════════════════════════════════════════
# 4. 中概股 ADR
# ═══════════════════════════════════════════════════════════════
@safe_section("中概股")
def section_china_adr(data: dict) -> list[str]:
    lines = ["🇨🇳 **中概股 ADR**"]
    quotes = data.get("quotes", [])
    if not quotes:
        return lines + ["  数据暂无"]

    sorted_q = sorted(quotes, key=lambda q: q["change_pct"], reverse=True)
    avg_pct = sum(q["change_pct"] for q in sorted_q) / len(sorted_q)

    for q in sorted_q:
        icon = pct_icon(q["change_pct"])
        name = q.get("cn_name") or q["symbol"]
        vol_str = ""
        if q.get("volume") and q["volume"] > 0:
            vol_m = q["volume"] / 1e6
            vol_str = f" 成交:{vol_m:.0f}M"
        lines.append(
            f"  {icon} {name}({q['symbol']}): ${format_price(q['price'])} "
            f"({q['change_pct']:+.2f}%){vol_str}"
        )

    icon_avg = pct_icon(avg_pct)
    up_count = sum(1 for q in sorted_q if q["change_pct"] > 0)
    down_count = len(sorted_q) - up_count
    lines.append(f"  {icon_avg} 中概股: {up_count}涨/{down_count}跌 均涨幅{avg_pct:+.2f}%")

    return lines


# ═══════════════════════════════════════════════════════════════
# 5. 商品（贵金属 / 能源 / 工业金属）
# ═══════════════════════════════════════════════════════════════
@safe_section("商品")
def section_commodities(data: dict) -> list[str]:
    lines = ["📦 **商品期货**"]
    commodities = data.get("commodities", [])
    if not commodities:
        return lines + ["  数据暂无"]

    precious, energy, industrial = [], [], []
    for c in commodities:
        entry = {
            "cn_name": c.get("cn_name") or c["name"],
            "symbol": c["symbol"],
            "price": c["price"],
            "pct": c.get("change_pct", 0),
        }
        if c["symbol"] in ("GC=F", "SI=F"):
            precious.append(entry)
        elif c["symbol"] in ("CL=F", "BZ=F", "NG=F"):
            energy.append(entry)
        elif c["symbol"] in ("HG=F",):
            industrial.append(entry)
        else:
            energy.append(entry)

    if precious:
        parts = []
        for c in precious:
            icon = pct_icon(c["pct"])
            parts.append(f"{icon}{c['cn_name']} ${format_price(c['price'])} ({c['pct']:+.2f}%)")
        lines.append(f"  贵金属: {' | '.join(parts)}")

    if energy:
        parts = []
        for c in energy:
            icon = pct_icon(c["pct"])
            parts.append(f"{icon}{c['cn_name']} ${format_price(c['price'])} ({c['pct']:+.2f}%)")
        lines.append(f"  能源: {' | '.join(parts)}")

    if industrial:
        parts = []
        for c in industrial:
            icon = pct_icon(c["pct"])
            parts.append(f"{icon}{c['cn_name']} ${format_price(c['price'])} ({c['pct']:+.2f}%)")
        lines.append(f"  工业金属: {' | '.join(parts)}")

    # Gold/Silver ratio
    gold_p = next((c["price"] for c in precious if c["symbol"] == "GC=F"), 0)
    silver_p = next((c["price"] for c in precious if c["symbol"] == "SI=F"), 0)
    if gold_p > 0 and silver_p > 0:
        gs_ratio = gold_p / silver_p
        label = "偏高→避险" if gs_ratio > 80 else "偏低→工业需求旺" if gs_ratio < 60 else "正常"
        lines.append(f"  📊 金银比: {gs_ratio:.1f} ({label})")

    return lines


# ═══════════════════════════════════════════════════════════════
# 6. 美债收益率 + 利差
# ═══════════════════════════════════════════════════════════════
@safe_section("债券")
def section_bonds(data: dict) -> list[str]:
    lines = ["🏦 **美债收益率**"]
    bonds = data.get("bonds", [])
    if not bonds:
        return lines + ["  数据暂无"]

    bond_map = {}
    for b in bonds:
        bond_map[b["symbol"]] = b
        icon = pct_icon(b.get("change_pct", 0))
        name = b.get("cn_name") or b["name"]
        lines.append(f"  {icon} {name}: {b['price']:.3f}% ({b.get('change_pct', 0):+.2f}%)")

    tnx = bond_map.get("^TNX")
    fvx = bond_map.get("^FVX")
    tyx = bond_map.get("^TYX")

    if tnx and fvx:
        spread_10_5 = tnx["price"] - fvx["price"]
        label = "正常" if spread_10_5 > 0 else "⚠️ 倒挂"
        lines.append(f"  📐 10Y-5Y利差: {spread_10_5:+.3f}% ({label})")
    if tyx and tnx:
        spread_30_10 = tyx["price"] - tnx["price"]
        lines.append(f"  📐 30Y-10Y利差: {spread_30_10:+.3f}%")

    # Yield level commentary
    if tnx:
        y10 = tnx["price"]
        if y10 > 5.0:
            lines.append(f"  🔴 10Y > 5%：紧缩环境，股市承压")
        elif y10 > 4.5:
            lines.append(f"  🟡 10Y > 4.5%：利率偏高，关注通胀数据")
        elif y10 < 3.5:
            lines.append(f"  🟢 10Y < 3.5%：宽松预期，利好成长股")

    return lines


# ═══════════════════════════════════════════════════════════════
# 7. 美元指数 / 外汇
# ═══════════════════════════════════════════════════════════════
@safe_section("外汇")
def section_forex(data: dict) -> list[str]:
    lines = ["💵 **美元指数 / 外汇**"]
    forex = data.get("forex", [])
    if not forex:
        return lines + ["  数据暂无"]

    for f in forex:
        icon = pct_icon(f.get("change_pct", 0))
        name = f.get("cn_name") or f["name"]
        lines.append(f"  {icon} {name}: {f['price']:.3f} ({f.get('change_pct', 0):+.2f}%)")

    # Dollar strength commentary
    dxy = next((f for f in forex if f["symbol"] == "DX-Y.NYB"), None)
    if dxy:
        p = dxy["price"]
        if p > 105:
            lines.append(f"  💪 美元强势 → 压制商品/新兴市场")
        elif p < 95:
            lines.append(f"  📉 美元弱势 → 利好商品/新兴市场")

    return lines


# ═══════════════════════════════════════════════════════════════
# 8. 盘中全程回顾（指数快照时间线）
# ═══════════════════════════════════════════════════════════════
@safe_section("盘中回顾")
def section_intraday_table() -> list[str]:
    if not SNAPSHOT_FILE.exists():
        return []

    data = json.loads(SNAPSHOT_FILE.read_text())
    snapshots = data.get("snapshots", [])
    if len(snapshots) < 2:
        return []  # Need at least 2 points to show timeline

    lines = [f"📋 **盘中全程回顾** ({data.get('date', '今日')})"]

    # Track highs/lows
    idx_tracker = {}

    lines.append(f"{'时间':>6} | {'S&P500':>12} | {'纳斯达克':>12} | {'道琼斯':>12} | {'VIX':>8}")
    lines.append(f"{'─' * 6} | {'─' * 12} | {'─' * 12} | {'─' * 12} | {'─' * 8}")

    for snap in snapshots:
        t = snap["time"]
        idxs = snap.get("indexes", {})

        cols = [f"{t:>6}"]
        for code in ["^GSPC", "^IXIC", "^DJI"]:
            idx = idxs.get(code, {})
            price = idx.get("price", 0)
            pct = idx.get("pct", 0)
            if price > 0:
                sign = "+" if pct >= 0 else ""
                col_str = f"{sign}{pct:.2f}%"
                # Track high/low
                if code not in idx_tracker:
                    idx_tracker[code] = {
                        "name": idx.get("name", code),
                        "high_pct": pct, "high_time": t,
                        "low_pct": pct, "low_time": t,
                    }
                else:
                    tr = idx_tracker[code]
                    if pct > tr["high_pct"]:
                        tr["high_pct"] = pct
                        tr["high_time"] = t
                    if pct < tr["low_pct"]:
                        tr["low_pct"] = pct
                        tr["low_time"] = t
            else:
                col_str = "—"
            cols.append(f"{col_str:>12}")

        # VIX
        vix_data = idxs.get("^VIX", {})
        if vix_data.get("price", 0) > 0:
            cols.append(f"{vix_data['price']:.2f}".rjust(8))
        else:
            cols.append("—".rjust(8))

        lines.append(" | ".join(cols))

    # High/Low summary
    if idx_tracker:
        lines.append("")
        lines.append("📍 **高低点:**")
        name_map = {"^GSPC": "S&P500", "^IXIC": "纳斯达克", "^DJI": "道琼斯"}
        for code in ["^GSPC", "^IXIC", "^DJI"]:
            if code in idx_tracker:
                tr = idx_tracker[code]
                lines.append(
                    f"  {name_map.get(code, code)}: "
                    f"高点({tr['high_pct']:+.2f}%) @{tr['high_time']} | "
                    f"低点({tr['low_pct']:+.2f}%) @{tr['low_time']}"
                )

    return lines


# ═══════════════════════════════════════════════════════════════
# 9. 快讯
# ═══════════════════════════════════════════════════════════════
@safe_section("快讯")
def section_news(data: dict) -> list[str]:
    lines = ["📰 **快讯**"]
    news_list = data.get("news", [])
    if isinstance(data, list):
        news_list = data
    if not news_list:
        return lines + ["  暂无快讯"]

    for item in news_list[:8]:
        title = item.get("title", "")[:80]
        t = item.get("time", "")
        src = item.get("source_name") or item.get("source", "")
        if t and len(t) >= 5:
            if len(t) >= 16 and "T" in t:
                t = t[11:16]
            elif ":" in t:
                t = t[:5]
        prefix = f"[{t}]" if t else ""
        src_tag = f"({src})" if src else ""
        lines.append(f"  • {prefix} {title} {src_tag}")

    return lines


# ═══════════════════════════════════════════════════════════════
# 10. 🧠 Wendy分析（规则引擎，纯确定性）
# ═══════════════════════════════════════════════════════════════
def section_analysis(
    index_data: dict,
    sector_data: dict,
    mag7_data: dict,
    adr_data: dict,
    commodity_data: dict,
    bond_data: dict,
    forex_data: dict,
) -> tuple[list[str], dict]:
    """Returns (lines, signal_data) for use in summary."""
    try:
        return _section_analysis_inner(
            index_data, sector_data, mag7_data,
            adr_data, commodity_data, bond_data, forex_data,
        )
    except Exception as e:
        return [f"⚠️ [Wendy分析] 获取失败: {e}"], {}


def _section_analysis_inner(
    index_data, sector_data, mag7_data,
    adr_data, commodity_data, bond_data, forex_data,
) -> tuple[list[str], dict]:

    lines = ["🧠 **Wendy分析**"]

    # ── Extract key metrics ──
    quotes = index_data.get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}

    sp500 = quote_map.get("^GSPC", {})
    nasdaq = quote_map.get("^IXIC", {})
    dow = quote_map.get("^DJI", {})
    ndx100 = quote_map.get("^NDX", {})
    vix_q = quote_map.get("^VIX", {})

    sp_pct = sp500.get("change_pct", 0)
    nas_pct = nasdaq.get("change_pct", 0)
    dow_pct = dow.get("change_pct", 0)
    vix_level = vix_q.get("price", 0)
    vix_pct = vix_q.get("change_pct", 0)

    mag_quotes = mag7_data.get("quotes", [])
    mag_avg = sum(q["change_pct"] for q in mag_quotes) / len(mag_quotes) if mag_quotes else 0

    adr_quotes = adr_data.get("quotes", [])
    adr_avg = sum(q["change_pct"] for q in adr_quotes) / len(adr_quotes) if adr_quotes else 0

    commodities = commodity_data.get("commodities", [])
    commodity_map = {c["symbol"]: c for c in commodities}
    gold = commodity_map.get("GC=F", {})
    gold_pct = gold.get("change_pct", 0)
    oil = commodity_map.get("CL=F", {})
    oil_pct = oil.get("change_pct", 0)
    copper = commodity_map.get("HG=F", {})
    copper_pct = copper.get("change_pct", 0)

    bonds = bond_data.get("bonds", [])
    bond_map = {b["symbol"]: b for b in bonds}
    tnx = bond_map.get("^TNX", {})
    y10 = tnx.get("price", 0)
    y10_pct = tnx.get("change_pct", 0)

    forex = forex_data.get("forex", [])
    fx_map = {f["symbol"]: f for f in forex}
    dxy = fx_map.get("DX-Y.NYB", {})
    dxy_price = dxy.get("price", 0)
    dxy_pct = dxy.get("change_pct", 0)

    sectors = sector_data.get("sectors", [])
    etf_sectors = []
    for s in sectors:
        if s.get("etf"):
            etf_sectors.append({
                "name_cn": s["name_cn"],
                "symbol": s["etf"]["symbol"],
                "pct": s["etf"]["change_pct"],
            })
    etf_sectors.sort(key=lambda x: x["pct"], reverse=True)

    # ═══ 10a. 市场定性 ═══
    lines.append("")
    lines.append("**市场定性:**")

    # VIX signal
    if vix_level >= 30:
        vix_signal = "🔴 极度恐慌（VIX≥30）— 市场剧烈波动"
    elif vix_level >= 25:
        vix_signal = "🟠 高度恐慌（VIX≥25）— 避险情绪浓厚"
    elif vix_level >= 20:
        vix_signal = "🟡 警惕（VIX≥20）— 波动率偏高"
    elif vix_level >= 15:
        vix_signal = "⚖️ 正常（VIX 15-20）— 市场中性"
    elif vix_level > 0:
        vix_signal = "🟢 低波动（VIX<15）— 市场乐观"
    else:
        vix_signal = "⚪ VIX数据暂无"
    lines.append(f"  VIX: {vix_signal}")

    # Value vs Growth
    scissor = dow_pct - nas_pct
    if scissor > 1.0:
        style_signal = "⚠️ 价值>成长（道指强、纳指弱）→ Risk OFF"
    elif scissor < -1.0:
        style_signal = "🚀 成长>价值（纳指强、道指弱）→ Risk ON"
    elif sp_pct > 0.5 and nas_pct > 0.5:
        style_signal = "🟢 普涨行情"
    elif sp_pct < -0.5 and nas_pct < -0.5:
        style_signal = "🔴 普跌行情"
    else:
        style_signal = "⚖️ 中性震荡"
    lines.append(f"  风格: {style_signal}")
    lines.append(f"  道指{dow_pct:+.2f}% vs 纳指{nas_pct:+.2f}% → 剪刀差{scissor:+.2f}%")

    # ═══ 10b. 资金轮动 ═══
    lines.append("")
    lines.append("**资金轮动:**")
    if etf_sectors:
        top3 = etf_sectors[:3]
        bot3 = etf_sectors[-3:]
        in_names = " / ".join([f"{s['name_cn']}({s['pct']:+.2f}%)" for s in top3])
        out_names = " / ".join([f"{s['name_cn']}({s['pct']:+.2f}%)" for s in bot3])
        lines.append(f"  🔺 资金涌入: {in_names}")
        lines.append(f"  🔻 资金撤离: {out_names}")

        # Sector breadth
        up_ratio = sum(1 for s in etf_sectors if s["pct"] > 0) / len(etf_sectors) if etf_sectors else 0
        lines.append(f"  板块上涨比: {up_ratio:.0%}（{sum(1 for s in etf_sectors if s['pct'] > 0)}/{len(etf_sectors)}）")
    else:
        lines.append("  数据暂无")

    # ═══ 10c. Mag7健康度 ═══
    lines.append("")
    lines.append("**Mag7 健康度:**")
    if mag_quotes:
        mag_up = sum(1 for q in mag_quotes if q["change_pct"] > 0)
        mag_down = len(mag_quotes) - mag_up
        best = max(mag_quotes, key=lambda q: q["change_pct"])
        worst = min(mag_quotes, key=lambda q: q["change_pct"])
        spread = best["change_pct"] - worst["change_pct"]

        lines.append(f"  {mag_up}涨/{mag_down}跌 | 均涨幅{mag_avg:+.2f}%")
        lines.append(
            f"  最强: {best.get('cn_name', best['symbol'])} {best['change_pct']:+.2f}% | "
            f"最弱: {worst.get('cn_name', worst['symbol'])} {worst['change_pct']:+.2f}%"
        )
        if spread > 5:
            lines.append(f"  ⚠️ 内部分化严重（差距{spread:.1f}%），事件驱动")
        elif mag_avg > 1:
            lines.append(f"  🟢 科技巨头整体强势，风险偏好高")
        elif mag_avg < -1:
            lines.append(f"  🔴 科技巨头整体疲弱，大盘承压")
    else:
        lines.append("  数据暂无")

    # ═══ 10d. 中概 vs 大盘 ═══
    lines.append("")
    lines.append("**中概 vs 大盘:**")
    if adr_quotes:
        adr_up = sum(1 for q in adr_quotes if q["change_pct"] > 0)
        adr_down = len(adr_quotes) - adr_up
        relative = adr_avg - sp_pct
        lines.append(f"  中概均涨幅: {adr_avg:+.2f}% vs S&P500: {sp_pct:+.2f}%")
        lines.append(f"  相对强弱: {relative:+.2f}% ({adr_up}涨/{adr_down}跌)")
        if relative > 2:
            lines.append(f"  🟢 中概显著跑赢大盘，中国资产受追捧")
        elif relative < -2:
            lines.append(f"  🔴 中概显著跑输大盘，地缘/政策风险溢价")
        elif adr_avg > 0 and sp_pct < 0:
            lines.append(f"  🟢 中概逆势走强，独立行情")
        elif adr_avg < 0 and sp_pct > 0:
            lines.append(f"  🔴 中概逆势走弱，资金回避中国资产")
        else:
            lines.append(f"  ⚖️ 中概跟随大盘")
    else:
        lines.append("  数据暂无")

    # ═══ 10e. 🛡️ 避险信号组合（类似A股护盘指标） ═══
    lines.append("")
    lines.append("**🛡️ 避险信号组合:**")
    safe_haven_signals = 0
    safe_haven_total = 0

    # Signal 1: VIX spike
    if vix_level >= 20:
        safe_haven_signals += 1
        lines.append(f"  🔴 VIX={vix_level:.2f}({vix_pct:+.2f}%) → 恐慌升温")
    elif vix_level >= 15:
        lines.append(f"  🟡 VIX={vix_level:.2f}({vix_pct:+.2f}%) → 正常偏高")
    else:
        lines.append(f"  🟢 VIX={vix_level:.2f}({vix_pct:+.2f}%) → 市场平静")

    # Signal 2: Gold rally
    if gold_pct > 1.5:
        safe_haven_signals += 1
        lines.append(f"  🔴 黄金{gold_pct:+.2f}% → 避险需求强劲")
    elif gold_pct < -1:
        lines.append(f"  🟢 黄金{gold_pct:+.2f}% → 无避险需求")
    else:
        lines.append(f"  ⚖️ 黄金{gold_pct:+.2f}% → 中性")

    # Signal 3: Bond yield drop (flight to safety)
    if y10_pct < -2:
        safe_haven_signals += 1
        lines.append(f"  🔴 10Y美债收益率{y10_pct:+.2f}%大跌 → 资金涌入国债避险")
    elif y10_pct > 2:
        lines.append(f"  🟡 10Y美债收益率{y10_pct:+.2f}%大涨 → 通胀/紧缩预期")
    else:
        lines.append(f"  ⚖️ 10Y美债收益率{y10_pct:+.2f}% → 中性")

    # Signal 4: Defensive sectors outperforming
    defensive_names = {"公用事业", "必需消费", "医疗健康", "房地产"}
    offensive_names = {"半导体", "可选消费", "通信服务"}
    def_pcts = [s["pct"] for s in etf_sectors if s["name_cn"] in defensive_names]
    off_pcts = [s["pct"] for s in etf_sectors if s["name_cn"] in offensive_names]
    if def_pcts and off_pcts:
        def_avg = sum(def_pcts) / len(def_pcts)
        off_avg = sum(off_pcts) / len(off_pcts)
        if def_avg > off_avg + 1:
            safe_haven_signals += 1
            lines.append(f"  🔴 防御板块领涨({def_avg:+.2f}% vs 进攻{off_avg:+.2f}%) → 避险轮动")
        elif off_avg > def_avg + 1:
            lines.append(f"  🟢 进攻板块领涨({off_avg:+.2f}% vs 防御{def_avg:+.2f}%) → 风险偏好")
        else:
            lines.append(f"  ⚖️ 攻防均衡（进攻{off_avg:+.2f}% / 防御{def_avg:+.2f}%）")

    # Combined verdict
    if safe_haven_signals >= 3:
        lines.append(f"  🚨 {safe_haven_signals}/4避险信号亮灯 → **全面避险模式**，科技/成长承压严重")
    elif safe_haven_signals >= 2:
        lines.append(f"  ⚠️ {safe_haven_signals}/4避险信号 → 避险情绪偏浓，谨慎操作")
    elif safe_haven_signals >= 1:
        lines.append(f"  🟡 {safe_haven_signals}/4避险信号 → 轻微避险，但不构成系统风险")
    else:
        lines.append(f"  🟢 0/4避险信号 → 市场情绪正常，无需过度防御")

    # ═══ 10f. 📏 趋势强度标尺 ═══
    lines.append("")
    lines.append("**📏 趋势强度:**")
    if etf_sectors:
        best_sector = etf_sectors[0]
        worst_sector = etf_sectors[-1]
        sector_spread = best_sector["pct"] - worst_sector["pct"]

        lines.append(
            f"  #1 {best_sector['name_cn']}({best_sector['symbol']}): {best_sector['pct']:+.2f}%"
        )

        if sector_spread > 5:
            trend_strength = "🔥 强分化"
            trend_desc = "资金方向明确，做多有方向感"
        elif sector_spread > 3:
            trend_strength = "📊 中等分化"
            trend_desc = "有选择性进攻，但力度一般"
        elif sector_spread > 1:
            trend_strength = "⚖️ 弱分化"
            trend_desc = "板块齐涨齐跌，缺乏主线"
        else:
            trend_strength = "😶 无方向"
            trend_desc = "极度窄幅，观望为主"

        lines.append(f"  板块离散度: {sector_spread:.2f}% → {trend_strength}（{trend_desc}）")

        # Check if tech-heavy
        tech_sectors = {"半导体", "通信服务", "可选消费"}
        tech_in_top3 = sum(1 for s in etf_sectors[:3] if s["name_cn"] in tech_sectors)
        if tech_in_top3 >= 2:
            lines.append(f"  🚀 TOP3中{tech_in_top3}个科技/成长板块 → 科技主线日")
        value_sectors = {"金融", "能源", "材料", "工业"}
        value_in_top3 = sum(1 for s in etf_sectors[:3] if s["name_cn"] in value_sectors)
        if value_in_top3 >= 2:
            lines.append(f"  🏛️ TOP3中{value_in_top3}个价值/周期板块 → 价值轮动日")
    else:
        lines.append("  数据暂无")

    # ═══ 10g. 商品/利率/汇率联动信号 ═══
    lines.append("")
    lines.append("**关键联动信号:**")

    signals_list = []

    # Gold + VIX combo
    if gold_pct > 1.5 and vix_level >= 20:
        signals_list.append("🚨 黄金+VIX同涨 → 市场恐慌模式")
    elif gold_pct > 1.5 and vix_level < 15:
        signals_list.append("🤔 黄金涨但VIX低 → 可能是通胀交易而非避险")

    # Oil + copper combo (economic signal)
    if oil_pct < -3 and copper_pct < -2:
        signals_list.append("⚠️ 原油+铜同跌 → 全球经济衰退预期")
    elif oil_pct > 3 and copper_pct > 2:
        signals_list.append("🟢 原油+铜同涨 → 全球经济复苏预期")

    # Yield + dollar combo
    if y10_pct > 2 and dxy_pct > 0.3:
        signals_list.append("⚠️ 利率上行+美元走强 → 金融条件收紧")
    elif y10_pct < -2 and dxy_pct < -0.3:
        signals_list.append("🟢 利率下行+美元走弱 → 金融条件宽松")

    # Mag7 vs market
    if mag_avg < -2 and sp_pct > -0.5:
        signals_list.append("⚠️ 巨头大跌但大盘稳 → 权重轮动，非系统风险")
    elif mag_avg > 2 and sp_pct < 0.5:
        signals_list.append("🤔 巨头大涨但大盘弱 → 资金集中头部，中小盘承压")

    # ADR vs A-share anticipation
    if adr_avg > 2:
        signals_list.append("🟢 中概股大涨 → 明日A股相关标的有望受益")
    elif adr_avg < -3:
        signals_list.append("🔴 中概股大跌 → 明日A股情绪可能受拖累")

    if signals_list:
        for s in signals_list:
            lines.append(f"  {s}")
    else:
        lines.append("  ⚖️ 各资产类别联动正常，无异常信号")

    # ═══ 10h. 综合评分 & 操作建议 ═══
    lines.append("")
    lines.append("**📏 综合评分:**")

    bullish = 0
    bearish = 0

    # Index direction
    if sp_pct > 0.3: bullish += 1
    elif sp_pct < -0.3: bearish += 1
    if nas_pct > 0.3: bullish += 1
    elif nas_pct < -0.3: bearish += 1

    # VIX
    if vix_level < 15: bullish += 1
    elif vix_level >= 25: bearish += 2
    elif vix_level >= 20: bearish += 1

    # Mag7
    if mag_avg > 0.5: bullish += 1
    elif mag_avg < -0.5: bearish += 1

    # Gold (inverse)
    if gold_pct > 2: bearish += 1
    elif gold_pct < -1: bullish += 1

    # Bond yield direction
    if y10_pct > 2: bearish += 1
    elif y10_pct < -2: bullish += 1

    # Sector breadth
    if etf_sectors:
        up_ratio = sum(1 for s in etf_sectors if s["pct"] > 0) / len(etf_sectors)
        if up_ratio > 0.7: bullish += 1
        elif up_ratio < 0.3: bearish += 1

    # Safe haven count
    if safe_haven_signals >= 3: bearish += 2
    elif safe_haven_signals >= 2: bearish += 1

    # Scissor
    if scissor > 1.5: bearish += 1  # Extreme value > growth = risk-off
    elif scissor < -1.5: bullish += 1  # Extreme growth = risk-on

    total_score = bullish - bearish
    if total_score >= 4:
        advice = "✅ 多头主导 — 市场风险偏好高，积极参与"
    elif total_score >= 2:
        advice = "🟢 偏多 — 温和看涨，关注主线板块"
    elif total_score <= -4:
        advice = "🛑 空头主导 — 避险为主，减仓观望"
    elif total_score <= -2:
        advice = "🟡 偏空 — 谨慎操作，控制仓位"
    elif abs(scissor) > 1.5:
        advice = "⚠️ 风格极端分化 — 跟随强势风格，回避弱势"
    else:
        advice = "⚖️ 中性震荡 — 轻仓灵活应对"

    lines.append(f"  多头信号: {bullish} | 空头信号: {bearish} | 净值: {total_score:+d}")
    lines.append(f"  {advice}")

    # Collect signal data for summary
    signal_data = {
        "sp_pct": sp_pct,
        "nas_pct": nas_pct,
        "dow_pct": dow_pct,
        "scissor": scissor,
        "style_signal": style_signal,
        "vix_level": vix_level,
        "vix_pct": vix_pct,
        "mag_avg": mag_avg,
        "mag_quotes": mag_quotes,
        "adr_avg": adr_avg,
        "adr_quotes": adr_quotes,
        "gold_pct": gold_pct,
        "oil_pct": oil_pct,
        "copper_pct": copper_pct,
        "y10": y10,
        "y10_pct": y10_pct,
        "dxy_price": dxy_price,
        "dxy_pct": dxy_pct,
        "safe_haven_signals": safe_haven_signals,
        "etf_sectors": etf_sectors,
        "bullish": bullish,
        "bearish": bearish,
        "total_score": total_score,
        "advice": advice,
    }

    return lines, signal_data


# ═══════════════════════════════════════════════════════════════
# 11. 📝 盘后总结（模板化叙事，类似A股版）
# ═══════════════════════════════════════════════════════════════
@safe_section("盘后总结")
def section_summary(signal_data: dict) -> list[str]:
    if not signal_data:
        return []

    sp_pct = signal_data.get("sp_pct", 0)
    nas_pct = signal_data.get("nas_pct", 0)
    dow_pct = signal_data.get("dow_pct", 0)
    scissor = signal_data.get("scissor", 0)
    vix_level = signal_data.get("vix_level", 0)
    mag_avg = signal_data.get("mag_avg", 0)
    mag_quotes = signal_data.get("mag_quotes", [])
    adr_avg = signal_data.get("adr_avg", 0)
    gold_pct = signal_data.get("gold_pct", 0)
    y10 = signal_data.get("y10", 0)
    y10_pct = signal_data.get("y10_pct", 0)
    safe_haven = signal_data.get("safe_haven_signals", 0)
    etf_sectors = signal_data.get("etf_sectors", [])
    bullish = signal_data.get("bullish", 0)
    bearish = signal_data.get("bearish", 0)

    lines = ["═══ 📝 总结 ═══", ""]

    # ── Determine day type ──
    if safe_haven >= 3 and nas_pct < -1:
        day_type = "extreme_risk_off"
    elif safe_haven >= 2:
        day_type = "risk_off"
    elif bullish >= 5:
        day_type = "strong_bull"
    elif bearish >= 5:
        day_type = "strong_bear"
    elif scissor > 1.5:
        day_type = "value_rotation"
    elif scissor < -1.5:
        day_type = "growth_chase"
    elif sp_pct > 0.5 and nas_pct > 0.5:
        day_type = "broad_rally"
    elif sp_pct < -0.5 and nas_pct < -0.5:
        day_type = "broad_selloff"
    else:
        day_type = "mixed"

    # ── Headline ──
    sp_dir = "涨" if sp_pct >= 0 else "跌"
    nas_dir = "涨" if nas_pct >= 0 else "跌"

    if day_type == "extreme_risk_off":
        lines.append(
            f"今天三大避险信号齐亮，纳指{nas_dir}{abs(nas_pct):.2f}%：**全面避险日**。"
        )
    elif day_type == "risk_off":
        lines.append(
            f"S&P {sp_dir}{abs(sp_pct):.2f}%，纳指{nas_dir}{abs(nas_pct):.2f}%。"
            f"资金偏防御，避险情绪升温。"
        )
    elif day_type == "strong_bull":
        lines.append(f"多头全面发力，S&P {sp_dir}{abs(sp_pct):.2f}%，市场情绪极度乐观。")
    elif day_type == "strong_bear":
        lines.append(f"空头占据绝对优势，S&P {sp_dir}{abs(sp_pct):.2f}%，全面承压。")
    elif day_type == "value_rotation":
        lines.append(
            f"典型的价值轮动日：道指+{abs(dow_pct):.2f}%跑赢纳指{nas_pct:+.2f}%，"
            f"剪刀差{scissor:+.2f}%。资金从成长切换到价值。"
        )
    elif day_type == "growth_chase":
        lines.append(
            f"成长股强势日：纳指{nas_dir}{abs(nas_pct):.2f}%领涨，"
            f"科技主线明确。"
        )
    elif day_type == "broad_rally":
        lines.append(f"三大指数全面上涨，S&P {sp_pct:+.2f}%，普涨格局。")
    elif day_type == "broad_selloff":
        lines.append(f"三大指数全面下跌，S&P {sp_pct:+.2f}%，普跌格局。")
    else:
        lines.append(
            f"S&P {sp_dir}{abs(sp_pct):.2f}%，纳指{nas_dir}{abs(nas_pct):.2f}%，"
            f"方向不明朗。"
        )

    lines.append("")

    # ── Three signals (like A-share) ──
    # 1. 避险信号
    if safe_haven >= 3:
        lines.append(f"1. 避险信号{safe_haven}/4灯全亮 → 市场极度恐慌")
    elif safe_haven >= 2:
        lines.append(f"1. 避险信号{safe_haven}/4灯 → 避险情绪偏浓")
    elif safe_haven == 1:
        lines.append(f"1. 避险信号1/4灯 → 轻微担忧但可控")
    else:
        lines.append(f"1. 避险信号0/4灯 → 市场情绪正常")

    # 2. Mag7 health (like A-share trend strength)
    best_mag = max(mag_quotes, key=lambda q: q["change_pct"]) if mag_quotes else {}
    worst_mag = min(mag_quotes, key=lambda q: q["change_pct"]) if mag_quotes else {}
    if mag_avg > 1:
        lines.append(f"2. Mag7均涨{mag_avg:+.2f}% → 科技牛市基调，可跟")
    elif mag_avg < -1:
        lines.append(
            f"2. Mag7均跌{mag_avg:+.2f}% → 巨头承压"
            + (f"（{worst_mag.get('cn_name', '')} {worst_mag.get('change_pct', 0):+.2f}%领跌）" if worst_mag else "")
        )
    else:
        lines.append(f"2. Mag7均涨幅{mag_avg:+.2f}% → 巨头表现中性")

    # 3. Style signal
    if scissor > 1.5:
        lines.append(f"3. 道/纳剪刀差{scissor:+.2f}% → 极端价值偏好，成长股资金外流")
    elif scissor < -1.5:
        lines.append(f"3. 道/纳剪刀差{scissor:+.2f}% → 极端成长偏好，科技主导")
    elif scissor > 0.5:
        lines.append(f"3. 道/纳剪刀差{scissor:+.2f}% → 偏价值风格")
    elif scissor < -0.5:
        lines.append(f"3. 道/纳剪刀差{scissor:+.2f}% → 偏成长风格")
    else:
        lines.append(f"3. 道/纳剪刀差{scissor:+.2f}% → 风格中性")

    lines.append("")

    # ── Notable moves ──
    if etf_sectors:
        best_s = etf_sectors[0]
        worst_s = etf_sectors[-1]
        spread = best_s["pct"] - worst_s["pct"]
        if spread > 3:
            lines.append(
                f"板块分化明显：{best_s['name_cn']}{best_s['pct']:+.2f}%领涨，"
                f"{worst_s['name_cn']}{worst_s['pct']:+.2f}%领跌，"
                f"离散度{spread:.2f}%。"
            )

    # ADR impact on A-share
    if abs(adr_avg) > 2:
        adr_dir = "大涨" if adr_avg > 0 else "大跌"
        impact = "正面提振" if adr_avg > 0 else "负面拖累"
        lines.append(f"中概股{adr_dir}({adr_avg:+.2f}%)，对明日A股中概相关标的{impact}。")

    lines.append("")

    # ── 明日关注 ──
    lines.append("**明日关注：**")
    focus = []

    if safe_haven >= 2:
        focus.append("避险信号能否缓解、VIX能否回落20以下")
    if abs(mag_avg) > 2:
        focus.append(f"Mag7{'反弹' if mag_avg < 0 else '持续性'}，关注是否有财报/事件催化")
    if abs(scissor) > 1.5:
        focus.append("道/纳剪刀差能否收窄、风格切换信号")
    if y10 > 4.5:
        focus.append(f"10Y美债{y10:.3f}%偏高，关注后续通胀数据影响")
    if abs(adr_avg) > 3:
        focus.append("中概股表现对A股开盘影响")

    if not focus:
        focus.append("继续观察主线方向与资金流向变化")

    for fp in focus:
        lines.append(f"  • {fp}")

    return lines


# ═══════════════════════════════════════════════════════════════
# 12. 经济日历
# ═══════════════════════════════════════════════════════════════
@safe_section("经济日历")
def section_calendar() -> list[str]:
    data = fetch("/api/us-stock/calendar")
    events = data.get("events", data.get("data", []))
    if not events:
        return []

    lines = ["📅 **经济日历**"]
    for e in events[:5]:
        date = e.get("date", "")
        event = e.get("event", e.get("name", ""))
        actual = e.get("actual", "")
        forecast = e.get("forecast", "")
        extra = ""
        if actual:
            extra += f" 实际:{actual}"
        if forecast:
            extra += f" 预期:{forecast}"
        lines.append(f"  • {date} {event}{extra}")

    return lines


# ═══════════════════════════════════════════════════════════════
# Main: Assemble all sections
# ═══════════════════════════════════════════════════════════════
def format_briefing(show_time: bool = False) -> str:
    now = datetime.now()
    time_label = now.strftime("%Y-%m-%d %H:%M")
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]

    output = []
    output.append(f"{'═' * 50}")
    output.append(f"🇺🇸 **美股简报** ({time_label} {weekday_cn})")
    output.append(f"{'═' * 50}")

    if show_time:
        output.append(f"⏱ 生成时间戳: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        output.append("")

    # ── Fetch all data concurrently ──
    endpoints = {
        "index": "/api/us-stock/indexes",
        "sector": "/api/us-stock/sectors",
        "mag7": "/api/us-stock/mag7",
        "adr": "/api/us-stock/china-adr",
        "commodity": "/api/us-stock/commodities",
        "bond": "/api/us-stock/bonds",
        "forex": "/api/us-stock/forex",
        "news": "/api/news/latest?limit=8",
    }
    results = {}
    with ThreadPoolExecutor(max_workers=4) as executor:  # Reduced from 8 to avoid overwhelming API
        futures = {executor.submit(fetch, ep): key for key, ep in endpoints.items()}
        for future in as_completed(futures):
            key = futures[future]
            results[key] = future.result()

    index_data = results.get("index", {})
    sector_data = results.get("sector", {})
    mag7_data = results.get("mag7", {})
    adr_data = results.get("adr", {})
    commodity_data = results.get("commodity", {})
    bond_data = results.get("bond", {})
    forex_data = results.get("forex", {})
    news_data = results.get("news", {})

    # Save index snapshot
    index_quotes = index_data.get("quotes", [])
    if index_quotes:
        save_index_snapshot(index_quotes)

    # ── Assemble sections ──

    # 1-7: Data sections
    output.extend(section_indexes(index_data))
    output.append("")
    output.extend(section_sectors(sector_data))
    output.append("")
    output.extend(section_mag7(mag7_data))
    output.append("")
    output.extend(section_china_adr(adr_data))
    output.append("")
    output.extend(section_commodities(commodity_data))
    output.append("")
    output.extend(section_bonds(bond_data))
    output.append("")
    output.extend(section_forex(forex_data))
    output.append("")

    # 8: Intraday timeline
    intraday = section_intraday_table()
    if intraday:
        output.extend(intraday)
        output.append("")

    # 9: News
    output.extend(section_news(news_data))
    output.append("")

    # 10: Analysis
    analysis_result = section_analysis(
        index_data, sector_data, mag7_data,
        adr_data, commodity_data, bond_data, forex_data,
    )
    signal_data = {}
    if isinstance(analysis_result, tuple):
        analysis_lines, signal_data = analysis_result
        output.extend(analysis_lines)
    else:
        output.extend(analysis_result)
    output.append("")

    # 11: Summary (narrative)
    summary = section_summary(signal_data)
    if summary:
        output.extend(summary)
        output.append("")

    # 12: Calendar
    cal = section_calendar()
    if cal:
        output.extend(cal)
        output.append("")

    output.append(f"{'═' * 50}")
    output.append(f"⏱ 生成: {datetime.now().strftime('%H:%M:%S')} | 数据仅供参考")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="美股简报 v3")
    parser.add_argument("--time", action="store_true", help="显示详细时间戳")
    args = parser.parse_args()

    print(format_briefing(show_time=args.time))


if __name__ == "__main__":
    main()
