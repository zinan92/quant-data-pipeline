# A-Share Monitor 项目架构全解析

> 面向非技术人员，用 ASCII 图 + 白话解释整个系统从"数据"到"你收到简报"的完整链路。

---

## 一、项目整体结构 (文件夹地图)

```
/Users/wendy/ashare/
│
├── web/app.py              ← FastAPI 应用入口 (创建 API 服务器)
├── start_all.sh            ← 一键启动脚本 (后端+前端)
├── monitor.sh              ← 健康监控 (自动重启挂掉的服务)
│
├── src/                        ← 后端核心代码
│   ├── api/                    ← 32个 API 路由文件 (HTTP 端点)
│   │   ├── router.py           ← 总路由注册表
│   │   ├── routes_us_stock.py  ← 美股 API
│   │   ├── routes_concepts.py  ← A股概念板块 API
│   │   ├── routes_anomaly.py   ← 异动检测 API
│   │   ├── routes_rotation.py  ← 板块轮动 API
│   │   └── ... (共32个)
│   │
│   ├── services/               ← 39个业务逻辑服务
│   │   ├── us_stock/           ← 美股服务 (Yahoo Finance)
│   │   ├── tushare_client.py   ← Tushare A股数据客户端
│   │   ├── sina_kline_provider.py  ← 新浪实时行情
│   │   ├── anomaly_monitor.py  ← 异动检测引擎
│   │   └── ...
│   │
│   ├── models/                 ← 数据库表结构定义 (ORM)
│   ├── repositories/           ← 数据库读写层
│   ├── tasks/scheduler.py      ← 定时任务管理器 (APScheduler)
│   ├── config.py               ← 全局配置 (数据库路径、API Key等)
│   ├── database.py             ← SQLite 数据库连接
│   └── lifecycle.py            ← 启动/关闭生命周期钩子
│
├── scripts/                    ← 112个独立脚本
│   ├── full_briefing.py        ← A股深度简报 (1010行, 含Wendy分析)
│   ├── us_briefing_v2.py       ← 美股深度简报 (896行, 含Wendy分析)
│   ├── concept_briefing_cron.py← A股简报调度器 (9个时间点)
│   ├── market_briefing.py      ← 基础市场简报 (指数+异动+新闻)
│   ├── push_to_notion.py       ← 推送到 Notion 数据库
│   ├── generate_review.py      ← Claude AI 生成复盘报告
│   ├── intraday_snapshot.py    ← 盘中快照采集
│   ├── concept_flow_analysis.py← 概念板块资金流分析
│   └── update_*.py             ← 各类数据更新脚本
│
├── data/
│   ├── market.db               ← SQLite 主数据库
│   ├── snapshots/              ← 盘中快照 JSON 文件
│   └── cache/                  ← 概念成分股缓存
│
├── frontend/                   ← React 前端仪表盘
├── config/                     ← 配置文件 (自选股列表等)
├── docs/                       ← 文档
└── .env                        ← 环境变量 (API Key等)
```

---

## 二、系统三大"常驻服务"

你的电脑上有三个东西一直在跑（由 `start_all.sh` 启动）：

