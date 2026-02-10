# AShare Code Review 完整修复文档

> **项目**: AShare — A 股市场数据平台
> **审查日期**: 2026-02-10
> **审查方式**: 3 Agent 并行 Code Review（架构质量 / 安全审计 / 测试覆盖）
> **发现**: 26 个问题（5 P0 / 6 P1 / 15 P2）→ 29 个修复任务，4 个 Sprint

---

## 文档结构

| Phase | 内容 | 定位 |
|-------|------|------|
| **Phase 1: Discovery** | 项目概述、审查方法论、26 项发现清单、依赖关系图 | 发现了什么 |
| **Phase 2: Plan** | 4 个 Sprint 规划、29 个 Task 概览、依赖与时间线 | 怎么修 |
| **Phase 3: Execute** | 每个 Task 的文件/当前代码/目标代码/步骤/工作量 | 具体怎么改 |
| **Phase 4: Review** | 每个 Sprint 的 grep/curl/pytest 验证命令 | 怎么验 |
| **Phase 5: Acceptance** | DoD、指标矩阵、最终签收标准 | 怎么收 |

---

# Phase 1: Discovery（发现）

## 1.1 项目概述 & Executive Summary

**AShare** 是一个面向中国 A 股市场的数据平台，提供行情数据采集、自选股管理、板块分析、筛选器、加密货币行情、感知系统和新闻情绪分析等功能。

**技术栈：**

| 层级 | 技术选型 |
|------|---------|
| Backend | FastAPI + SQLAlchemy + SQLite (Python 3.12) |
| Frontend | React + TypeScript + Vite |
| 数据源 | Tushare Pro, Sina Finance, Binance WebSocket |
| 部署 | Docker + docker-compose |

**核心功能模块：** K 线数据、自选股管理、条件筛选器、板块/概念分析、加密货币行情、Perception 感知系统、新闻情绪分析

**审查信息：**

- 审查日期：2026-02-10
- 审查方式：3 个并行 Agent 审查员
  - Agent 1：架构与代码质量
  - Agent 2：安全审计
  - Agent 3：测试覆盖率与错误处理
- **审查结果：共发现 26 个问题 — 5 个 P0（严重）/ 6 个 P1（高）/ 15 个 P2（中等）**

---

## 1.2 审查方法论

本次代码审查采用 **3-Agent 并行审查模式**，每个 Agent 专注于不同的审查维度：

| Agent | 审查领域 | 关注重点 |
|-------|---------|---------|
| Agent 1 | 架构与代码质量 | 分层设计、模式一致性、代码重复、死代码 |
| Agent 2 | 安全审计 | 认证/授权、注入攻击、敏感信息泄露、容器安全 |
| Agent 3 | 测试覆盖率与错误处理 | 单元测试覆盖、异常处理模式、边界情况 |

**审查流程：**

1. **独立审查** — 每个 Agent 独立扫描整个代码库，从各自专业角度发现问题
2. **交叉去重** — 三方发现汇总后去除重复项，合并同类问题
3. **优先级分类** — 按影响范围和修复紧迫性分为三级：
   - **P0（立即修复）** — 存在安全漏洞或数据丢失风险，需在 24 小时内处理
   - **P1（本周修复）** — 架构缺陷或显著技术债务，影响系统可维护性
   - **P2（本月修复）** — 代码质量改进项，不影响运行但应逐步优化

---

## 1.3 做得好的方面

在列出问题之前，有必要肯定项目中已有的优秀实践：

| 方面 | 说明 |
|------|------|
| **Repository 模式** | `BaseRepository` 泛型 CRUD 设计清晰，继承层次合理 |
| **Perception 子系统** | Source -> Detector -> Aggregator pipeline 架构可扩展，测试覆盖约 71% |
| **数据标准化层** | `NormalizedTicker` / `NormalizedDate` / `NormalizedDateTime` 统一多种输入格式 |
| **异常体系设计** | 层次结构完善，18 种自定义异常覆盖各种场景（只是还没被广泛使用） |
| **已有测试质量** | Repository 和 Crypto 模块的测试编写专业，fixture 设计合理 |
| **Sina 速率限制** | 断路器（Circuit Breaker）+ 指数退避（Exponential Backoff）实现优秀 |
| **Pydantic Settings** | 配置管理支持 `.env` 和环境变量覆盖，结构清晰 |

**测试覆盖率现状：**

| Layer | Tested/Total | Coverage |
|-------|-------------|----------|
| `repositories/` | 5/6 | ~83% |
| `services/` (core) | 6/20+ | ~30% |
| `api/` (routes) | 4/18 | ~22% |
| `perception/` | ~20/28 | ~71% |
| `schemas/` | 0/4 | 0% |
| `utils/` | 1/6 | ~17% |
| **Total** | **~36/82** | **~44%** |

---

## 1.4 发现清单

### P0 — 严重问题（5 个）

| ID | 优先级 | 类别 | 问题描述 | 涉及文件 |
|-----|--------|------|---------|----------|
| F-01 | P0 | Security | 所有 API 端点无认证 — 132 个路由（包括 POST/DELETE）全部裸奔 | `src/api/routes_*.py` (26 files) |
| F-02 | P0 | Architecture | Session 管理混乱 — `Depends(get_db)` 和 `session_scope()` 两种模式混用 | `src/api/routes_watchlist.py`, `routes_evaluations.py`, `routes_boards.py`, `routes_meta.py`, `routes_concepts.py` |
| F-03 | P0 | Architecture | MarketDataService 单例持有永不关闭的 Session | `src/api/dependencies.py:34-49` |
| F-04 | P0 | Quality | `anomaly_monitor.py` 等 5 处 bare except — 异常被完全吞掉 | `src/services/anomaly_monitor.py:182`, `routes_pattern.py:78`, `routes_concepts.py:273`, `news_sentiment.py:130`, `daily_review_data_service.py:580` |
| F-05 | P0 | Testing | 核心服务无测试 — `simulated_service`（模拟交易）、`data_pipeline`（数据管道） | `src/services/simulated_service.py`, `src/services/data_pipeline.py` |

### P1 — 高优先级问题（6 个）

| ID | 优先级 | 类别 | 问题描述 | 涉及文件 |
|-----|--------|------|---------|----------|
| F-06 | P1 | Security | 无 API 速率限制 — 外部 API 额度可被刷爆 | `src/api/routes_*.py` |
| F-07 | P1 | Security | SSRF 风险 — RSS endpoint 接受任意 URL，可探测内网 | `src/api/routes_news.py`, `src/services/news/external_service.py:196-214` |
| F-08 | P1 | Security | `shell=True` subprocess — scheduler 和 tasks 脚本执行无认证 | `src/tasks/scheduler.py:93`, `scripts/update_concept_daily.py:26` |
| F-09 | P1 | Architecture | 直接 `sqlite3` 绕过 ORM — 14 处混用 | `routes_watchlist.py:118`, `routes_meta.py:22`, `perception/sources/market_data_source.py:15` |
| F-10 | P1 | Architecture | `models_old.py` 529 行死代码 — 枚举值与新模型不一致 | `src/models_old.py` (529 lines) |
| F-11 | P1 | Architecture | `on_event` 已弃用 — `lifecycle.py` 应迁移到 FastAPI lifespan | `src/lifecycle.py:14,40` |

### P2 — 中等优先级问题（15 个）

| ID | 优先级 | 类别 | 问题描述 | 涉及文件 |
|-----|--------|------|---------|----------|
| F-12 | P2 | Security | Docker 容器以 root 运行 | `Dockerfile` |
| F-13 | P2 | Security | CORS `allow_methods` / `allow_headers` 过宽 | `web/app.py:34-40`, `src/config.py:45` |
| F-14 | P2 | Security | 错误信息 `str(e)` 泄露内部细节 | Multiple route files |
| F-15 | P2 | Security | WebSocket 管理端点无保护 | `src/api/routes_crypto_ws.py` |
| F-16 | P2 | Security | `.env` 文件安全 — 确认未被提交到 Git 历史 | `.env`, `docker-compose.yml` |
| F-17 | P2 | Architecture | Ticker 标准化逻辑重复 — 两套实现 | `src/utils/ticker_utils.py`, `src/schemas/normalized.py` |
| F-18 | P2 | Architecture | `routes_watchlist.py` 636 行过度膨胀 | `src/api/routes_watchlist.py` (635 lines) |
| F-19 | P2 | Architecture | `routes_status.py` update-times 返回伪造时间戳 | `src/api/routes_status.py` |
| F-20 | P2 | Architecture | 自定义异常定义了 18 种但几乎没人用 | `src/exceptions.py` (264 lines) vs route files |
| F-21 | P2 | Architecture | 日志方式不统一 — `LOGGER` vs `get_logger` vs `logging.getLogger` | Multiple files |
| F-22 | P2 | Architecture | SQLite `pool_size=20` 不合理 | `src/database.py:19` |
| F-23 | P2 | Architecture | `exceptions.TimeoutError` 遮盖内置 `TimeoutError` | `src/exceptions.py:256` |
| F-24 | P2 | Architecture | Perception 子系统硬编码路径 | `src/perception/pipeline.py:53-58` |
| F-25 | P2 | Architecture | `BaseRepository.count()` 加载全部对象再 `len()` | `src/repositories/base_repository.py:126-135` |
| F-26 | P2 | Testing | 整体覆盖率约 44%，18 路由中仅 4 有测试，`pytest-cov` 被注释 | `pytest.ini`, `tests/` |

---

## 1.5 依赖关系图

修复各问题之间存在依赖关系，需按正确顺序执行：

```
F-01 (API 认证)
 ├──> F-06 (速率限制) ──── 需要认证中间件作为基础
 └──> F-15 (WebSocket 保护) ── 认证机制扩展到 WS

F-02 (Session 统一)
 ├──> F-03 (MarketDataService Session) ── Session 管理方式统一后再修
 ├──> F-09 (消除 sqlite3) ──── 统一到 ORM 后才能清理直接调用
 │     └──> F-10 (删除 models_old.py) ── sqlite3 清理后才能安全删除旧模型
 └──> F-18 (拆分 watchlist) ── Session 统一后再做路由拆分

F-04 (bare except) ──> F-20 (统一异常使用) ── 先修 except 再推广自定义异常

F-05 (核心测试) ── 独立，可与安全修复并行

F-26 (测试基础设施) ── 独立，为后续测试补全提供 conftest.py 基础
```

**关键路径：** `F-01 → F-06` 和 `F-02 → F-09 → F-10` 是两条最长依赖链，决定了整体修复节奏。

---

---

# Phase 2: Plan（计划）

## 2.1 Sprint 总览

整个修复计划分为 4 个 Sprint，总计 29 个任务：

| Sprint | 主题 | Tasks | 阻塞关系 | 预期时间 |
|--------|------|-------|---------|---------|
| Sprint 1 | 安全加固 | T-01 ~ T-08 (8 tasks) | 无 | Week 1 |
| Sprint 2 | 架构基础 | T-09 ~ T-14 (6 tasks) | 依赖 Sprint 1 完成 | Week 2 |
| Sprint 3 | 代码质量 | T-15 ~ T-23 (9 tasks) | 依赖 Sprint 2 完成 | Week 3-4 |
| Sprint 4 | 测试补全 | T-24 ~ T-29 (6 tasks) | Sprint 1 完成后即可开始 | Week 3-4 |

