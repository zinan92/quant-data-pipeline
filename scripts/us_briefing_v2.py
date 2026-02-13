#!/usr/bin/env python3
"""
美股简报 v2 — 深度分析版
数据源: ashare API http://127.0.0.1:8000

8 个 Section:
  1. 📈 三大指数 (含 VIX 解读)
  2. 🏛️ 板块轮动分析 (Risk ON/OFF + 领涨解读)
  3. 🚨 异动检测 (大涨大跌个股)
  4. 💎 Mag7 深度分析 (整体强弱 + vs 大盘)
  5. 🇨🇳 中概股
  6. 📦 跨资产联动 (股债、美元、避险信号解读)
  7. 🧠 Wendy 深度分析 (5层分析)
  8. 📰 快讯 + 📅 经济日历
"""

import requests
import sys
from datetime import datetime

API = "http://127.0.0.1:8000"

# ── 板块分类 ──────────────────────────────────────────────────
OFFENSIVE_ETFS = {"XLK", "SMH", "ARKK", "XLY", "XLC", "KWEB", "LIT", "TAN"}
DEFENSIVE_ETFS = {"XLU", "XLP", "XLV", "GLD", "TLT", "SLV", "XLRE"}

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
    """Decorator: catch errors in each section so one failure won't break all."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return [f"⚠️ [{section_name}] 获取失败: {e}"]
        return wrapper
    return decorator


def _q_pct(quotes, symbol):
    """从 quotes list 中按 symbol 取 change_pct，找不到返回 0。"""
    for q in quotes:
        if q.get("symbol") == symbol:
            return q.get("change_pct", 0)
    return 0


def _q_price(quotes, symbol):
    """从 quotes list 中按 symbol 取 price。"""
    for q in quotes:
        if q.get("symbol") == symbol:
            return q.get("price", 0)
    return 0


def fetch_all_watchlist_quotes():
    """批量获取所有 watchlist 个股报价，返回去重后的 list[dict]。"""
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
# 1. 三大指数 (含 VIX 解读)
# ═══════════════════════════════════════════════════════════════
@safe_section("三大指数")
def section_indexes(idx_quotes: list) -> list[str]:
    lines = ["📈 **三大指数**"]
    if not idx_quotes:
        return lines + ["  数据暂无"]

    vix_quote = None
    for q in idx_quotes:
        name = q.get("cn_name") or q.get("name", "")
        pct = q.get("change_pct", 0)
        price = q.get("price", 0)
        if "VIX" in q.get("symbol", "") or "恐慌" in name or "VIX" in name:
            vix_quote = q
            continue
        icon = "🟢" if pct >= 0 else "🔴"
        lines.append(f"  {icon} {name}: {price:,.2f} ({pct:+.2f}%)")

    # VIX 解读
    if vix_quote:
        vix = vix_quote.get("price", 0)
        vix_pct = vix_quote.get("change_pct", 0)
        if vix < 15:
            vix_tag = "😌 低波动"
        elif vix < 20:
            vix_tag = "😐 正常"
        elif vix < 25:
            vix_tag = "😰 警惕"
        elif vix < 30:
            vix_tag = "😨 恐慌"
        else:
            vix_tag = "🔥 极端恐慌"
        vix_dir = "↑" if vix_pct > 0 else "↓" if vix_pct < 0 else "→"
        lines.append(f"  ⚠️ VIX: {vix:.2f} ({vix_pct:+.2f}%) {vix_dir} | {vix_tag}")

    return lines


# ═══════════════════════════════════════════════════════════════
# 2. 板块轮动分析
# ═══════════════════════════════════════════════════════════════
@safe_section("板块轮动")
def section_sector_rotation(sector_data: list) -> list[str]:
    lines = ["🏛️ **板块轮动分析**"]

    # 提取有 ETF 数据的板块
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
        return lines + ["  数据暂无"]

    etf_list.sort(key=lambda x: x["pct"], reverse=True)
    best = etf_list[0]
    worst = etf_list[-1]
    spread = best["pct"] - worst["pct"]

    # ── Risk ON / Risk OFF ──
    off_sum = sum(e["pct"] for e in etf_list if e["symbol"] in OFFENSIVE_ETFS)
    off_cnt = max(1, sum(1 for e in etf_list if e["symbol"] in OFFENSIVE_ETFS))
    def_sum = sum(e["pct"] for e in etf_list if e["symbol"] in DEFENSIVE_ETFS)
    def_cnt = max(1, sum(1 for e in etf_list if e["symbol"] in DEFENSIVE_ETFS))
    off_avg = off_sum / off_cnt
    def_avg = def_sum / def_cnt

    if off_avg > def_avg + 0.5:
        risk_label = "🚀 Risk ON — 进攻板块领先，资金追逐成长"
    elif def_avg > off_avg + 0.5:
        risk_label = "🛡️ Risk OFF — 防御板块领先，资金涌入避险"
    else:
        risk_label = "⚖️ 中性 — 进攻与防御板块旗鼓相当"
    lines.append(f"  {risk_label}")
    lines.append(f"  进攻均值 {off_avg:+.2f}% vs 防御均值 {def_avg:+.2f}%")
    lines.append("")

    # ── 领涨 TOP3 ──
    lines.append("  **领涨 TOP3:**")
    for e in etf_list[:3]:
        lines.append(f"    🟢 {e['name_cn']}({e['symbol']}) {e['pct']:+.2f}%")

    # ── 领跌 TOP3 ──
    lines.append("  **领跌 TOP3:**")
    for e in etf_list[-3:]:
        lines.append(f"    🔴 {e['name_cn']}({e['symbol']}) {e['pct']:+.2f}%")
    lines.append("")

    # ── 分化度 ──
    if spread < 1.5:
        div_tag = "普涨/普跌" if best["pct"] > 0 else "齐跌"
        lines.append(f"  📊 分化度: {spread:.2f}% — {div_tag}，板块同向性强")
    elif spread < 3:
        lines.append(f"  📊 分化度: {spread:.2f}% — 温和分化")
    else:
        lines.append(f"  📊 分化度: {spread:.2f}% — 结构性分化严重，选对板块很关键")

    # 全部ETF列表 (紧凑格式)
    lines.append("")
    gainers = [e for e in etf_list if e["pct"] >= 0]
    losers = [e for e in etf_list if e["pct"] < 0]
    if gainers:
        parts = [f"{e['name_cn']} {e['pct']:+.2f}%" for e in gainers]
        lines.append(f"  🟢 {' | '.join(parts)}")
    if losers:
        parts = [f"{e['name_cn']} {e['pct']:+.2f}%" for e in losers]
        lines.append(f"  🔴 {' | '.join(parts)}")

    return lines


# ═══════════════════════════════════════════════════════════════
# 3. 异动检测
# ═══════════════════════════════════════════════════════════════
@safe_section("异动检测")
def section_movers(all_quotes: list) -> list[str]:
    lines = ["🚨 **异动检测**"]
    if not all_quotes:
        return lines + ["  数据暂无"]

    # 筛选有效报价
    valid = [q for q in all_quotes if q.get("change_pct") is not None and q.get("price", 0) > 0]
    if not valid:
        return lines + ["  无有效报价"]

    # 按涨跌幅排序
    sorted_q = sorted(valid, key=lambda q: q.get("change_pct", 0), reverse=True)

    big_up = [q for q in sorted_q if q.get("change_pct", 0) >= 5]
    big_down = [q for q in sorted_q if q.get("change_pct", 0) <= -5]

    if not big_up and not big_down:
        lines.append("  ✅ 无大幅异动 (所有个股波动 <5%)")
        return lines

    if big_up:
        lines.append(f"  🚀 **暴涨 (≥5%): {len(big_up)}只**")
        for q in big_up[:5]:
            name = q.get("cn_name") or q.get("name", q.get("symbol", "?"))
            sym = q.get("symbol", "")
            pct = q.get("change_pct", 0)
            price = q.get("price", 0)
            lines.append(f"    🟢 {name}({sym}) ${price:.2f} ({pct:+.2f}%)")
        if len(big_up) > 5:
            lines.append(f"    （还有{len(big_up) - 5}只...）")

    if big_down:
        lines.append(f"  📉 **暴跌 (≤-5%): {len(big_down)}只**")
        for q in sorted(big_down, key=lambda q: q.get("change_pct", 0))[:5]:
            name = q.get("cn_name") or q.get("name", q.get("symbol", "?"))
            sym = q.get("symbol", "")
            pct = q.get("change_pct", 0)
            price = q.get("price", 0)
            lines.append(f"    🔴 {name}({sym}) ${price:.2f} ({pct:+.2f}%)")
        if len(big_down) > 5:
            lines.append(f"    （还有{len(big_down) - 5}只...）")

    return lines


# ═══════════════════════════════════════════════════════════════
# 4. Mag7 深度分析
# ═══════════════════════════════════════════════════════════════
@safe_section("Mag7深度分析")
def section_mag7_analysis(mag_quotes: list, sp500_pct: float) -> list[str]:
    lines = ["💎 **Mag7 深度分析**"]
    if not mag_quotes:
        return lines + ["  数据暂无"]

    sorted_mag = sorted(mag_quotes, key=lambda q: q.get("change_pct", 0), reverse=True)
    up_count = sum(1 for q in sorted_mag if q.get("change_pct", 0) >= 0)
    down_count = len(sorted_mag) - up_count
    avg_pct = sum(q.get("change_pct", 0) for q in sorted_mag) / max(1, len(sorted_mag))

    # 整体强弱
    if up_count >= 6:
        strength = "💪 整体强势"
    elif up_count >= 4:
        strength = "🟢 偏强"
    elif up_count <= 2:
        strength = "😰 整体疲弱"
    else:
        strength = "⚖️ 分化"
    lines.append(f"  {strength} | {up_count}涨 {down_count}跌 | 均值 {avg_pct:+.2f}%")

    # vs S&P 500
    gap = avg_pct - sp500_pct
    if gap > 0.5:
        vs_sp = f"Mag7 跑赢 S&P {gap:.2f}% — 大盘被龙头\"扛着\""
    elif gap < -0.5:
        vs_sp = f"Mag7 跑输 S&P {abs(gap):.2f}% — 龙头拖后腿，市场广度更好"
    else:
        vs_sp = f"Mag7 与 S&P 基本同步 (差值 {gap:+.2f}%)"
    lines.append(f"  📊 {vs_sp}")
    lines.append("")

    # 逐只列表 + 领涨/领跌标注
    parts = []
    for i, q in enumerate(sorted_mag):
        icon = "🟢" if q.get("change_pct", 0) >= 0 else "🔴"
        name = q.get("cn_name") or q.get("symbol", "?")
        pct = q.get("change_pct", 0)
        tag = ""
        if i == 0 and pct > 0:
            tag = "👑"
        elif i == len(sorted_mag) - 1 and pct < 0:
            tag = "⬇️"
        parts.append(f"{icon}{name} {pct:+.2f}%{tag}")
    lines.append("  " + " | ".join(parts))

    # 内部分化
    if len(sorted_mag) >= 2:
        top_pct = sorted_mag[0].get("change_pct", 0)
        bot_pct = sorted_mag[-1].get("change_pct", 0)
        mag_spread = top_pct - bot_pct
        if mag_spread > 5:
            lines.append(f"  ⚠️ 内部分化严重: spread {mag_spread:.1f}% — 龙头阵营出现裂痕")

    return lines


# ═══════════════════════════════════════════════════════════════
# 5. 中概股
# ═══════════════════════════════════════════════════════════════
@safe_section("中概股")
def section_china_adr(adr_quotes: list) -> list[str]:
    lines = ["🇨🇳 **中概股**"]
    if not adr_quotes:
        return lines + ["  数据暂无"]

    sorted_adr = sorted(adr_quotes, key=lambda q: q.get("change_pct", 0), reverse=True)
    for q in sorted_adr:
        icon = "🟢" if q.get("change_pct", 0) >= 0 else "🔴"
        name = q.get("cn_name", q.get("symbol", ""))
        lines.append(f"  {icon} {name} ${q.get('price', 0):.2f} ({q.get('change_pct', 0):+.2f}%)")

    return lines


# ═══════════════════════════════════════════════════════════════
# 6. 跨资产联动分析
# ═══════════════════════════════════════════════════════════════
@safe_section("跨资产联动")
def section_cross_asset(commod_quotes, bond_quotes, forex_quotes,
                        sp500_pct: float, vix_price: float, vix_pct: float) -> list[str]:
    lines = ["📦 **跨资产联动**"]

    # 先展示原始数据
    macro_items = []
    for d in [commod_quotes, bond_quotes, forex_quotes]:
        for q in (d if isinstance(d, list) else d.get("quotes", d.get("data", []))):
            if q.get("price"):
                icon = "🟢" if q.get("change_pct", 0) >= 0 else "🔴"
                name = q.get("cn_name") or q.get("name", "?")
                macro_items.append(f"{icon}{name} {q['price']:.2f} ({q.get('change_pct', 0):+.2f}%)")
    if macro_items:
        lines.append("  " + " | ".join(macro_items))
    lines.append("")

    # ── 提取关键数据 ──
    # 10Y yield
    yield_10y_pct = 0
    yield_10y_price = 0
    for q in (bond_quotes if isinstance(bond_quotes, list) else bond_quotes.get("quotes", bond_quotes.get("data", []))):
        if "10Y" in q.get("cn_name", "") or "TNX" in q.get("symbol", ""):
            yield_10y_pct = q.get("change_pct", 0)
            yield_10y_price = q.get("price", 0)
            break

    # 黄金
    gold_pct = 0
    for q in (commod_quotes if isinstance(commod_quotes, list) else commod_quotes.get("quotes", commod_quotes.get("data", []))):
        if "黄金" in q.get("cn_name", "") or "GC=F" in q.get("symbol", ""):
            gold_pct = q.get("change_pct", 0)
            break

    # 原油
    oil_pct = 0
    for q in (commod_quotes if isinstance(commod_quotes, list) else commod_quotes.get("quotes", commod_quotes.get("data", []))):
        if "WTI" in q.get("cn_name", "") or "CL=F" in q.get("symbol", ""):
            oil_pct = q.get("change_pct", 0)
            break

    # 美元指数
    dxy_pct = 0
    for q in (forex_quotes if isinstance(forex_quotes, list) else forex_quotes.get("quotes", forex_quotes.get("data", []))):
        if "美元" in q.get("cn_name", "") or "DX-Y" in q.get("symbol", ""):
            dxy_pct = q.get("change_pct", 0)
            break

    # TLT (从 bond_quotes 或 sector data 中可能没有，用 yield 反向推断)
    tlt_pct = -yield_10y_pct * 0.5  # 近似: yield涨 → TLT跌

    # ── 解读层 ──
    lines.append("  **信号解读:**")

    # 1) 股债跷跷板
    if sp500_pct > 0.3 and yield_10y_pct > 0:
        lines.append("  • 股债: S&P涨+Yield涨 → 经济乐观，同涨反映通胀预期")
    elif sp500_pct < -0.3 and yield_10y_pct < 0:
        lines.append("  • 股债: S&P跌+Yield跌 → 避险情绪，资金涌入国债")
    elif sp500_pct > 0.3 and yield_10y_pct < 0:
        lines.append("  • 股债: S&P涨+Yield跌 → 典型Risk ON，最健康的上涨")
    elif sp500_pct < -0.3 and yield_10y_pct > 0:
        lines.append("  • 股债: S&P跌+Yield涨 → 加息恐慌/通胀担忧")
    else:
        lines.append("  • 股债: 无明显方向性信号")

    # 2) 美元 vs 大宗
    if dxy_pct > 0.3 and gold_pct < 0:
        lines.append("  • 美元&大宗: 美元走强+黄金承压 → 美元回流，利空商品")
    elif dxy_pct < -0.3 and gold_pct > 0:
        lines.append("  • 美元&大宗: 美元走弱+黄金上涨 → 弱美元利多贵金属")
    elif dxy_pct > 0.3 and gold_pct > 0:
        lines.append("  • 美元&大宗: 美元和黄金同涨 → 避险双保险，不确定性很高")
    else:
        lines.append(f"  • 美元&大宗: DXY {dxy_pct:+.2f}% | 金 {gold_pct:+.2f}% | 油 {oil_pct:+.2f}%")

    # 3) VIX 解读
    if vix_price > 0:
        if vix_price < 15:
            vix_label = "😌 低波动区间"
        elif vix_price < 20:
            vix_label = "😐 正常波动"
        elif vix_price < 25:
            vix_label = "😰 恐慌升温"
        elif vix_price < 30:
            vix_label = "😨 恐慌区间"
        else:
            vix_label = "🔥 极端恐慌"

        vix_move = ""
        if vix_pct > 15:
            vix_move = "⚡ VIX飙升，市场剧烈波动"
        elif vix_pct > 5:
            vix_move = "↑ VIX上行，恐慌加剧"
        elif vix_pct < -5:
            vix_move = "↓ VIX回落，情绪缓和"
        else:
            vix_move = "→ VIX平稳"
        lines.append(f"  • 恐慌: VIX {vix_price:.2f} ({vix_pct:+.2f}%) {vix_label} | {vix_move}")

    # 4) 避险 vs 风险综合判断
    risk_off_signals = 0
    if gold_pct > 0.3:
        risk_off_signals += 1
    if tlt_pct > 0.3:
        risk_off_signals += 1
    if sp500_pct < -0.3:
        risk_off_signals += 1
    if vix_pct > 10:
        risk_off_signals += 1

    if risk_off_signals >= 3:
        lines.append("  • 💡 综合判断: **Risk OFF** — 多重避险信号亮起")
    elif risk_off_signals == 0 and sp500_pct > 0.3:
        lines.append("  • 💡 综合判断: **Risk ON** — 风险偏好回升")
    else:
        lines.append("  • 💡 综合判断: 信号混合，无明确避险/追险方向")

    return lines


# ═══════════════════════════════════════════════════════════════
# 7. 🧠 Wendy 深度分析 (5 层)
# ═══════════════════════════════════════════════════════════════
@safe_section("Wendy分析")
def section_wendy_analysis(idx_quotes: list, sector_data: list,
                           mag_quotes: list, commod_quotes, bond_quotes,
                           forex_quotes) -> list[str]:
    lines = ["🧠 **Wendy 深度分析**"]
    lines.append("")

    # ══════════════════════════════════════════════════════════
    # 基础数据提取
    # ══════════════════════════════════════════════════════════
    sp500_pct = _q_pct(idx_quotes, "^GSPC")
    dji_pct = _q_pct(idx_quotes, "^DJI")
    nasdaq_pct = _q_pct(idx_quotes, "^IXIC")
    ndx_pct = _q_pct(idx_quotes, "^NDX")

    # VIX
    vix_price = 0
    vix_pct = 0
    for q in idx_quotes:
        if q.get("symbol") == "^VIX":
            vix_price = q.get("price", 0)
            vix_pct = q.get("change_pct", 0)
            break

    # 10Y yield
    yield_pct = 0
    yield_price = 0
    bond_list = bond_quotes if isinstance(bond_quotes, list) else bond_quotes.get("quotes", bond_quotes.get("data", []))
    for q in bond_list:
        if "10Y" in q.get("cn_name", "") or "TNX" in q.get("symbol", ""):
            yield_pct = q.get("change_pct", 0)
            yield_price = q.get("price", 0)
            break

    # 黄金/美元
    gold_pct = 0
    oil_pct = 0
    commod_list = commod_quotes if isinstance(commod_quotes, list) else commod_quotes.get("quotes", commod_quotes.get("data", []))
    for q in commod_list:
        cn = q.get("cn_name", "")
        if "黄金" in cn or "GC=F" in q.get("symbol", ""):
            gold_pct = q.get("change_pct", 0)
        if "WTI" in cn or "CL=F" in q.get("symbol", ""):
            oil_pct = q.get("change_pct", 0)

    dxy_pct = 0
    forex_list = forex_quotes if isinstance(forex_quotes, list) else forex_quotes.get("quotes", forex_quotes.get("data", []))
    for q in forex_list:
        if "美元" in q.get("cn_name", "") or "DX-Y" in q.get("symbol", ""):
            dxy_pct = q.get("change_pct", 0)
            break

    # 板块 ETF 数据
    etf_map = {}  # symbol -> change_pct
    for s in sector_data:
        etf = s.get("etf")
        if etf and etf.get("symbol"):
            etf_map[etf["symbol"]] = etf.get("change_pct", 0)

    off_avg = 0
    def_avg = 0
    off_vals = [v for k, v in etf_map.items() if k in OFFENSIVE_ETFS]
    def_vals = [v for k, v in etf_map.items() if k in DEFENSIVE_ETFS]
    if off_vals:
        off_avg = sum(off_vals) / len(off_vals)
    if def_vals:
        def_avg = sum(def_vals) / len(def_vals)

    # Mag7 数据
    mag_avg = 0
    mag_up = 0
    mag_spread = 0
    if mag_quotes:
        mag_pcts = [q.get("change_pct", 0) for q in mag_quotes]
        mag_avg = sum(mag_pcts) / len(mag_pcts)
        mag_up = sum(1 for p in mag_pcts if p >= 0)
        if len(mag_pcts) >= 2:
            mag_spread = max(mag_pcts) - min(mag_pcts)

    # ══════════════════════════════════════════════════════════
    # Layer 1️⃣ 今日市场画像
    # ══════════════════════════════════════════════════════════
    lines.append("**1️⃣ 今日市场画像**")

    xlk_pct = etf_map.get("XLK", 0)
    smh_pct = etf_map.get("SMH", 0)
    xlu_pct = etf_map.get("XLU", 0)
    xlp_pct = etf_map.get("XLP", 0)
    gld_pct = etf_map.get("GLD", 0)

    if (nasdaq_pct > sp500_pct + 0.5 and nasdaq_pct > 0
            and (xlk_pct > 0.5 or smh_pct > 0.5)):
        market_state = "🔥 科技领涨日"
        market_reason = (f"Nasdaq {nasdaq_pct:+.2f}% 大幅跑赢 S&P {sp500_pct:+.2f}%，"
                         f"XLK {xlk_pct:+.2f}% / SMH {smh_pct:+.2f}% 领涨，资金追逐科技成长")
    elif (sp500_pct < -1 and nasdaq_pct < -1 and dji_pct < -1
          and vix_price > 20):
        market_state = "💀 恐慌抛售日"
        market_reason = (f"三大指数均跌超1%，VIX {vix_price:.1f} 进入恐慌区间，"
                         f"全面抛售模式")
    elif (xlu_pct > 0.3 and xlp_pct > 0.3 and gld_pct > 0.3
          and xlk_pct < 0 and smh_pct < 0):
        market_state = "🛡️ 防御轮动日"
        market_reason = (f"公用+必需消费+黄金齐涨，科技+半导体下跌，"
                         f"资金从进攻板块撤往防御板块")
    elif (sp500_pct > 0.3 and nasdaq_pct > 0.3 and dji_pct > 0.3
          and off_avg > def_avg and vix_pct < 0):
        market_state = "🚀 Risk ON 日"
        market_reason = (f"三大指数齐涨，进攻板块领涨 {off_avg:+.2f}%，"
                         f"VIX 回落 {vix_pct:+.2f}%，风险偏好全面回升")
    elif (abs(sp500_pct) < 0.3 and abs(nasdaq_pct) < 0.3
          and abs(dji_pct) < 0.3 and vix_price < 15):
        market_state = "😴 低波震荡日"
        market_reason = (f"三大指数波动 <0.3%，VIX {vix_price:.1f} 处于低位，"
                         f"市场缺乏方向")
    elif (yield_pct > 2 and sp500_pct < -0.3 and gold_pct < 0):
        market_state = "⚠️ 加息恐慌日"
        market_reason = (f"10Y yield 上涨 {yield_pct:+.2f}%，股跌+金跌，"
                         f"市场交易加息/通胀预期升温")
    else:
        market_state = "⚖️ 分化震荡日"
        market_reason = (f"S&P {sp500_pct:+.2f}% | Nasdaq {nasdaq_pct:+.2f}% | "
                         f"道琼斯 {dji_pct:+.2f}%，结构分化，无明确主导")

    lines.append(f"  {market_state}")
    lines.append(f"  💡 *{market_reason}*")
    lines.append("")

    # ══════════════════════════════════════════════════════════
    # Layer 2️⃣ 板块主线 & 轮动方向
    # ══════════════════════════════════════════════════════════
    lines.append("**2️⃣ 板块主线 & 轮动方向**")

    sorted_etfs = sorted(etf_map.items(), key=lambda x: x[1], reverse=True)
    if sorted_etfs:
        top3 = sorted_etfs[:3]
        top3_str = ", ".join(
            f"{ETF_SHORT_NAMES.get(sym, sym)}({sym}) {pct:+.2f}%"
            for sym, pct in top3
        )
        lines.append(f"  • 最强板块: {top3_str}")

    # 进攻 vs 防御
    if off_avg > def_avg + 0.8:
        lines.append(f"  • 风格: 资金坚定追逐成长 (进攻 {off_avg:+.2f}% >> 防御 {def_avg:+.2f}%)")
    elif def_avg > off_avg + 0.8:
        lines.append(f"  • 风格: 资金转向防御 (防御 {def_avg:+.2f}% >> 进攻 {off_avg:+.2f}%)")
        lines.append("  • ⚠️ Sector Rotation 正在发生，成长→价值切换")
    elif abs(off_avg - def_avg) < 0.3:
        lines.append(f"  • 风格: 进攻与防御同步 ({off_avg:+.2f}% vs {def_avg:+.2f}%)，无明显轮动")
    else:
        lines.append(f"  • 风格: 进攻 {off_avg:+.2f}% vs 防御 {def_avg:+.2f}%，轻微偏向{'成长' if off_avg > def_avg else '价值'}")
    lines.append("")

    # ══════════════════════════════════════════════════════════
    # Layer 3️⃣ 跨资产信号解读
    # ══════════════════════════════════════════════════════════
    lines.append("**3️⃣ 跨资产信号**")

    # 股债关系
    if sp500_pct > 0.3 and yield_pct > 0:
        lines.append("  • 股债同涨 → 经济向好预期 + 通胀未退，关注后续利率压力")
    elif sp500_pct < -0.3 and yield_pct < 0:
        lines.append("  • 股债同跌(yield跌=债涨) → 典型避险，资金涌入国债")
    elif sp500_pct > 0.3 and yield_pct < -0.5:
        lines.append("  • 股涨+yield跌 → \"金发女孩\"行情，最理想的上涨环境")
    elif sp500_pct < -0.3 and yield_pct > 0.5:
        lines.append("  • 股跌+yield涨 → 利率上行打压估值，科技股最受伤")
    else:
        lines.append(f"  • 股债: S&P {sp500_pct:+.2f}% vs 10Y yield {yield_pct:+.2f}%，无明显背离")

    # 美元 + 商品
    lines.append(f"  • 美元 {dxy_pct:+.2f}% | 黄金 {gold_pct:+.2f}% | 原油 {oil_pct:+.2f}%")
    if dxy_pct > 0.5 and gold_pct < -0.3:
        lines.append("    → 强美元压制商品，美元回流趋势")
    elif dxy_pct < -0.5 and gold_pct > 0.3:
        lines.append("    → 弱美元推升商品，通胀/降息预期")

    # VIX
    if vix_price > 0:
        lines.append(f"  • VIX: {vix_price:.2f} ({vix_pct:+.2f}%)")
        if vix_pct > 15:
            lines.append("    → ⚡ VIX 飙升，短期波动剧烈，注意尾部风险")
        elif vix_pct > 5:
            lines.append("    → 恐慌情绪上升中")
        elif vix_pct < -10:
            lines.append("    → 恐慌快速消退，反弹窗口")
    lines.append("")

    # ══════════════════════════════════════════════════════════
    # Layer 4️⃣ 风险信号扫描
    # ══════════════════════════════════════════════════════════
    lines.append("**4️⃣ 风险信号**")

    risks = []

    # VIX 飙升
    if vix_price > 25:
        risks.append(f"🚨 VIX {vix_price:.1f} > 25 — 恐慌区间，市场可能剧烈波动")
    elif vix_price > 20:
        risks.append(f"⚠️ VIX {vix_price:.1f} > 20 — 进入警戒区间")
    if vix_pct > 15:
        risks.append(f"⚠️ VIX 单日飙升 {vix_pct:+.1f}% — 恐慌快速升温")

    # 防御板块集体上涨
    defensive_up = sum(1 for sym in ["XLU", "XLP", "GLD"]
                       if etf_map.get(sym, 0) > 0.3)
    if defensive_up >= 3:
        risks.append("⚠️ 公用+必需消费+黄金全部上涨 — 避险资金涌入")

    # 10Y yield 大幅波动
    if abs(yield_pct) > 3:
        risks.append(f"⚠️ 10Y yield 大幅波动 {yield_pct:+.2f}% — 利率风险")

    # Mag7 内部分化
    if mag_spread > 5:
        risks.append(f"⚠️ Mag7 内部 spread {mag_spread:.1f}% — 龙头阵营出现裂痕")

    # Nasdaq vs S&P 剪刀差
    nq_sp_gap = abs(nasdaq_pct - sp500_pct)
    if nq_sp_gap > 1:
        if nasdaq_pct > sp500_pct:
            risks.append(f"⚠️ Nasdaq vs S&P 剪刀差 {nq_sp_gap:.1f}% — 科技独涨，市场广度差")
        else:
            risks.append(f"⚠️ S&P vs Nasdaq 剪刀差 {nq_sp_gap:.1f}% — 科技落后，风格切换信号")

    # 美元暴涨
    if dxy_pct > 1:
        risks.append(f"⚠️ 美元指数暴涨 {dxy_pct:+.2f}% — 强美元压力，利空新兴市场和商品")

    if not risks:
        lines.append("  ✅ 暂无明显风险信号")
    else:
        for r in risks:
            lines.append(f"  • {r}")
    lines.append("")

    # ══════════════════════════════════════════════════════════
    # Layer 5️⃣ Wendy 建议
    # ══════════════════════════════════════════════════════════
    lines.append("**5️⃣ Wendy 建议**")

    # 多头信号 (7个, including qualitative)
    bull = 0
    if sp500_pct > 0.3:
        bull += 1
    if nasdaq_pct > 0.3:
        bull += 1
    if vix_price < 15 or (vix_price < 20 and vix_pct < -5):
        bull += 1
    if off_avg > def_avg + 0.3:
        bull += 1
    if mag_up >= 5:
        bull += 1
    if abs(yield_pct) < 1.5:
        bull += 1

    # 空头信号 (7个, including qualitative)
    bear = 0
    if sp500_pct < -0.3:
        bear += 1
    if nasdaq_pct < -0.3:
        bear += 1
    if vix_price > 20 or vix_pct > 15:
        bear += 1
    if def_avg > off_avg + 0.3:
        bear += 1
    if dxy_pct > 0.8:
        bear += 1
    if yield_pct > 2:
        bear += 1

    # 定性维度: park-intel 舆情动量
    intel_accel, intel_decel = _fetch_intel_momentum()
    if intel_accel > intel_decel and intel_accel > 0:
        bull += 1
    if intel_decel > intel_accel and intel_decel > 0:
        bear += 1

    score = bull - bear

    if score >= 4:
        advice = "✅ 积极做多"
        detail = "多重利好共振，可加仓科技/成长板块"
    elif score >= 2:
        advice = "🟢 偏多操作"
        detail = "整体偏多，参与强势板块，控制仓位"
    elif score <= -4:
        advice = "🛑 防守为主"
        detail = "多重利空叠加，降低仓位，持有现金或避险资产"
    elif score <= -2:
        advice = "🟡 谨慎观望"
        detail = "空头信号偏多，轻仓观望，等待企稳信号"
    else:
        advice = "⚖️ 灵活应对"
        detail = "多空信号混杂，无明确方向，高抛低吸"

    lines.append(f"  **{advice}** — {detail}")
    intel_note = ""
    if intel_accel > 0 or intel_decel > 0:
        intel_note = f" | 舆情: 加速{intel_accel} vs 降温{intel_decel}"
    lines.append(f"  (多头信号 {bull}/7 | 空头信号 {bear}/7 | 综合 {score:+d}{intel_note})")

    return lines


# ═══════════════════════════════════════════════════════════════
# 8. 舆情信号 (park-intel)
# ═══════════════════════════════════════════════════════════════
@safe_section("舆情信号")
def section_intel() -> list[str]:
    """Fetch qualitative signals from park-intel and format for US briefing."""
    lines = ["📡 **舆情信号** (park-intel)"]
    try:
        r = requests.get(
            "http://127.0.0.1:8001/api/articles/signals",
            timeout=10,
        )
        if r.status_code != 200:
            return lines + ["  park-intel 请求失败"]
        data = r.json()
    except Exception:
        return lines + ["  park-intel 不可用"]

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.services.narrative_mapping import format_intel_section
    lines.extend(format_intel_section(data))
    return lines


def _fetch_intel_momentum() -> tuple[int, int]:
    """Return (accelerating_count, decelerating_count) from park-intel signals.

    Used by Wendy analysis to add a qualitative bull/bear signal.
    Returns (0, 0) if park-intel is unavailable.
    """
    try:
        r = requests.get(
            "http://127.0.0.1:8001/api/articles/signals",
            timeout=10,
        )
        if r.status_code != 200:
            return 0, 0
        data = r.json()
        topic_heat = data.get("topic_heat", [])
        accel = sum(1 for t in topic_heat if t.get("momentum_label") == "accelerating")
        decel = sum(1 for t in topic_heat if t.get("momentum_label") == "decelerating")
        return accel, decel
    except Exception:
        return 0, 0


# ═══════════════════════════════════════════════════════════════
# 9. 快讯 + 经济日历
# ═══════════════════════════════════════════════════════════════
@safe_section("快讯")
def section_news() -> list[str]:
    lines = ["📰 **快讯**"]
    news = fetch("/api/us-stock/news")
    news_list = news if isinstance(news, list) else news.get("news", news.get("data", news.get("articles", [])))
    if not news_list:
        return lines + ["  暂无快讯"]
    for n in (news_list or [])[:4]:
        src = n.get("source", "")
        title = n.get("title", "")
        if title:
            lines.append(f"  • [{src}] {title[:60]}")
    return lines


@safe_section("经济日历")
def section_calendar() -> list[str]:
    lines = ["📅 **经济日历**"]
    cal = fetch("/api/us-stock/calendar")
    events = cal.get("events", cal.get("data", []))
    if not events:
        return lines + ["  暂无近期事件"]
    for e in events[:3]:
        date = e.get("date", "")
        event = e.get("event", e.get("name", ""))
        lines.append(f"  • {date} {event}")
    return lines


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════
def main():
    """收集数据 → 逐 section 生成 → 组装输出"""

    # ── Data Gathering ──────────────────────────────────────
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

    # 提取关键值供多个 section 复用
    sp500_pct = _q_pct(idx_quotes, "^GSPC")
    vix_price = _q_price(idx_quotes, "^VIX")
    vix_pct = _q_pct(idx_quotes, "^VIX")

    # ── Build Output ────────────────────────────────────────
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    output = [f"🇺🇸 **美股简报** | {now}", ""]

    # 1. 三大指数
    output.extend(section_indexes(idx_quotes))
    output.append("")

    # 2. 板块轮动分析
    output.extend(section_sector_rotation(sector_list))
    output.append("")

    # 3. 异动检测
    output.extend(section_movers(all_wl_quotes))
    output.append("")

    # 4. Mag7 深度分析
    output.extend(section_mag7_analysis(mag_quotes, sp500_pct))
    output.append("")

    # 5. 中概股
    output.extend(section_china_adr(adr_quotes))
    output.append("")

    # 6. 跨资产联动
    output.extend(section_cross_asset(
        commod_quotes, bond_quotes, forex_quotes,
        sp500_pct, vix_price, vix_pct,
    ))
    output.append("")

    # 7. 舆情信号
    output.extend(section_intel())
    output.append("")

    # 8. Wendy 深度分析
    output.extend(section_wendy_analysis(
        idx_quotes, sector_list, mag_quotes,
        commod_quotes, bond_quotes, forex_quotes,
    ))
    output.append("")

    # 9. 快讯 + 经济日历
    output.extend(section_news())
    output.append("")
    output.extend(section_calendar())

    output.append("")
    output.append(f"{'═' * 50}")
    output.append(f"⏱ 生成时间: {datetime.now().strftime('%H:%M:%S')} | 数据仅供参考")

    full_text = "\n".join(output)
    print(full_text)

    # ── Auto-push to Notion ──
    try:
        from scripts.push_us_to_notion import push_us_briefing_to_notion
        push_us_briefing_to_notion(full_text)
    except Exception:
        try:
            from push_us_to_notion import push_us_briefing_to_notion
            push_us_briefing_to_notion(full_text)
        except Exception:
            pass  # Notion push is optional


if __name__ == "__main__":
    main()
