#!/usr/bin/env python3

"""
统一版全量简报 - 集成版本
包含：指数、flow、异动、Wendy分析、自选股、快讯
可通过 --time/--closing/--midday 参数支持多时段

使用方式:
    python3 scripts/full_briefing.py --time closing
    python3 scripts/full_briefing.py --time midday  
    python3 scripts/full_briefing.py --time opening
"""

import json
import requests
import sys
import time
from datetime import datetime
from typing import Optional
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOT_FILE = PROJECT_ROOT / "data" / "snapshots" / "intraday" / "today_index_snapshots.json"
VOLUME_HISTORY_FILE = PROJECT_ROOT / "data" / "snapshots" / "daily_volume_history.json"
SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)

API_BASE = "http://127.0.0.1:8000"
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
                return [f"⚠️ [{section_name}] 获取失败: {e}"]
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════
# 1. A股指数
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
                        amount = float(data[9]) if data[9] else 0  # 成交金额(元)
                        
                        # Find name
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
        
        # Yesterday's volume
        yesterday = history[-1] if history else {}
        
        # 5-day average
        recent_5 = history[-5:] if len(history) >= 5 else history
        avg_5_total = sum(h.get("total", 0) for h in recent_5) / len(recent_5) if recent_5 else 0
        
        return {
            "yesterday_total": yesterday.get("total", 0),
            "avg_5_total": avg_5_total,
        }
    except Exception:
        return {}


@safe_section("A股指数")
def section_indices(index_data: dict) -> list[str]:
    lines = ["📈 **A股指数**"]
    if not index_data:
        return lines + ["  数据暂无"]

    # Calculate total volume
    total_amount = 0
    for code, _ in INDEX_CODES:
        if code not in index_data:
            continue
        d = index_data[code]
        emoji = "🟢" if d["pct"] >= 0 else "🔴"
        sign = "+" if d["pct"] >= 0 else ""
        amt_yi = d["amount"] / 1e4 if d["amount"] else 0  # amount in万 → 亿
        total_amount += amt_yi
        lines.append(
            f"  {emoji} {d['name']}: {d['price']:.2f} ({sign}{d['pct']:.2f}%)"
            + (f" 成交:{amt_yi:.0f}亿" if amt_yi > 0 else "")
        )
    
    # Volume comparison
    vol_ctx = get_volume_context()
    if vol_ctx and total_amount > 0:
        lines.append("")
        yesterday = vol_ctx.get("yesterday_total", 0)
        avg_5 = vol_ctx.get("avg_5_total", 0)
        
        if yesterday > 0:
            vs_yesterday = (total_amount - yesterday) / yesterday * 100
            vol_emoji = "📈" if vs_yesterday > 10 else "📉" if vs_yesterday < -10 else "➡️"
            vol_label = "放量" if vs_yesterday > 10 else "缩量" if vs_yesterday < -10 else "平量"
            lines.append(f"  💹 两市成交:{total_amount:.0f}亿 | {vol_emoji}{vol_label}{abs(vs_yesterday):.0f}% vs昨日")
        
        if avg_5 > 0:
            vs_avg = (total_amount - avg_5) / avg_5 * 100
            avg_label = "高于" if vs_avg > 0 else "低于"
            lines.append(f"     5日均量:{avg_5:.0f}亿 ({avg_label}均值{abs(vs_avg):.0f}%)")
    
    return lines


# ═══════════════════════════════════════════════════════════════
# 2. 异动榜
# ═══════════════════════════════════════════════════════════════
@safe_section("市场异动")
def section_alerts() -> list[str]:
    try:
        r = requests.get(f"{API_BASE}/api/anomaly/alerts", timeout=20)
        if r.status_code != 200:
            return ["⚠️ **市场异动**", "  API请求失败"]
        
        alerts = r.json()
        lines = ["⚠️ **市场异动**"]
        
        if not alerts:
            lines.append("  暂无异动数据")
            return lines
        
        # Sort categories for consistent display
        categories = ["封涨停板", "封跌停板", "炸板", "急速拉升", "急速下跌", "量比放大"]
        for category in categories:
            if category in alerts:
                data = alerts[category]
                count = data.get("count", 0)
                stocks = data.get("stocks", [])
                
                if count > 0:
                    emoji = {"封涨停板": "📈", "封跌停板": "📉", "炸板": "💥"}.get(category, "⚡")
                    lines.append(f"  {emoji} {category}: {count}只")
                    
                    # Show top 3
                    for stock in stocks[:3]:
                        name = stock.get("name", "")
                        code = stock.get("code", "")
                        pct = stock.get("change_pct", 0)
                        lines.append(f"    • {name}({code}) {pct:+.2f}%")
                    
                    if len(stocks) > 3:
                        lines.append(f"    （还有{len(stocks) - 3}只...）")
        return lines
    except Exception as e:
        return ["⚠️ **市场异动**", f"  获取失败: {e}"]


