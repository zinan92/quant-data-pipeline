#!/usr/bin/env python3
"""
美股完整简报 v4 — 增强版（参考A股简报格式）
=============================================
用法: python scripts/us_briefing_enhanced.py [--time]

模块:
1. 三大指数 + VIX         — 详细行情数据
2. 异动统计              — 涨跌幅榜、成交量异常
3. 盘中全程回顾表格       — 指数快照历史跟踪
4. 板块资金流TOP20       — 板块ETF资金流排行
5. Mag7 + 科技重点股     — 科技七巨头详细分析
6. 中概股/国际股         — ADR + 国际市场
7. 商品期货全景          — 贵金属/能源/农产品
8. 债券/利率曲线         — 收益率曲线分析
9. 外汇/货币信号         — 美元指数+主要货币对
10. 🧠 Morning分析        — 规则引擎，综合信号
11. 重点自选股异动        — 自定义关注股票
12. 重要快讯             — 实时新闻
13. 📝 盘后总结          — 市场回顾和明日展望

数据源: ashare API http://127.0.0.1:8000
"""

import sys
import json
import time
import argparse
import requests
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── Config ───────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOT_FILE = PROJECT_ROOT / "data" / "snapshots" / "us_stocks" / "today_us_snapshots.json"
SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)

API_BASE = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 5

# 美股重点关注股票 (可自定义)
US_WATCHLIST = [
    ("AAPL", "苹果"),
    ("MSFT", "微软"), 
    ("GOOGL", "谷歌"),
    ("AMZN", "亚马逊"),
    ("TSLA", "特斯拉"),
    ("NVDA", "英伟达"),
    ("META", "Meta"),
    ("NFLX", "奈飞"),
    ("AMD", "AMD"),
    ("INTC", "英特尔"),
    ("CRM", "Salesforce"),
    ("ORCL", "甲骨文"),
    ("BABA", "阿里巴巴"),
    ("PDD", "拼多多"),
    ("JD", "京东"),
    ("NIO", "蔚来"),
    ("XPEV", "小鹏"),
    ("LI", "理想"),
    ("BIDU", "百度"),
]


# ═══════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════
def fetch(endpoint: str) -> dict:
    """Fetch JSON from API. Returns {} on failure."""
    try:
        r = requests.get(f"{API_BASE}{endpoint}", timeout=(2, REQUEST_TIMEOUT))
        return r.json() if r.ok else {}
    except Exception:
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
    """Return colored icon for percentage change."""
    return "🟢" if pct >= 0 else "🔴"


def format_price(price: float, decimals: int = 2) -> str:
    """Format price with comma separator."""
    if price >= 1000:
        return f"{price:,.{decimals}f}"
    return f"{price:.{decimals}f}"


def format_volume(vol: float) -> str:
    """Format volume to human-readable."""
    if vol >= 1e9:
        return f"{vol / 1e9:.1f}B"
    elif vol >= 1e6:
        return f"{vol / 1e6:.0f}M"
    elif vol >= 1e3:
        return f"{vol / 1e3:.0f}K"
    return f"{vol:.0f}"


def format_market_cap(cap: float) -> str:
    """Format market cap to human-readable."""
    if cap >= 1e12:
        return f"{cap / 1e12:.2f}T"
    elif cap >= 1e9:
        return f"{cap / 1e9:.1f}B"
    elif cap >= 1e6:
        return f"{cap / 1e6:.0f}M"
    return ""


# ═══════════════════════════════════════════════════════════════
# 0. Save index snapshot (runs every time)
# ═══════════════════════════════════════════════════════════════
def save_us_index_snapshot(index_data: dict):
    """Save current US index data as a snapshot point."""
    try:
        if SNAPSHOT_FILE.exists():
            snapshots = json.loads(SNAPSHOT_FILE.read_text())
            if snapshots.get("date") != datetime.now().strftime("%Y-%m-%d"):
                snapshots = {"date": datetime.now().strftime("%Y-%m-%d"), "snapshots": []}
        else:
            snapshots = {"date": datetime.now().strftime("%Y-%m-%d"), "snapshots": []}

        now_time = datetime.now().strftime("%H:%M")
        # Avoid duplicate timestamps
        existing_times = {s["time"] for s in snapshots["snapshots"]}
        if now_time in existing_times:
            return

        snapshot_entry = {"time": now_time, "indexes": {}}
        
        quotes = index_data.get("quotes", [])
        for q in quotes:
            symbol = q["symbol"]
            snapshot_entry["indexes"][symbol] = {
                "name": q.get("cn_name") or q["name"],
                "price": q["price"],
                "pct": q["change_pct"],
                "volume": q.get("volume", 0),
            }

        snapshots["snapshots"].append(snapshot_entry)
        SNAPSHOT_FILE.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2))
    except Exception:
        pass  # Non-critical


