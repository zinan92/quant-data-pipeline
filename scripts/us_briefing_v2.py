#!/usr/bin/env python3
"""
美股简报 v3 — 完整版（模块化 + 规则引擎分析）
=============================================
用法: python scripts/us_briefing_v2.py [--time]

模块:
1. 三大指数 + VIX          — /api/us-stock/indexes
2. 板块表现                — /api/us-stock/sectors
3. Mag7 + 重点个股         — /api/us-stock/mag7
4. 中概股 ADR              — /api/us-stock/china-adr
5. 商品（黄金白银原油铜）     — /api/us-stock/commodities
6. 债券收益率（10Y/5Y/30Y） — /api/us-stock/bonds
7. 美元指数/外汇           — /api/us-stock/forex
8. 重要新闻/快讯           — /api/news/latest
9. 🧠 Wendy分析           — 规则引擎，纯确定性
10. 经济日历（如有）         — /api/us-stock/calendar

数据源: ashare API http://127.0.0.1:8000
"""

import sys
import argparse
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── Config ───────────────────────────────────────────────────
API_BASE = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 5


# ═══════════════════════════════════════════════════════════════
# Helper: safe fetch wrapper
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
# 1. 三大指数 + VIX
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
        vix_level = vix["price"]
        vix_emoji = "🟢"
        if vix_level >= 30:
            vix_emoji = "🔴🔴"
        elif vix_level >= 25:
            vix_emoji = "🔴"
        elif vix_level >= 20:
            vix_emoji = "🟡"
        lines.append(f"  {vix_emoji} VIX恐慌指数: {vix_level:.2f} ({vix['change_pct']:+.2f}%)")

    return lines


# ═══════════════════════════════════════════════════════════════
# 2. 板块表现（按涨跌排序）
# ═══════════════════════════════════════════════════════════════
@safe_section("板块表现")
def section_sectors(data: dict) -> list[str]:
    lines = ["🏛️ **板块表现**"]
    sectors = data.get("sectors", [])
    if not sectors:
        return lines + ["  数据暂无"]

    # Filter sectors that have ETF data
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

    # Leaders
    top = etf_sectors[:3]
    bot = etf_sectors[-3:]

    lines.append("  📈 领涨:")
    for s in top:
        icon = pct_icon(s["pct"])
        lines.append(f"    {icon} {s['name_cn']}({s['symbol']}) {s['pct']:+.2f}%")

    lines.append("  📉 领跌:")
    for s in bot:
        icon = pct_icon(s["pct"])
        lines.append(f"    {icon} {s['name_cn']}({s['symbol']}) {s['pct']:+.2f}%")

    # Breadth: count up vs down
    up_count = sum(1 for s in etf_sectors if s["pct"] > 0)
    down_count = sum(1 for s in etf_sectors if s["pct"] < 0)
    flat_count = len(etf_sectors) - up_count - down_count
    lines.append(f"  板块广度: {up_count}涨 / {down_count}跌 / {flat_count}平")

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

    # Calculate average
    avg_pct = sum(q["change_pct"] for q in sorted_q) / len(sorted_q) if sorted_q else 0
    total_cap = sum(q.get("market_cap", 0) for q in sorted_q)

    for q in sorted_q:
        icon = pct_icon(q["change_pct"])
        name = q.get("cn_name") or q["symbol"]
        cap_str = format_market_cap(q.get("market_cap", 0))
        cap_display = f" [{cap_str}]" if cap_str else ""
        lines.append(
            f"  {icon} {name}({q['symbol']}): ${format_price(q['price'])} "
            f"({q['change_pct']:+.2f}%){cap_display}"
        )

    icon_avg = pct_icon(avg_pct)
    total_cap_str = format_market_cap(total_cap)
    lines.append(f"  {icon_avg} Mag7均涨幅: {avg_pct:+.2f}% | 总市值: {total_cap_str}")

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
    avg_pct = sum(q["change_pct"] for q in sorted_q) / len(sorted_q) if sorted_q else 0

    for q in sorted_q:
        icon = pct_icon(q["change_pct"])
        name = q.get("cn_name") or q["symbol"]
        lines.append(
            f"  {icon} {name}({q['symbol']}): ${format_price(q['price'])} "
            f"({q['change_pct']:+.2f}%)"
        )

    icon_avg = pct_icon(avg_pct)
    lines.append(f"  {icon_avg} 中概股均涨幅: {avg_pct:+.2f}%")

    return lines