> Sprint 4 与 Sprint 2/3 可并行推进，测试补全不依赖架构重构。

---

## 2.2 Sprint 1: 安全加固 — 8 tasks

**目标：** 消除所有安全漏洞，建立认证和防护基础设施。

| Task ID | 标题 | 发现 ID | 工作量 | 依赖 |
|---------|------|---------|--------|------|
| T-01 | 实现 API Key 认证中间件 | F-01 | L | None |
| T-02 | 为写操作端点添加认证 | F-01 | M | T-01 |
| T-03 | 添加 `slowapi` 速率限制 | F-06 | M | T-01 |
| T-04 | 修复 RSS SSRF 漏洞 | F-07 | S | None |
| T-05 | 消除 `shell=True` 调用 | F-08 | S | None |
| T-06 | Docker 添加非特权用户 | F-12 | S | None |
| T-07 | 收紧 CORS 配置 | F-13 | S | None |
| T-08 | 隐藏 `str(e)` 错误详情 | F-14 | M | None |

> 工作量：S = 小（< 1h），M = 中（1-4h），L = 大（4h+）

**执行顺序建议：** T-04/T-05/T-06/T-07 无依赖可并行 -> T-01 完成后 -> T-02/T-03 并行 -> T-08 收尾

---

## 2.3 Sprint 2: 架构基础 — 6 tasks

**目标：** 统一数据访问模式，清理技术债务，为后续重构打好基础。

| Task ID | 标题 | 发现 ID | 工作量 | 依赖 |
|---------|------|---------|--------|------|
| T-09 | 统一 Session 管理 -> `Depends(get_db)` | F-02 | L | None |
| T-10 | 修复 MarketDataService Session 泄漏 | F-03 | M | T-09 |
| T-11 | 消除直接 `sqlite3` 调用 | F-09 | M | T-09 |
| T-12 | 删除 `models_old.py` | F-10 | M | T-11 |
| T-13 | 迁移 `lifecycle.py` -> lifespan | F-11 | S | None |
| T-14 | 修复 `BaseRepository.count()` | F-25 | S | None |

**执行顺序建议：** T-13/T-14 无依赖可并行 -> T-09 完成后 -> T-10/T-11 并行 -> T-12 收尾

---

## 2.4 Sprint 3: 代码质量 — 9 tasks

**目标：** 提升代码可维护性，统一编码风格，消除代码异味。

| Task ID | 标题 | 发现 ID | 工作量 | 依赖 |
|---------|------|---------|--------|------|
| T-15 | 修复 5 处 bare except | F-04 | M | None |
| T-16 | 统一异常使用 — 路由用自定义异常 | F-20 | M | T-15 |
| T-17 | 统一日志方式 | F-21 | S | None |
| T-18 | 修复 SQLite `pool_size` 配置 | F-22 | S | None |
| T-19 | 重命名 `exceptions.TimeoutError` | F-23 | S | None |
| T-20 | 修复 Perception 硬编码路径 | F-24 | S | None |
| T-21 | 拆分 `routes_watchlist.py` | F-18 | L | T-09 |
| T-22 | 修复 `routes_status.py` 伪造时间戳 | F-19 | S | None |
| T-23 | 合并 Ticker 标准化逻辑 | F-17 | M | None |

**执行顺序建议：** T-15 -> T-16 -> T-19 依次进行；其余 T-17/T-18/T-20/T-22/T-23 可并行；T-21 需等待 T-09 完成

---

## 2.5 Sprint 4: 测试补全 — 6 tasks

**目标：** 将测试覆盖率从 44% 提升至 70%+，建立持续测试基础设施。

| Task ID | 标题 | 发现 ID | 工作量 | 依赖 |
|---------|------|---------|--------|------|
| T-24 | 创建共享 `conftest.py` | F-26 | M | None |
| T-25 | 为 `simulated_service` 补测试 | F-05 | L | T-24 |
| T-26 | 为 `data_pipeline` 补测试 | F-05 | L | T-24 |
| T-27 | 为未覆盖 API 路由补测试 | F-26 | L | T-24 |
| T-28 | 启用 `pytest-cov` 覆盖率收集 | F-26 | S | None |
| T-29 | 清理问题测试文件 | F-26 | S | None |

**执行顺序建议：** T-24/T-28/T-29 可并行 -> T-24 完成后 -> T-25/T-26/T-27 并行推进

**覆盖率目标：**

| Layer | 当前 | 目标 |
|-------|------|------|
| `repositories/` | ~83% | 90%+ |
| `services/` (core) | ~30% | 70%+ |
| `api/` (routes) | ~22% | 60%+ |
| `perception/` | ~71% | 80%+ |
| `schemas/` | 0% | 50%+ |
| `utils/` | ~17% | 60%+ |
| **Total** | **~44%** | **70%+** |
# Phase 3: Execute（执行）

> 本章节包含 29 个任务的完整实施指引，按 4 个 Sprint 组织。每个任务均给出受影响文件路径+行号、当前代码（Before）、目标代码（After）、分步实施指引、工作量估算及依赖关系。

---

## 3.1 Sprint 1: 安全加固（T-01 ~ T-08）

### T-01: 实现 API Key 认证中间件

| 属性 | 值 |
|------|-----|
| **受影响文件** | 新建 `src/api/auth.py`；修改 `src/config.py:30-80` |
| **工作量** | L |
| **依赖** | 无 |

**Before — `src/config.py:30-36`（Settings 类无 api_key 字段）：**

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///data/market.db", alias="DATABASE_URL")
```

**After — `src/config.py`（新增 api_key 和 debug 字段）：**

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///data/market.db", alias="DATABASE_URL")
    api_key: str = Field(default="", alias="API_KEY")
    debug: bool = Field(default=False, alias="DEBUG")
```

**After — `src/api/auth.py`（新建文件）：**

```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from src.config import get_settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    """验证 API Key。若 settings.api_key 为空则跳过验证（开发模式）。"""
    settings = get_settings()
    if not settings.api_key:
        return  # 未配置 key = 允许所有请求（开发模式）
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
```

**分步实施指引：**

1. 在 `src/config.py` 的 `Settings` 类中添加 `api_key` 和 `debug` 字段
2. 新建 `src/api/auth.py`，实现 `verify_api_key` 依赖
3. 在 `.env.example` 中添加 `API_KEY=` 示例
4. 编写单元测试：验证有 key 时未传 key 返回 401，传正确 key 返回 200，无 key 配置时直接通过

---

### T-02: 为写操作端点添加认证

| 属性 | 值 |
|------|-----|
| **受影响文件** | 所有含 POST/PUT/DELETE/PATCH 端点的 `routes_*.py` 文件 |
| **工作量** | M |
| **依赖** | T-01 |

**Before — `src/api/routes_watchlist.py:99-103`：**

```python
@router.post("", status_code=201)
async def add_to_watchlist(
    request: WatchlistAdd,
    db: Session = Depends(get_db),
):
```

**After：**

```python
from src.api.auth import verify_api_key

@router.post("", status_code=201)
async def add_to_watchlist(
    request: WatchlistAdd,
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
```

**需要添加认证的端点清单（写操作）：**

| 文件 | 端点 | 方法 |
|------|------|------|
| `routes_watchlist.py:99` | `/watchlist` | POST |
| `routes_watchlist.py:196` | `/watchlist` | DELETE |
| `routes_watchlist.py:204` | `/watchlist/{ticker}` | DELETE |
| `routes_watchlist.py:591` | `/watchlist/{ticker}/focus` | PATCH |
| `routes_watchlist.py:618` | `/watchlist/{ticker}/positioning` | PATCH |
| `routes_evaluations.py:141` | `/evaluations` | POST |
| `routes_evaluations.py:342` | `/evaluations/{id}` | DELETE |
| `routes_news.py:109` | `/news/keywords` | POST |
| `routes_news.py:137` | `/news/clear` | POST |
| `routes_news.py:274` | `/news/smart-alerts/scan` | POST |
| `routes_news.py:298` | `/news/smart-alerts/add-keyword-rule` | POST |
| `routes_news.py:310` | `/news/smart-alerts/add-stock-rule` | POST |
| `routes_boards.py:53` | `/boards/build` | POST |
| `routes_boards.py:88` | `/boards/verify` | POST |

**分步实施指引：**

1. 在每个包含写操作的路由文件顶部 import `verify_api_key`
2. 为所有 POST/PUT/DELETE/PATCH 端点参数列表末尾添加 `_: None = Depends(verify_api_key)`
3. 只读 GET 端点不需要认证
4. 逐文件修改，每修改一个文件跑一次测试验证

---

### T-03: 添加 slowapi 速率限制

| 属性 | 值 |
|------|-----|
| **受影响文件** | `web/app.py:26-48`，`requirements.txt:12` |
| **工作量** | M |
| **依赖** | T-01 |

**Before — `web/app.py:26-48`（无速率限制）：**

```python
def create_app() -> FastAPI:
    """Instantiate the FastAPI application with routing and middleware."""
    application = FastAPI(
        title="A-Share Monitor API",
        version="0.1.0",
        description="Batch K-line data service for A-share monitoring dashboard.",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

**After — `web/app.py`：**

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)


def create_app() -> FastAPI:
    application = FastAPI(
        title="A-Share Monitor API",
        version="0.1.0",
        description="Batch K-line data service for A-share monitoring dashboard.",
    )

    # 速率限制
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )
```

**After — `requirements.txt`（新增一行）：**

```
slowapi>=0.1.9
```

**在路由中使用限流（示例 — `routes_news.py:241-255`）：**

```python
from web.app import limiter

@router.get("/rss")
@limiter.limit("10/minute")
async def get_rss_feed(
    request: Request,
    url: str = Query(..., description="RSS feed URL"),
    ...
):
```

**分步实施指引：**

1. 在 `requirements.txt` 末尾添加 `slowapi>=0.1.9`
2. 在 `web/app.py` 初始化 `Limiter` 并注册异常处理器
3. 对公开端点（如 RSS 抓取、新闻轮询）添加 `@limiter.limit()` 装饰器
4. 建议配置：公开 GET 端点 `30/minute`，写操作端点 `10/minute`
5. 运行 `pip install -r requirements.txt` 安装依赖

---

### T-04: 修复 RSS SSRF 漏洞

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/api/routes_news.py:241-255` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `src/api/routes_news.py:241-255`（RSS 端点直接将用户提供的 URL 传给后端服务，无校验）：**

```python
@router.get("/rss")
async def get_rss_feed(
    url: str = Query(..., description="RSS feed URL"),
    name: str = Query("RSS Feed", description="Feed 名称"),
    limit: int = Query(10, ge=1, le=50),
):
    service = get_external_service()
    items = service.fetch_rss_feed(url, name=name, limit=limit)
    return {"name": name, "url": url, "count": len(items), "items": items}