# ═══════════════════════════════════════════════════════════════
# 1. 三大指数 + VIX （增强版）
# ═══════════════════════════════════════════════════════════════
@safe_section("三大指数")
def section_indexes(data: dict) -> list[str]:
    lines = ["📈 **三大指数 + VIX**"]
    quotes = data.get("quotes", [])
    if not quotes:
        return lines + ["  数据暂无"]

    # Separate VIX from main indexes
    main_indexes = []
    vix = None
    for q in quotes:
        if q["symbol"] == "^VIX":
            vix = q
        else:
            main_indexes.append(q)

    # Main indexes with detailed info
    for q in main_indexes:
        icon = pct_icon(q["change_pct"])
        name = q.get("cn_name") or q["name"]
        price = format_price(q["price"])
        change = q.get("change", 0)
        vol = q.get("volume", 0)
        
        vol_str = f" 成交:{format_volume(vol)}" if vol > 0 else ""
        high = q.get("day_high", 0)
        low = q.get("day_low", 0)
        range_str = ""
        if high > 0 and low > 0:
            range_str = f" 日内:{format_price(low)}-{format_price(high)}"
        
        lines.append(
            f"  {icon} {name}: {price} ({q['change_pct']:+.2f}%/"
            f"{change:+.2f}){vol_str}{range_str}"
        )

    # VIX with detailed interpretation
    if vix:
        vix_level = vix["price"]
        if vix_level >= 35:
            vix_emoji, vix_status = "🔴🔴", "极度恐慌"
        elif vix_level >= 30:
            vix_emoji, vix_status = "🔴", "严重恐慌"
        elif vix_level >= 25:
            vix_emoji, vix_status = "🟠", "高度恐慌"
        elif vix_level >= 20:
            vix_emoji, vix_status = "🟡", "警惕"
        elif vix_level >= 15:
            vix_emoji, vix_status = "⚖️", "正常"
        else:
            vix_emoji, vix_status = "🟢", "低波动"
        
        lines.append(
            f"  {vix_emoji} VIX恐慌指数: {vix_level:.2f} ({vix['change_pct']:+.2f}%) "
            f"— {vix_status}"
        )

    return lines


# ═══════════════════════════════════════════════════════════════
# 2. 异动统计（新增）
# ═══════════════════════════════════════════════════════════════
@safe_section("异动统计")
def section_market_movers() -> list[str]:
    """Get market movers - biggest gainers/losers by volume."""
    lines = ["⚡ **异动统计**"]
    
    # This would require additional API endpoints for US market movers
    # For now, we'll use sector data as proxy
    sector_data = fetch("/api/us-stock/sectors")
    sectors = sector_data.get("sectors", [])
    
    if not sectors:
        return lines + ["  数据暂无"]
    
    etf_sectors = []
    for s in sectors:
        if s.get("etf"):
            etf_sectors.append({
                "name": s["name_cn"],
                "symbol": s["etf"]["symbol"],
                "pct": s["etf"]["change_pct"],
                "volume": s["etf"].get("volume", 0),
            })
    
    if not etf_sectors:
        return lines + ["  ETF数据暂无"]
    
    # Sort by performance
    sorted_sectors = sorted(etf_sectors, key=lambda x: x["pct"], reverse=True)
    
    # Gainers and losers
    top_gainers = sorted_sectors[:3]
    top_losers = sorted_sectors[-3:]
    
    gainer_names = [f"{s['name']}({s['pct']:+.1f}%)" for s in top_gainers]
    loser_names = [f"{s['name']}({s['pct']:+.1f}%)" for s in top_losers]
    
    lines.append(f"  🟢 领涨板块: {' | '.join(gainer_names)}")
    lines.append(f"  🔴 领跌板块: {' | '.join(loser_names)}")
    
    # Breadth analysis
    up_count = sum(1 for s in etf_sectors if s["pct"] > 0)
    down_count = sum(1 for s in etf_sectors if s["pct"] < 0)
    flat_count = len(etf_sectors) - up_count - down_count
    
    lines.append(f"  📊 板块广度: {up_count}涨 / {down_count}跌 / {flat_count}平")
    
    return lines


# ═══════════════════════════════════════════════════════════════
# 3. 盘中全程回顾表格（参考A股格式）
# ═══════════════════════════════════════════════════════════════
@safe_section("盘中回顾")
def section_intraday_table() -> list[str]:
    if not SNAPSHOT_FILE.exists():
        return ["📋 **盘中全程回顾**", "  暂无快照数据"]

    data = json.loads(SNAPSHOT_FILE.read_text())
    snapshots = data.get("snapshots", [])
    if not snapshots:
        return ["📋 **盘中全程回顾**", "  暂无快照数据"]

    lines = [f"📋 **盘中全程回顾** ({data.get('date', '今日')})"]

    # Track highs/lows per index
    idx_tracker = {}
    
    # Table header
    lines.append(f"{'时间':>6} | {'标普500':>12} | {'纳斯达克':>12} | {'道琼斯':>12}")
    lines.append(f"{'─'*6} | {'─'*12} | {'─'*12} | {'─'*12}")

    for snap in snapshots:
        t = snap["time"]
        indexes = snap.get("indexes", {})

        cols = [f"{t:>6}"]
        for symbol in ["^GSPC", "^IXIC", "^DJI"]:
            idx = indexes.get(symbol, {})
            price = idx.get("price", 0)
            pct = idx.get("pct", 0)

            if price > 0:
                sign = "+" if pct >= 0 else ""
                col_str = f"{price:.0f}({sign}{pct:.2f}%)"

                # Track high/low
                if symbol not in idx_tracker:
                    idx_tracker[symbol] = {
                        "name": idx.get("name", symbol),
                        "high_price": price, "high_time": t, "high_pct": pct,
                        "low_price": price, "low_time": t, "low_pct": pct,
                    }
                else:
                    tr = idx_tracker[symbol]
                    if price > tr["high_price"]:
                        tr["high_price"] = price
                        tr["high_time"] = t
                        tr["high_pct"] = pct
                    if price < tr["low_price"]:
                        tr["low_price"] = price
                        tr["low_time"] = t
                        tr["low_pct"] = pct
            else:
                col_str = "—"

            cols.append(f"{col_str:>12}")
        
        lines.append(" | ".join(cols))

    # High/Low summary
    if idx_tracker:
        lines.append("")
        lines.append("📍 **高低点:**")
        for symbol in ["^GSPC", "^IXIC", "^DJI"]:
            if symbol in idx_tracker:
                tr = idx_tracker[symbol]
                lines.append(
                    f"  {tr['name']}: "
                    f"高点 {tr['high_price']:.0f}({tr['high_pct']:+.2f}%) @{tr['high_time']} | "
                    f"低点 {tr['low_price']:.0f}({tr['low_pct']:+.2f}%) @{tr['low_time']}"
                )

    return lines