# ═══════════════════════════════════════════════════════════════
# 3. 盘中路径分析 (替代原来的表格)
# ═══════════════════════════════════════════════════════════════
@safe_section("盘中路径")
def section_intraday_table() -> list[str]:
    if not SNAPSHOT_FILE.exists():
        return ["📈 **盘中路径**", "  暂无快照数据"]

    data = json.loads(SNAPSHOT_FILE.read_text())
    snapshots = data.get("snapshots", [])
    if len(snapshots) < 2:
        return ["📈 **盘中路径**", "  快照不足，无法分析"]

    lines = ["📈 **盘中路径分析**"]
    
    # 分析上证指数路径 (000001.SH)
    sh_data = []
    for snap in snapshots:
        idx = snap.get("indexes", {}).get("000001.SH", {})
        price = idx.get("price", 0)
        pct = idx.get("pct", 0)
        if price > 0:
            sh_data.append({"time": snap["time"], "price": price, "pct": pct})
    
    if len(sh_data) < 2:
        return lines + ["  数据不足"]
    
    # 关键点分析
    open_pct = sh_data[0]["pct"]
    current_pct = sh_data[-1]["pct"]
    current_price = sh_data[-1]["price"]
    current_time = sh_data[-1]["time"]
    
    # 找高低点
    high_point = max(sh_data, key=lambda x: x["price"])
    low_point = min(sh_data, key=lambda x: x["price"])
    
    # 开盘定性
    if open_pct < -0.5:
        open_desc = f"低开{abs(open_pct):.1f}%"
    elif open_pct > 0.5:
        open_desc = f"高开{open_pct:.1f}%"
    else:
        open_desc = "平开"
    
    # 走势描述
    path_parts = []
    path_parts.append(f"开盘{open_desc}")
    
    # 分析走势阶段
    if len(sh_data) >= 3:
        # 前1/3时段
        early_idx = len(sh_data) // 3
        early_pct = sh_data[early_idx]["pct"]
        early_time = sh_data[early_idx]["time"]
        
        if early_pct < open_pct - 0.3:
            path_parts.append(f"早盘下探至{early_pct:+.1f}%")
        elif early_pct > open_pct + 0.3:
            path_parts.append(f"早盘拉升至{early_pct:+.1f}%")
        else:
            path_parts.append("早盘窄幅震荡")
    
    # 低点到现在的走势
    if low_point["pct"] < current_pct - 0.5 and low_point["time"] < current_time:
        recovery = current_pct - low_point["pct"]
        path_parts.append(f"从{low_point['time']}低点{low_point['pct']:+.1f}%反弹{recovery:.1f}%")
    elif high_point["pct"] > current_pct + 0.5 and high_point["time"] < current_time:
        drop = high_point["pct"] - current_pct
        path_parts.append(f"从{high_point['time']}高点{high_point['pct']:+.1f}%回落{drop:.1f}%")
    
    # 当前状态
    lines.append(f"  **上证**: {' → '.join(path_parts)}")
    lines.append(f"  **现价**: {current_price:.2f} ({current_pct:+.2f}%) @{current_time}")
    
    # 形态判断
    amplitude = high_point["pct"] - low_point["pct"]
    if current_pct > 0.8:
        candle = "中阳线" if current_pct < 2 else "大阳线"
    elif current_pct < -0.8:
        candle = "中阴线" if current_pct > -2 else "大阴线"
    elif amplitude < 0.5:
        candle = "十字星"
    else:
        candle = "小阳线" if current_pct > 0 else "小阴线"
    
    lines.append(f"  **形态**: {candle} | 振幅{amplitude:.1f}%")
    
    # 趋势预判
    lines.append("")
    if current_pct > 0.5 and low_point["time"] < "10:30" and current_time >= "11:00":
        lines.append("  💡 *早盘探底回升，下午大概率延续涨势*")
    elif current_pct < -0.5 and high_point["time"] < "10:30":
        lines.append("  💡 *早盘冲高回落，下午或继续承压*")
    elif amplitude > 2 and abs(current_pct) < 0.5:
        lines.append("  💡 *振幅大但收盘中性，多空分歧大*")
    elif current_pct > 0 and amplitude < 1:
        lines.append("  💡 *窄幅上涨，走势平稳*")
    elif current_pct < 0 and amplitude < 1:
        lines.append("  💡 *窄幅下跌，抛压有限*")
    else:
        lines.append("  💡 *走势正常，关注下午能否突破*")

    return lines