```
┌──────────────────────────────────────────────────────────┐
│                  你的 Mac (localhost)                      │
│                                                          │
│  ┌─────────────────┐   ┌──────────────────┐             │
│  │ FastAPI 后端     │   │ React 前端        │             │
│  │ localhost:8000   │   │ localhost:5173    │             │
│  │                  │   │                  │             │
│  │ 提供 /api/* 端点  │   │ 浏览器仪表盘界面   │             │
│  │ (32个路由文件)    │   │ (K线图/板块/自选)  │             │
│  │                  │   │                  │             │
│  │ 内置定时任务:     │   │                  │             │
│  │ - 15:30 刷新行业  │   │                  │             │
│  │ - K线自动更新     │   │                  │             │
│  └────────┬─────────┘   └──────────────────┘             │
│           │                                              │
│  ┌────────▼──────────────────────────────────────────┐   │
│  │ SQLite 数据库 (data/market.db)                     │   │
│  │ K线、股票列表、概念板块、行业数据、自选股 ...        │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

**注意**: 后端服务器内部有一个 APScheduler 定时任务，但它**只负责数据更新**（每天15:30刷新行业/概念/ETF数据），**不负责生成简报**。

---

## 三、数据从哪来？(5 个外部数据源)

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Tushare Pro  │   │    AKShare    │   │ 新浪财经 API  │
│  (付费)       │   │  (免费)       │   │  (免费)       │
│              │   │              │   │              │
│ - A股日K线    │   │ - 涨停/跌停池 │   │ - 实时指数行情 │
│ - 资金流向    │   │ - 概念板块    │   │ - 30分钟K线   │
│ - 交易日历    │   │ - ETF资金流   │   │ - 财经快讯    │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       └─────────┬────────┴──────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────┐
│         FastAPI 后端 (localhost:8000)                      │
│                                                          │
│  src/services/ 层把原始数据加工成标准化格式:              │
│  - tushare_client.py    → 标准化 K线/资金流              │
│  - sina_kline_provider.py → 标准化 实时行情              │
│  - anomaly_monitor.py   → 异动检测算法                   │
│  - sector_rotation.py   → 板块轮动计算                   │
│                                                          │
│  然后通过 src/api/ 层暴露为 HTTP 端点:                   │
│  GET /api/anomaly/alerts  → 异动数据                     │
│  GET /api/rotation/top-inflow → 资金流入TOP              │
│  GET /api/watchlist → 自选股列表                          │
│  GET /api/news/latest → 最新快讯                          │
└──────────────────────────────────────────────────────────┘

┌──────────────┐   ┌──────────────┐
│Yahoo Finance │   │  Binance WS   │
│ (免费)       │   │  (免费)       │
│              │   │              │
│ - 美股指数    │   │ - 加密货币    │
│ - Mag7 报价  │   │ - 实时WebSocket│
│ - ETF/商品   │   │              │
│ - 债券/外汇  │   │              │
└──────┬───────┘   └──────┬───────┘
       │                  │
       ▼                  ▼
  /api/us-stock/*    /api/crypto/*
```

---

## 四、核心流程：A 股简报从触发到你收到

这是最关键的部分。整个链路分 **5 步**：