# ═══════════════════════════════════════════════════════════════
# 4. 板块资金流TOP20（增强版）
# ═══════════════════════════════════════════════════════════════
@safe_section("板块资金流")
def section_sector_flow(data: dict) -> tuple[list[str], list]:
    lines = ["💰 **板块ETF资金流TOP20**"]
    sectors = data.get("sectors", [])
    
    if not sectors:
        return lines + ["  数据暂无"], []
    
    # Extract ETF data
    etf_data = []
    for s in sectors:
        if s.get("etf"):
            etf = s["etf"]
            etf_data.append({
                "name": s["name_cn"],
                "symbol": etf["symbol"],
                "pct": etf["change_pct"],
                "price": etf["price"],
                "volume": etf.get("volume", 0),
                "market_cap": etf.get("market_cap", 0),
                "avg_volume": etf.get("avg_volume", 0),
            })
    
    if not etf_data:
        return lines + ["  ETF数据暂无"], []
    
    # Sort by performance (proxy for flow)
    sorted_etfs = sorted(etf_data, key=lambda x: x["pct"], reverse=True)
    
    total = len(sorted_etfs)
    net_up = sum(1 for e in sorted_etfs if e["pct"] > 0)
    net_down = total - net_up
    
    lines.append(f"共{total}个板块ETF | {net_up}个上涨 | {net_down}个下跌")
    lines.append("")
    
    # Top performers
    for i, etf in enumerate(sorted_etfs[:15], 1):
        icon = pct_icon(etf["pct"])
        vol_ratio = ""
        if etf["avg_volume"] > 0 and etf["volume"] > 0:
            ratio = etf["volume"] / etf["avg_volume"]
            if ratio > 2:
                vol_ratio = f" 🔥{ratio:.1f}x量"
            elif ratio > 1.5:
                vol_ratio = f" 📈{ratio:.1f}x量"
        
        lines.append(
            f"  {i:>2}. {etf['name']}({etf['symbol']}) {etf['pct']:+.2f}% "
            f"${format_price(etf['price'])} {format_volume(etf['volume'])}{vol_ratio}"
        )
    
    # Bottom performers
    if len(sorted_etfs) > 15:
        lines.append("")
        lines.append("  📉 **领跌板块:**")
        bottom_5 = sorted_etfs[-5:]
        for etf in bottom_5:
            icon = pct_icon(etf["pct"])
            lines.append(
                f"  {icon} {etf['name']}({etf['symbol']}) {etf['pct']:+.2f}%"
            )
    
    return lines, sorted_etfs


# ═══════════════════════════════════════════════════════════════
# 5. Mag7 + 科技重点股（增强版）
# ═══════════════════════════════════════════════════════════════
@safe_section("科技重点股")
def section_tech_detailed(mag7_data: dict) -> tuple[list[str], dict]:
    lines = ["💎 **Mag7 + 科技重点股**"]
    quotes = mag7_data.get("quotes", [])
    if not quotes:
        return lines + ["  数据暂无"], {}

    # Sort by performance  
    sorted_quotes = sorted(quotes, key=lambda q: q["change_pct"], reverse=True)
    
    # Calculate metrics
    avg_pct = sum(q["change_pct"] for q in sorted_quotes) / len(sorted_quotes)
    total_cap = sum(q.get("market_cap", 0) for q in sorted_quotes)
    up_count = sum(1 for q in sorted_quotes if q["change_pct"] > 0)
    down_count = len(sorted_quotes) - up_count
    
    lines.append(f"Mag7状态: {up_count}涨/{down_count}跌 | 平均涨幅: {avg_pct:+.2f}%")
    lines.append(f"总市值: {format_market_cap(total_cap)}")
    lines.append("")
    
    # Detailed breakdown
    for q in sorted_quotes:
        icon = pct_icon(q["change_pct"])
        name = q.get("cn_name") or q["symbol"]
        cap_str = format_market_cap(q.get("market_cap", 0))
        vol_str = format_volume(q.get("volume", 0))
        
        # P/E ratio if available
        pe_str = ""
        if q.get("pe_ratio"):
            pe_str = f" PE:{q['pe_ratio']:.1f}"
        
        lines.append(
            f"  {icon} {name}({q['symbol']}): ${format_price(q['price'])} "
            f"({q['change_pct']:+.2f}%) [{cap_str}] 量:{vol_str}{pe_str}"
        )
    
    # Performance analysis
    lines.append("")
    best = sorted_quotes[0]
    worst = sorted_quotes[-1]
    spread = best["change_pct"] - worst["change_pct"]
    
    if spread > 5:
        lines.append(f"⚠️ 分化严重: {best.get('cn_name', best['symbol'])} vs {worst.get('cn_name', worst['symbol'])} 差距{spread:.1f}%")
    elif avg_pct > 1:
        lines.append("🟢 科技股整体强势，市场风险偏好高")
    elif avg_pct < -1:
        lines.append("🔴 科技股整体疲弱，成长股承压")
    else:
        lines.append("⚖️ 科技股表现中性")
    
    signal_data = {
        "avg_pct": avg_pct,
        "up_count": up_count,
        "down_count": down_count,
        "spread": spread,
        "total_cap": total_cap,
    }
    
    return lines, signal_data