# ═══════════════════════════════════════════════════════════════
# 4. FLOW-TOP20 (概念资金流向)
# ═══════════════════════════════════════════════════════════════
def section_flow_top20() -> tuple[list[str], Optional]:
    try:
        r = requests.get(f"{API_BASE}/api/rotation/top-inflow", timeout=10)
        if r.status_code != 200:
            return ["💰 **Flow-TOP20**", "  API请求失败"], None
        
        df = r.json()
        if not df:
            return ["💰 **Flow-TOP20**", "  数据为空"], None
    except Exception as e:
        return ["💰 **Flow-TOP20**", f"  获取失败: {e}"], None

    import pandas as pd
    df = pd.DataFrame(df)
    
    # Remap new API column names to legacy names used throughout this function
    col_map = {"name": "行业", "net_inflow": "净额", "pct_change": "涨跌幅"}
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    
    # Add placeholder columns for leader stock (not available in new API)
    if "领涨股" not in df.columns:
        df["领涨股"] = ""
    if "领涨股-涨跌幅" not in df.columns:
        df["领涨股-涨跌幅"] = 0.0
    
    total = len(df)
    net_in = len(df[df["净额"] > 0])
    net_out = total - net_in
    
    # Sort by 净额 descending (should already be, but ensure)
    df_sorted = df.sort_values("净额", ascending=False).reset_index(drop=True)

    # ═══════════════════════════════════════════════════════════════
    # 主题聚合分析 — 把相关概念归类，算出真正的主线资金规模
    # ═══════════════════════════════════════════════════════════════
    THEME_KEYWORDS = {
        "电池/新能源车": ["锂电池", "储能", "固态电池", "钠离子", "新能源汽车", "比亚迪", "宁德时代", "动力电池", "电解液", "正极", "负极", "隔膜", "充电桩"],
        "机器人": ["机器人", "人形机器人", "减速器", "伺服", "工业母机"],
        "AI/算力": ["AI应用", "人工智能", "算力", "数据中心", "CPO", "光模块", "服务器", "英伟达", "华为昇腾"],
        "半导体": ["芯片", "半导体", "光刻", "封装", "存储", "IGBT"],
        "汽车链": ["特斯拉", "智能驾驶", "汽车电子", "线控", "一体化压铸"],
    }
    
    # 计算每个主题的总净流入
    theme_flows = {}
    theme_concepts = {}  # 记录每个主题包含哪些概念
    matched_concepts = set()
    
    for theme, keywords in THEME_KEYWORDS.items():
        theme_flows[theme] = 0
        theme_concepts[theme] = []
        for _, row in df_sorted.iterrows():
            concept_name = row["行业"]
            if concept_name in matched_concepts:
                continue
            for kw in keywords:
                if kw in concept_name:
                    theme_flows[theme] += row["净额"]
                    theme_concepts[theme].append((concept_name, row["净额"]))
                    matched_concepts.add(concept_name)
                    break
    
    # 按净流入排序
    sorted_themes = sorted(theme_flows.items(), key=lambda x: x[1], reverse=True)
    
    lines = [
        f"💰 **主线资金流分析**",
        f"共{total}个概念 | {net_in}个净流入 | {net_out}个净流出",
        "",
    ]
    
    # 输出主题聚合结果
    lines.append("**📊 今日主线（概念聚合）:**")
    main_themes = []
    for theme, total_flow in sorted_themes:
        if total_flow > 50:  # 只显示>50亿的主题
            concepts = theme_concepts[theme]
            concept_count = len(concepts)
            if concept_count > 0:
                emoji = "🔥" if total_flow > 300 else "📈" if total_flow > 100 else "📊"
                strength = "超强主线" if total_flow > 300 else "强主线" if total_flow > 150 else "主线"
                lines.append(f"  {emoji} **{theme}**: {total_flow:+.0f}亿 ({strength}, 含{concept_count}个概念)")
                main_themes.append((theme, total_flow))
    
    if not main_themes:
        lines.append("  无明显主线（各主题流入均<50亿）")
    
    lines.append("")
    
    # 过滤宽基概念，只保留真正的行业板块
    sector_df = df_sorted[~df_sorted["行业"].apply(
        lambda x: any(b in x for b in BROAD_CONCEPTS_FILTER)
    )].reset_index(drop=True)
    
    # 真正的行业TOP5
    lines.append("**📋 行业板块TOP5:**")
    top5 = sector_df.head(5)
    for i, (_, row) in enumerate(top5.iterrows(), 1):
        name = row["行业"]
        net = row["净额"]
        lead = row.get("领涨股", "")
        pct = row.get("涨跌幅", 0)
        if lead:
            lead_pct = row.get("领涨股-涨跌幅", 0)
            lines.append(f"  {i}. {name} {net:+.0f}亿 | 领涨:{lead}({lead_pct:+.1f}%)")
        else:
            lines.append(f"  {i}. {name} {net:+.0f}亿 | 板块{pct:+.1f}%")

    # 流出前3 (也过滤宽基)
    bot3 = sector_df.tail(3).iloc[::-1]
    lines.append("**📉 流出前3:**")
    for _, row in bot3.iterrows():
        name = row["行业"]
        net = row["净额"]
        lines.append(f"  • {name} {net:.0f}亿")

    return lines, df_sorted


