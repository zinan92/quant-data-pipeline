#!/usr/bin/env python3
"""
完整市场简报 v1 — 7大模块一次性输出
=============================================
用法: python scripts/full_briefing.py
输出: 完整简报文本到 stdout，可直接推送

模块:
1. A股指数        — 本地API实时行情
2. 异动统计        — /api/news/market-alerts
3. 盘中全程回顾表格  — today_index_snapshots.json
4. FLOW-TOP20     — akshare 实时概念资金流
5. 🧠 Wendy分析   — 规则引擎，纯确定性
6. 自选股异动      — 自选股涨跌排行
7. 快讯           — /api/news/latest

附加: 每次运行自动保存指数快照
"""

import sys
import json
import time
import traceback
import requests
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOT_FILE = PROJECT_ROOT / "data" / "snapshots" / "intraday" / "today_index_snapshots.json"
SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)

API_BASE = "http://127.0.0.1:8000"
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}

INDEX_CODES = [
    ("000001.SH", "上证指数"),
    ("399001.SZ", "深证成指"),
    ("399006.SZ", "创业板指"),
    ("000688.SH", "科创50"),
]


# ═══════════════════════════════════════════════════════════════
# Helper: safe section wrapper
# ═══════════════════════════════════════════════════════════════
def safe_section(name):
    """Decorator: if a section fails, print error and continue."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                return [f"⚠️ [{name}] 获取失败: {e}"]
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════
# 0. Save index snapshot (runs every time)
# ═══════════════════════════════════════════════════════════════
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
        # Avoid duplicate timestamps
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
        pass  # Non-critical


# ═══════════════════════════════════════════════════════════════
# 1. A股指数
# ═══════════════════════════════════════════════════════════════
def fetch_indices() -> dict:
    """Fetch index data from local API."""
    result = {}
    for code, fallback_name in INDEX_CODES:
        try:
            r = requests.get(f"{API_BASE}/api/index/realtime/{code}", timeout=5)
            if r.ok:
                d = r.json()
                result[code] = {
                    "name": d.get("name", fallback_name),
                    "price": d.get("price", 0),
                    "pct": d.get("change_pct", 0),
                    "amount": d.get("amount", 0),
                    "last_update": d.get("last_update", ""),
                }
        except Exception:
            pass
    return result


@safe_section("A股指数")
def section_indices(index_data: dict) -> list[str]:
    lines = ["📈 **A股指数**"]
    if not index_data:
        return lines + ["  数据暂无"]

    for code, _ in INDEX_CODES:
        if code not in index_data:
            continue
        d = index_data[code]
        emoji = "🟢" if d["pct"] >= 0 else "🔴"
        sign = "+" if d["pct"] >= 0 else ""
        amt_yi = d["amount"] / 1e4 if d["amount"] else 0  # amount in万 → 亿
        lines.append(
            f"  {emoji} {d['name']}: {d['price']:.2f} ({sign}{d['pct']:.2f}%)"
            + (f" 成交:{amt_yi:.0f}亿" if amt_yi > 0 else "")
        )
    return lines


# ═══════════════════════════════════════════════════════════════
# 2. 异动统计
# ═══════════════════════════════════════════════════════════════
@safe_section("异动统计")
def section_alerts() -> list[str]:
    r = requests.get(f"{API_BASE}/api/news/market-alerts", timeout=10)
    data = r.json()

    limit_up = data.get("封涨停板", {})
    limit_down = data.get("封跌停板", {})
    big_buy = data.get("大笔买入", {})
    big_sell = data.get("大笔卖出", {})

    up_count = limit_up.get("count", 0)
    down_count = limit_down.get("count", 0)
    buy_count = big_buy.get("count", 0)
    sell_count = big_sell.get("count", 0)

    # Top names
    up_names = [t["name"] for t in limit_up.get("top", [])[:5]]
    down_names = [t["name"] for t in limit_down.get("top", [])[:5]]

    up_str = "、".join(up_names) if up_names else "—"
    down_str = "、".join(down_names) if down_names else "—"
    net = buy_count - sell_count

    lines = [
        "⚡ **异动统计**",
        f"  🟢 涨停: {up_count}只 | {up_str}",
        f"  🔴 跌停: {down_count}只 | {down_str}",
        f"  💰 大笔买入: {buy_count}只 | 🔻 大笔卖出: {sell_count}只"
        f"（净{'买' if net >= 0 else '卖'}入{abs(net)}只差额）",
    ]
    return lines


# ═══════════════════════════════════════════════════════════════
# 3. 盘中全程回顾表格
# ═══════════════════════════════════════════════════════════════
@safe_section("盘中回顾")
def section_intraday_table() -> list[str]:
    if not SNAPSHOT_FILE.exists():
        return ["📋 **盘中全程回顾**", "  暂无快照数据"]

    data = json.loads(SNAPSHOT_FILE.read_text())
    snapshots = data.get("snapshots", [])
    if not snapshots:
        return ["📋 **盘中全程回顾**", "  暂无快照数据"]

    # Build table header
    lines = [f"📋 **盘中全程回顾** ({data.get('date', '今日')})"]

    # Track highs/lows per index
    idx_tracker = {}  # code -> {high_price, high_time, low_price, low_time}

    # Table header
    lines.append(f"{'时间':>6} | {'上证指数':>10} | {'深证成指':>11} | {'创业板指':>10}")
    lines.append(f"{'─'*6} | {'─'*10} | {'─'*11} | {'─'*10}")

    for snap in snapshots:
        t = snap["time"]
        indexes = snap.get("indexes", {})

        cols = [f"{t:>6}"]
        for code in ["000001.SH", "399001.SZ", "399006.SZ"]:
            idx = indexes.get(code, {})
            price = idx.get("price", 0)
            pct = idx.get("pct", 0)

            if price > 0:
                sign = "+" if pct >= 0 else ""
                col_str = f"{price:.2f}({sign}{pct:.2f}%)"

                # Track high/low
                if code not in idx_tracker:
                    idx_tracker[code] = {
                        "name": idx.get("name", code),
                        "high_price": price, "high_time": t, "high_pct": pct,
                        "low_price": price, "low_time": t, "low_pct": pct,
                    }
                else:
                    tr = idx_tracker[code]
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

            # Pad to match header width
            if code == "399001.SZ":
                cols.append(f"{col_str:>11}")
            else:
                cols.append(f"{col_str:>10}")
        lines.append(" | ".join(cols))

    # High/Low summary
    if idx_tracker:
        lines.append("")
        lines.append("📍 **高低点:**")
        for code in ["000001.SH", "399001.SZ", "399006.SZ"]:
            if code in idx_tracker:
                tr = idx_tracker[code]
                lines.append(
                    f"  {tr['name']}: "
                    f"高点 {tr['high_price']:.2f}({tr['high_pct']:+.2f}%) @{tr['high_time']} | "
                    f"低点 {tr['low_price']:.2f}({tr['low_pct']:+.2f}%) @{tr['low_time']}"
                )

    return lines


# ═══════════════════════════════════════════════════════════════
# 4. FLOW-TOP20 (实时概念资金流)
# ═══════════════════════════════════════════════════════════════
def fetch_concept_flow():
    """Fetch realtime concept flow via akshare."""
    import akshare as ak
    df = ak.stock_fund_flow_concept(symbol="即时")
    return df


@safe_section("FLOW-TOP20")
def section_flow_top20() -> tuple[list[str], object]:
    """Returns (lines, df) — df is used by section_analysis."""
    df = fetch_concept_flow()

    total = len(df)
    net_in = len(df[df["净额"] > 0])
    net_out = len(df[df["净额"] <= 0])

    # Sort by 净额 descending (should already be, but ensure)
    df_sorted = df.sort_values("净额", ascending=False).reset_index(drop=True)

    lines = [
        f"💰 **FLOW-TOP20 (实时概念资金流)**",
        f"共{total}个概念 | {net_in}个净流入 | {net_out}个净流出",
        "",
    ]

    # Top 20 inflow
    top20 = df_sorted.head(20)
    for i, (_, row) in enumerate(top20.iterrows(), 1):
        name = row["行业"]
        net = row["净额"]
        pct = row["行业-涨跌幅"]
        lead = row["领涨股"]
        lead_pct = row["领涨股-涨跌幅"]
        count = row["公司家数"]
        sign = "+" if net >= 0 else ""
        lines.append(
            f"  {i:>2}. {name} {sign}{net:.2f}亿 | {pct:+.2f}% | "
            f"{count}只 | 领涨:{lead}({lead_pct:+.2f}%)"
        )

    # Bottom 5 outflow
    bot5 = df_sorted.tail(5).iloc[::-1]  # Most negative last
    lines.append("")
    lines.append("  📉 **净流出前5:**")
    for _, row in bot5.iterrows():
        name = row["行业"]
        net = row["净额"]
        pct = row["行业-涨跌幅"]
        lines.append(f"  • {name} {net:.2f}亿 | {pct:+.2f}%")

    return lines, df_sorted


# ═══════════════════════════════════════════════════════════════
# 5. 🧠 Wendy分析 (Rule-based, ZERO AI)
# ═══════════════════════════════════════════════════════════════
@safe_section("Wendy分析")
def section_analysis(index_data: dict, flow_df, alert_data: dict = None) -> list[str]:
    lines = ["🧠 **Wendy分析**"]

    # ── 5a. 市场定性: 上证 vs 创业板剪刀差 ──
    sh_pct = index_data.get("000001.SH", {}).get("pct", 0)
    cy_pct = index_data.get("399006.SZ", {}).get("pct", 0)
    scissor = sh_pct - cy_pct  # Positive = 上证强于创业板

    if scissor > 1.0:
        market_tone = "⚠️ Risk OFF (大盘股避险，小盘承压)"
    elif scissor < -1.0:
        market_tone = "🚀 Risk ON (成长股活跃，资金做多小盘)"
    elif sh_pct > 0.5 and cy_pct > 0.5:
        market_tone = "🟢 普涨行情"
    elif sh_pct < -0.5 and cy_pct < -0.5:
        market_tone = "🔴 普跌行情"
    else:
        market_tone = "⚖️ 中性震荡"

    lines.append(f"")
    lines.append(f"**市场定性:** {market_tone}")
    lines.append(f"  上证 {sh_pct:+.2f}% vs 创业板 {cy_pct:+.2f}% → 剪刀差 {scissor:+.2f}%")

    # ── 5b. 资金轮动 ──
    lines.append("")
    lines.append("**资金轮动:**")
    if flow_df is not None and len(flow_df) > 0:
        top3_in = flow_df.head(3)
        top3_out = flow_df.tail(3).iloc[::-1]

        in_names = " / ".join(
            [f"{r['行业']}(+{r['净额']:.1f}亿)" for _, r in top3_in.iterrows()]
        )
        out_names = " / ".join(
            [f"{r['行业']}({r['净额']:.1f}亿)" for _, r in top3_out.iterrows()]
        )
        lines.append(f"  🔺 主力流入: {in_names}")
        lines.append(f"  🔻 主力流出: {out_names}")
    else:
        lines.append("  数据暂无")

    # ── 5c. 关键信号 ──
    lines.append("")
    lines.append("**关键信号:**")

    # Signal 1: 剪刀差
    lines.append(f"  • 上证/创业板剪刀差: {scissor:+.2f}%")

    # Signal 2: 净流入/流出比
    if flow_df is not None and len(flow_df) > 0:
        n_in = len(flow_df[flow_df["净额"] > 0])
        n_out = len(flow_df[flow_df["净额"] <= 0])
        total_concepts = len(flow_df)
        pct_in = n_in / total_concepts * 100 if total_concepts > 0 else 0
        ratio_str = f"{n_in}:{n_out}"
        lines.append(f"  • 净流入/流出比: {ratio_str} ({pct_in:.0f}%概念净流入)")

        # Total net flow
        total_net = flow_df["净额"].sum()
        lines.append(f"  • 全市场概念净额合计: {total_net:+.1f}亿")
    else:
        n_in, n_out, pct_in, total_net = 0, 0, 0, 0

    # Signal 3: 涨停/跌停比
    up_count = 0
    down_count = 0
    if alert_data:
        up_count = alert_data.get("封涨停板", {}).get("count", 0)
        down_count = alert_data.get("封跌停板", {}).get("count", 0)
    if up_count + down_count > 0:
        ud_ratio = up_count / down_count if down_count > 0 else float('inf')
        lines.append(f"  • 涨停/跌停比: {up_count}:{down_count} ({ud_ratio:.1f}x)")
    else:
        ud_ratio = 1.0

    # ── 5d. 🛡️ 护盘指标 (银行+保险+证券) ──
    lines.append("")
    lines.append("**🛡️ 护盘指标:**")
    # Map: display name → search keyword (同花顺概念名: 参股银行/参股保险/参股券商)
    護盘_sectors = {"银行": "参股银行", "保险": "参股保险", "证券": "参股券商"}
    護盘_data = {}  # display_name -> {net, pct, name}
    護盘_total = 0
    護盘_count = 0
    if flow_df is not None and len(flow_df) > 0:
        for display_name, search_key in 護盘_sectors.items():
            match = flow_df[flow_df["行业"] == search_key]
            if len(match) == 0:
                # Fallback: fuzzy match
                match = flow_df[flow_df["行业"].str.contains(search_key, na=False)]
            if len(match) > 0:
                row = match.iloc[0]
                net = row["净额"]
                pct = row["行业-涨跌幅"]
                護盘_data[display_name] = {"net": net, "pct": pct, "name": row["行业"]}
                護盘_total += net
                if net > 0:
                    護盘_count += 1

        sector_strs = []
        for display_name in 護盘_sectors:
            v = 護盘_data.get(display_name)
            if v is not None:
                emoji = "🟢" if v["net"] > 0 else "🔴"
                sector_strs.append(f"{emoji}{display_name} {v['net']:+.1f}亿({v['pct']:+.2f}%)")
            else:
                sector_strs.append(f"⚪{display_name} 无数据")
        lines.append(f"  {' | '.join(sector_strs)}")

        if 護盘_count == 3:
            lines.append(f"  ⚠️ 三大金融板块全部净流入({護盘_total:+.1f}亿) → **国家护盘信号**，科技/成长抛压大")
        elif 護盘_count >= 2:
            lines.append(f"  🟡 {護盘_count}/3金融板块净流入({護盘_total:+.1f}亿) → 有护盘迹象")
        elif 護盘_total < -10:
            lines.append(f"  🟢 金融板块净流出({護盘_total:+.1f}亿) → 无需护盘，资金在进攻")
        else:
            lines.append(f"  ⚖️ 金融板块中性({護盘_total:+.1f}亿)")
    else:
        lines.append("  数据暂无")

    # ── 5e. 📏 趋势强度标尺 ──
    lines.append("")
    lines.append("**📏 趋势强度:**")
    trend_strength = "未知"
    top1_net = 0
    # Exclude broad/index-level concepts — only real sector themes count
    BROAD_CONCEPTS = [
        "证金持股", "同花顺漂亮", "同花顺中特估", "融资融券", "深股通",
        "沪股通", "超级品牌", "参股银行", "参股保险", "参股券商",
    ]
    if flow_df is not None and len(flow_df) > 0:
        theme_df = flow_df[~flow_df["行业"].apply(
            lambda x: any(b in x for b in BROAD_CONCEPTS)
        )].reset_index(drop=True)

        if len(theme_df) == 0:
            theme_df = flow_df  # Fallback

        top1 = theme_df.iloc[0]
        top1_net = abs(top1["净额"])
        top1_name = top1["行业"]

        if top1_net >= 200:
            trend_strength = "🔥 强趋势"
            trend_desc = f"主线明确，可以跟"
        elif top1_net >= 100:
            trend_strength = "📊 中等趋势"
            trend_desc = f"有方向但力度一般"
        else:
            trend_strength = "😶 弱趋势/无主线"
            trend_desc = f"资金分散，无明确方向"

        lines.append(f"  #1 {top1_name}: {top1['净额']:+.1f}亿 → {trend_strength}（{trend_desc}）")

        # TOP10 concentration check (using theme_df, excludes broad indices)
        top10 = theme_df.head(10)
        top10_names = top10["行业"].tolist()
        # Simple sector clustering: check if keywords repeat
        sector_keywords = {
            "光伏/电池": ["光伏", "电池", "TOPCON", "BC", "HJT", "钙钛矿", "硅"],
            "AI/科技": ["人工智能", "AI", "算力", "芯片", "数据中心", "机器人"],
            "新能源车": ["新能源车", "锂电", "充电桩", "汽车"],
            "煤炭/能源": ["煤炭", "石油", "天然气", "能源"],
        }
        cluster_counts = {}
        for label, keywords in sector_keywords.items():
            count = sum(1 for name in top10_names if any(kw in name for kw in keywords))
            if count >= 2:
                cluster_counts[label] = count

        if cluster_counts:
            dominant = max(cluster_counts, key=cluster_counts.get)
            lines.append(f"  TOP10集中度: {dominant}占{cluster_counts[dominant]}/10 — 今日唯一主线")
            if len(cluster_counts) > 1:
                others = [f"{k}({v})" for k, v in cluster_counts.items() if k != dominant]
                lines.append(f"  其他线索: {', '.join(others)}")
        else:
            lines.append(f"  TOP10集中度: 分散，无明显主线集中")
    else:
        lines.append("  数据暂无")

    # ── 5f. 🍷 白酒/消费避险信号 ──
    lines.append("")
    lines.append("**🍷 避险信号:**")
    baijiu_net = None
    if flow_df is not None and len(flow_df) > 0:
        baijiu_match = flow_df[flow_df["行业"].str.contains("白酒", na=False)]
        if len(baijiu_match) > 0:
            bj = baijiu_match.iloc[0]
            baijiu_net = bj["净额"]
            bj_pct = bj["行业-涨跌幅"]
            emoji = "🟢" if baijiu_net > 0 else "🔴"
            lines.append(f"  白酒板块: {emoji} {baijiu_net:+.1f}亿 ({bj_pct:+.2f}%)")

            if baijiu_net > 10 and 護盘_count >= 2:
                lines.append(f"  🚨 白酒+金融同时流入 → **极端避险模式**，科技抛压极大")
            elif baijiu_net > 10:
                lines.append(f"  ⚠️ 白酒资金流入 → 防御性配置，Risk OFF信号")
            elif baijiu_net < -10:
                lines.append(f"  🟢 白酒资金流出 → 非避险，资金偏进攻")
            else:
                lines.append(f"  ⚖️ 白酒中性")
        else:
            lines.append("  白酒板块: 无数据")
    else:
        lines.append("  数据暂无")

    # ── 5g. 操作建议 (Template-based) ──
    lines.append("")
    lines.append("**操作建议:**")

    # Determine market regime and give template advice
    signals_bullish = 0
    signals_bearish = 0

    # Scoring
    if sh_pct > 0.3:
        signals_bullish += 1
    if sh_pct < -0.3:
        signals_bearish += 1
    if cy_pct > 0.3:
        signals_bullish += 1
    if cy_pct < -0.3:
        signals_bearish += 1
    if pct_in > 50:
        signals_bullish += 1
    if pct_in < 30:
        signals_bearish += 1
    if up_count > down_count * 1.5:
        signals_bullish += 1
    if down_count > up_count * 1.5:
        signals_bearish += 1
    if flow_df is not None and len(flow_df) > 0:
        if total_net > 0:
            signals_bullish += 1
        elif total_net < -50:
            signals_bearish += 1

    # Park's Three Signals integration
    if 護盘_count == 3:
        signals_bearish += 1  # Full 护盘 = bearish for growth
    if top1_net < 100:
        signals_bearish += 1  # Weak trend = no conviction
    elif top1_net >= 200:
        signals_bullish += 1  # Strong trend
    if baijiu_net is not None and baijiu_net > 10 and 護盘_count >= 2:
        signals_bearish += 2  # Extreme risk-off

    if signals_bullish >= 4:
        advice = "✅ 多头占优，可积极参与强势板块，关注资金流入TOP概念"
    elif signals_bearish >= 4:
        advice = "🛑 空头占优，建议减仓观望或仅做确定性机会，控制仓位"
    elif signals_bullish >= 3 and signals_bearish <= 1:
        advice = "🟢 偏多格局，可适当参与领涨板块，注意分散风险"
    elif signals_bearish >= 3 and signals_bullish <= 1:
        advice = "🟡 偏弱格局，轻仓操作，关注防御板块和超跌反弹机会"
    elif scissor > 1.5:
        advice = "⚠️ 大小盘分化严重，关注权重股机会，回避小盘题材"
    elif scissor < -1.5:
        advice = "🔄 题材活跃但权重拖累，精选强势概念，快进快出"
    else:
        advice = "⚖️ 震荡格局，保持仓位灵活，关注主线方向确认"

    lines.append(f"  {advice}")
    lines.append(f"  (多头信号: {signals_bullish} | 空头信号: {signals_bearish})")

    return lines


# ═══════════════════════════════════════════════════════════════
# 6. 自选股异动
# ═══════════════════════════════════════════════════════════════
@safe_section("自选股异动")
def section_watchlist() -> list[str]:
    # Get watchlist
    r = requests.get(f"{API_BASE}/api/watchlist", timeout=10)
    if r.status_code != 200:
        return ["⭐ **自选股异动**", "  获取自选股列表失败"]
    watchlist = r.json()
    if not watchlist:
        return ["⭐ **自选股异动**", "  自选股列表为空"]

    tickers = [w["ticker"] for w in watchlist]
    name_map = {w["ticker"]: w["name"] for w in watchlist}

    # Fetch prices via Sina
    results = []
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
                                results.append((name_map.get(ticker, ticker), ticker, pct, cur))
                        except (ValueError, ZeroDivisionError):
                            pass
        except Exception:
            pass
        time.sleep(0.2)

    if not results:
        return ["⭐ **自选股异动**", "  无法获取行情数据"]

    results.sort(key=lambda x: x[2], reverse=True)
    top5 = results[:5]
    bot5 = results[-5:]

    lines = ["⭐ **自选股异动**"]
    lines.append("  📈 **涨幅前5:**")
    for name, ticker, pct, price in top5:
        emoji = "🟢" if pct >= 0 else "🔴"
        lines.append(f"    {emoji} {name}({ticker}) {pct:+.2f}% 现价:{price:.2f}")
    lines.append("  📉 **跌幅前5:**")
    for name, ticker, pct, price in bot5:
        emoji = "🟢" if pct >= 0 else "🔴"
        lines.append(f"    {emoji} {name}({ticker}) {pct:+.2f}% 现价:{price:.2f}")

    return lines


# ═══════════════════════════════════════════════════════════════
# 7. 快讯
# ═══════════════════════════════════════════════════════════════
@safe_section("快讯")
def section_news() -> list[str]:
    r = requests.get(f"{API_BASE}/api/news/latest", timeout=10)
    data = r.json()
    news_list = data.get("news", [])

    lines = ["📰 **快讯**"]
    if not news_list:
        lines.append("  暂无快讯")
        return lines

    for item in news_list[:8]:
        title = item.get("title", "")[:80]
        t = item.get("time", "")
        # Extract just HH:MM from time string
        if t and len(t) >= 16:
            t = t[11:16]
        lines.append(f"  • [{t}] {title}")

    return lines


# ═══════════════════════════════════════════════════════════════
# Main: Assemble all sections
# ═══════════════════════════════════════════════════════════════
def main():
    now = datetime.now()
    time_label = now.strftime("%Y-%m-%d %H:%M")

    output_lines = [
        f"{'═' * 50}",
        f"📊 **全市场简报** ({time_label})",
        f"{'═' * 50}",
    ]

    # ── 1. A股指数 ──
    index_data = fetch_indices()
    output_lines.extend(section_indices(index_data))

    # Save snapshot (side effect)
    if index_data:
        save_index_snapshot(index_data)

    output_lines.append("")

    # ── 2. 异动统计 ──
    output_lines.extend(section_alerts())
    output_lines.append("")

    # Fetch alert data for analysis section
    alert_data = None
    try:
        r = requests.get(f"{API_BASE}/api/news/market-alerts", timeout=10)
        alert_data = r.json()
    except Exception:
        pass

    # ── 3. 盘中全程回顾表格 ──
    output_lines.extend(section_intraday_table())
    output_lines.append("")

    # ── 4. FLOW-TOP20 ──
    flow_result = section_flow_top20()
    flow_df = None
    if isinstance(flow_result, tuple):
        flow_lines, flow_df = flow_result
        output_lines.extend(flow_lines)
    else:
        # Error case — flow_result is just lines
        output_lines.extend(flow_result)
    output_lines.append("")

    # ── 5. Wendy分析 ──
    output_lines.extend(section_analysis(index_data, flow_df, alert_data))
    output_lines.append("")

    # ── 6. 自选股异动 ──
    output_lines.extend(section_watchlist())
    output_lines.append("")

    # ── 7. 快讯 ──
    output_lines.extend(section_news())

    output_lines.append("")
    output_lines.append(f"{'═' * 50}")
    output_lines.append(f"⏱ 生成时间: {datetime.now().strftime('%H:%M:%S')} | 数据仅供参考")

    print("\n".join(output_lines))


if __name__ == "__main__":
    main()