# ═══════════════════════════════════════════════════════════════
# 10. Morning分析（综合规则引擎）
# ═══════════════════════════════════════════════════════════════
@safe_section("Morning分析")
def section_morning_analysis(
    index_data: dict,
    sector_data: list,
    tech_data: dict,
    commodity_data: dict,
    bond_data: dict,
    forex_data: dict,
) -> tuple[list[str], dict]:
    """Comprehensive rule-based analysis following A-share format."""
    lines = ["🧠 **Morning分析**"]
    
    # Extract key metrics
    quotes = index_data.get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}
    
    sp500 = quote_map.get("^GSPC", {})
    nasdaq = quote_map.get("^IXIC", {})
    dow = quote_map.get("^DJI", {})
    vix_q = quote_map.get("^VIX", {})
    
    sp_pct = sp500.get("change_pct", 0)
    nas_pct = nasdaq.get("change_pct", 0)
    dow_pct = dow.get("change_pct", 0)
    vix_level = vix_q.get("price", 0)
    
    # ── 市场定性 ──
    lines.append("")
    lines.append("**市场定性:**")
    
    # Style rotation: Value vs Growth (Dow vs Nasdaq)
    style_scissor = dow_pct - nas_pct
    if style_scissor > 1.0:
        market_tone = "⚠️ Value > Growth (道指强、纳指弱) → Risk OFF模式"
    elif style_scissor < -1.0:
        market_tone = "🚀 Growth > Value (纳指强、道指弱) → Risk ON模式"
    elif sp_pct > 0.5 and nas_pct > 0.5:
        market_tone = "🟢 普涨行情（指数齐升）"
    elif sp_pct < -0.5 and nas_pct < -0.5:
        market_tone = "🔴 普跌行情（指数齐跌）"
    else:
        market_tone = "⚖️ 中性震荡"
    
    lines.append(f"  {market_tone}")
    lines.append(f"  道指 {dow_pct:+.2f}% vs 纳指 {nas_pct:+.2f}% → 风格剪刀差 {style_scissor:+.2f}%")
    
    # VIX fear gauge
    if vix_level > 0:
        if vix_level >= 30:
            vix_signal = "🔴 VIX极度恐慌区（≥30），市场剧烈波动"
        elif vix_level >= 20:
            vix_signal = "🟡 VIX警戒区（20-30），投资者紧张"
        else:
            vix_signal = "🟢 VIX舒适区（<20），市场相对平静"
        lines.append(f"  {vix_signal}")
    
    # ── 板块轮动 ──
    lines.append("")
    lines.append("**板块轮动:**")
    if sector_data:
        top3_up = sector_data[:3]
        top3_down = sector_data[-3:]
        
        up_names = " / ".join([f"{s['name']}({s['pct']:+.1f}%)" for s in top3_up])
        down_names = " / ".join([f"{s['name']}({s['pct']:+.1f}%)" for s in top3_down])
        
        lines.append(f"  🔺 主力流入: {up_names}")
        lines.append(f"  🔻 主力流出: {down_names}")
        
        # Sector breadth
        up_sectors = sum(1 for s in sector_data if s["pct"] > 0)
        total_sectors = len(sector_data)
        breadth_pct = up_sectors / total_sectors * 100 if total_sectors > 0 else 0
        lines.append(f"  📊 板块广度: {up_sectors}/{total_sectors} ({breadth_pct:.0f}%上涨)")
    else:
        lines.append("  数据暂无")
    
    # ── 关键信号 ──
    lines.append("")
    lines.append("**关键信号:**")
    
    # Signal 1: VIX vs Market direction
    if vix_level > 0:
        vix_direction = vix_q.get("change_pct", 0)
        if vix_direction > 5 and sp_pct < 0:
            lines.append(f"  • VIX飙升+市场下跌 → 恐慌性抛售")
        elif vix_direction < -5 and sp_pct > 0:
            lines.append(f"  • VIX回落+市场上涨 → 风险偏好回升")
        else:
            lines.append(f"  • VIX {vix_level:.1f} ({vix_direction:+.1f}%) vs 标普 {sp_pct:+.2f}%")
    
    # Signal 2: Tech leadership
    if tech_data:
        mag7_avg = tech_data.get("avg_pct", 0)
        mag7_spread = tech_data.get("spread", 0)
        if mag7_spread > 5:
            lines.append(f"  • Mag7分化严重（价差{mag7_spread:.1f}%）→ 个股驱动")
        elif mag7_avg > sp_pct + 1:
            lines.append(f"  • 科技股跑赢大盘{mag7_avg - sp_pct:.1f}% → 成长主导")
        elif mag7_avg < sp_pct - 1:
            lines.append(f"  • 科技股跑输大盘{sp_pct - mag7_avg:.1f}% → 权重拖累")
    
    # ── 🛡️ 避险指标 ──
    lines.append("")
    lines.append("**🛡️ 避险指标:**")
    
    # Get commodity data
    commodities = commodity_data.get("commodities", [])
    commodity_map = {c["symbol"]: c for c in commodities}
    gold = commodity_map.get("GC=F")
    treasury = None
    
    # Get bond data
    bonds = bond_data.get("bonds", [])
    bond_map = {b["symbol"]: b for b in bonds}
    tnx = bond_map.get("^TNX")  # 10Y Treasury
    
    # Get USD data
    forex = forex_data.get("forex", [])
    fx_map = {f["symbol"]: f for f in forex}
    dxy = fx_map.get("DX-Y.NYB")  # Dollar Index
    
    safe_haven_signals = []
    safe_haven_count = 0
    
    # Gold signal
    if gold:
        gold_pct = gold.get("change_pct", 0)
        if gold_pct > 1.5:
            safe_haven_signals.append(f"🟢黄金 {gold_pct:+.1f}% (避险买入)")
            safe_haven_count += 1
        elif gold_pct < -1.5:
            safe_haven_signals.append(f"🔴黄金 {gold_pct:+.1f}% (风险偏好)")
        else:
            safe_haven_signals.append(f"⚖️黄金 {gold_pct:+.1f}% (中性)")
    
    # Treasury signal (inverse of yield)
    if tnx:
        yield_pct = tnx.get("change_pct", 0)
        if yield_pct < -2:  # Yield down = bond up = safe haven
            safe_haven_signals.append(f"🟢美债 (收益率{yield_pct:+.1f}%，债券上涨)")
            safe_haven_count += 1
        elif yield_pct > 2:   # Yield up = bond down = risk on
            safe_haven_signals.append(f"🔴美债 (收益率{yield_pct:+.1f}%，债券下跌)")
        else:
            safe_haven_signals.append(f"⚖️美债 (收益率{yield_pct:+.1f}%)")
    
    # USD signal
    if dxy:
        usd_pct = dxy.get("change_pct", 0)
        if usd_pct > 0.5:
            safe_haven_signals.append(f"🟢美元 {usd_pct:+.1f}% (避险资金)")
            safe_haven_count += 1
        elif usd_pct < -0.5:
            safe_haven_signals.append(f"🔴美元 {usd_pct:+.1f}% (风险偏好)")
        else:
            safe_haven_signals.append(f"⚖️美元 {usd_pct:+.1f}% (中性)")
    
    lines.append(f"  {' | '.join(safe_haven_signals)}")
    
    if safe_haven_count >= 2:
        lines.append(f"  ⚠️ {safe_haven_count}/3避险资产同时上涨 → **风险规避情绪浓厚**")
    elif safe_haven_count == 0:
        lines.append(f"  🟢 避险资产未见流入 → 市场风险偏好良好")
    else:
        lines.append(f"  📊 避险信号中性（{safe_haven_count}/3）")
    
    # ── 📏 趋势强度 ──
    lines.append("")
    lines.append("**📏 趋势强度:**")
    
    if sector_data and len(sector_data) > 0:
        top1_sector = sector_data[0]
        top1_pct = abs(top1_sector["pct"])
        top1_name = top1_sector["name"]
        
        if top1_pct >= 3:
            trend_strength = "🔥 强趋势"
            trend_desc = "板块分化明显，主线清晰"
        elif top1_pct >= 1.5:
            trend_strength = "📊 中等趋势"
            trend_desc = "有方向但力度一般"
        else:
            trend_strength = "😶 弱趋势"
            trend_desc = "板块轮动不明显"
        
        lines.append(f"  领涨板块 {top1_name}: {top1_sector['pct']:+.2f}% → {trend_strength}（{trend_desc}）")
    
    # ── 操作建议 ──
    lines.append("")
    lines.append("**操作建议:**")
    
    # Scoring system
    bullish_signals = 0
    bearish_signals = 0
    
    # Index signals
    if sp_pct > 0.3: bullish_signals += 1
    if sp_pct < -0.3: bearish_signals += 1
    if nas_pct > 0.3: bullish_signals += 1
    if nas_pct < -0.3: bearish_signals += 1
    
    # VIX signals
    if vix_level > 0:
        if vix_level < 15: bullish_signals += 1
        elif vix_level >= 25: bearish_signals += 2
        elif vix_level >= 20: bearish_signals += 1
    
    # Tech signals
    if tech_data:
        mag7_avg = tech_data.get("avg_pct", 0)
        if mag7_avg > 1: bullish_signals += 1
        elif mag7_avg < -1: bearish_signals += 1
    
    # Safe haven signals
    if safe_haven_count >= 2: bearish_signals += 1
    elif safe_haven_count == 0: bullish_signals += 1
    
    # Sector breadth
    if sector_data:
        up_ratio = sum(1 for s in sector_data if s["pct"] > 0) / len(sector_data)
        if up_ratio > 0.7: bullish_signals += 1
        elif up_ratio < 0.3: bearish_signals += 1
    
    # Generate advice
    if bullish_signals >= 4:
        advice = "✅ 多头占优，可积极参与强势板块，关注科技和成长股"
    elif bearish_signals >= 4:
        advice = "🛑 空头占优，建议减仓观望，关注防御性板块"
    elif bullish_signals >= 3 and bearish_signals <= 1:
        advice = "🟢 偏多格局，可适当参与领涨板块，控制风险"
    elif bearish_signals >= 3 and bullish_signals <= 1:
        advice = "🟡 偏弱格局，轻仓为主，关注避险资产"
    elif abs(style_scissor) > 1.5:
        advice = "🔄 风格轮动剧烈，精选个股，快进快出"
    else:
        advice = "⚖️ 震荡格局，保持灵活，等待方向明确"
    
    lines.append(f"  {advice}")
    lines.append(f"  (多头信号: {bullish_signals} | 空头信号: {bearish_signals})")
    
    # Collect signal data
    signal_data = {
        "sp_pct": sp_pct,
        "nas_pct": nas_pct,
        "dow_pct": dow_pct,
        "vix_level": vix_level,
        "style_scissor": style_scissor,
        "market_tone": market_tone,
        "safe_haven_count": safe_haven_count,
        "trend_strength": trend_strength if 'trend_strength' in locals() else "未知",
        "bullish_signals": bullish_signals,
        "bearish_signals": bearish_signals,
        "advice": advice,
    }
    
    return lines, signal_data