# ═══════════════════════════════════════════════════════════════
# 5. 🧠 Wendy分析 (Rule-based, ZERO AI) — 重Insight版
# ═══════════════════════════════════════════════════════════════
@safe_section("Wendy分析")
def section_analysis(index_data: dict, flow_df, alert_data: dict = None) -> list[str]:
    lines = ["🧠 **Wendy 深度分析**"]
    lines.append("")

    # ══════════════════════════════════════════════════════════
    # 基础数据提取
    # ══════════════════════════════════════════════════════════
    sh_pct = index_data.get("000001.SH", {}).get("pct", 0)
    sz_pct = index_data.get("399001.SZ", {}).get("pct", 0)
    cy_pct = index_data.get("399006.SZ", {}).get("pct", 0)
    kc_pct = index_data.get("000688.SH", {}).get("pct", 0)
    scissor = sh_pct - cy_pct

    # 涨跌停数据
    up_count = alert_data.get("封涨停板", {}).get("count", 0) if alert_data else 0
    down_count = alert_data.get("封跌停板", {}).get("count", 0) if alert_data else 0
    ud_ratio = up_count / down_count if down_count > 0 else float('inf')

    # 资金流数据
    n_in, n_out, pct_in, total_net = 0, 0, 0, 0
    top1_name, top1_net = "", 0
    護盘_count, 護盘_total = 0, 0
    baijiu_net = None
    theme_clusters = {}

    if flow_df is not None and len(flow_df) > 0:
        n_in = len(flow_df[flow_df["净额"] > 0])
        n_out = len(flow_df[flow_df["净额"] <= 0])
        total_concepts = len(flow_df)
        pct_in = n_in / total_concepts * 100 if total_concepts > 0 else 0
        total_net = flow_df["净额"].sum()

        # 排除宽基概念
        BROAD_CONCEPTS = ["证金持股", "同花顺漂亮", "同花顺中特估", "融资融券", 
                         "深股通", "沪股通", "超级品牌", "参股银行", "参股保险", "参股券商"]
        theme_df = flow_df[~flow_df["行业"].apply(
            lambda x: any(b in x for b in BROAD_CONCEPTS)
        )].reset_index(drop=True)
        if len(theme_df) == 0:
            theme_df = flow_df
        top1 = theme_df.iloc[0]
        top1_name = top1["行业"]
        top1_net = top1["净额"]

        # 护盘板块
        護盘_sectors = {"银行": "参股银行", "保险": "参股保险", "证券": "参股券商"}
        for display_name, search_key in 護盘_sectors.items():
            match = flow_df[flow_df["行业"] == search_key]
            if len(match) == 0:
                match = flow_df[flow_df["行业"].str.contains(search_key, na=False)]
            if len(match) > 0:
                net = match.iloc[0]["净额"]
                護盘_total += net
                if net > 0:
                    護盘_count += 1

        # 白酒
        baijiu_match = flow_df[flow_df["行业"].str.contains("白酒", na=False)]
        if len(baijiu_match) > 0:
            baijiu_net = baijiu_match.iloc[0]["净额"]

        # 主题聚类
        sector_keywords = {
            "新能源/电池": ["锂电池", "储能", "固态电池", "钠离子", "新能源汽车", "比亚迪", "宁德时代", "充电桩"],
            "机器人/智造": ["机器人", "人形机器人", "减速器", "伺服", "工业母机"],
            "AI/算力": ["AI应用", "人工智能", "算力", "数据中心", "CPO", "光模块", "英伟达", "华为昇腾"],
            "半导体": ["芯片", "半导体", "光刻", "封装", "存储", "IGBT"],
            "汽车链": ["特斯拉", "智能驾驶", "汽车电子", "线控", "一体化压铸"],
        }
        top10_names = theme_df.head(10)["行业"].tolist()
        for label, keywords in sector_keywords.items():
            count = sum(1 for name in top10_names if any(kw in name for kw in keywords))
            if count >= 2:
                theme_clusters[label] = count

    # ══════════════════════════════════════════════════════════
    # 1️⃣ 今日市场画像 (一句话定性 + 原因)
    # ══════════════════════════════════════════════════════════
    lines.append("**1️⃣ 今日市场画像**")
    
    # 综合判断市场状态
    if sh_pct > 0.5 and cy_pct > 0.5 and ud_ratio > 3:
        market_state = "🔥 强势做多日"
        market_reason = f"两市普涨，涨停{up_count}只远超跌停{down_count}只，资金进攻意愿强"
    elif sh_pct < -0.5 and cy_pct < -0.5 and ud_ratio < 0.5:
        market_state = "💀 恐慌杀跌日"
        market_reason = f"两市普跌，跌停{down_count}只多于涨停，恐慌情绪蔓延"
    elif scissor > 1.5:
        market_state = "🛡️ 大盘股护盘日"
        market_reason = f"上证跑赢创业板{scissor:.1f}%，权重股拉指数、小盘股被抛售"
    elif scissor < -1.5:
        market_state = "🚀 题材炒作日"
        market_reason = f"创业板跑赢上证{-scissor:.1f}%，资金弃大做小、追逐概念"
    elif abs(sh_pct) < 0.3 and abs(cy_pct) < 0.3:
        market_state = "😴 缩量震荡日"
        market_reason = "两市波动极小，多空僵持，观望情绪浓"
    elif 護盘_count >= 2 and (baijiu_net is not None and baijiu_net > 10):
        market_state = "⚠️ 极端避险日"
        market_reason = "金融+白酒同时吸金，机构抛售成长股、涌入防御板块"
    else:
        market_state = "⚖️ 分化震荡日"
        market_reason = f"板块分化，上证{sh_pct:+.2f}% vs 创业板{cy_pct:+.2f}%"

    lines.append(f"  {market_state}")
    lines.append(f"  💡 *{market_reason}*")
    lines.append("")

    # ══════════════════════════════════════════════════════════
    # 2️⃣ 主线识别 + 持续性判断
    # ══════════════════════════════════════════════════════════
    lines.append("**2️⃣ 今日主线 & 持续性**")
    
    if top1_net >= 200:
        strength_tag = "🔥超强主线"
        persistence = "高概率延续，可重仓跟进"
    elif top1_net >= 100:
        strength_tag = "📊中等主线"
        persistence = "有延续可能，适度参与"
    elif top1_net >= 50:
        strength_tag = "📉弱主线"
        persistence = "持续性存疑，快进快出"
    else:
        strength_tag = "😶无主线"
        persistence = "资金分散，不宜追涨"

    lines.append(f"  • 主线：**{top1_name}** ({top1_net:+.0f}亿) — {strength_tag}")
    lines.append(f"  • 持续性判断：{persistence}")

    # 主题集中度分析
    if theme_clusters:
        dominant = max(theme_clusters, key=theme_clusters.get)
        lines.append(f"  • 集中度：TOP10中{dominant}占{theme_clusters[dominant]}席 → 方向明确")
        if len(theme_clusters) > 1:
            others = [f"{k}({v})" for k, v in theme_clusters.items() if k != dominant]
            lines.append(f"  • 次线索：{', '.join(others)}")
    else:
        lines.append(f"  • 集中度：TOP10分散，无明显主题聚集 → 难以持续")
    lines.append("")

    # ══════════════════════════════════════════════════════════
    # 3️⃣ 资金行为分析 (流向 vs 涨跌一致性)
    # ══════════════════════════════════════════════════════════
    lines.append("**3️⃣ 资金行为解读**")
    
    # 全市场资金流
    if total_net > 50:
        flow_state = f"🟢 净流入{total_net:.0f}亿"
        flow_meaning = "场外资金进场，行情有支撑"
    elif total_net < -50:
        flow_state = f"🔴 净流出{abs(total_net):.0f}亿"
        flow_meaning = "资金出逃，谨慎追涨"
    else:
        flow_state = f"⚖️ 净额{total_net:+.0f}亿"
        flow_meaning = "资金拉锯，方向不明"
    
    lines.append(f"  • 全市场：{flow_state} → {flow_meaning}")
    lines.append(f"  • 概念分布：{n_in}个流入 vs {n_out}个流出 ({pct_in:.0f}%正向)")

    # 资金流向 vs 指数涨跌的一致性判断
    if total_net > 30 and sh_pct > 0.3:
        consistency = "✅ 一致：资金流入+指数上涨，健康上涨"
    elif total_net < -30 and sh_pct < -0.3:
        consistency = "✅ 一致：资金流出+指数下跌，顺势调整"
    elif total_net > 30 and sh_pct < -0.3:
        consistency = "⚠️ 背离：资金净流入但指数跌 → 主力可能在吸筹"
    elif total_net < -30 and sh_pct > 0.3:
        consistency = "⚠️ 背离：资金净流出但指数涨 → 拉高出货风险"
    else:
        consistency = "⚖️ 无明显背离"
    
    lines.append(f"  • 流向vs涨跌：{consistency}")
    lines.append("")

    # ══════════════════════════════════════════════════════════
    # 4️⃣ 风险信号扫描
    # ══════════════════════════════════════════════════════════
    lines.append("**4️⃣ 风险信号**")
    
    risks = []
    
    # 护盘信号
    if 護盘_count == 3:
        risks.append(f"🚨 三大金融全部净流入({護盘_total:+.0f}亿) — 国家护盘，成长股承压")
    elif 護盘_count >= 2:
        risks.append(f"⚠️ {護盘_count}/3金融板块净流入 — 有护盘迹象")
    
    # 白酒避险
    if baijiu_net is not None and baijiu_net > 15:
        risks.append(f"⚠️ 白酒吸金{baijiu_net:.0f}亿 — 资金涌入防御，Risk OFF")
    
    # 跌停风险
    if down_count > 30:
        risks.append(f"⚠️ 跌停{down_count}只 — 个股雷区多，注意踩雷")
    
    # 涨跌停比极端
    if ud_ratio < 0.5:
        risks.append(f"🔴 涨跌停比{up_count}:{down_count} — 空头占绝对优势")
    
    # 大小盘剪刀差
    if scissor > 2:
        risks.append(f"⚠️ 大小盘剪刀差{scissor:.1f}% — 小盘股被抛弃")
    elif scissor < -2:
        risks.append(f"⚠️ 大小盘剪刀差{scissor:.1f}% — 权重拖累，指数失真")
    
    if not risks:
        lines.append("  ✅ 暂无明显风险信号")
    else:
        for r in risks:
            lines.append(f"  • {r}")
    lines.append("")

    # ══════════════════════════════════════════════════════════
    # 5️⃣ 操作建议 (结论导向)
    # ══════════════════════════════════════════════════════════
    lines.append("**5️⃣ Wendy建议**")
    
    # 综合打分
    score = 0
    if sh_pct > 0.3: score += 1
    if cy_pct > 0.3: score += 1
    if pct_in > 55: score += 1
    if ud_ratio > 2: score += 1
    if top1_net >= 150: score += 1
    if total_net > 30: score += 1
    
    if sh_pct < -0.3: score -= 1
    if cy_pct < -0.3: score -= 1
    if pct_in < 40: score -= 1
    if ud_ratio < 0.7: score -= 1
    if 護盘_count >= 2: score -= 1
    if baijiu_net is not None and baijiu_net > 10: score -= 1

    if score >= 4:
        advice = "✅ 积极做多"
        detail = f"跟进{top1_name}等主线，仓位可加到7成"
    elif score >= 2:
        advice = "🟢 偏多操作"
        detail = f"参与强势板块，控制在5成仓位"
    elif score <= -3:
        advice = "🛑 防守为主"
        detail = "降仓至3成以下，只做超跌反弹"
    elif score <= -1:
        advice = "🟡 谨慎观望"
        detail = "轻仓试探，严格止损"
    else:
        advice = "⚖️ 灵活应对"
        detail = "无明确方向，日内高抛低吸"

    lines.append(f"  **{advice}** — {detail}")
    lines.append(f"  (综合评分: {score:+d} | 多空信号比)")

    return lines