```

**After — 添加 URL 校验函数并在端点中使用：**

```python
from urllib.parse import urlparse
import ipaddress

ALLOWED_RSS_DOMAINS = [
    "finance.sina.com.cn",
    "rss.eastmoney.com",
    "rsshub.app",
]


def validate_rss_url(url: str) -> str:
    """校验 RSS URL，防止 SSRF 攻击。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Only HTTP(S) URLs allowed")
    # 阻止私有 IP
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback:
            raise HTTPException(400, "Private/loopback URLs not allowed")
    except ValueError:
        pass  # hostname 是域名而非 IP — OK
    if ALLOWED_RSS_DOMAINS and parsed.hostname not in ALLOWED_RSS_DOMAINS:
        raise HTTPException(400, f"Domain not in allowlist: {parsed.hostname}")
    return url


@router.get("/rss")
async def get_rss_feed(
    url: str = Query(..., description="RSS feed URL"),
    name: str = Query("RSS Feed", description="Feed 名称"),
    limit: int = Query(10, ge=1, le=50),
):
    validated_url = validate_rss_url(url)
    service = get_external_service()
    items = service.fetch_rss_feed(validated_url, name=name, limit=limit)
    return {"name": name, "url": validated_url, "count": len(items), "items": items}
```

**分步实施指引：**

1. 在 `routes_news.py` 顶部添加 `urlparse`、`ipaddress` 导入
2. 定义 `ALLOWED_RSS_DOMAINS` 白名单和 `validate_rss_url()` 校验函数
3. 在 `/rss` 端点调用 `validate_rss_url()` 后再传给服务层
4. 编写测试：内网 IP 返回 400，非白名单域名返回 400，白名单域名通过

---

### T-05: 消除 shell=True 调用

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/tasks/scheduler.py:84-96` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `src/tasks/scheduler.py:82-96`：**

```python
def _update_concept_data(self) -> None:
    """Update concept daily data (AKShare - runs in background)"""
    try:
        import subprocess
        from pathlib import Path
        script_path = Path(__file__).parent.parent.parent / "scripts" / "update_concept_daily.py"
        log_path = Path(__file__).parent.parent.parent / "logs" / "concept_daily.log"
        log_path.parent.mkdir(exist_ok=True)

        # Run in background since it takes ~6 minutes
        cmd = f'nohup python {script_path} > {log_path} 2>&1 &'
        subprocess.Popen(cmd, shell=True)
        LOGGER.info("Concept daily update started in background")
    except Exception as e:
        LOGGER.error(f"Concept daily update exception: {e}", exc_info=True)
```

**After：**

```python
def _update_concept_data(self) -> None:
    """Update concept daily data (AKShare - runs in background)"""
    try:
        import subprocess
        import sys
        from pathlib import Path
        script_path = Path(__file__).parent.parent.parent / "scripts" / "update_concept_daily.py"
        log_path = Path(__file__).parent.parent.parent / "logs" / "concept_daily.log"
        log_path.parent.mkdir(exist_ok=True)

        # Run in background since it takes ~6 minutes
        with open(log_path, "w") as log_file:
            subprocess.Popen(
                [sys.executable, str(script_path)],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        LOGGER.info("Concept daily update started in background")
    except Exception as e:
        LOGGER.error(f"Concept daily update exception: {e}", exc_info=True)
```

**分步实施指引：**

1. 将 `f'nohup python ...'` 字符串命令替换为列表参数 `[sys.executable, str(script_path)]`
2. 移除 `shell=True` 参数
3. 使用 `start_new_session=True` 替代 `nohup` 实现后台运行
4. 使用文件对象替代 shell 重定向
5. 全局搜索 `shell=True` 确认无其他遗漏

---

### T-06: Docker 添加非特权用户

| 属性 | 值 |
|------|-----|
| **受影响文件** | `Dockerfile:26-30` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `Dockerfile:26-30`（以 root 运行）：**

```dockerfile
RUN mkdir -p data logs

EXPOSE 8000

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**After：**

```dockerfile
RUN mkdir -p data logs

RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**分步实施指引：**

1. 在 `EXPOSE` 之前添加 `RUN useradd` 和 `USER appuser` 指令
2. 确保 `/app`（WORKDIR）及 `data`、`logs` 目录归 `appuser` 所有
3. 本地构建测试：`docker build -t ashare-test . && docker run --rm ashare-test whoami`，确认输出 `appuser`

---

### T-07: 收紧 CORS 配置

| 属性 | 值 |
|------|-----|
| **受影响文件** | `web/app.py:34-40` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `web/app.py:34-40`：**

```python
application.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**After：**

```python
application.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)
```

**分步实施指引：**

1. 将 `allow_methods=["*"]` 替换为显式列表
2. 将 `allow_headers=["*"]` 替换为实际使用的头部
3. 前端测试各类请求确认无 CORS 报错

---

### T-08: 隐藏 str(e) 错误详情

| 属性 | 值 |
|------|-----|
| **受影响文件** | 多个 `routes_*.py` 文件（共 30+ 处 `str(e)` 泄漏） |
| **工作量** | M |
| **依赖** | T-01（需要 `debug` 字段） |

**代表性文件及行号（部分清单）：**

| 文件 | 行号 |
|------|------|
| `routes_watchlist.py` | 193 |
| `routes_pattern.py` | 57, 87 |
| `routes_index.py` | 122, 207 |
| `routes_screener.py` | 71, 90 |
| `routes_boards.py` | 84, 113, 135 |
| `routes_concepts.py` | 347 |
| `routes_sectors.py` | 193, 226, 272, 310, 331, 357, 374 |
| `routes_sentiment.py` | 54, 71, 113 |
| `routes_anomaly.py` | 49, 61, 114 |
| `routes_rotation.py` | 50, 60, 85 |
| `routes_commodities.py` | 121, 173 |

**Before — `src/api/routes_watchlist.py:191-193`：**

```python
except Exception as e:
    db.rollback()
    raise HTTPException(status_code=500, detail=str(e))
```

**After：**

```python
except Exception as e:
    db.rollback()
    logger.exception("Unexpected error in add_to_watchlist")
    detail = str(e) if get_settings().debug else "Internal server error"
    raise HTTPException(status_code=500, detail=detail)
```

**Before — `src/api/routes_pattern.py:56-57`：**

```python
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```

**After：**

```python
except Exception as e:
    logger.exception(f"Pattern analysis failed for {ticker}")
    detail = str(e) if get_settings().debug else "Internal server error"
    raise HTTPException(status_code=500, detail=detail)
```

**分步实施指引：**

1. 确认 `Settings` 类已有 `debug: bool` 字段（T-01 中添加）
2. 全局搜索 `str(e)` 在 `HTTPException` 中的使用：`grep -rn "str(e)" src/api/routes_*.py`
3. 对每处替换为条件表达式：`str(e) if get_settings().debug else "Internal server error"`
4. 在每个 `except` 块中添加 `logger.exception(...)` 日志
5. 确保每个文件有 `from src.config import get_settings` 导入
6. 注意：`routes_status.py:78` 的 `"error": str(e)` 在 `data-freshness` 响应体内，也需处理

---

## 3.2 Sprint 2: 架构基础（T-09 ~ T-14）

### T-09: 统一 Session 管理 -> Depends(get_db)

| 属性 | 值 |
|------|-----|
| **受影响文件** | `routes_watchlist.py`, `routes_evaluations.py`, `routes_boards.py`, `routes_meta.py`, `routes_concepts.py` |
| **工作量** | L |
| **依赖** | 无 |

**当前各文件 `session_scope()` 调用统计：**

| 文件 | 使用次数 | 行号 |
|------|---------|------|
| `routes_watchlist.py` | 8 处 | 54, 199, 207, 224, 240, 349, 594, 621 |
| `routes_evaluations.py` | 5 处 | 171, 219, 280, 316, 345 |
| `routes_boards.py` | 3 处 | 151, 322, 392 |
| `routes_meta.py` | 2 处 | 24, 86 |
| `routes_concepts.py` | 1 处 | 412 |

**Before — `src/api/routes_watchlist.py:51-54`：**

```python
@router.get("", response_model=List[WatchlistItemResponse])
def get_watchlist():
    """获取自选股列表，返回完整的股票信息和分类"""
    with session_scope() as session:
        watchlist_items = session.query(Watchlist).order_by(
```

**After：**

```python
@router.get("", response_model=List[WatchlistItemResponse])
def get_watchlist(db: Session = Depends(get_db)):
    """获取自选股列表，返回完整的股票信息和分类"""
    watchlist_items = db.query(Watchlist).order_by(
```

**Before — `src/api/routes_evaluations.py:141-171`：**

```python
@router.post("", response_model=EvaluationResponse)
def create_evaluation(data: EvaluationCreate):
    # ... 截图处理逻辑 ...
    eval_date = date.today().isoformat()

    with session_scope() as session:
        evaluation = KlineEvaluation(...)
        session.add(evaluation)
        session.flush()
```

**After：**

```python
@router.post("", response_model=EvaluationResponse)
def create_evaluation(data: EvaluationCreate, db: Session = Depends(get_db)):
    # ... 截图处理逻辑 ...
    eval_date = date.today().isoformat()

    evaluation = KlineEvaluation(...)
    db.add(evaluation)
    db.flush()
```

**Before — `src/api/routes_boards.py:149-151`：**

```python
@router.get("/list")
def list_board_mappings(board_type: Optional[str] = None) -> dict:
    from sqlalchemy import select
    with session_scope() as session:
```

**After：**

```python
@router.get("/list")
def list_board_mappings(board_type: Optional[str] = None, db: Session = Depends(get_db)) -> dict:
    from sqlalchemy import select
    # 直接使用 db，不再需要 session_scope
```

**Before — `src/api/routes_meta.py:17-24`：**

```python
@router.get("/search")
def search_symbols(q: str):
    from src.database import session_scope
    from src.models import SymbolMetadata, Watchlist
    import sqlite3

    with session_scope() as session:
```

**After：**

```python
@router.get("/search")
def search_symbols(q: str, db: Session = Depends(get_db)):
    from src.models import SymbolMetadata, Watchlist
    # 使用 db 替代 session_scope()
    # 注意：此端点还有 sqlite3 直连问题，将在 T-11 中一并修复
```

**分步实施指引：**

1. 逐文件处理：移除 `from src.database import session_scope` 导入
2. 确认 `from src.api.dependencies import get_db` 已导入
3. 为每个使用 `session_scope()` 的函数签名添加 `db: Session = Depends(get_db)`
4. 将 `with session_scope() as session:` 块体的内容提升一级缩进，把 `session` 替换为 `db`
5. 移除 `with` 语句本身（Depends(get_db) 会自动管理 session 生命周期）
6. 注意：`routes_evaluations.py` 中 `session.flush()` 后的手动 commit 不再需要（FastAPI 的 `get_db` 在请求结束时自动关闭）
7. 逐文件运行测试确认功能正常

---

### T-10: 修复 MarketDataService Session 泄漏

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/api/dependencies.py:33-49` |
| **工作量** | M |
| **依赖** | T-09 |

**Before — `src/api/dependencies.py:33-49`：**

```python
# 全局服务实例（单例模式）
_market_data_service: MarketDataService | None = None


def get_data_service() -> MarketDataService:
    """
    获取 MarketDataService 单例

    注意：使用全局单例和专用Session，因为服务需要长期存在
    """
    global _market_data_service
    if _market_data_service is None:
        # 为服务创建专用session（不会自动关闭）
        session = SessionLocal()
        symbol_repo = SymbolRepository(session)
        _market_data_service = MarketDataService(symbol_repo=symbol_repo)
    return _market_data_service
```

**After：**

```python
def get_data_service(db: Session = Depends(get_db)) -> MarketDataService:
    """
    获取 MarketDataService（每请求一个实例，共享请求级 Session）

    Session 由 get_db 管理生命周期，请求结束自动关闭。
    """
    symbol_repo = SymbolRepository(db)
    return MarketDataService(symbol_repo=symbol_repo)
```

**分步实施指引：**

1. 删除 `_market_data_service` 全局变量和单例逻辑
2. 将 `get_data_service()` 改为接收 `db: Session = Depends(get_db)` 参数
3. 每次请求创建新的 `SymbolRepository` 和 `MarketDataService`
4. 更新所有使用 `Depends(get_data_service)` 的路由——签名不变，FastAPI 会自动注入依赖链
5. 检查 `MarketDataService` 内部是否缓存了 session，如有也需清理

---

### T-11: 消除直接 sqlite3 调用

| 属性 | 值 |
|------|-----|
| **受影响文件** | `routes_watchlist.py:117-128`, `routes_meta.py:22-49`, `perception/sources/market_data_source.py:15,216-254` |
| **工作量** | M |
| **依赖** | T-09 |

**Before — `src/api/routes_watchlist.py:117-128`：**

```python
if not symbol:
    # 从全量 stock_basic 表查找
    import sqlite3
    from src.config import get_settings
    db_url = get_settings().database_url
    db_path = db_url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT symbol, name, industry, market FROM stock_basic WHERE symbol = ?",
        (request.ticker,)
    ).fetchone()
    conn.close()
```

**After：**

```python
if not symbol:
    from sqlalchemy import text
    row = db.execute(
        text("SELECT symbol, name, industry, market FROM stock_basic WHERE symbol = :ticker"),
        {"ticker": request.ticker}
    ).mappings().first()
```

**Before — `src/api/routes_meta.py:22-49`：**

```python
import sqlite3
from src.config import get_settings
db_url = get_settings().database_url
db_path = db_url.replace("sqlite:///", "")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute(
    """SELECT symbol, name, industry, market
       FROM stock_basic
       WHERE symbol LIKE ? OR name LIKE ?
       ORDER BY CASE WHEN symbol = ? THEN 0
                     WHEN symbol LIKE ? THEN 1
                     ELSE 2 END,
                symbol
       LIMIT 30""",
    (f"%{q}%", f"%{q}%", q, f"{q}%")
)
rows = c.fetchall()
conn.close()
```

**After：**

```python
from sqlalchemy import text

rows = db.execute(
    text("""SELECT symbol, name, industry, market
       FROM stock_basic
       WHERE symbol LIKE :pattern OR name LIKE :pattern
       ORDER BY CASE WHEN symbol = :exact THEN 0
                     WHEN symbol LIKE :prefix THEN 1
                     ELSE 2 END,
                symbol
       LIMIT 30"""),
    {"pattern": f"%{q}%", "exact": q, "prefix": f"{q}%"}
).mappings().fetchall()
```

**Before — `src/perception/sources/market_data_source.py:216-231`：**

```python
def get_watchlist(self) -> List[Dict[str, Any]]:
    db = Path(self._db_path)
    if not db.exists():
        logger.warning("DB not found: %s", self._db_path)
        return []
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT ticker, category, is_focus FROM watchlist ORDER BY is_focus DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
```

**After：**

```python
def get_watchlist(self) -> List[Dict[str, Any]]:
    from src.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    try:
        rows = session.execute(
            text("SELECT ticker, category, is_focus FROM watchlist ORDER BY is_focus DESC")
        ).mappings().fetchall()
        return [dict(r) for r in rows]
    finally:
        session.close()
```

**分步实施指引：**

1. 全局搜索 `import sqlite3` 找到所有使用位置
2. 将 `sqlite3.connect()` + 原生 SQL 替换为 SQLAlchemy `text()` 查询
3. 对路由文件使用已有的 `db` session 参数（依赖 T-09 转换完成）
4. 对非路由文件（如 `market_data_source.py`）使用 `SessionLocal()` + `try/finally`
5. 使用 `.mappings()` 获取 dict-like 结果，与 `sqlite3.Row` 行为一致
6. 注意：SQL 参数占位符从 `?` 改为 `:name` 形式

---

### T-12: 删除 models_old.py

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/models_old.py`（529 行） |
| **工作量** | M |
| **依赖** | T-11 |

**分步实施指引：**

1. 搜索所有引用：`grep -rn "models_old" src/ tests/`
2. 对比 `models_old.py` 中的枚举/类定义与 `src/models.py` 的对应项，确认功能已迁移
3. 若发现仍被引用的模型，将引用改为指向 `src/models.py` 中的等价定义
4. 删除 `src/models_old.py`
5. 运行全量测试：`pytest tests/ -x`

---

### T-13: 迁移 lifecycle.py -> lifespan

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/lifecycle.py:1-54`, `web/app.py:7,28,47` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `src/lifecycle.py:13-54`（使用已弃用的 `on_event`）：**

```python
def register_startup_shutdown(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _startup() -> None:
        LOGGER.info("Application startup - using Tushare Pro")
        init_db()
        settings = get_settings()
        if settings.scheduler:
            global _scheduler_manager
            _scheduler_manager = SchedulerManager()
            _scheduler_manager.start()
            kline_scheduler = get_scheduler()
            kline_scheduler.start()
            LOGGER.info("K-line scheduler STARTED (daily=Tushare, 30m=Sina)")
        try:
            await start_crypto_ws()
            LOGGER.info("Crypto WebSocket STARTED (Binance realtime)")
        except Exception as e:
            LOGGER.warning(f"Crypto WebSocket failed to start: {e} (non-fatal)")

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        LOGGER.info("Application shutdown")
        if _scheduler_manager:
            _scheduler_manager.shutdown()
        stop_scheduler()
        try:
            await stop_crypto_ws()
        except Exception as e:
            LOGGER.warning(f"Crypto WS shutdown error: {e}")
```

**After — `src/lifecycle.py`（使用 `lifespan` 上下文管理器）：**

```python
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import get_settings
from src.database import init_db
from src.tasks.scheduler import SchedulerManager
from src.services.kline_scheduler import get_scheduler, stop_scheduler
from src.services.crypto_ws import start_crypto_ws, stop_crypto_ws
from src.utils.logging import LOGGER


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    LOGGER.info("Application startup - using Tushare Pro")
    init_db()

    settings = get_settings()
    scheduler_manager = None
    if settings.scheduler:
        scheduler_manager = SchedulerManager()
        scheduler_manager.start()
        kline_scheduler = get_scheduler()
        kline_scheduler.start()
        LOGGER.info("K-line scheduler STARTED (daily=Tushare, 30m=Sina)")

    try:
        await start_crypto_ws()
        LOGGER.info("Crypto WebSocket STARTED (Binance realtime)")
    except Exception as e:
        LOGGER.warning(f"Crypto WebSocket failed to start: {e} (non-fatal)")

    yield

    # ── Shutdown ──
    LOGGER.info("Application shutdown")
    if scheduler_manager:
        scheduler_manager.shutdown()
    stop_scheduler()
    try:
        await stop_crypto_ws()
    except Exception as e:
        LOGGER.warning(f"Crypto WS shutdown error: {e}")
```

**After — `web/app.py`（修改 `create_app`）：**

```python
# Before
from src.lifecycle import register_startup_shutdown

application = FastAPI(
    title="A-Share Monitor API",
    ...
)
register_startup_shutdown(application)

# After
from src.lifecycle import lifespan

application = FastAPI(
    title="A-Share Monitor API",
    ...,
    lifespan=lifespan,
)
# 删除 register_startup_shutdown(application)
```

**分步实施指引：**

1. 重写 `src/lifecycle.py`，将 startup/shutdown 合并为 `lifespan` async context manager
2. 消除 `_scheduler_manager` 全局变量，改用 `yield` 前后的局部变量
3. 在 `web/app.py` 中用 `FastAPI(lifespan=lifespan)` 替代 `register_startup_shutdown(app)`
4. 移除 `web/app.py` 中对 `register_startup_shutdown` 的导入
5. 测试 startup/shutdown 事件正常触发

---

### T-14: 修复 BaseRepository.count()

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/repositories/base_repository.py:126-135` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `src/repositories/base_repository.py:126-135`：**

```python
def count(self) -> int:
    """
    统计记录总数

    Returns:
        记录数量
    """
    stmt = select(self.model_class)
    result = self.session.execute(stmt)
    return len(list(result.scalars().all()))
```

> 问题：加载全表数据到内存只为计数，在大表上会导致严重性能问题。

**After：**

```python
from sqlalchemy import func

def count(self) -> int:
    """
    统计记录总数

    Returns:
        记录数量
    """
    stmt = select(func.count()).select_from(self.model_class)
    return self.session.execute(stmt).scalar() or 0
```

**分步实施指引：**

1. 在文件顶部导入 `from sqlalchemy import func`（与已有的 `select` 同行）
2. 替换 `count()` 方法实现
3. 编写单元测试验证：空表返回 0，含数据表返回正确计数

---

## 3.3 Sprint 3: 代码质量（T-15 ~ T-23）

### T-15: 修复 5 处 bare except

| 属性 | 值 |
|------|-----|
| **受影响文件** | 见下表 |
| **工作量** | M |
| **依赖** | 无 |

**各处 bare except 位置及修复方案：**

**1) `src/services/anomaly_monitor.py:182`**

Before:
```python
except:
    pass
```

After:
```python
except Exception as e:
    LOGGER.warning(f"Failed to save anomaly for {anomaly.get('ticker')}: {e}")
```

**2) `src/api/routes_pattern.py:78`**

Before:
```python
for ticker in ticker_list:
    try:
        result = analyze_stock_pattern(ticker, pattern_days)
        results.append(result)
    except:
        continue
```

After:
```python
for ticker in ticker_list:
    try:
        result = analyze_stock_pattern(ticker, pattern_days)
        results.append(result)
    except Exception as e:
        logger.warning(f"Pattern analysis failed for {ticker}: {e}")
        continue
```

**3) `src/api/routes_concepts.py:273`**

Before:
```python
async def fetch_one(code: str):
    try:
        return await get_concept_realtime(code)
    except:
        return None
```

After:
```python
async def fetch_one(code: str):
    try:
        return await get_concept_realtime(code)
    except Exception as e:
        logger.warning(f"Failed to fetch realtime for concept {code}: {e}")
        return None
```

**4) `src/services/news_sentiment.py:130`**

Before:
```python
try:
    resp = requests.get(f'http://127.0.0.1:8000/api/news/latest?limit={limit}', timeout=5)
    if resp.ok:
        data = resp.json()
        return data if isinstance(data, list) else data.get('news', [])
except:
    pass
return []
```

After:
```python
try:
    resp = requests.get(f'http://127.0.0.1:8000/api/news/latest?limit={limit}', timeout=5)
    if resp.ok:
        data = resp.json()
        return data if isinstance(data, list) else data.get('news', [])
except Exception as e:
    logger.warning(f"Failed to fetch recent news: {e}")
return []
```

**5) `src/services/daily_review_data_service.py:580`**

Before:
```python
try:
    return json.loads(board.constituents)
except:
    return []
```

After:
```python
try:
    return json.loads(board.constituents)
except (json.JSONDecodeError, TypeError) as e:
    logger.warning(f"Failed to parse board constituents for {board_code}: {e}")
    return []
```

**分步实施指引：**

1. 对每处 bare `except:` 替换为 `except Exception as e:`
2. 添加适当的日志输出，包含上下文信息
3. 对于已知只会抛特定异常的地方（如 `json.loads`），使用具体异常类型
4. 全局搜索确认无遗漏：`grep -rn "except:" src/ --include="*.py" | grep -v "except Exception"`

---

### T-16: 统一异常使用

| 属性 | 值 |
|------|-----|
| **受影响文件** | 各 `routes_*.py` 中直接使用 `raise HTTPException` 的地方 |
| **工作量** | M |
| **依赖** | T-15 |

> 注意：`web/app.py` 中已有完善的异常处理器注册（第 51-142 行），覆盖了 `DataNotFoundError`、`ValidationError`、`AuthenticationError`、`AuthorizationError`、`ExternalAPIError`、`ServiceUnavailableError`、`DatabaseError`、`BusinessLogicError`、`ConfigurationError`、`AShareBaseException` 等。

**当前问题：** 路由文件中大量直接使用 `raise HTTPException(...)` 而非抛出自定义业务异常，导致异常处理器无法统一拦截。

**Before — 路由中直接抛 HTTPException：**

```python
# routes_boards.py:82-85
except Exception as e:
    raise HTTPException(
        status_code=500,
        detail=f"Failed to build board mappings: {str(e)}"
    )
```

**After — 使用已有的自定义异常：**

```python
# routes_boards.py
from src.exceptions import DatabaseError

except Exception as e:
    raise DatabaseError(operation="build_board_mappings", reason=str(e))
```

**重构方向（按场景映射）：**

| 当前写法 | 替换为 |
|---------|--------|
| `HTTPException(404, "...not found")` | `DataNotFoundError(resource, identifier)` |
| `HTTPException(400, "Invalid...")` | `ValidationError(field, reason)` |
| `HTTPException(500, str(e))` | 对应业务异常（`DatabaseError` / `BusinessLogicError`）|
| `HTTPException(503, "...failed")` | `ServiceUnavailableError(service, reason)` |

**分步实施指引：**

1. 保留 `web/app.py` 中已有的异常处理器，不需要新增
2. 逐文件将 `raise HTTPException(...)` 替换为对应的自定义异常
3. 对于 `400` 级别的 `HTTPException`（如参数校验）可保留 HTTPException（这是 FastAPI 标准用法）
4. 重点替换 `500` 级别的 HTTPException，改为抛出业务异常
5. 每修改一个文件运行相关测试

---

### T-17: 统一日志方式

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/perception/pipeline.py:42`, `src/perception/sources/market_data_source.py:32`, `src/api/routes_boards.py:298` 等 |
| **工作量** | S |
| **依赖** | 无 |

**Before — 不统一的日志获取方式：**

```python
# perception/pipeline.py:42
import logging
logger = logging.getLogger(__name__)

# perception/sources/market_data_source.py:32
import logging
logger = logging.getLogger(__name__)

# routes_boards.py:298
import logging
logging.warning(f"Failed to fetch THS members for {board_name}: {e}")
```

**After — 统一使用项目日志工具：**

```python
from src.utils.logging import get_logger

logger = get_logger(__name__)
```

**分步实施指引：**

1. 全局搜索 `logging.getLogger(__name__)` 和 `import logging`
2. 替换为 `from src.utils.logging import get_logger` + `logger = get_logger(__name__)`
3. 内联的 `logging.warning(...)` 替换为 `logger.warning(...)`
4. 不修改第三方库或标准库代码

---

### T-18: 修复 SQLite pool_size 配置

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/database.py:11-23` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `src/database.py:11-23`：**

```python
engine = create_engine(
    settings.database_url,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    }
    if settings.database_url.startswith("sqlite")
    else {},
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    future=True,
)
```

> 问题：SQLite 不支持多连接池（同文件锁），`pool_size=20` 会导致 `OperationalError: database is locked`。

**After：**

```python
from sqlalchemy.pool import StaticPool

if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=StaticPool,
        future=True,
    )
else:
    engine = create_engine(
        settings.database_url,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        future=True,
    )
```

**分步实施指引：**

1. 导入 `from sqlalchemy.pool import StaticPool`
2. 使用 `if/else` 分支为 SQLite 和其他数据库使用不同的引擎配置
3. SQLite 使用 `StaticPool`（单连接复用），保留 WAL 模式的 pragma 配置
4. 非 SQLite 保持原有的连接池配置
5. 测试：确认并发请求不再出现 `database is locked`

---

### T-19: 重命名 exceptions.TimeoutError

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/exceptions.py:256-264` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `src/exceptions.py:256-264`：**

```python
class TimeoutError(AShareBaseException):
    """操作超时"""

    def __init__(self, operation: str, timeout: float):
        super().__init__(
            message=f"Operation {operation} timed out after {timeout}s",
            code="TIMEOUT_ERROR",
            details={"operation": operation, "timeout": timeout}
        )
```

> 问题：`TimeoutError` 遮蔽了 Python 内置的 `builtins.TimeoutError`。

**After：**

```python
class OperationTimeoutError(AShareBaseException):
    """操作超时"""

    def __init__(self, operation: str, timeout: float):
        super().__init__(
            message=f"Operation {operation} timed out after {timeout}s",
            code="TIMEOUT_ERROR",
            details={"operation": operation, "timeout": timeout}
        )
```

**分步实施指引：**

1. 在 `src/exceptions.py` 中将 `class TimeoutError` 重命名为 `class OperationTimeoutError`
2. 全局搜索引用：`grep -rn "TimeoutError" src/ tests/ --include="*.py"`
3. 更新所有 `from src.exceptions import TimeoutError` 为 `from src.exceptions import OperationTimeoutError`
4. 更新所有 `raise TimeoutError(...)` 为 `raise OperationTimeoutError(...)`

---

### T-20: 修复 Perception 硬编码路径

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/perception/pipeline.py:49-58` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `src/perception/pipeline.py:49-58`：**

```python
@dataclass
class PipelineConfig:
    """Pipeline-level configuration."""

    # ashare API base URL
    api_base_url: str = "http://127.0.0.1:8000"

    # SQLite DB path for market data
    db_path: str = "data/market.db"
```

**After：**

```python
@dataclass
class PipelineConfig:
    """Pipeline-level configuration."""

    api_base_url: str = ""
    db_path: str = ""

    def __post_init__(self):
        if not self.api_base_url or not self.db_path:
            from src.config import get_settings
            settings = get_settings()
            if not self.api_base_url:
                self.api_base_url = "http://127.0.0.1:8000"
            if not self.db_path:
                self.db_path = str(settings.data_dir / "market.db")
```

**分步实施指引：**

1. 将 `db_path` 的默认值改为从 `get_settings().data_dir` 动态派生
2. 保留 `api_base_url` 的默认值（本地开发用），但可通过参数覆盖
3. 同时检查 `market_data_source.py:41` 的 `DEFAULT_DB_PATH = "data/market.db"` 也需使用配置

---

### T-21: 拆分 routes_watchlist.py

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/api/routes_watchlist.py`（636 行）；新建 `src/services/watchlist_service.py` |
| **工作量** | L |
| **依赖** | T-09 |

**当前问题：** `routes_watchlist.py` 包含 636 行代码，路由处理函数内嵌大量业务逻辑（组合计算、行业分析、盈亏统计等）。

**重构方向：**

```
routes_watchlist.py (636 lines)
├── GET  /watchlist            → 54 行业务逻辑
├── POST /watchlist            → 88 行业务逻辑
├── GET  /watchlist/portfolio  → 99 行业务逻辑
├── GET  /watchlist/analytics  → 240 行业务逻辑  ← 最需要提取
├── PATCH /watchlist/focus     → 17 行
└── PATCH /watchlist/positioning → 15 行
```

**After — `src/services/watchlist_service.py`（新建）：**

```python
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from src.models import Watchlist, SymbolMetadata, Kline, KlineTimeframe, SymbolType


class WatchlistService:
    def __init__(self, db: Session):
        self.db = db

    def get_watchlist_items(self) -> List[Dict[str, Any]]:
        """获取自选股列表，组合股票信息和分类"""
        ...

    def calculate_portfolio_history(self) -> Dict[str, Any]:
        """计算投资组合历史净值曲线"""
        ...

    def calculate_analytics(self) -> Dict[str, Any]:
        """计算自选股组合分析数据（行业分配、涨跌统计等）"""
        ...
```

**After — `src/api/routes_watchlist.py`（瘦化后）：**

```python
from src.services.watchlist_service import WatchlistService

@router.get("/analytics")
def get_watchlist_analytics(db: Session = Depends(get_db)):
    """获取自选股组合分析数据"""
    service = WatchlistService(db)
    return service.calculate_analytics()
```

**分步实施指引：**

1. 新建 `src/services/watchlist_service.py`
2. 将 `get_watchlist()`、`get_portfolio_history()`、`get_watchlist_analytics()` 中的业务逻辑提取到 `WatchlistService`
3. 路由函数只做：参数校验 -> 调用服务 -> 返回结果
4. 每提取一个方法，运行对应 API 测试验证功能不变
5. 目标：`routes_watchlist.py` 缩减到 ~150 行

---

### T-22: 修复 routes_status.py 伪造时间戳

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/api/routes_status.py:120-172` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `src/api/routes_status.py:120-172`：**

```python
@router.get("/update-times")
def get_update_times() -> dict[str, Any]:
    """返回数据更新时间信息，用于前端显示。"""
    now = datetime.now()

    # 返回前端期望的格式
    return {
        "current_time": now.isoformat(),
        "kline_times": {
            "stock_day": {
                "symbol_type": "stock",
                "timeframe": "day",
                "last_update": now.isoformat()  # ← 伪造！使用当前时间而非真实更新时间
            },
            # ... 所有 6 个类型都返回 now.isoformat()
        },
        "scheduled_jobs": {
            "daily_update": {
                "next_run": (now + timedelta(hours=1)).isoformat(),  # ← 伪造！
            },
        }
    }
```

> 问题：所有 `last_update` 字段都返回 `datetime.now()`，而非从数据库查询真实的最后更新时间。`next_run` 也是伪造的相对时间。前端显示的"数据更新于"信息完全不可靠。

**After：**

```python
@router.get("/update-times")
def get_update_times(db: Session = Depends(get_db)) -> dict[str, Any]:
    """返回数据更新时间信息，用于前端显示。"""
    now = datetime.now()

    kline_times = {}
    for symbol_type in [SymbolType.STOCK, SymbolType.INDEX, SymbolType.CONCEPT]:
        for timeframe in [KlineTimeframe.DAY, KlineTimeframe.MINS_30]:
            key = f"{symbol_type.value}_{timeframe.value}"
            last_time = db.query(func.max(Kline.trade_time)).filter(
                Kline.symbol_type == symbol_type,
                Kline.timeframe == timeframe,
            ).scalar()

            kline_times[key] = {
                "symbol_type": symbol_type.value,
                "timeframe": timeframe.value,
                "last_update": last_time if last_time else None,
            }

    return {
        "current_time": now.isoformat(),
        "kline_times": kline_times,
    }
```

**分步实施指引：**

1. 将函数签名添加 `db: Session = Depends(get_db)`
2. 用真实的 `func.max(Kline.trade_time)` 查询替代 `now.isoformat()`
3. 移除 `scheduled_jobs` 中的伪造 `next_run`（如需保留，从 APScheduler 实例获取真实调度信息）
4. 前端验证显示的时间是否合理

---

### T-23: 合并 Ticker 标准化逻辑

| 属性 | 值 |
|------|-----|
| **受影响文件** | `src/utils/ticker_utils.py`, `src/schemas/normalized.py` |
| **工作量** | M |
| **依赖** | 无 |

**当前问题：** 两个文件都实现了 ticker 标准化：
- `src/utils/ticker_utils.py:15-182` — `TickerNormalizer` 类（含验证、市场识别）
- `src/schemas/normalized.py:27-106` — `NormalizedTicker` Pydantic 模型（含格式转换）

存在重复的正则匹配、前缀剥离、补零逻辑。

**合并策略：**

保留 `NormalizedTicker`（Pydantic 模型）作为唯一的标准化入口，将 `TickerNormalizer` 中独有的功能（`is_valid()` A 股模式验证、`identify_market()` 市场识别）合并到 `NormalizedTicker`。

**After — `src/schemas/normalized.py`（增强）：**

```python
class NormalizedTicker(BaseModel):
    raw: str  # 6位代码

    # A 股合法模式（来自 TickerNormalizer）
    VALID_PATTERNS = [
        r"^60[0135]\d{3}$",
        r"^000\d{3}$",
        r"^002\d{3}$",
        r"^300\d{3}$",
        r"^68[89]\d{3}$",
        r"^[48]\d{5}$",
    ]

    @field_validator("raw", mode="before")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        # ... 现有逻辑 ...

    @classmethod
    def is_valid_ashare(cls, ticker: str) -> bool:
        """验证是否为合法 A 股代码"""
        if not ticker or len(ticker) != 6 or not ticker.isdigit():
            return False
        return any(re.match(p, ticker) for p in cls.VALID_PATTERNS)

    def identify_market(self) -> str:
        """识别所属交易所"""
        first_three = self.raw[:3]
        if first_three in ("600", "601", "603", "605"):
            return "SSE"
        elif first_three == "000":
            return "SZSE"
        elif first_three == "002":
            return "SME"
        elif first_three == "300":
            return "ChiNext"
        elif self.raw[:2] == "68":
            return "STAR"
        elif self.raw[0] in ("4", "8"):
            return "BSE"
        return "Unknown"
```

**After — `src/utils/ticker_utils.py`（薄代理层）：**

```python
"""保持向后兼容的 thin wrapper。新代码请直接使用 NormalizedTicker。"""

from src.schemas.normalized import NormalizedTicker


class TickerNormalizer:
    @classmethod
    def normalize(cls, ticker: str) -> str:
        return NormalizedTicker(raw=ticker).raw

    @classmethod
    def is_valid(cls, ticker: str) -> bool:
        return NormalizedTicker.is_valid_ashare(ticker)

    @classmethod
    def normalize_batch(cls, tickers: list[str]) -> list[str]:
        seen = set()
        result = []
        for raw in tickers:
            try:
                t = NormalizedTicker(raw=raw).raw
                if t not in seen:
                    result.append(t)
                    seen.add(t)
            except ValueError:
                continue
        return result

    @classmethod
    def identify_market(cls, ticker: str) -> str:
        return NormalizedTicker(raw=ticker).identify_market()
```

**分步实施指引：**

1. 将 `TickerNormalizer` 的 `VALID_PATTERNS` 和 `identify_market()` 迁移到 `NormalizedTicker`
2. 将 `TickerNormalizer` 重写为委托给 `NormalizedTicker` 的薄代理
3. 搜索所有 `TickerNormalizer` 的调用方确认兼容
4. 新代码统一使用 `NormalizedTicker`

---

## 3.4 Sprint 4: 测试补全（T-24 ~ T-29）

### T-24: 创建共享 conftest.py

| 属性 | 值 |
|------|-----|
| **受影响文件** | 新建 `tests/conftest.py` |
| **工作量** | M |
| **依赖** | 无 |

**After — `tests/conftest.py`（新建）：**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base


@pytest.fixture
def db_engine():
    """创建内存数据库引擎"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine):
    """创建数据库 Session，每个测试自动回滚"""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """创建 FastAPI TestClient，注入测试数据库"""
    from fastapi.testclient import TestClient
    from web.app import create_app
    from src.api.dependencies import get_db

    app = create_app()

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
```

**分步实施指引：**

1. 新建 `tests/conftest.py`
2. 定义 `db_engine`、`db_session`、`client` 三个核心 fixture
3. 使用 `sqlite:///:memory:` + `StaticPool` 实现隔离测试
4. 通过 `dependency_overrides` 注入测试数据库到 FastAPI 应用
5. 确认 `tests/__init__.py` 存在（如无则创建空文件）
6. 运行现有测试验证 fixture 不影响已有测试