# ═══════════════════════════════════════════════════════════════
# 11. 重点自选股异动（新增）
# ═══════════════════════════════════════════════════════════════
@safe_section("自选股异动")
def section_us_watchlist() -> list[str]:
    lines = ["⭐ **重点自选股异动**"]
    
    # This would require implementing a US stock quote API
    # For now, we'll use a placeholder
    lines.append("  功能开发中，需要实现美股实时行情API")
    
    # Future implementation:
    # 1. Get quotes for US_WATCHLIST symbols
    # 2. Sort by performance 
    # 3. Show top gainers/losers
    # 4. Include volume analysis
    
    return lines


# ═══════════════════════════════════════════════════════════════
# 12. 重要快讯（增强版）
# ═══════════════════════════════════════════════════════════════
@safe_section("快讯")
def section_enhanced_news(data: dict) -> list[str]:
    lines = ["📰 **重要快讯**"]
    news_list = data.get("news", [])
    if isinstance(data, list):
        news_list = data
    if not news_list:
        return lines + ["  暂无快讯"]

    # Categorize news by importance/type
    market_news = []
    fed_news = []
    earnings_news = []
    other_news = []
    
    for item in news_list[:10]:
        title = item.get("title", "").lower()
        if any(keyword in title for keyword in ["fed", "federal", "powell", "interest", "rate"]):
            fed_news.append(item)
        elif any(keyword in title for keyword in ["earnings", "报告", "财报", "revenue"]):
            earnings_news.append(item) 
        elif any(keyword in title for keyword in ["market", "stock", "index", "trading"]):
            market_news.append(item)
        else:
            other_news.append(item)
    
    # Display categorized news
    categories = [
        ("🏛️ 美联储政策", fed_news),
        ("📊 市场动态", market_news),
        ("💰 财报信息", earnings_news),
        ("📈 其他", other_news),
    ]
    
    shown_count = 0
    for category_name, news_items in categories:
        if news_items and shown_count < 8:
            lines.append(f"  {category_name}:")
            for item in news_items[:3]:  # Max 3 per category
                if shown_count >= 8:
                    break
                title = item.get("title", "")[:70]
                t = item.get("time", "")
                if t and len(t) >= 5:
                    if len(t) >= 16 and "T" in t:
                        t = t[11:16]
                    elif ":" in t:
                        t = t[:5]
                prefix = f"[{t}] " if t else ""
                lines.append(f"    • {prefix}{title}")
                shown_count += 1
    
    return lines


