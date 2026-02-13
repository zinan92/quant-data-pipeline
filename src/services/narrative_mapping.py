"""
Narrative → Ticker mapping service.

Maps park-intel's qualitative tags (topic_heat) to concrete tickers/concepts
so briefing scripts can show "what KOLs are talking about → which assets move".
"""

# tag → (US tickers, CN concept keywords)
TAG_TICKER_MAP: dict[str, dict] = {
    "ai": {
        "us": ["NVDA", "MSFT", "GOOGL", "META", "AMD"],
        "cn": ["AI概念", "算力"],
    },
    "crypto": {
        "us": ["COIN", "MSTR", "BITO"],
        "cn": ["数字货币"],
    },
    "sector/tech": {
        "us": ["SMH", "SOXX", "TSM"],
        "cn": ["半导体", "芯片"],
    },
    "sector/energy": {
        "us": ["XLE", "USO", "LIT"],
        "cn": ["新能源", "锂电池"],
    },
    "macro": {
        "us": ["TLT", "GLD", "SPY"],
        "cn": [],
    },
    "china-market": {
        "us": ["KWEB", "FXI"],
        "cn": ["沪深300"],
    },
    "us-market": {
        "us": ["SPY", "QQQ"],
        "cn": [],
    },
    "geopolitics": {
        "us": ["GLD", "UUP"],
        "cn": ["军工"],
    },
    "sector/finance": {
        "us": ["XLF", "KBE"],
        "cn": ["银行", "券商"],
    },
    "earnings": {
        "us": [],
        "cn": [],
    },
    "trading": {
        "us": [],
        "cn": [],
    },
    "regulation": {
        "us": [],
        "cn": [],
    },
    "commodities": {
        "us": ["GLD", "SLV", "USO"],
        "cn": ["有色金属", "贵金属"],
    },
}


def map_signals_to_tickers(topic_heat: list[dict]) -> list[dict]:
    """Map topic_heat items to related tickers.

    Args:
        topic_heat: list of dicts from park-intel /signals endpoint, each with
            tag, current_count, previous_count, momentum, momentum_label.

    Returns:
        list of dicts with tag, momentum_label, us_tickers, cn_concepts.
        Only includes tags that have at least one mapped ticker/concept.
    """
    results = []
    for item in topic_heat:
        tag = item.get("tag", "")
        mapping = TAG_TICKER_MAP.get(tag)
        if not mapping:
            continue
        us = mapping.get("us", [])
        cn = mapping.get("cn", [])
        if not us and not cn:
            continue
        results.append({
            "tag": tag,
            "momentum_label": item.get("momentum_label", "stable"),
            "momentum": item.get("momentum", 0),
            "current_count": item.get("current_count", 0),
            "previous_count": item.get("previous_count", 0),
            "us_tickers": us,
            "cn_concepts": cn,
        })
    return results


def format_intel_section(signals_data: dict) -> list[str]:
    """Format park-intel signals into briefing text lines.

    Args:
        signals_data: full response from park-intel /api/articles/signals

    Returns:
        list of formatted text lines for the briefing.
    """
    if not signals_data or "error" in signals_data:
        return ["  park-intel 不可用"]

    lines = []
    topic_heat = signals_data.get("topic_heat", [])
    article_count = signals_data.get("article_count", 0)
    high_rel = signals_data.get("high_relevance_count", 0)

    if not topic_heat:
        lines.append("  暂无舆情信号")
        return lines

    # Accelerating / decelerating topics
    accel = [t for t in topic_heat if t.get("momentum_label") == "accelerating"]
    decel = [t for t in topic_heat if t.get("momentum_label") == "decelerating"]

    if accel:
        parts = []
        for t in accel[:5]:
            prev = t.get("previous_count", 0)
            curr = t.get("current_count", 0)
            m = t.get("momentum", 0)
            parts.append(f"{t['tag']}({prev}→{curr}, {m:+.0%})")
        lines.append(f"  🔥 加速: {', '.join(parts)}")

    if decel:
        parts = []
        for t in decel[:5]:
            prev = t.get("previous_count", 0)
            curr = t.get("current_count", 0)
            m = t.get("momentum", 0)
            parts.append(f"{t['tag']}({prev}→{curr}, {m:+.0%})")
        lines.append(f"  📉 降温: {', '.join(parts)}")

    # Related tickers
    mapped = map_signals_to_tickers(topic_heat)
    accel_mapped = [m for m in mapped if m["momentum_label"] == "accelerating"]
    if accel_mapped:
        lines.append("  🎯 关联标的:")
        for m in accel_mapped[:4]:
            tickers = m["us_tickers"] + m["cn_concepts"]
            if tickers:
                lines.append(f"    • {m['tag']} 加速 → {', '.join(tickers)}")

    # High relevance articles
    top_articles = signals_data.get("top_articles", [])
    high_articles = [a for a in top_articles if (a.get("relevance_score") or 0) >= 4]
    if high_articles:
        lines.append(f"  ⚡ 高相关文章 (score>=4): {len(high_articles)}篇")
        for a in high_articles[:3]:
            src = a.get("source", "")
            author = a.get("author", "")
            title = (a.get("title") or "")[:50]
            prefix = f"[{src}]"
            if author:
                prefix += f" @{author}"
            lines.append(f"    • {prefix}: {title}")

    return lines