# ═══════════════════════════════════════════════════════════════
# 5. 商品（黄金白银原油铜天然气）
# ═══════════════════════════════════════════════════════════════
@safe_section("商品")
def section_commodities(data: dict) -> list[str]:
    lines = ["📦 **商品期货**"]
    commodities = data.get("commodities", [])
    if not commodities:
        return lines + ["  数据暂无"]

    # Group by type for readability
    precious = []  # gold, silver
    energy = []    # oil, gas
    industrial = []  # copper

    for c in commodities:
        symbol = c["symbol"]
        entry = {
            "cn_name": c.get("cn_name") or c["name"],
            "price": c["price"],
            "pct": c.get("change_pct", 0),
            "change": c.get("change", 0),
        }
        if symbol in ("GC=F", "SI=F"):
            precious.append(entry)
        elif symbol in ("CL=F", "BZ=F", "NG=F"):
            energy.append(entry)
        elif symbol in ("HG=F",):
            industrial.append(entry)
        else:
            energy.append(entry)  # fallback

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

    return lines


# ═══════════════════════════════════════════════════════════════
# 6. 债券收益率
# ═══════════════════════════════════════════════════════════════
@safe_section("债券")
def section_bonds(data: dict) -> list[str]:
    lines = ["🏦 **美债收益率**"]
    bonds = data.get("bonds", [])
    if not bonds:
        return lines + ["  数据暂无"]

    # Map by symbol for analysis
    bond_map = {}
    for b in bonds:
        bond_map[b["symbol"]] = b

    for b in bonds:
        icon = pct_icon(b.get("change_pct", 0))
        name = b.get("cn_name") or b["name"]
        lines.append(f"  {icon} {name}: {b['price']:.3f}% ({b.get('change_pct', 0):+.2f}%)")

    # Yield spread: 10Y - 5Y (proxy for 10Y-2Y since API has 5Y)
    tnx = bond_map.get("^TNX")  # 10Y
    fvx = bond_map.get("^FVX")  # 5Y
    if tnx and fvx:
        spread_10_5 = tnx["price"] - fvx["price"]
        spread_label = "正常" if spread_10_5 > 0 else "⚠️ 倒挂"
        lines.append(f"  📐 10Y-5Y利差: {spread_10_5:+.3f}% ({spread_label})")

    tyx = bond_map.get("^TYX")  # 30Y
    if tyx and tnx:
        spread_30_10 = tyx["price"] - tnx["price"]
        lines.append(f"  📐 30Y-10Y利差: {spread_30_10:+.3f}%")

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

    return lines