# ═══════════════════════════════════════════════════════════════
# 13. 盘后总结（新增，模仿A股格式）
# ═══════════════════════════════════════════════════════════════
@safe_section("盘后总结")
def section_market_summary(signal_data: dict, sector_data: list) -> list[str]:
    """Generate narrative summary based on signal data."""
    if not signal_data:
        return []
    
    lines = ["═══ 📝 总结 ═══", ""]
    
    sp_pct = signal_data.get("sp_pct", 0)
    nas_pct = signal_data.get("nas_pct", 0) 
    dow_pct = signal_data.get("dow_pct", 0)
    vix_level = signal_data.get("vix_level", 0)
    style_scissor = signal_data.get("style_scissor", 0)
    safe_haven_count = signal_data.get("safe_haven_count", 0)
    bullish_signals = signal_data.get("bullish_signals", 0)
    bearish_signals = signal_data.get("bearish_signals", 0)
    
    # ── Market character assessment ──
    if safe_haven_count >= 2 and vix_level > 25:
        day_type = "extreme_risk_off"
    elif vix_level > 30:
        day_type = "panic_day"
    elif abs(style_scissor) > 2:
        day_type = "style_rotation"
    elif bullish_signals >= 4:
        day_type = "bullish_day"
    elif bearish_signals >= 4:
        day_type = "bearish_day" 
    else:
        day_type = "mixed_day"
    
    # ── Headline ──
    sp_sign = "涨" if sp_pct >= 0 else "跌"
    nas_sign = "涨" if nas_pct >= 0 else "跌"
    
    if day_type == "extreme_risk_off":
        lines.append(
            f"今日三大避险资产同时上涨，VIX达{vix_level:.1f}，"
            f"标普{sp_sign}{abs(sp_pct):.2f}%的表现掩盖不了市场的**极度恐慌情绪**。"
        )
    elif day_type == "panic_day":
        lines.append(f"VIX恐慌指数飙升至{vix_level:.1f}，市场陷入恐慌性抛售。")
    elif day_type == "style_rotation":
        stronger = "价值股(道指)" if style_scissor > 0 else "成长股(纳指)"
        weaker = "成长股(纳指)" if style_scissor > 0 else "价值股(道指)"
        lines.append(
            f"今日最显著特征是风格剧烈轮动：{stronger}大幅跑赢{weaker}，"
            f"剪刀差达{abs(style_scissor):.2f}%。"
        )
    elif day_type == "bullish_day":
        lines.append(
            f"标普{sp_sign}{abs(sp_pct):.2f}%，纳指{nas_sign}{abs(nas_pct):.2f}%，"
            f"多重信号显示市场风险偏好高涨。"
        )
    elif day_type == "bearish_day":
        lines.append(
            f"三大指数全线收{sp_sign}，空头信号占主导，投资者情绪谨慎。"
        )
    else:
        lines.append(
            f"标普{sp_sign}{abs(sp_pct):.2f}%，纳指{nas_sign}{abs(nas_pct):.2f}%，"
            f"市场方向性不明确。"
        )
    
    lines.append("")
    
    # ── Key themes ──
    if sector_data and len(sector_data) > 0:
        best_sector = sector_data[0]
        worst_sector = sector_data[-1]
        sector_spread = best_sector["pct"] - worst_sector["pct"]
        
        if sector_spread > 4:
            lines.append(
                f"板块分化严重：{best_sector['name']}领涨({best_sector['pct']:+.2f}%)，"
                f"{worst_sector['name']}垫底({worst_sector['pct']:+.2f}%)，价差{sector_spread:.1f}%。"
            )
        elif best_sector["pct"] > 2:
            lines.append(f"今日亮点：{best_sector['name']}强势上涨{best_sector['pct']:+.2f}%。")
    
    # ── Tomorrow focus ──
    lines.append("")
    lines.append("**明日关注：**")
    focus_points = []
    
    if vix_level > 25:
        focus_points.append("VIX能否从恐慌区回落")
    if abs(style_scissor) > 1.5:
        focus_points.append("价值成长风格轮动是否持续")
    if safe_haven_count >= 2:
        focus_points.append("避险资产流入是否减弱")
    if bearish_signals >= 3:
        focus_points.append("空头信号能否缓解")
    
    # Add market-specific focus
    if not focus_points:
        focus_points.append("关键支撑阻力位表现")
        focus_points.append("科技股与大盘走势分化")
    
    for fp in focus_points:
        lines.append(f"  • {fp}")
    
    return lines