```
  你 (在 Claude Code 对话框中)
  │
  │  "给我A股简报" 或 定时触发
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│ 步骤1: 触发                                             │
│                                                         │
│ Claude Code (LLM) 执行 bash 命令:                       │
│                                                         │
│   python3 scripts/full_briefing.py                      │
│          或                                             │
│   python3 scripts/concept_briefing_cron.py --auto       │
│                                                         │
│ 注意: 没有系统级 crontab！                              │
│ 触发方式是:                                             │
│   a) 你手动在 Claude Code 中说"给我简报"               │
│   b) Claude Code 的自动化/定时任务                      │
│   c) 或者外部脚本定时调用                               │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 步骤2: 数据采集 (Data Gathering)                        │
│                                                         │
│ full_briefing.py 的 main() 函数会:                      │
│                                                         │
│  1. fetch_indices()                                     │
│     → 调用新浪API获取实时指数 (上证/深证/创业板/科创50)  │
│                                                         │
│  2. requests.get("localhost:8000/api/anomaly/alerts")    │
│     → 调用本地API获取异动数据 (涨停/跌停/急拉/急跌)     │
│                                                         │
│  3. requests.get("localhost:8000/api/rotation/top-inflow")│
│     → 调用本地API获取概念板块资金流向TOP20              │
│                                                         │
│  4. requests.get("localhost:8000/api/watchlist")         │
│     → 调用本地API获取自选股列表                         │
│     → 再调新浪API批量获取自选股实时价格                 │
│                                                         │
│  5. requests.get("localhost:8000/api/news/latest")       │
│     → 调用本地API获取最新财经快讯                       │
│                                                         │
│ 简报脚本本身不直接连数据库！                            │
│ 它通过 HTTP 调用本地 FastAPI 后端来获取一切数据。       │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 步骤3: 分析生成 (Section by Section)                    │
│                                                         │
│ full_briefing.py 依次执行 8 个 section 函数:            │
│                                                         │
│  1. section_indices(index_data)    → A股指数             │
│  2. section_alerts()               → 市场异动            │
│  3. section_intraday_table()       → 盘中路径分析        │
│  4. section_flow_top20()           → 主线资金流分析      │
│  5. section_analysis(...)          → Wendy深度分析       │
│     ├── Layer 1: 今日市场画像 (7种状态分类)             │
│     ├── Layer 2: 主线识别 + 持续性判断                  │
│     ├── Layer 3: 资金行为解读 (流向vs涨跌一致性)        │
│     ├── Layer 4: 风险信号扫描 (护盘/白酒/剪刀差)        │
│     └── Layer 5: Wendy建议 (综合打分→5档操作建议)       │
│  6. section_stock_sectors()        → 赛道汇总            │
│  7. section_watchlist()            → 自选股异动           │
│  8. section_news()                 → 市场快讯            │
│                                                         │
│ Wendy分析是纯规则引擎 (Rule-based, ZERO AI)             │
│ 不调用任何LLM！是 if/else 条件判断 + 综合打分           │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 步骤4: 格式化输出                                       │
│                                                         │
│  所有 section 的输出 (list[str]) 被拼接成一个大字符串:   │
│                                                         │
│  full_text = "\n".join(output_lines)                    │
│  print(full_text)  ← 打印到 stdout                      │
│                                                         │
│  此时 Claude Code 能看到 stdout 的输出，                 │
│  就是你在对话框中看到的简报内容。                        │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 步骤5: 推送到 Notion (可选)                              │
│                                                         │
│  push_to_notion.py:                                     │
│                                                         │
│  1. parse_briefing(text)                                │
│     → 从简报文本中提取结构化数据:                       │
│       上证涨跌%, 创业板涨跌%, 市场定性, 护盘信号, 趋势  │
│                                                         │
│  2. text_to_blocks(text)                                │
│     → 把文本切分成 <=1900字符 的块 (Notion API限制)     │
│                                                         │
│  3. requests.post("https://api.notion.com/v1/pages")    │
│     → 创建一个 Notion 页面，写入:                       │
│       - 简报标题: "A股简报 2026-02-13 10:30 (盘中)"      │
│       - 属性: 日期, 时间, 类型, 市场定性, 护盘信号 ...  │
│       - 正文: 完整简报内容                              │
│                                                         │
│  Notion Database ID: 2fdf137e-7fdf-81ad-886d-...        │
│  API Key 存储位置: ~/.config/notion/api_key             │
└─────────────────────────────────────────────────────────┘
```

### 完整时序图 (从你说话到收到简报):

```
你(Claude Code对话框)        full_briefing.py         FastAPI后端         外部数据源         Notion
    │                           │                      │                   │                │
    │  "给我A股简报"             │                      │                   │                │
    ├──bash: python3 scripts/──►│                      │                   │                │
    │   full_briefing.py        │                      │                   │                │
    │                           │                      │                   │                │
    │                           │──GET 新浪实时指数────────────────────────►│                │
    │                           │◄─────────指数数据────────────────────────│                │
    │                           │                      │                   │                │
    │                           │──GET /api/anomaly/──►│                   │                │
    │                           │◄───异动数据──────────│                   │                │
    │                           │                      │                   │                │
    │                           │──GET /api/rotation/─►│──Tushare资金流───►│                │
    │                           │◄───资金流TOP20───────│◄─────────────────│                │
    │                           │                      │                   │                │
    │                           │──GET /api/watchlist/─►│                   │                │
    │                           │◄───自选股列表────────│                   │                │
    │                           │                      │                   │                │
    │                           │──GET 新浪自选股价格──────────────────────►│                │
    │                           │◄────────实时价格─────────────────────────│                │
    │                           │                      │                   │                │
    │                           │  ┌──────────────────────────┐           │                │
    │                           │  │ 逐section生成文本:        │           │                │
    │                           │  │ 1.指数 2.异动 3.盘中路径  │           │                │
    │                           │  │ 4.资金流 5.Wendy分析      │           │                │
    │                           │  │ 6.赛道 7.自选 8.快讯     │           │                │
    │                           │  └──────────────────────────┘           │                │
    │                           │                      │                   │                │
    │◄──print(full_text)────────│                      │                   │                │
    │  (你在对话框看到简报)      │                      │                   │                │
    │                           │                      │                   │                │
    │                           │──POST notion/pages──────────────────────────────────────►│
    │                           │◄────────200 OK──────────────────────────────────────────│
    │                           │                      │                   │                │
    ▼                           ▼                      ▼                   ▼                ▼
```