# ═══════════════════════════════════════════════════════════════
# 6. 自选股赛道汇总
# ═══════════════════════════════════════════════════════════════
@safe_section("赛道汇总")
def section_stock_sectors() -> list[str]:
    """按自定义赛道分组统计涨跌"""
    # Get watchlist with sector info
    r = requests.get(f"{API_BASE}/api/watchlist", timeout=10)
    if r.status_code != 200:
        return ["📊 **赛道汇总**", "  获取自选股列表失败"]
    watchlist = r.json()
    if not watchlist:
        return ["📊 **赛道汇总**", "  自选股列表为空"]

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
    price_data = {}  # ticker -> (price, change_pct)
    
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
            "count": 0,
            "changes": [],
            "up": 0,
            "down": 0,
            "limit_up": 0,
            "limit_down": 0,
            "max_gainer": None,
            "max_loser": None,
        }

    for ticker, sector in ticker_sector.items():
        if sector not in sector_stats:
            continue
        if ticker not in price_data:
            continue
        
        price, pct = price_data[ticker]
        name = ticker_name.get(ticker, ticker)
        
        sector_stats[sector]["count"] += 1
        sector_stats[sector]["changes"].append(pct)
        
        if pct > 0.01:
            sector_stats[sector]["up"] += 1
        elif pct < -0.01:
            sector_stats[sector]["down"] += 1
        
        if pct >= 9.9:
            sector_stats[sector]["limit_up"] += 1
        elif pct <= -9.9:
            sector_stats[sector]["limit_down"] += 1
        
        current = {"ticker": ticker, "name": name, "change": pct}
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
            "count": stats["count"],
            "avg_change": avg_change,
            "up": stats["up"],
            "down": stats["down"],
            "limit_up": stats["limit_up"],
            "limit_down": stats["limit_down"],
            "gainer": stats["max_gainer"],
            "loser": stats["max_loser"],
        })

    # Sort by avg_change desc
    results.sort(key=lambda x: x["avg_change"], reverse=True)

    # 计算整体涨跌比例
    total_sectors = len(results)
    up_sectors = sum(1 for r in results if r["avg_change"] > 0.1)
    down_sectors = sum(1 for r in results if r["avg_change"] < -0.1)
    flat_sectors = total_sectors - up_sectors - down_sectors
    
    # Risk ON/OFF 判断
    if total_sectors > 0:
        up_ratio = up_sectors / total_sectors
        if up_ratio >= 0.7:
            risk_label = "🚀 Risk ON (科技主导上涨)"
        elif up_ratio >= 0.5:
            risk_label = "🟢 偏多 (多数赛道上涨)"
        elif up_ratio <= 0.3:
            risk_label = "🛡️ Risk OFF (科技赛道承压)"
        else:
            risk_label = "⚖️ 中性分化"
    else:
        risk_label = "无数据"

    lines = ["📊 **赛道汇总** (自选股分组)"]
    if not results:
        lines.append("  无数据")
        return lines
    
    # 先显示整体统计
    lines.append(f"  **整体**: {total_sectors}赛道 | 🟢涨{up_sectors} 🔴跌{down_sectors} ➡️平{flat_sectors}")
    lines.append(f"  **判断**: {risk_label}")
    lines.append("")

    # 只显示TOP5涨 + TOP3跌（精简版）
    top5 = results[:5]
    bot3 = [r for r in results if r["avg_change"] < 0][-3:] if len([r for r in results if r["avg_change"] < 0]) >= 3 else [r for r in results if r["avg_change"] < 0]
    
    lines.append("  **涨幅前5:**")
    for r in top5:
        emoji = "🟢" if r["avg_change"] >= 0 else "🔴"
        gainer_str = f"领涨:{r['gainer']['name']}({r['gainer']['change']:+.1f}%)" if r['gainer'] else ""
        lines.append(f"    {emoji} {r['sector']} {r['avg_change']:+.2f}% | {gainer_str}")
    
    if bot3:
        lines.append("  **跌幅前3:**")
        for r in bot3[::-1]:  # 倒序显示（跌最多的在前）
            loser_str = f"领跌:{r['loser']['name']}({r['loser']['change']:+.1f}%)" if r['loser'] else ""
            lines.append(f"    🔴 {r['sector']} {r['avg_change']:+.2f}% | {loser_str}")

    return lines


