#!/usr/bin/env python3
"""
美股数据采集简报 — 纯数据输出版

采集所有截面数据，输出结构化 markdown，不做分析判断。
LLM 分析由 OpenClaw 调度 Claude Code CLI 完成。

输出保存到 ~/knowledge-base/briefings/us/{YYYY-MM-DD}.md (append 模式)

使用方式:
    python3 scripts/us_briefing_v2.py
"""

import requests
import sys
from datetime import datetime
from pathlib import Path

API = "http://127.0.0.1:8000"
PARK_INTEL_BASE = "http://127.0.0.1:8001"
BRIEFING_DIR = Path.home() / "knowledge-base" / "briefings" / "us"
PROJECT_ROOT = Path(__file__).parent.parent

# ETF symbol → 简短中文名
ETF_SHORT_NAMES = {
    "XLK": "科技", "SMH": "半导体", "ARKK": "ARK创新", "XLC": "通信",
    "XLY": "可选消费", "XLP": "必需消费", "XLV": "医疗", "XLF": "金融",
    "XLE": "能源", "XLI": "工业", "XLB": "材料", "XLRE": "房地产",
    "XLU": "公用事业", "KWEB": "中概互联", "LIT": "锂电", "TAN": "太阳能",
    "ICLN": "清洁能源", "GLD": "黄金ETF", "SLV": "白银ETF", "TLT": "长期美债",
    "ARKG": "生物科技",
}


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def fetch(endpoint):
    """GET API endpoint, return JSON or empty dict/list on failure."""
    try:
        r = requests.get(f"{API}{endpoint}", timeout=15)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def safe_section(section_name: str):
    """Decorator: catch errors in each section."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return [f"[{section_name}] 获取失败: {e}"]
        return wrapper
    return decorator


def fetch_all_watchlist_quotes():
    """批量获取所有 watchlist 个股报价。"""
    wl_resp = fetch("/api/us-stock/watchlists")
    if not wl_resp:
        return []
    seen = set()
    all_quotes = []
    for wl_name in wl_resp:
        data = fetch(f"/api/us-stock/watchlist/{wl_name}")
        for q in data.get("quotes", []):
            sym = q.get("symbol", "")
            if sym and sym not in seen:
                seen.add(sym)
                all_quotes.append(q)
    return all_quotes


# ═══════════════════════════════════════════════════════════════
# 1. 三大指数 + VIX
# ═══════════════════════════════════════════════════════════════
@safe_section("三大指数")
def section_indexes(idx_quotes: list) -> list[str]:
    lines = ["### 三大指数 + VIX"]
    if not idx_quotes:
        return lines + ["数据暂无"]

    lines.append("| 指数 | 现价 | 涨跌% |")
    lines.append("|------|------|--------|")

    for q in idx_quotes:
        name = q.get("cn_name") or q.get("name", "")
        pct = q.get("change_pct", 0)
        price = q.get("price", 0)
        lines.append(f"| {name} | {price:,.2f} | {pct:+.2f}% |")

    return lines


# ═══════════════════════════════════════════════════════════════
# 2. 板块 ETF 涨跌幅
# ═══════════════════════════════════════════════════════════════
@safe_section("板块ETF")
def section_sector_etfs(sector_data: list) -> list[str]:
    lines = ["### 板块 ETF"]

    etf_list = []
    for s in sector_data:
        etf = s.get("etf")
        if etf and etf.get("change_pct") is not None:
            sym = etf.get("symbol", "")
            etf_list.append({
                "symbol": sym,
                "name_cn": ETF_SHORT_NAMES.get(sym, s.get("name_cn", sym)),
                "pct": etf.get("change_pct", 0),
            })

    if not etf_list:
        return lines + ["数据暂无"]

    etf_list.sort(key=lambda x: x["pct"], reverse=True)

    lines.append("| ETF | 名称 | 涨跌% |")
    lines.append("|-----|------|--------|")
    for e in etf_list:
        lines.append(f"| {e['symbol']} | {e['name_cn']} | {e['pct']:+.2f}% |")

    return lines


# ═══════════════════════════════════════════════════════════════
# 3. 大幅异动股 (±5%)
# ═══════════════════════════════════════════════════════════════
@safe_section("异动检测")
def section_movers(all_quotes: list) -> list[str]:
    lines = ["### 大幅异动 (±5%)"]
    if not all_quotes:
        return lines + ["数据暂无"]

    valid = [q for q in all_quotes if q.get("change_pct") is not None and q.get("price", 0) > 0]
    if not valid:
        return lines + ["无有效报价"]

    sorted_q = sorted(valid, key=lambda q: q.get("change_pct", 0), reverse=True)
    big_up = [q for q in sorted_q if q.get("change_pct", 0) >= 5]
    big_down = [q for q in sorted_q if q.get("change_pct", 0) <= -5]

    if not big_up and not big_down:
        return lines + ["无大幅异动 (所有个股波动 <5%)"]

    if big_up:
        lines.append(f"**暴涨 (>=5%): {len(big_up)}只**")
        for q in big_up[:5]:
            name = q.get("cn_name") or q.get("name", q.get("symbol", "?"))
            sym = q.get("symbol", "")
            lines.append(f"- {name}({sym}) ${q.get('price', 0):.2f} ({q.get('change_pct', 0):+.2f}%)")
        if len(big_up) > 5:
            lines.append(f"- ...还有{len(big_up) - 5}只")

    if big_down:
        lines.append(f"**暴跌 (<=-5%): {len(big_down)}只**")
        for q in sorted(big_down, key=lambda q: q.get("change_pct", 0))[:5]:
            name = q.get("cn_name") or q.get("name", q.get("symbol", "?"))
            sym = q.get("symbol", "")
            lines.append(f"- {name}({sym}) ${q.get('price', 0):.2f} ({q.get('change_pct', 0):+.2f}%)")
        if len(big_down) > 5:
            lines.append(f"- ...还有{len(big_down) - 5}只")

    return lines


# ═══════════════════════════════════════════════════════════════
# 4. Mag7 报价
# ═══════════════════════════════════════════════════════════════
@safe_section("Mag7")
def section_mag7(mag_quotes: list) -> list[str]:
    lines = ["### Mag7"]
    if not mag_quotes:
        return lines + ["数据暂无"]

    sorted_mag = sorted(mag_quotes, key=lambda q: q.get("change_pct", 0), reverse=True)

    lines.append("| 股票 | 现价 | 涨跌% |")
    lines.append("|------|------|--------|")
    for q in sorted_mag:
        name = q.get("cn_name") or q.get("symbol", "?")
        sym = q.get("symbol", "")
        lines.append(f"| {name}({sym}) | ${q.get('price', 0):.2f} | {q.get('change_pct', 0):+.2f}% |")

    return lines


# ═══════════════════════════════════════════════════════════════
# 5. 中概股 ADR
# ═══════════════════════════════════════════════════════════════
@safe_section("中概股")
def section_china_adr(adr_quotes: list) -> list[str]:
    lines = ["### 中概股 ADR"]
    if not adr_quotes:
        return lines + ["数据暂无"]

    sorted_adr = sorted(adr_quotes, key=lambda q: q.get("change_pct", 0), reverse=True)

    lines.append("| 股票 | 现价 | 涨跌% |")
    lines.append("|------|------|--------|")
    for q in sorted_adr:
        name = q.get("cn_name", q.get("symbol", ""))
        lines.append(f"| {name} | ${q.get('price', 0):.2f} | {q.get('change_pct', 0):+.2f}% |")

    return lines


# ═══════════════════════════════════════════════════════════════
# 6. 跨资产数据
# ═══════════════════════════════════════════════════════════════
@safe_section("跨资产")
def section_cross_asset(commod_quotes, bond_quotes, forex_quotes) -> list[str]:
    lines = ["### 跨资产"]

    lines.append("| 资产 | 现价 | 涨跌% |")
    lines.append("|------|------|--------|")

    for data_source in [bond_quotes, commod_quotes, forex_quotes]:
        items = data_source if isinstance(data_source, list) else data_source.get("quotes", data_source.get("data", []))
        for q in items:
            if q.get("price"):
                name = q.get("cn_name") or q.get("name", "?")
                lines.append(f"| {name} | {q['price']:.2f} | {q.get('change_pct', 0):+.2f}% |")

    return lines


# ═══════════════════════════════════════════════════════════════
# 7. 舆情信号 (park-intel)
# ═══════════════════════════════════════════════════════════════
@safe_section("舆情信号")
def section_intel() -> list[str]:
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

    try:
        sig_r = requests.get(f"{API}/api/perception/signals?limit=20", timeout=10)
        if sig_r.status_code != 200:
            return lines + ["perception API 请求失败"]
        sig_data = sig_r.json()
    except Exception:
        return lines + ["perception API 不可用"]

    signals = sig_data.get("signals", [])
    count = sig_data.get("count", len(signals))

    longs = [s for s in signals if s.get("direction") == "long"]
    shorts = [s for s in signals if s.get("direction") == "short"]
    longs.sort(key=lambda s: s.get("composite_score", 0), reverse=True)
    shorts.sort(key=lambda s: s.get("composite_score", 0), reverse=True)

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

    try:
        health_r = requests.get(f"{API}/api/perception/health", timeout=5)
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
# 9. 经济日历
# ═══════════════════════════════════════════════════════════════
@safe_section("经济日历")
def section_calendar() -> list[str]:
    lines = ["### 经济日历"]
    cal = fetch("/api/us-stock/calendar")
    events = cal.get("events", cal.get("data", []))
    if not events:
        return lines + ["暂无近期事件"]
    for e in events[:5]:
        date = e.get("date", "")
        event = e.get("event", e.get("name", ""))
        lines.append(f"- {date} {event}")
    return lines


# ═══════════════════════════════════════════════════════════════
# 10. 快讯
# ═══════════════════════════════════════════════════════════════
@safe_section("快讯")
def section_news() -> list[str]:
    lines = ["### 快讯"]
    news = fetch("/api/us-stock/news")
    news_list = news if isinstance(news, list) else news.get("news", news.get("data", news.get("articles", [])))
    if not news_list:
        return lines + ["暂无快讯"]
    for n in (news_list or [])[:5]:
        src = n.get("source", "")
        title = n.get("title", "")
        if title:
            lines.append(f"- [{src}] {title[:80]}")
    return lines


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    """采集数据 → 输出结构化 markdown → 保存到 Obsidian"""
    now = datetime.now()

    # ── Data Gathering ──
    idx_data = fetch("/api/us-stock/indexes")
    idx_quotes = idx_data.get("quotes", [])

    sec_data = fetch("/api/us-stock/sectors")
    sector_list = sec_data.get("sectors", [])

    mag_data = fetch("/api/us-stock/mag7")
    mag_quotes = mag_data.get("quotes", [])

    adr_data = fetch("/api/us-stock/china-adr")
    adr_quotes = adr_data.get("quotes", [])

    commod_data = fetch("/api/us-stock/commodities")
    commod_quotes = commod_data.get("commodities", commod_data.get("quotes", commod_data.get("data", [])))

    bond_data = fetch("/api/us-stock/bonds")
    bond_quotes = bond_data.get("bonds", bond_data.get("quotes", bond_data.get("data", [])))

    forex_data = fetch("/api/us-stock/forex")
    forex_quotes = forex_data.get("forex", forex_data.get("quotes", forex_data.get("data", [])))

    all_wl_quotes = fetch_all_watchlist_quotes()

    # ── Build Output ──
    output = [f"## {now.strftime('%H:%M')} 数据快照", ""]

    output.extend(section_indexes(idx_quotes))
    output.append("")
    output.extend(section_sector_etfs(sector_list))
    output.append("")
    output.extend(section_movers(all_wl_quotes))
    output.append("")
    output.extend(section_mag7(mag_quotes))
    output.append("")
    output.extend(section_china_adr(adr_quotes))
    output.append("")
    output.extend(section_cross_asset(commod_quotes, bond_quotes, forex_quotes))
    output.append("")
    output.extend(section_intel())
    output.append("")
    output.extend(section_perception())
    output.append("")
    output.extend(section_calendar())
    output.append("")
    output.extend(section_news())

    output.append("")
    output.append("---")
    output.append(f"生成时间: {now.strftime('%H:%M:%S')}")
    output.append("")

    full_text = "\n".join(output)
    print(full_text)

    # ── Save to Obsidian (append mode) ──
    BRIEFING_DIR.mkdir(parents=True, exist_ok=True)
    out_file = BRIEFING_DIR / f"{now.strftime('%Y-%m-%d')}.md"
    with open(out_file, "a", encoding="utf-8") as f:
        f.write(full_text)
    print(f"\n>> 已保存到 {out_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