---

### T-25: 为 simulated_service 补测试

| 属性 | 值 |
|------|-----|
| **受影响文件** | 新建 `tests/services/test_simulated_service.py` |
| **工作量** | L |
| **依赖** | T-24 |

**测试覆盖范围：**

```python
# tests/services/test_simulated_service.py

class TestSimulatedService:
    """模拟交易服务测试"""

    def test_open_position(self, db_session):
        """测试开仓"""
        ...

    def test_close_position(self, db_session):
        """测试平仓"""
        ...

    def test_calculate_pnl(self, db_session):
        """测试盈亏计算"""
        ...

    def test_position_tracking(self, db_session):
        """测试持仓跟踪"""
        ...

    def test_order_execution(self, db_session):
        """测试订单执行"""
        ...

    def test_portfolio_value(self, db_session):
        """测试组合市值计算"""
        ...
```

**分步实施指引：**

1. 阅读 `src/services/simulated_service.py` 了解完整 API
2. 创建 `tests/services/` 目录（如不存在）
3. 编写测试覆盖：开仓、平仓、盈亏计算、持仓跟踪、订单执行
4. 使用 `db_session` fixture 提供隔离数据库
5. 目标覆盖率：核心业务逻辑 >= 80%

---

### T-26: 为 data_pipeline 补测试