# ═══════════════════════════════════════════════════════════════
# 7. 自选股异动
# ═══════════════════════════════════════════════════════════════
@safe_section("自选股异动")
def section_watchlist() -> list[str]:
    try:
        r = requests.get(f"{API_BASE}/api/watchlist/analytics", timeout=8)
        if r.status_code != 200:
            return ["📊 **自选股异动**", "  API请求失败"]
        
        data = r.json()
        lines = ["📊 **自选股异动**"]
        
        # Handle both list and dict responses
        alerts = data if isinstance(data, list) else data.get("alerts", data.get("stocks", []))
        
        if not alerts:
            return lines + ["  暂无异动"]
        
        # Show up to 8 alerts
        for i, alert in enumerate(alerts[:8], 1):
            name = alert.get("name", "")
            code = alert.get("code", alert.get("ticker", ""))
            trigger = alert.get("trigger", alert.get("signal", ""))
            value = alert.get("value", alert.get("change_pct", 0))
            
            emoji = "📈" if trigger in ["涨停", "急拉"] else "📉" if trigger in ["跌停", "急跌"] else "⚡"
            lines.append(f"  {emoji} {name}({code}) {trigger} {value:+.2f}%")
        
        return lines
    except Exception as e:
        return ["📊 **自选股异动**", f"  获取失败: {e}"]