# ═══════════════════════════════════════════════════════════════
# Other existing sections (simplified for brevity)
# ═══════════════════════════════════════════════════════════════

@safe_section("中概股")
def section_china_adr(data: dict) -> list[str]:
    # ... existing implementation
    lines = ["🇨🇳 **中概股 ADR**"]
    quotes = data.get("quotes", [])
    if not quotes:
        return lines + ["  数据暂无"]

    sorted_q = sorted(quotes, key=lambda q: q["change_pct"], reverse=True)
    avg_pct = sum(q["change_pct"] for q in sorted_q) / len(sorted_q) if sorted_q else 0

    for q in sorted_q:
        icon = pct_icon(q["change_pct"])
        name = q.get("cn_name") or q["symbol"]
        vol_str = f" 量:{format_volume(q.get('volume', 0))}" if q.get("volume") else ""
        lines.append(
            f"  {icon} {name}({q['symbol']}): ${format_price(q['price'])} "
            f"({q['change_pct']:+.2f}%){vol_str}"
        )

    icon_avg = pct_icon(avg_pct)
    lines.append(f"  {icon_avg} 中概股平均涨幅: {avg_pct:+.2f}%")
    return lines


@safe_section("商品期货")
def section_commodities(data: dict) -> list[str]:
    # ... existing implementation with enhancements
    lines = ["📦 **商品期货全景**"]
    commodities = data.get("commodities", [])
    if not commodities:
        return lines + ["  数据暂无"]

    # Group by category
    precious = []
    energy = []
    industrial = []
    
    for c in commodities:
        symbol = c["symbol"]
        entry = {
            "cn_name": c.get("cn_name") or c["name"],
            "price": c["price"],
            "pct": c.get("change_pct", 0),
            "volume": c.get("volume", 0),
        }
        if symbol in ("GC=F", "SI=F"):
            precious.append(entry)
        elif symbol in ("CL=F", "BZ=F", "NG=F"):
            energy.append(entry)
        elif symbol in ("HG=F",):
            industrial.append(entry)
        else:
            energy.append(entry)

    categories = [
        ("贵金属", precious),
        ("能源", energy), 
        ("工业金属", industrial),
    ]
    
    for cat_name, items in categories:
        if items:
            parts = []
            for c in items:
                icon = pct_icon(c["pct"])
                vol_str = f" 量:{format_volume(c['volume'])}" if c["volume"] > 0 else ""
                parts.append(f"{icon}{c['cn_name']} ${format_price(c['price'])} ({c['pct']:+.2f}%){vol_str}")
            lines.append(f"  {cat_name}: {' | '.join(parts)}")

    return lines


