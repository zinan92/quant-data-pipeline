#!/usr/bin/env python3
"""
push_to_notion.py — 将简报推送到 Notion 数据库
================================================
用法:
  1. 作为模块调用: push_briefing_to_notion(text)
  2. 命令行:       python push_to_notion.py < briefing.txt
                   python push_to_notion.py "简报文本..."
"""

import re
import sys
import json
import requests
from datetime import datetime
from pathlib import Path

# ── Config ───────────────────────────────────────────────────
DATABASE_ID = "2fdf137e-7fdf-81ad-886d-c6fb1b264ce3"
API_KEY_PATH = Path.home() / ".config" / "notion" / "api_key"
NOTION_VERSION = "2025-09-03"
NOTION_BASE = "https://api.notion.com/v1"
MAX_RT_CHARS = 1900  # Notion limit is 2000, leave margin


def _get_api_key() -> str:
    return API_KEY_PATH.read_text().strip()


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


# ═══════════════════════════════════════════════════════════════
# Time → Type mapping
# ═══════════════════════════════════════════════════════════════
def get_briefing_type(now: datetime = None) -> str:
    if now is None:
        now = datetime.now()
    hhmm = now.strftime("%H:%M")
    h, m = now.hour, now.minute
    t = h * 60 + m  # minutes since midnight

    mapping = {
        "09:35": "开盘",
        "10:00": "盘中", "10:30": "盘中", "11:00": "盘中",
        "11:30": "午间",
        "13:00": "午后",
        "13:30": "盘中", "14:00": "盘中", "14:30": "盘中",
        "15:05": "收盘",
    }

    if hhmm in mapping:
        return mapping[hhmm]

    # Fuzzy: find nearest within 10 min
    for key, label in mapping.items():
        kh, km = map(int, key.split(":"))
        kt = kh * 60 + km
        if abs(t - kt) <= 10:
            return label

    # Fallback
    if t < 9 * 60 + 30:
        return "开盘"
    elif t <= 11 * 60 + 30:
        return "盘中"
    elif t <= 13 * 60:
        return "午间"
    elif t <= 15 * 60 + 5:
        return "盘中"
    else:
        return "盘后总结"


# ═══════════════════════════════════════════════════════════════
# Parse briefing text → structured data
# ═══════════════════════════════════════════════════════════════
def parse_briefing(text: str) -> dict:
    """Extract key metrics from briefing text."""
    data = {
        "sh_pct": None,        # 上证涨跌 (decimal, e.g. 0.0052 for +0.52%)
        "cy_pct": None,        # 创业板涨跌
        "market_tone": None,   # 市场定性
        "护盘": None,          # 护盘信号
        "trend": None,         # 趋势强度
    }

    # ── 上证涨跌 ──
    m = re.search(r"上证指数.*?([+-]?\d+\.?\d*)%", text)
    if m:
        data["sh_pct"] = float(m.group(1)) / 100  # Notion percent format

    # ── 创业板涨跌 ──
    m = re.search(r"创业板指.*?([+-]?\d+\.?\d*)%", text)
    if m:
        data["cy_pct"] = float(m.group(1)) / 100

    # ── 市场定性 ──
    m = re.search(r"市场定性.*?(Risk\s*ON|Risk\s*OFF|普涨|普跌|中性)", text)
    if m:
        tone = m.group(1).strip()
        # Normalize
        tone_map = {
            "Risk ON": "Risk ON",
            "Risk OFF": "Risk OFF",
            "普涨": "普涨",
            "普跌": "普跌",
            "中性": "中性",
        }
        for k, v in tone_map.items():
            if k.lower().replace(" ", "") in tone.lower().replace(" ", ""):
                data["market_tone"] = v
                break

    # ── 护盘信号 ──
    if "三大金融板块全部净流入" in text or "全亮" in text:
        data["护盘"] = "全亮(3/3)"
    elif re.search(r"[23]/3金融板块净流入", text) or "有护盘迹象" in text:
        data["护盘"] = "部分"
    elif "无需护盘" in text or "金融板块中性" in text or "金融板块净流出" in text:
        data["护盘"] = "无"
    else:
        data["护盘"] = "无"  # default

    # ── 趋势强度 ──
    m = re.search(r"(强趋势|中等趋势|弱趋势|无主线)", text)
    if m:
        t = m.group(1)
        if "强" in t:
            data["trend"] = "强(>200亿)"
        elif "中" in t:
            data["trend"] = "中(100-200)"
        else:
            data["trend"] = "弱(<100)"

    return data