| 属性 | 值 |
|------|-----|
| **受影响文件** | 新建 `tests/services/test_data_pipeline.py` |
| **工作量** | L |
| **依赖** | T-24 |

**测试覆盖范围：**

```python
# tests/services/test_data_pipeline.py

class TestMarketDataService:
    """数据管道服务测试"""

    def test_list_symbols(self, db_session):
        """测试获取标的列表"""
        ...

    def test_last_refresh_time(self, db_session):
        """测试最后刷新时间"""
        ...

    def test_data_fetching_with_mock(self, db_session):
        """测试数据拉取（mock Tushare API）"""
        ...

    def test_data_transformation(self, db_session):
        """测试数据转换标准化"""
        ...

    def test_data_storage(self, db_session):
        """测试数据存储（upsert 逻辑）"""
        ...
```

**分步实施指引：**

1. 阅读 `src/services/data_pipeline.py` 了解完整 API
2. 对依赖外部 API（Tushare）的方法使用 `unittest.mock.patch` 进行 mock
3. 覆盖数据获取、转换、存储三个阶段
4. 测试边界情况：空数据、重复数据、异常数据

---

### T-27: 为未覆盖 API 路由补测试

| 属性 | 值 |
|------|-----|
| **受影响文件** | 新建多个测试文件 |
| **工作量** | L |
| **依赖** | T-24 |