---

## 五、美股简报的完整链路

美股简报更简单，因为只有一个数据源 (Yahoo Finance → FastAPI → 脚本):

```
你(Claude Code)         us_briefing_v2.py        FastAPI后端          Yahoo Finance
    │                        │                      │                    │
    │ "给我美股简报"          │                      │                    │
    ├──bash: python3────────►│                      │                    │
    │                        │                      │                    │
    │                        │──GET /api/us-stock/  │                    │
    │                        │   indexes ──────────►│──yfinance.get()──►│
    │                        │◄────指数(S&P/DOW/──│◄──────────────────│
    │                        │     NASDAQ/VIX)      │                    │
    │                        │                      │                    │
    │                        │──GET /api/us-stock/  │                    │
    │                        │   sectors ──────────►│──yfinance(21ETF)─►│
    │                        │◄────板块ETF数据──────│◄──────────────────│
    │                        │                      │                    │
    │                        │──GET /api/us-stock/  │                    │
    │                        │   mag7 ─────────────►│──yfinance(7只)───►│
    │                        │◄────Mag7数据─────────│◄──────────────────│
    │                        │                      │                    │
    │                        │ (同理: china-adr, commodities,            │
    │                        │  bonds, forex, news, calendar)            │
    │                        │                      │                    │
    │                        │  ┌─────────────────────────────────┐     │
    │                        │  │ 8个section生成:                  │     │
    │                        │  │ 1.三大指数(VIX解读)              │     │
    │                        │  │ 2.板块轮动(Risk ON/OFF)         │     │
    │                        │  │ 3.异动检测(>5%涨跌)             │     │
    │                        │  │ 4.Mag7深度(vs S&P对比)          │     │
    │                        │  │ 5.中概股                        │     │
    │                        │  │ 6.跨资产联动(股债/美元/VIX)     │     │
    │                        │  │ 7.Wendy深度分析(5层)            │     │
    │                        │  │ 8.快讯+经济日历                 │     │
    │                        │  └─────────────────────────────────┘     │
    │                        │                      │                    │
    │◄──print(full_text)─────│                      │                    │
    │  (你在对话框看到简报)   │                      │                    │
    ▼                        ▼                      ▼                    ▼
```

---

## 六、Wendy 分析到底在哪一步？

**关键理解**: Wendy 分析 **不是 AI/LLM 生成的**，它是纯 Python `if/else` 规则引擎。

```
                    full_briefing.py 的 main() 函数
                               │
    ┌──────────────────────────┼──────────────────────────┐
    │                          │                          │
    ▼                          ▼                          ▼
 采集数据(步骤2)          生成Section 1-4             生成Section 5
 index_data               (指数/异动/路径/资金)         │
 flow_df                                               ▼
 alert_data                              section_analysis(index_data,
                                                        flow_df,
                                                        alert_data)
                                                    │
                              ┌─────────────────────┼─────────────────────┐
                              │     Wendy 分析函数内部 (纯规则, 无AI)       │
                              │                                           │
                              │  输入:                                    │
                              │  - 上证/深证/创业板涨跌% (from 新浪)      │
                              │  - 涨停/跌停数量 (from AKShare/API)       │
                              │  - 概念资金流TOP20 DataFrame (from Tushare)│
                              │  - 护盘板块(银行/保险/券商)净流入         │
                              │  - 白酒板块净流入                         │
                              │                                           │
                              │  Layer 1: if 上证>0.5% and 创业板>0.5%    │
                              │           and 涨停/跌停比>3               │
                              │           → "强势做多日"                  │
                              │           elif ...                        │
                              │           → 7种市场状态之一               │
                              │                                           │
                              │  Layer 2: if top1资金流>=200亿            │
                              │           → "超强主线, 高概率延续"        │
                              │           elif ...                        │
                              │                                           │
                              │  Layer 3: if 总净流入>30 and 上证>0.3%    │
                              │           → "一致: 健康上涨"              │
                              │           elif 净流入>30 but 上证<-0.3%   │
                              │           → "背离: 主力可能在吸筹"        │
                              │                                           │
                              │  Layer 4: 扫描6种风险信号                 │
                              │                                           │
                              │  Layer 5: 多头+1分 / 空头-1分            │
                              │           score >= 4 → "积极做多"        │
                              │           score >= 2 → "偏多操作"        │
                              │           score <= -3 → "防守为主"       │
                              │                                           │
                              │  输出: list[str] (一系列格式化文本行)     │
                              └───────────────────────────────────────────┘
```