# ═══════════════════════════════════════════════════════════════
# Build Notion page body (split into blocks, respecting 2000 char limit)
# ═══════════════════════════════════════════════════════════════
def text_to_blocks(text: str) -> list[dict]:
    """Convert briefing text to Notion paragraph blocks.
    
    Splits on section boundaries (blank lines or ═ lines) and
    respects the 2000 char limit per rich_text element.
    """
    blocks = []
    # Split into sections by double newline or separator lines
    sections = re.split(r'\n(?=═|📈|⚡|📋|💰|🧠|⭐|📰|⏱)', text)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # If section is short enough, one block
        if len(section) <= MAX_RT_CHARS:
            blocks.append(_paragraph_block(section))
        else:
            # Split by lines, accumulate chunks
            lines = section.split("\n")
            chunk = ""
            for line in lines:
                if len(chunk) + len(line) + 1 > MAX_RT_CHARS:
                    if chunk:
                        blocks.append(_paragraph_block(chunk))
                    chunk = line
                else:
                    chunk = chunk + "\n" + line if chunk else line
            if chunk:
                blocks.append(_paragraph_block(chunk))

    return blocks


def _paragraph_block(text: str) -> dict:
    """Create a single Notion paragraph block."""
    # Further split rich_text if needed (each element max 2000 chars)
    elements = []
    while text:
        chunk = text[:MAX_RT_CHARS]
        text = text[MAX_RT_CHARS:]
        elements.append({
            "type": "text",
            "text": {"content": chunk},
        })

    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": elements,
        },
    }


# ═══════════════════════════════════════════════════════════════
# Create Notion page
# ═══════════════════════════════════════════════════════════════
def push_briefing_to_notion(text: str, now: datetime = None) -> dict:
    """Push briefing text to Notion database. Returns API response."""
    if now is None:
        now = datetime.now()

    parsed = parse_briefing(text)
    btype = get_briefing_type(now)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    title = f"📊 A股简报 {date_str} {time_str} ({btype})"

    # ── Build properties ──
    properties = {
        "简报标题": {
            "title": [{"text": {"content": title}}],
        },
        "日期": {
            "date": {"start": date_str},
        },
        "时间": {
            "rich_text": [{"text": {"content": time_str}}],
        },
        "类型": {
            "select": {"name": btype},
        },
    }

    if parsed["market_tone"]:
        properties["市场定性"] = {"select": {"name": parsed["market_tone"]}}
    if parsed["护盘"]:
        properties["护盘信号"] = {"select": {"name": parsed["护盘"]}}
    if parsed["trend"]:
        properties["趋势强度"] = {"select": {"name": parsed["trend"]}}
    if parsed["sh_pct"] is not None:
        properties["上证涨跌"] = {"number": parsed["sh_pct"]}
    if parsed["cy_pct"] is not None:
        properties["创业板涨跌"] = {"number": parsed["cy_pct"]}

    # ── Build body blocks (max 100 per request) ──
    blocks = text_to_blocks(text)
    # Notion API allows max 100 children per request
    children = blocks[:100]

    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": properties,
        "children": children,
    }

    resp = requests.post(
        f"{NOTION_BASE}/pages",
        headers=_headers(),
        json=payload,
        timeout=30,
    )

    result = resp.json()

    if resp.status_code == 200:
        page_url = result.get("url", "")
        print(f"✅ Notion推送成功: {title}")
        print(f"   URL: {page_url}")
    else:
        print(f"❌ Notion推送失败 ({resp.status_code}): {result.get('message', result)}")

    return result


# ═══════════════════════════════════════════════════════════════
# CLI entry
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if len(sys.argv) > 1:
        briefing_text = sys.argv[1]
    else:
        briefing_text = sys.stdin.read()

    if not briefing_text.strip():
        print("❌ 无输入文本")
        sys.exit(1)

    push_briefing_to_notion(briefing_text)