**优先测试的路由模块：**

| 路由文件 | 测试文件 | 优先级 |
|---------|---------|--------|
| `routes_watchlist.py` | `tests/api/test_routes_watchlist.py` | P0 |
| `routes_evaluations.py` | `tests/api/test_routes_evaluations.py` | P1 |
| `routes_news.py` | `tests/api/test_routes_news.py` | P1 |
| `routes_boards.py` | `tests/api/test_routes_boards.py` | P2 |
| `routes_concepts.py` | `tests/api/test_routes_concepts.py` | P2 |

**示例 — `tests/api/test_routes_watchlist.py`：**

```python
import pytest


class TestWatchlistRoutes:
    def test_get_watchlist_empty(self, client):
        resp = client.get("/api/watchlist")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_add_to_watchlist(self, client, db_session):
        # 先在 db_session 中插入 stock_basic 测试数据
        ...
        resp = client.post("/api/watchlist", json={"ticker": "600519"})
        assert resp.status_code == 201

    def test_add_duplicate_returns_400(self, client, db_session):
        ...

    def test_remove_from_watchlist(self, client, db_session):
        ...

    def test_check_in_watchlist(self, client, db_session):
        ...

    def test_toggle_focus(self, client, db_session):
        ...
```

**分步实施指引：**

1. 创建 `tests/api/` 目录
2. 对每个路由模块编写 Happy Path + Error Path 测试
3. 使用 `client` fixture 进行 HTTP 级测试
4. 使用 `db_session` fixture 预置测试数据
5. 需 mock 外部依赖的端点（如 Tushare API、新闻爬虫）使用 `unittest.mock.patch`

---

### T-28: 启用 pytest-cov 覆盖率收集

| 属性 | 值 |
|------|-----|
| **受影响文件** | `pytest.ini:9-16` |
| **工作量** | S |
| **依赖** | 无 |

**Before — `pytest.ini:9-16`：**

```ini
# Output options
addopts =
    -v
    --tb=short
    --strict-markers
    --disable-warnings

# Coverage options (if pytest-cov is installed)
# addopts = --cov=src --cov-report=html --cov-report=term
```

**After：**

```ini
# Output options
addopts =
    -v
    --tb=short
    --strict-markers
    --disable-warnings
    --cov=src
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-fail-under=50
```

**分步实施指引：**

1. 安装 pytest-cov：`pip install pytest-cov` 并添加到 `requirements.txt` 开发依赖
2. 取消注释覆盖率配置，合并到现有 `addopts`
3. 初始阈值设为 `--cov-fail-under=50`，随测试补全逐步提高
4. `--cov-report=term-missing` 显示未覆盖行号，便于定位
5. `--cov-report=html:htmlcov` 生成 HTML 报告
6. 将 `htmlcov/` 添加到 `.gitignore`