美股版 Wendy 分析 (`us_briefing_v2.py` 的 `section_wendy_analysis`) 逻辑相同，
但用美股特有指标替换:
- 上证/创业板 → S&P 500 / Nasdaq / 道琼斯
- 涨停/跌停 → VIX 恐慌指数
- 银行/保险/券商 护盘 → XLU/XLP/GLD 防御板块
- 资金流TOP → ETF板块涨跌排序

---

## 七、两种简报的数据流对比

```
┌─────────────────────────────────────────────────────────────────────┐
│                        A 股简报                                     │
│                                                                     │
│  数据源: 新浪(实时) + Tushare(资金流) + AKShare(涨跌停)            │
│          ↓                   ↓                  ↓                   │
│  采集层: fetch_indices()     /api/rotation/     /api/anomaly/       │
│          (直连新浪)          (通过FastAPI)       (通过FastAPI)       │
│          ↓                   ↓                  ↓                   │
│  分析层: full_briefing.py 的 section_analysis()                     │
│          (Wendy 5层分析: 画像→主线→资金→风险→建议)                  │
│          ↓                                                          │
│  输出层: print() → 你看到   +   push_to_notion() → Notion数据库    │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                        美 股简报                                    │
│                                                                     │
│  数据源: Yahoo Finance (全部通过 yfinance 库)                       │
│          ↓                                                          │
│  采集层: us_briefing_v2.py 通过 /api/us-stock/* 端点获取            │
│          (indexes, sectors, mag7, china-adr, commodities,           │
│           bonds, forex, news, calendar)                             │
│          ↓                                                          │
│  分析层: section_wendy_analysis() (美股版5层分析)                    │
│          (画像→板块主线→跨资产→风险→建议)                           │
│          ↓                                                          │
│  输出层: print() → 你看到                                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 八、后台数据更新 (和简报无关，但保证数据新鲜)

```
FastAPI 启动时 (lifecycle.py)
    │
    ├── 启动 SchedulerManager (APScheduler)
    │   └── 每天 15:30 (Asia/Shanghai) 执行:
    │       ├── update_industry_daily.py   → 刷新行业数据
    │       ├── update_concept_daily.py    → 刷新概念板块 (~6分钟)
    │       └── ETF 5步更新流程:
    │           ├── update_etf_daily_summary.py
    │           ├── build_etf_filtered.py
    │           ├── update_etf_daily_flow.py
    │           ├── download_etf_klines.py
    │           └── calc_etf_flow_history.py
    │
    ├── 启动 KlineScheduler
    │   ├── 日K线更新 (Tushare, 收盘后)
    │   └── 30分钟K线更新 (新浪, 交易时间每30分钟)
    │
    └── 启动 Crypto WebSocket (Binance实时行情)
```

---

## 九、一句话总结

> **你说"给我简报" → Claude Code 执行 Python 脚本 → 脚本调用本地 API 服务器 →
> API 服务器从外部数据源(新浪/Tushare/Yahoo)拉取实时数据 → 脚本用纯规则引擎
> (不是AI)生成 Wendy 分析 → 文本打印到对话框给你看 → 同时推送到 Notion 存档**

整个过程中，**没有任何一步用到 LLM/AI 来生成分析内容**。
Wendy 的"深度分析"全是写死的 if/else 规则 + 数学公式打分。
唯一用到 Claude AI 的地方是 `generate_review.py`（收盘后的叙事性复盘报告），
但这是独立流程，不在常规简报中。