@safe_section("债券收益率")
def section_bonds(data: dict) -> list[str]:
    # ... existing implementation
    lines = ["🏦 **美债收益率曲线**"]
    bonds = data.get("bonds", [])
    if not bonds:
        return lines + ["  数据暂无"]

    # Show yield curve
    for b in bonds:
        icon = pct_icon(b.get("change_pct", 0))
        name = b.get("cn_name") or b["name"]
        lines.append(f"  {icon} {name}: {b['price']:.3f}% ({b.get('change_pct', 0):+.3f}%)")

    # Yield curve analysis
    bond_map = {b["symbol"]: b for b in bonds}
    tnx = bond_map.get("^TNX")  # 10Y
    fvx = bond_map.get("^FVX")  # 5Y
    tyx = bond_map.get("^TYX")  # 30Y
    
    if tnx and fvx:
        spread_10_5 = tnx["price"] - fvx["price"]
        curve_status = "正常" if spread_10_5 > 0 else "⚠️ 倒挂"
        lines.append(f"  📐 收益率曲线: 10Y-5Y = {spread_10_5:+.3f}% ({curve_status})")
    
    if tyx and tnx:
        spread_30_10 = tyx["price"] - tnx["price"]
        lines.append(f"  📐 长端利差: 30Y-10Y = {spread_30_10:+.3f}%")

    return lines


@safe_section("外汇")
def section_forex(data: dict) -> list[str]:
    # ... existing implementation
    lines = ["💵 **美元指数 / 主要货币**"]
    forex = data.get("forex", [])
    if not forex:
        return lines + ["  数据暂无"]

    for f in forex:
        icon = pct_icon(f.get("change_pct", 0))
        name = f.get("cn_name") or f["name"]
        lines.append(f"  {icon} {name}: {f['price']:.3f} ({f.get('change_pct', 0):+.2f}%)")

    return lines


# ═══════════════════════════════════════════════════════════════
# Main assembly function
# ═══════════════════════════════════════════════════════════════
def format_enhanced_briefing(show_time: bool = False) -> str:
    now = datetime.now()
    time_label = now.strftime("%Y-%m-%d %H:%M")
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]

    output = []
    output.append(f"{'═' * 50}")
    output.append(f"🇺🇸 **美股完整简报** ({time_label} {weekday_cn})")
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
        "news": "/api/news/latest?limit=10",
    }
    
    results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
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
    if index_data:
        save_us_index_snapshot(index_data)

    # ── Section 1: Indexes ──
    output.extend(section_indexes(index_data))
    output.append("")

    # ── Section 2: Market movers ──
    output.extend(section_market_movers())
    output.append("")

    # ── Section 3: Intraday table ──
    output.extend(section_intraday_table()) 
    output.append("")

    # ── Section 4: Sector flow ──
    sector_flow_result = section_sector_flow(sector_data)
    if isinstance(sector_flow_result, tuple):
        sector_lines, processed_sectors = sector_flow_result
        output.extend(sector_lines)
    else:
        output.extend(sector_flow_result)
        processed_sectors = []
    output.append("")

    # ── Section 5: Tech detailed ──
    tech_result = section_tech_detailed(mag7_data)
    if isinstance(tech_result, tuple):
        tech_lines, tech_signal_data = tech_result
        output.extend(tech_lines)
    else:
        output.extend(tech_result)
        tech_signal_data = {}
    output.append("")

    # ── Section 6: China ADR ──
    output.extend(section_china_adr(adr_data))
    output.append("")

    # ── Section 7: Commodities ──
    output.extend(section_commodities(commodity_data))
    output.append("")

    # ── Section 8: Bonds ──
    output.extend(section_bonds(bond_data))
    output.append("")

    # ── Section 9: Forex ──
    output.extend(section_forex(forex_data))
    output.append("")

    # ── Section 10: Morning Analysis ──
    analysis_result = section_morning_analysis(
        index_data, processed_sectors, tech_signal_data,
        commodity_data, bond_data, forex_data
    )
    if isinstance(analysis_result, tuple):
        analysis_lines, signal_data = analysis_result
        output.extend(analysis_lines)
    else:
        output.extend(analysis_result)
        signal_data = {}
    output.append("")

    # ── Section 11: US Watchlist ──
    output.extend(section_us_watchlist())
    output.append("")

    # ── Section 12: Enhanced News ──
    output.extend(section_enhanced_news(news_data))
    output.append("")

    # ── Section 13: Market Summary ──
    summary_lines = section_market_summary(signal_data, processed_sectors)
    if summary_lines:
        output.extend(summary_lines)
        output.append("")

    output.append(f"{'═' * 50}")
    output.append(f"⏱ 生成: {datetime.now().strftime('%H:%M:%S')} | 数据仅供参考")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="美股完整简报 v4 增强版")
    parser.add_argument("--time", action="store_true", help="显示详细时间戳")
    args = parser.parse_args()

    print(format_enhanced_briefing(show_time=args.time))


if __name__ == "__main__":
    main()