---

### T-29: 清理问题测试文件

| 属性 | 值 |
|------|-----|
| **受影响文件** | `tests/test_momentum_signals.py`, `test_market_style.py`（项目根目录），`tests/test_persist_metadata_chunking.py` |
| **工作量** | S |
| **依赖** | T-24 |

**问题 1: `tests/test_momentum_signals.py` — 非标准测试（print 驱动，无 assert）**

Before:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_signal_detection():
    print("\n" + "="*60)
    print("动量信号检测功能测试")
```

After — 重写为标准 pytest 测试：
```python
import pytest

def test_signal_detection():
    """测试动量信号检测逻辑"""
    # 使用 assert 替代 print
    ...
```

**问题 2: `test_market_style.py` — 位于项目根目录而非 `tests/`**

```bash
# 移动到正确位置
mv test_market_style.py tests/test_market_style.py
```

Before（项目根 `test_market_style.py:5`）:
```python
from src.database import SessionLocal
```

After（使用 conftest fixture）:
```python
def test_market_style_index(db_session):
    """Test the market style index calculation"""
    # 使用 db_session fixture 替代 SessionLocal()
```

**问题 3: `tests/test_persist_metadata_chunking.py` — 直连生产数据库**

Before:
```python
from src.database import SessionLocal
from src.models import SymbolMetadata
from src.repositories.symbol_repository import SymbolRepository

session = SessionLocal()  # ← 连接生产数据库！
symbol_repo = SymbolRepository(session)
```

After — 使用 conftest 的 `db_session` fixture:
```python
def test_persist_metadata_handles_large_ticker_list(db_session):
    from src.models import SymbolMetadata
    from src.repositories.symbol_repository import SymbolRepository

    symbol_repo = SymbolRepository(db_session)  # ← 使用内存数据库
```

**分步实施指引：**

1. `test_momentum_signals.py`：移除 `sys.path` hack，改用 assert 断言替代 print
2. `test_market_style.py`：`mv` 到 `tests/` 目录，改用 `db_session` fixture
3. `test_persist_metadata_chunking.py`：用 `db_session` 参数替代 `SessionLocal()` 直连
4. 运行 `pytest tests/ -v` 确认所有测试通过

---

## 3.5 Sprint 依赖关系总览

```
Sprint 1 (安全加固)
  T-01 ──┬──> T-02
         ├──> T-03
         └──> T-08
  T-04 (独立)
  T-05 (独立)
  T-06 (独立)
  T-07 (独立)

Sprint 2 (架构基础)
  T-09 ──┬──> T-10
         ├──> T-11 ──> T-12
         └──> T-21
  T-13 (独立)
  T-14 (独立)

Sprint 3 (代码质量)
  T-15 ──> T-16
  T-17 (独立)
  T-18 (独立)
  T-19 (独立)
  T-20 (独立)
  T-22 (独立)
  T-23 (独立)

Sprint 4 (测试补全)
  T-24 ──┬──> T-25
         ├──> T-26
         ├──> T-27
         └──> T-29
  T-28 (独立)
```

## 3.6 工作量汇总

| 工作量 | 任务数 | 任务编号 |
|--------|--------|---------|
| **S** (< 2h) | 12 | T-04, T-05, T-06, T-07, T-13, T-14, T-17, T-18, T-19, T-20, T-22, T-28, T-29 |
| **M** (2-8h) | 11 | T-02, T-03, T-08, T-10, T-11, T-12, T-15, T-16, T-23, T-24 |
| **L** (> 8h) | 6 | T-01, T-09, T-21, T-25, T-26, T-27 |
# Phase 4: Review（验证）

> 本阶段为每个 Sprint 交付物提供可执行的验证 Checklist。每条验证项包含具体命令和期望输出，确保修复完整、无遗漏。

---

## 4.1 Sprint 1 验证 Checklist — 安全加固

### T-01 & T-02: API 认证验证

```bash
# 验证未认证请求被拒绝 (应返回 401)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/watchlist -X POST -d '{"ticker":"000001.SZ"}'
# Expected: 401

# 验证认证请求成功 (应返回 200)
curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: your-key" http://localhost:8000/api/watchlist -X POST -d '{"ticker":"000001.SZ"}'
# Expected: 200 or 201

# 验证 GET 请求仍然可用（读操作无需认证）
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/watchlist
# Expected: 200

# 确认所有写端点都加了认证
grep -rn "router\.\(post\|put\|delete\|patch\)" src/api/routes_*.py | grep -v "verify_api_key"
# Expected: 空输出（所有写端点都应包含 verify_api_key）
```

### T-03: 速率限制验证

```bash
# 快速发送 15 个请求测试限流（假设限制为 10/minute）
for i in $(seq 1 15); do
  echo "Request $i: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/news/rss?url=https://rsshub.app/cls/telegraph)"
done
# Expected: 前 10 个返回 200，后 5 个返回 429

# 验证 slowapi 已安装
pip show slowapi | grep Version
```

### T-04: SSRF 修复验证

```bash
# 尝试访问内网 IP（应被拒绝）
curl -s http://localhost:8000/api/news/rss?url=http://127.0.0.1:8080/secret
# Expected: 400 Bad Request

curl -s http://localhost:8000/api/news/rss?url=http://192.168.1.1/admin
# Expected: 400 Bad Request

# 尝试非白名单域名
curl -s http://localhost:8000/api/news/rss?url=http://evil.com/rss
# Expected: 400 Bad Request