# ═══════════════════════════════════════════════════════════════
# 8. 舆情信号 (park-intel)
# ═══════════════════════════════════════════════════════════════
@safe_section("舆情信号")
def section_intel_signals() -> list[str]:
    """Fetch qualitative signals from park-intel and format for A-share briefing."""
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

    # Use narrative_mapping to format
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.services.narrative_mapping import format_intel_section
    lines.extend(format_intel_section(data))
    return lines


# ═══════════════════════════════════════════════════════════════
# 9. 市场快讯
# ═══════════════════════════════════════════════════════════════
@safe_section("市场快讯")
def section_news() -> list[str]:
    try:
        r = requests.get(f"{API_BASE}/api/news/latest", timeout=8)
        if r.status_code != 200:
            return ["📰 **市场快讯**", "  API请求失败"]
        
        data = r.json()
        # Handle both list and {"news": [...]} responses
        news = data if isinstance(data, list) else data.get("news", data.get("data", []))
        lines = ["📰 **市场快讯**"]
        
        if not news:
            return lines + ["  暂无快讯"]
        
        # Show latest 3 news
        for item in news[:3]:
            title = item.get("title", "")
            time_str = item.get("time", "")
            if title:
                lines.append(f"  • {time_str} {title}")
        
        return lines
    except Exception as e:
        return ["📰 **市场快讯**", f"  获取失败: {e}"]