# ═══════════════════════════════════════════════════════════════
# 8. 重要新闻/快讯
# ═══════════════════════════════════════════════════════════════
@safe_section("快讯")
def section_news(data: dict) -> list[str]:
    lines = ["📰 **快讯**"]
    news_list = data.get("news", [])
    if isinstance(data, list):
        news_list = data
    if not news_list:
        return lines + ["  暂无快讯"]

    for item in news_list[:6]:
        title = item.get("title", "")[:80]
        t = item.get("time", "")
        src = item.get("source_name") or item.get("source", "")
        # Extract HH:MM
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
# 9. 🧠 Wendy分析（规则引擎，纯确定性，ZERO AI）
# ═══════════════════════════════════════════════════════════════
@safe_section("Wendy分析")
def section_analysis(
    index_data: dict,
    sector_data: dict,
    mag7_data: dict,
    adr_data: dict,
    commodity_data: dict,
    bond_data: dict,
    forex_data: dict,
) -> list[str]:
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

    # ── 9a. 市场定性 ──
    lines.append("")
    lines.append("**市场定性:**")

    # Risk gauge based on VIX
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

    # Dow vs Nasdaq divergence (value vs growth)
    scissor = dow_pct - nas_pct
    if scissor > 1.0:
        style_signal = "⚠️ 价值 > 成长（道指强、纳指弱）→ Risk OFF，防御模式"
    elif scissor < -1.0:
        style_signal = "🚀 成长 > 价值（纳指强、道指弱）→ Risk ON，追逐增长"
    elif sp_pct > 0.5 and nas_pct > 0.5:
        style_signal = "🟢 普涨行情（标普+纳指同涨）"
    elif sp_pct < -0.5 and nas_pct < -0.5:
        style_signal = "🔴 普跌行情（标普+纳指同跌）"
    else:
        style_signal = "⚖️ 中性震荡"
    lines.append(f"  风格: {style_signal}")
    lines.append(f"  道指 {dow_pct:+.2f}% vs 纳指 {nas_pct:+.2f}% → 剪刀差 {scissor:+.2f}%")

    # ── 9b. Mag7 健康度 ──
    lines.append("")
    lines.append("**Mag7 健康度:**")
    mag_quotes = mag7_data.get("quotes", [])
    if mag_quotes:
        mag_up = sum(1 for q in mag_quotes if q["change_pct"] > 0)
        mag_down = len(mag_quotes) - mag_up
        mag_avg = sum(q["change_pct"] for q in mag_quotes) / len(mag_quotes)
        best = max(mag_quotes, key=lambda q: q["change_pct"])
        worst = min(mag_quotes, key=lambda q: q["change_pct"])

        lines.append(f"  {mag_up}涨/{mag_down}跌 | 均涨幅 {mag_avg:+.2f}%")
        lines.append(
            f"  最强: {best.get('cn_name', best['symbol'])} {best['change_pct']:+.2f}% | "
            f"最弱: {worst.get('cn_name', worst['symbol'])} {worst['change_pct']:+.2f}%"
        )

        # Mag7 divergence: if spread > 5%, something is happening
        spread = best["change_pct"] - worst["change_pct"]
        if spread > 5:
            lines.append(f"  ⚠️ 内部分化严重（差距{spread:.1f}%），关注财报/事件驱动")
        elif mag_avg > 1:
            lines.append(f"  🟢 科技巨头整体强势，市场风险偏好高")
        elif mag_avg < -1:
            lines.append(f"  🔴 科技巨头整体疲弱，大盘承压")
    else:
        lines.append("  数据暂无")

    # ── 9c. 中概 vs 大盘 ──
    lines.append("")
    lines.append("**中概 vs 大盘:**")
    adr_quotes = adr_data.get("quotes", [])
    if adr_quotes and sp_pct != 0:
        adr_avg = sum(q["change_pct"] for q in adr_quotes) / len(adr_quotes)
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

    # ── 9d. 板块轮动信号 ──
    lines.append("")
    lines.append("**板块轮动:**")
    sectors = sector_data.get("sectors", [])
    etf_sectors = []
    for s in sectors:
        if s.get("etf"):
            etf_sectors.append({
                "name_cn": s["name_cn"],
                "symbol": s["etf"]["symbol"],
                "pct": s["etf"]["change_pct"],
            })

    if etf_sectors:
        etf_sectors.sort(key=lambda x: x["pct"], reverse=True)
        best_sector = etf_sectors[0]
        worst_sector = etf_sectors[-1]
        sector_spread = best_sector["pct"] - worst_sector["pct"]

        lines.append(
            f"  最强: {best_sector['name_cn']}({best_sector['symbol']}) {best_sector['pct']:+.2f}%"
        )
        lines.append(
            f"  最弱: {worst_sector['name_cn']}({worst_sector['symbol']}) {worst_sector['pct']:+.2f}%"
        )
        lines.append(f"  板块离散度: {sector_spread:.2f}%")

        if sector_spread > 3:
            lines.append(f"  ⚠️ 板块分化严重，资金选择性进攻")
        elif sector_spread < 1:
            lines.append(f"  📊 板块齐涨齐跌，系统性行情")

        # Defensive vs offensive check
        defensive_names = {"公用事业", "消费必需品", "医疗保健", "房地产"}
        offensive_names = {"科技", "半导体", "可选消费", "通信服务", "AI概念"}
        def_pcts = [s["pct"] for s in etf_sectors if s["name_cn"] in defensive_names]
        off_pcts = [s["pct"] for s in etf_sectors if s["name_cn"] in offensive_names]

        if def_pcts and off_pcts:
            def_avg = sum(def_pcts) / len(def_pcts)
            off_avg = sum(off_pcts) / len(off_pcts)
            if def_avg > off_avg + 1:
                lines.append(f"  🛡️ 防御板块领涨（{def_avg:+.2f}% vs 进攻{off_avg:+.2f}%）→ 避险情绪")
            elif off_avg > def_avg + 1:
                lines.append(f"  ⚔️ 进攻板块领涨（{off_avg:+.2f}% vs 防御{def_avg:+.2f}%）→ 风险偏好高")
    else:
        lines.append("  数据暂无")

    # ── 9e. 商品信号 ──
    lines.append("")
    lines.append("**商品信号:**")
    commodities = commodity_data.get("commodities", [])
    commodity_map = {c["symbol"]: c for c in commodities}

    gold = commodity_map.get("GC=F")
    silver = commodity_map.get("SI=F")
    oil_wti = commodity_map.get("CL=F")
    copper = commodity_map.get("HG=F")

    signals = []
    if gold:
        gold_pct = gold.get("change_pct", 0)
        if gold_pct > 1.5:
            signals.append(f"🥇 黄金大涨{gold_pct:+.2f}% → 避险需求强劲")
        elif gold_pct < -1.5:
            signals.append(f"🥇 黄金大跌{gold_pct:+.2f}% → 风险偏好回升/美元走强")
        else:
            signals.append(f"🥇 黄金{gold_pct:+.2f}%（中性）")

    if oil_wti:
        oil_pct = oil_wti.get("change_pct", 0)
        if oil_pct > 3:
            signals.append(f"🛢️ 原油大涨{oil_pct:+.2f}% → 通胀压力/供给收紧")
        elif oil_pct < -3:
            signals.append(f"🛢️ 原油大跌{oil_pct:+.2f}% → 需求担忧/衰退预期")
        else:
            signals.append(f"🛢️ 原油{oil_pct:+.2f}%（中性）")

    if copper:
        copper_pct = copper.get("change_pct", 0)
        if copper_pct > 2:
            signals.append(f"🔶 铜大涨{copper_pct:+.2f}% → 经济复苏预期")
        elif copper_pct < -2:
            signals.append(f"🔶 铜大跌{copper_pct:+.2f}% → 经济放缓信号")

    # Gold/Silver ratio (inverse correlation with risk)
    if gold and silver and silver["price"] > 0:
        gs_ratio = gold["price"] / silver["price"]
        if gs_ratio > 80:
            signals.append(f"📊 金银比{gs_ratio:.1f} → 偏高，避险氛围")
        elif gs_ratio < 60:
            signals.append(f"📊 金银比{gs_ratio:.1f} → 偏低，工业需求旺盛")

    if signals:
        for s in signals:
            lines.append(f"  {s}")
    else:
        lines.append("  数据暂无")

    # ── 9f. 债券/美元信号 ──
    lines.append("")
    lines.append("**利率/汇率信号:**")
    bonds = bond_data.get("bonds", [])
    bond_map = {b["symbol"]: b for b in bonds}
    forex = forex_data.get("forex", [])
    fx_map = {f["symbol"]: f for f in forex}

    tnx = bond_map.get("^TNX")  # 10Y
    dxy = fx_map.get("DX-Y.NYB")  # Dollar Index

    rate_signals = []
    if tnx:
        y10 = tnx["price"]
        y10_pct = tnx.get("change_pct", 0)
        if y10 > 5.0:
            rate_signals.append(f"🔴 10Y美债 {y10:.3f}%（>5%，紧缩环境，股市承压）")
        elif y10 > 4.5:
            rate_signals.append(f"🟡 10Y美债 {y10:.3f}%（偏高，关注通胀数据）")
        elif y10 < 3.5:
            rate_signals.append(f"🟢 10Y美债 {y10:.3f}%（偏低，宽松预期）")
        else:
            rate_signals.append(f"⚖️ 10Y美债 {y10:.3f}%（中性区间）")

    if dxy:
        dxy_price = dxy["price"]
        dxy_pct = dxy.get("change_pct", 0)
        if dxy_price > 105:
            rate_signals.append(f"💪 美元指数 {dxy_price:.2f}（强势，新兴市场/商品承压）")
        elif dxy_price < 95:
            rate_signals.append(f"📉 美元指数 {dxy_price:.2f}（弱势，利好新兴市场/商品）")
        else:
            rate_signals.append(f"⚖️ 美元指数 {dxy_price:.2f}（中性）")

    # Combined: rising yields + strong dollar = tightening
    if tnx and dxy:
        if tnx.get("change_pct", 0) > 1 and dxy.get("change_pct", 0) > 0.3:
            rate_signals.append("⚠️ 利率上行+美元走强 → 金融条件收紧，风险资产承压")
        elif tnx.get("change_pct", 0) < -1 and dxy.get("change_pct", 0) < -0.3:
            rate_signals.append("🟢 利率下行+美元走弱 → 金融条件宽松，利好风险资产")

    if rate_signals:
        for s in rate_signals:
            lines.append(f"  {s}")
    else:
        lines.append("  数据暂无")

    # ── 9g. 综合信号评分 & 操作建议 ──
    lines.append("")
    lines.append("**📏 综合评分:**")

    bullish = 0
    bearish = 0

    # Index direction
    if sp_pct > 0.3:
        bullish += 1
    elif sp_pct < -0.3:
        bearish += 1
    if nas_pct > 0.3:
        bullish += 1
    elif nas_pct < -0.3:
        bearish += 1

    # VIX
    if vix_level < 15:
        bullish += 1
    elif vix_level >= 25:
        bearish += 2
    elif vix_level >= 20:
        bearish += 1

    # Mag7
    if mag_quotes:
        mag_avg = sum(q["change_pct"] for q in mag_quotes) / len(mag_quotes)
        if mag_avg > 0.5:
            bullish += 1
        elif mag_avg < -0.5:
            bearish += 1

    # Gold (inverse)
    if gold and gold.get("change_pct", 0) > 2:
        bearish += 1  # Gold rally = risk-off
    elif gold and gold.get("change_pct", 0) < -1:
        bullish += 1  # Gold sell = risk-on

    # Bond yield direction
    if tnx and tnx.get("change_pct", 0) > 2:
        bearish += 1  # Rising yields fast = bad for stocks
    elif tnx and tnx.get("change_pct", 0) < -2:
        bullish += 1  # Falling yields = good for stocks

    # Sector breadth
    if etf_sectors:
        up_ratio = sum(1 for s in etf_sectors if s["pct"] > 0) / len(etf_sectors)
        if up_ratio > 0.7:
            bullish += 1
        elif up_ratio < 0.3:
            bearish += 1

    total_score = bullish - bearish
    if total_score >= 3:
        outlook = "✅ 多头主导 — 市场风险偏好高，可积极参与"
    elif total_score >= 1:
        outlook = "🟢 偏多 — 温和看涨，关注主线板块"
    elif total_score <= -3:
        outlook = "🛑 空头主导 — 避险为主，减仓观望"
    elif total_score <= -1:
        outlook = "🟡 偏空 — 谨慎操作，控制仓位"
    else:
        outlook = "⚖️ 中性震荡 — 轻仓灵活应对"

    lines.append(f"  多头信号: {bullish} | 空头信号: {bearish} | 净值: {total_score:+d}")
    lines.append(f"  {outlook}")

    return lines