# 白名单域名正常工作
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/api/news/rss?url=https://rsshub.app/cls/telegraph"
# Expected: 200
```

### T-05: shell=True 消除验证

```bash
# 确认没有 shell=True 调用（排除测试文件和注释）
grep -rn "shell=True" src/ scripts/*.py --include="*.py"
# Expected: 空输出

# 确认 scheduler 仍能正常启动脚本
curl -s http://localhost:8000/api/status | python -m json.tool
```

### T-06: Docker 非特权用户验证

```bash
# 验证 Dockerfile 包含 USER 指令
grep "^USER" Dockerfile
# Expected: USER appuser

# 构建并验证容器不以 root 运行
docker build -t ashare-test .
docker run --rm ashare-test whoami
# Expected: appuser
```

### T-07: CORS 配置验证

```bash
# 验证 CORS 不再使用通配符
grep -n "allow_methods\|allow_headers" web/app.py
# Expected: 看到具体的方法和头部列表，而非 "*"
```

### T-08: 错误信息隐藏验证

```bash
# 在非 debug 模式下触发错误
curl -s http://localhost:8000/api/some-endpoint-that-errors | python -m json.tool
# Expected: {"detail": "Internal server error"} 而非 stack trace

# 确认 str(e) 不再直接用于响应
grep -rn 'detail=str(e)' src/api/
# Expected: 空输出
```

---

## 4.2 Sprint 2 验证 Checklist — 架构基础

### T-09: Session 管理统一验证

```bash
# 确认不再使用 session_scope() in route files
grep -rn "session_scope" src/api/
# Expected: 空输出

# 确认所有路由使用 Depends(get_db)
grep -rn "Depends(get_db)" src/api/routes_*.py | wc -l
# Expected: 数量 >= 之前的 session_scope 使用次数
```

### T-10: MarketDataService Session 修复验证

```bash
# 确认不再有全局 _market_data_service 变量
grep -n "_market_data_service" src/api/dependencies.py
# Expected: 空输出

# 确认 get_data_service 使用 Depends(get_db)
grep -A5 "def get_data_service" src/api/dependencies.py
# Expected: 看到 db: Session = Depends(get_db)
```

### T-11: sqlite3 直接调用消除验证

```bash
# 确认 src/ 下无直接 sqlite3 导入
grep -rn "import sqlite3" src/
# Expected: 空输出
```

### T-12: models_old.py 删除验证

```bash
# 确认文件已删除
ls src/models_old.py 2>&1
# Expected: No such file or directory

# 确认无引用
grep -rn "models_old" src/ tests/
# Expected: 空输出

# 运行测试确认无回归
pytest tests/ -x --tb=short
```

### T-13: Lifespan 迁移验证

```bash
# 确认不再使用 on_event
grep -rn "on_event" src/
# Expected: 空输出

# 确认使用 lifespan
grep -n "lifespan" src/lifecycle.py web/app.py
# Expected: 看到 @asynccontextmanager + lifespan 定义
```

### T-14: BaseRepository.count() 验证

```bash
# 确认使用 func.count()
grep -A3 "def count" src/repositories/base_repository.py
# Expected: 看到 func.count() 而非 len(list(...))

# 运行 repository 测试
pytest tests/repositories/ -v
```

---

## 4.3 Sprint 3 验证 Checklist — 代码质量

### T-15: Bare except 消除验证

```bash
# 确认无 bare except
grep -rn "except:" src/ --include="*.py" | grep -v "except Exception" | grep -v "# except"
# Expected: 空输出（Python 语法的 except: 全部消除）

# 更精确的 AST 检查
python -c "
import ast, sys, pathlib
for p in pathlib.Path('src').rglob('*.py'):
    tree = ast.parse(p.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            print(f'{p}:{node.lineno}: bare except')
"
# Expected: 空输出
```

### T-16: 异常使用统一验证

```bash
# 确认注册了自定义异常处理器
grep -n "exception_handler" web/app.py
# Expected: 看到 AShareBaseException 和 DataNotFoundError 的处理器
```

### T-17: 日志统一验证

```bash
# 确认统一使用 LOGGER
grep -rn "logging.getLogger" src/ --include="*.py" | grep -v "__pycache__"
# Expected: 只在 src/utils/logging.py 中出现
```

### T-18: SQLite pool_size 验证

```bash
# 确认 SQLite 使用 StaticPool
grep -n "poolclass\|pool_size" src/database.py
# Expected: 看到 StaticPool 用于 SQLite
```

### T-19: TimeoutError 重命名验证

```bash
# 确认无遮盖
python -c "from src.exceptions import OperationTimeoutError; print('OK')"
# Expected: OK

# 确认旧名称不存在
grep -rn "exceptions.TimeoutError" src/
# Expected: 空输出
```

### T-20: Perception 硬编码路径验证

```bash
# 确认无硬编码路径
grep -n "api_base_url\|db_path" src/perception/pipeline.py
# Expected: 使用 get_settings() 而非硬编码
```

### T-21: routes_watchlist.py 拆分验证

```bash
# 确认路由文件行数减少
wc -l src/api/routes_watchlist.py
# Expected: < 300 行

# 确认 service 层已创建
ls src/services/watchlist_service.py
# Expected: 文件存在

# 验证功能正常
pytest tests/ -k watchlist -v
```

### T-22 & T-23: 其他修复验证

```bash
# routes_status.py 时间戳验证
curl -s http://localhost:8000/api/status/update-times | python -m json.tool
# Expected: 真实时间戳

# Ticker 统一性验证
grep -rn "normalize_ticker\|NormalizedTicker" src/ --include="*.py" | head -20
# Expected: 统一使用一个入口
```

---

## 4.4 Sprint 4 验证 Checklist — 测试补全

### T-24: conftest.py 验证

```bash
# 确认 conftest.py 存在
ls tests/conftest.py
# Expected: 文件存在

# 确认 fixtures 可用
pytest tests/ --co -q | head -20
# Expected: 看到测试用例列表
```

### T-25 ~ T-27: 新测试验证

```bash
# 运行全部测试
pytest tests/ -v --tb=short

# 验证新增测试文件
ls tests/services/test_simulated_service.py tests/services/test_data_pipeline.py
# Expected: 文件存在

# 验证测试通过率
pytest tests/ --tb=line -q
```

### T-28: 覆盖率验证

```bash
# 运行带覆盖率的测试
pytest tests/ --cov=src --cov-report=term-missing

# 验证覆盖率 >= 50%（最低门槛）
pytest tests/ --cov=src --cov-fail-under=50
# Expected: 通过
```

### T-29: 问题测试文件清理验证

```bash
# 确认无硬编码路径
grep -rn "/Users/" tests/ --include="*.py"
# Expected: 空输出

# 确认 test_market_style.py 已移动
ls test_market_style.py 2>&1
# Expected: No such file

ls tests/test_market_style.py
# Expected: 文件存在
```

---

## 4.5 回归测试命令集

> 以下命令集应在每个 Sprint 结束后完整执行一次，确保无回归问题。建议将其保存为 `scripts/regression_test.sh`。

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "====== AShare 完整回归测试套件 ======"
echo ""

# 1. 运行全部单元测试
echo "--- [1/4] 单元测试 + 覆盖率 ---"
pytest tests/ -v --tb=short --cov=src --cov-report=term-missing

# 2. 运行安全检查
echo ""
echo "--- [2/4] 安全静态检查 ---"

echo -n "  2.1 Bare except:        "
BARE=$(grep -rn "except:" src/ --include="*.py" | grep -v "except Exception" | wc -l)
[ "$BARE" -eq 0 ] && echo "PASS" || echo "FAIL ($BARE found)"

echo -n "  2.2 shell=True:          "
SHELL=$(grep -rn "shell=True" src/ --include="*.py" | wc -l)
[ "$SHELL" -eq 0 ] && echo "PASS" || echo "FAIL ($SHELL found)"

echo -n "  2.3 Direct sqlite3:      "
SQLITE=$(grep -rn "import sqlite3" src/ --include="*.py" | wc -l)
[ "$SQLITE" -eq 0 ] && echo "PASS" || echo "FAIL ($SQLITE found)"

echo -n "  2.4 Unauth write endpoints: "
UNAUTH=$(grep -rn "router\.\(post\|put\|delete\|patch\)" src/api/routes_*.py | grep -v "verify_api_key" | wc -l)
[ "$UNAUTH" -eq 0 ] && echo "PASS" || echo "FAIL ($UNAUTH found)"

echo -n "  2.5 Error detail leak:   "
LEAK=$(grep -rn "detail=str(e)" src/api/ --include="*.py" | wc -l)
[ "$LEAK" -eq 0 ] && echo "PASS" || echo "FAIL ($LEAK found)"

# 3. API 冒烟测试（需要服务器运行）
echo ""
echo "--- [3/4] API 冒烟测试 ---"
if curl -s -o /dev/null -w "" http://localhost:8000/api/health 2>/dev/null; then
  python -c "
import requests
BASE = 'http://localhost:8000'
tests = [
    ('GET',  f'{BASE}/api/health',     200),
    ('GET',  f'{BASE}/api/watchlist',   200),
    ('POST', f'{BASE}/api/watchlist',   401),  # Should require auth
]
passed = 0
for method, url, expected in tests:
    r = requests.request(method, url)
    ok = r.status_code == expected
    passed += ok
    status = 'PASS' if ok else 'FAIL'
    print(f'  {status} {method} {url} -> {r.status_code} (expected {expected})')
print(f'  Smoke tests: {passed}/{len(tests)} passed')
"
else
  echo "  SKIP: 服务器未运行，跳过冒烟测试"
fi

# 4. Docker 构建验证
echo ""
echo "--- [4/4] Docker 构建验证 ---"
if command -v docker &>/dev/null; then
  docker build -t ashare-test . && docker run --rm ashare-test whoami
  # Expected: appuser
else
  echo "  SKIP: Docker 未安装"
fi

echo ""
echo "====== 回归测试完成 ======"
```

---

# Phase 5: Acceptance（验收）

> 验收阶段定义每个 Sprint 的完成标准（Definition of Done）、整体指标目标、以及最终签收流程。确保所有改进可量化、可追踪。

---

## 5.1 每个 Sprint 的 Definition of Done

### Sprint 1: 安全加固 DoD

| 条件 | 验证方法 |
|------|---------|
| 所有写操作 API 要求 X-API-Key 认证 | `curl -X POST` 返回 401 |
| API Key 通过环境变量配置 | `grep "API_KEY" .env.example` |
| 速率限制对高频端点生效 | 15 次请求后返回 429 |
| RSS 端点拒绝内网 URL | `curl ?url=http://127.0.0.1` 返回 400 |
| 无 `shell=True` 调用 | `grep -rn "shell=True" src/` 空输出 |
| Docker 以非 root 用户运行 | `docker run --rm image whoami` = appuser |
| CORS 使用白名单方法和头部 | 代码审查确认 |
| 生产环境不泄露错误详情 | `DEBUG=false` 时错误返回通用信息 |
| 所有安全测试通过 | `pytest tests/ -k security` |

### Sprint 2: 架构基础 DoD

| 条件 | 验证方法 |
|------|---------|
| API 路由中无 `session_scope()` 调用 | `grep -rn "session_scope" src/api/` 空输出 |
| MarketDataService 使用请求级 Session | 代码审查 `dependencies.py` |
| `src/` 下无直接 `import sqlite3` | `grep -rn "import sqlite3" src/` 空输出 |
| `models_old.py` 已删除 | `ls src/models_old.py` 报错 |
| `on_event` 已迁移到 `lifespan` | `grep "on_event" src/` 空输出 |
| `BaseRepository.count()` 使用 SQL COUNT | 代码审查 + 测试通过 |
| 所有现有测试仍通过 | `pytest tests/ -x` |

### Sprint 3: 代码质量 DoD

| 条件 | 验证方法 |
|------|---------|
| 无 bare `except:` | AST 检查脚本输出为空 |
| 自定义异常处理器已注册 | `grep "exception_handler" web/app.py` |
| 日志方式统一使用 LOGGER | `grep "logging.getLogger" src/` 仅在 logging.py |
| SQLite 使用 StaticPool | `grep "StaticPool" src/database.py` |
| `TimeoutError` 已重命名 | `from src.exceptions import OperationTimeoutError` |
| `routes_watchlist.py` < 300 行 | `wc -l` 确认 |
| 所有测试通过 | `pytest tests/ -x` |

### Sprint 4: 测试补全 DoD

| 条件 | 验证方法 |
|------|---------|
| `tests/conftest.py` 提供 db_session 和 client fixtures | `pytest --co -q` |
| simulated_service 测试覆盖 >= 70% | `pytest --cov=src/services/simulated_service` |
| data_pipeline 测试覆盖 >= 60% | `pytest --cov=src/services/data_pipeline` |
| 路由测试覆盖 >= 6/18 模块 | 文件计数 |
| pytest-cov 已启用且门槛 50% | `pytest --cov-fail-under=50` 通过 |
| 无硬编码路径或真实 DB 操作 | `grep "/Users/" tests/` 空输出 |

---

## 5.2 指标目标矩阵

| 指标 | 当前值 | Sprint 1 后 | Sprint 2 后 | Sprint 3 后 | Sprint 4 后（目标） |
|------|--------|------------|------------|------------|-------------------|
| **测试覆盖率** | ~44% | 44% | 45% | 48% | >=65% |
| **Bare except 数量** | 5 | 5 | 5 | 0 | 0 |
| **未认证写端点** | ~50+ | 0 | 0 | 0 | 0 |
| **session_scope() in routes** | 19 | 19 | 0 | 0 | 0 |
| **直接 sqlite3 导入 (src/)** | 3 | 3 | 0 | 0 | 0 |
| **shell=True 调用** | 2 | 0 | 0 | 0 | 0 |
| **Docker root 运行** | Yes | No | No | No | No |
| **废弃 API (on_event)** | 2 | 2 | 0 | 0 | 0 |
| **models_old.py 行数** | 529 | 529 | 0 (deleted) | 0 | 0 |
| **routes_watchlist.py 行数** | 635 | 635 | 635 | <300 | <300 |
| **pytest-cov 启用** | No | No | No | No | Yes |
| **conftest.py 存在** | No | No | No | No | Yes |
| **API 路由测试覆盖** | 4/18 | 4/18 | 4/18 | 4/18 | >=8/18 |

> 注意：每个指标的变化节奏与其所属 Sprint 对齐。例如安全指标在 Sprint 1 后即达标，架构指标在 Sprint 2 后达标，以此类推。

---

## 5.3 最终签收标准

### 整体质量门控

所有以下条件 **必须同时满足** 才能签收：

**1. 安全基线**

- [ ] 所有 POST/PUT/DELETE/PATCH 端点要求 API Key 认证
- [ ] 速率限制对外部 API 代理端点生效
- [ ] 无 SSRF 漏洞（RSS 端点已加固）
- [ ] 无命令注入风险（`shell=True` 已消除）
- [ ] Docker 容器以非 root 用户运行
- [ ] 生产环境不泄露内部错误信息

**2. 架构一致性**

- [ ] 数据库会话管理统一使用 `Depends(get_db)`
- [ ] 无全局长生命周期 Session
- [ ] 无直接 `sqlite3` 调用（在 src/ 下）
- [ ] 无废弃 API 使用（`on_event` -> `lifespan`）
- [ ] 无遗留死代码（`models_old.py` 已删除）

**3. 代码质量**

- [ ] 零 bare `except:` 语句
- [ ] 异常处理统一使用自定义异常体系
- [ ] 日志方式统一
- [ ] 最大路由文件 < 400 行

**4. 测试保障**

- [ ] 整体测试覆盖率 >= 50%（目标 65%）
- [ ] 核心服务（simulated_service, data_pipeline）有测试
- [ ] API 路由覆盖 >= 8/18 模块
- [ ] `pytest-cov` 已启用且门槛设置
- [ ] 所有测试在 CI 中通过

**5. 运维就绪**

- [ ] `.env.example` 包含所有必需环境变量
- [ ] Docker 构建成功
- [ ] 健康检查端点可用

### 签收流程

```
1. 开发者完成所有 Sprint
       |
       v
2. 运行完整回归测试套件（Phase 4.5）
       |
       v
3. 代码审查（至少 1 人）
       |
       v
4. 性能基准对比（确认无性能回归）
       |
       v
5. 在 staging 环境部署验证
       |
       v
6. 产品负责人签收
```

> 签收完成后，将本文档归档至 `docs/reviews/` 目录，并在项目 README 中更新安全和测试状态徽章。