def main():
    """主函数"""
    # ── Data Gathering ──
    index_data = fetch_indices()
    flow_lines, flow_df = section_flow_top20()
    alert_data = None
    try:
        r = requests.get(f"{API_BASE}/api/anomaly/alerts", timeout=20)
        if r.status_code == 200:
            alert_data = r.json()
    except Exception:
        pass

    # ── Build Output ──
    output_lines = [
        f"🔥 **A股市场简报** | {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # ── 1. A股指数 ──
    output_lines.extend(section_indices(index_data))
    output_lines.append("")

    # ── 2. 市场异动 ──
    output_lines.extend(section_alerts())
    output_lines.append("")

    # ── 3. 盘中路径 ──
    output_lines.extend(section_intraday_table())
    output_lines.append("")

    # ── 4. FLOW-TOP20 ──
    output_lines.extend(flow_lines)
    output_lines.append("")

    # ── 5. Wendy分析 ──
    output_lines.extend(section_analysis(index_data, flow_df, alert_data))
    output_lines.append("")

    # ── 6. 自选股赛道汇总 ──
    output_lines.extend(section_stock_sectors())
    output_lines.append("")

    # ── 7. 自选股异动 ──
    output_lines.extend(section_watchlist())
    output_lines.append("")

    # ── 8. 舆情信号 ──
    output_lines.extend(section_intel_signals())
    output_lines.append("")

    # ── 9. 快讯 ──
    output_lines.extend(section_news())

    output_lines.append("")
    output_lines.append(f"{'═' * 50}")
    output_lines.append(f"⏱ 生成时间: {datetime.now().strftime('%H:%M:%S')} | 数据仅供参考")

    full_text = "\n".join(output_lines)
    print(full_text)

    # ── Auto-push to Notion ──
    try:
        from scripts.push_to_notion import push_briefing_to_notion
        push_briefing_to_notion(full_text)
    except Exception:
        try:
            from push_to_notion import push_briefing_to_notion
            push_briefing_to_notion(full_text)
        except Exception as e:
            print(f"\n⚠️ Notion推送失败（不影响主流程）: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()