# ═══════════════════════════════════════════════════════════════
# 10. 经济日历（如有）
# ═══════════════════════════════════════════════════════════════
@safe_section("经济日历")
def section_calendar() -> list[str]:
    data = fetch("/api/us-stock/calendar")
    events = data.get("events", data.get("data", []))
    if not events:
        return []  # Silently skip if no calendar endpoint

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
    output.append(f"{'═' * 40}")
    output.append(f"🇺🇸 **美股简报** ({time_label} {weekday_cn})")
    output.append(f"{'═' * 40}")

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
        "news": "/api/news/latest?limit=6",
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

    # ── Assemble sections ──
    sections = [
        section_indexes(index_data),
        section_sectors(sector_data),
        section_mag7(mag7_data),
        section_china_adr(adr_data),
        section_commodities(commodity_data),
        section_bonds(bond_data),
        section_forex(forex_data),
        section_news(news_data),
        section_analysis(
            index_data, sector_data, mag7_data,
            adr_data, commodity_data, bond_data, forex_data,
        ),
        section_calendar(),
    ]

    for section_lines in sections:
        if section_lines:  # Skip empty sections (e.g., calendar)
            output.extend(section_lines)
            output.append("")

    output.append(f"{'═' * 40}")
    output.append(f"⏱ 生成: {datetime.now().strftime('%H:%M:%S')} | 数据仅供参考")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="美股简报 v3")
    parser.add_argument("--time", action="store_true", help="显示详细时间戳")
    args = parser.parse_args()

    print(format_briefing(show_time=args.time))


if __name__ == "__main__":
    main()
