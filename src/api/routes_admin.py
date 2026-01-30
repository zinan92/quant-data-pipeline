"""
管理员API
提供系统状态、调度任务管理等功能
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, text
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.models import DataUpdateLog, DataUpdateStatus, Kline, KlineTimeframe, SymbolType
from src.schemas import SchedulerJobsResponse, TradingStatusResponse
from src.services.kline_scheduler import get_scheduler
from src.utils.logging import get_logger

# 使用上海时区（UTC+8）
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

router = APIRouter()
logger = get_logger(__name__)


@router.get("/update-status")
def get_update_status(
    limit: int = Query(default=20, ge=1, le=100, description="返回记录数"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """获取数据更新状态"""
    try:
        # 获取最近的更新记录
        logs = (
            db.query(DataUpdateLog)
            .order_by(desc(DataUpdateLog.completed_at))
            .limit(limit)
            .all()
        )

        # 按数据类型分组获取最新状态
        latest_by_type = {}
        for log in logs:
            if log.update_type not in latest_by_type:
                latest_by_type[log.update_type] = {
                    "update_type": log.update_type,
                    "symbol_type": log.symbol_type,
                    "timeframe": log.timeframe,
                    "status": log.status.value,
                    "records_updated": log.records_updated,
                    "started_at": log.started_at.isoformat() if log.started_at else None,
                    "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                    "error_message": log.error_message,
                }

        # 获取K线数据统计
        kline_stats = (
            db.query(
                Kline.symbol_type,
                Kline.timeframe,
                func.count(Kline.id).label("count"),
                func.max(Kline.trade_time).label("latest_time"),
            )
            .group_by(Kline.symbol_type, Kline.timeframe)
            .all()
        )

        stats = []
        for row in kline_stats:
            stats.append({
                "symbol_type": row.symbol_type.value,
                "timeframe": row.timeframe.value,
                "count": row.count,
                "latest_time": row.latest_time,
            })

        return {
            "latest_updates": latest_by_type,
            "kline_stats": stats,
            "recent_logs": [
                {
                    "id": log.id,
                    "update_type": log.update_type,
                    "symbol_type": log.symbol_type,
                    "timeframe": log.timeframe,
                    "status": log.status.value,
                    "records_updated": log.records_updated,
                    "started_at": log.started_at.isoformat() if log.started_at else None,
                    "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                    "error_message": log.error_message,
                }
                for log in logs
            ],
        }

    except Exception as e:
        logger.exception("获取更新状态失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/jobs", response_model=SchedulerJobsResponse)
def get_scheduler_jobs() -> SchedulerJobsResponse:
    """获取调度任务列表"""
    try:
        scheduler = get_scheduler()
        jobs = scheduler.get_jobs()

        return SchedulerJobsResponse(
            jobs=jobs,
            count=len(jobs),
            is_running=scheduler._is_running,
        )
    except Exception as e:
        logger.exception("获取调度任务失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/run/{job_id}")
async def run_scheduler_job(job_id: str) -> Dict[str, Any]:
    """手动触发指定任务"""
    try:
        scheduler = get_scheduler()
        success = await scheduler.run_job_now(job_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"未找到任务: {job_id}")

        return {
            "success": True,
            "job_id": job_id,
            "message": f"任务 {job_id} 已触发",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"触发任务失败: {job_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/update-times")
def get_update_times(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    获取各数据源的更新时间信息
    包括最后更新时间和下次更新时间
    """
    try:
        scheduler = get_scheduler()
        jobs = scheduler.get_jobs() if scheduler._is_running else []

        # 获取最新的K线数据时间
        kline_times = {}
        for symbol_type in ["index", "concept", "stock"]:
            for timeframe in ["day", "30m"]:
                latest = (
                    db.query(func.max(Kline.trade_time))
                    .filter(
                        Kline.symbol_type == symbol_type,
                        Kline.timeframe == timeframe
                    )
                    .scalar()
                )

                # 将字符串时间转换为带时区的datetime
                last_update_iso = None
                if latest:
                    try:
                        # 尝试解析不同的时间格式
                        if len(latest) == 10:  # YYYY-MM-DD
                            dt = datetime.strptime(latest, "%Y-%m-%d")
                            # 日线数据假设是当天收盘时间 15:00
                            dt = dt.replace(hour=15, minute=0, second=0)
                        elif len(latest) == 19:  # YYYY-MM-DD HH:MM:SS
                            dt = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S")
                        else:
                            dt = datetime.fromisoformat(latest.replace(' ', 'T'))

                        # 添加时区信息（上海时区）
                        dt = dt.replace(tzinfo=SHANGHAI_TZ)
                        last_update_iso = dt.isoformat()
                    except Exception as e:
                        logger.warning(f"Failed to parse trade_time: {latest}, error: {e}")
                        last_update_iso = latest  # 保留原始字符串

                key = f"{symbol_type}_{timeframe}"
                kline_times[key] = {
                    "symbol_type": symbol_type,
                    "timeframe": timeframe,
                    "last_update": last_update_iso,
                }

        # 添加调度任务的下次运行时间
        job_next_run = {}
        for job in jobs:
            job_next_run[job["id"]] = job.get("next_run")

        # 返回当前时间（带时区）
        current_time_with_tz = datetime.now(SHANGHAI_TZ)

        return {
            "current_time": current_time_with_tz.isoformat(),
            "kline_times": kline_times,
            "scheduled_jobs": {
                "daily_update": {
                    "description": "日线更新 (交易日 15:30)",
                    "next_run": job_next_run.get("daily_update"),
                    "applies_to": ["index_day", "concept_day", "stock_day"]
                },
                "30m_update": {
                    "description": "30分钟更新 (交易时间每30分钟)",
                    "next_run": job_next_run.get("30m_update"),
                    "applies_to": ["index_30m", "concept_30m", "stock_30m"]
                },
                "all_stock_daily": {
                    "description": "全市场日线更新 (交易日 16:00)",
                    "next_run": job_next_run.get("all_stock_daily"),
                    "applies_to": ["all_stock_day"]
                }
            }
        }

    except Exception as e:
        logger.exception("获取更新时间失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kline-summary")
def get_kline_summary(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """获取K线数据摘要"""
    try:
        # 各类型K线统计
        stats = (
            db.query(
                Kline.symbol_type,
                Kline.timeframe,
                func.count(Kline.id).label("count"),
                func.count(func.distinct(Kline.symbol_code)).label("symbols"),
                func.min(Kline.trade_time).label("earliest"),
                func.max(Kline.trade_time).label("latest"),
            )
            .group_by(Kline.symbol_type, Kline.timeframe)
            .all()
        )

        summary = []
        total_count = 0
        for row in stats:
            summary.append({
                "symbol_type": row.symbol_type.value,
                "timeframe": row.timeframe.value,
                "record_count": row.count,
                "symbol_count": row.symbols,
                "earliest_time": row.earliest,
                "latest_time": row.latest,
            })
            total_count += row.count

        return {
            "total_records": total_count,
            "by_type": summary,
            "generated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.exception("获取K线摘要失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trading-status", response_model=TradingStatusResponse)
def get_trading_status() -> TradingStatusResponse:
    """获取当前交易状态"""
    scheduler = get_scheduler()

    now = datetime.now()
    is_trading_day = scheduler.is_trading_day(now)
    is_trading_time = scheduler.is_trading_time(now)

    return TradingStatusResponse(
        is_trading_day=is_trading_day,
        is_trading_time=is_trading_time,
        current_time=now.isoformat(),
        latest_trade_date=None,  # TODO: 从数据库获取
    )


@router.get("/data-freshness")
def validate_data_freshness(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    验证数据新鲜度
    检查各类数据是否过期，返回问题列表和建议
    """
    from datetime import timedelta

    try:
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        issues = []
        warnings = []

        # 1. 检查概念日线数据新鲜度
        concept_daily_stats = db.execute(
            text("""
                SELECT
                    MAX(trade_time) as latest,
                    COUNT(DISTINCT symbol_code) as total_concepts,
                    SUM(CASE WHEN trade_time >= :yesterday THEN 1 ELSE 0 END) as fresh_count
                FROM (
                    SELECT symbol_code, MAX(trade_time) as trade_time
                    FROM klines
                    WHERE symbol_type = 'CONCEPT' AND timeframe = 'DAY'
                    GROUP BY symbol_code
                )
            """),
            {"yesterday": yesterday.isoformat()}
        ).fetchone()

        if concept_daily_stats:
            latest_concept_daily = concept_daily_stats[0]
            total_concepts = concept_daily_stats[1] or 0
            fresh_concepts = concept_daily_stats[2] or 0
            stale_concepts = total_concepts - fresh_concepts

            if stale_concepts > 0:
                issues.append({
                    "type": "concept_daily_stale",
                    "severity": "warning" if stale_concepts < 10 else "error",
                    "message": f"概念日线数据: {stale_concepts}/{total_concepts} 个概念数据过期",
                    "latest_date": latest_concept_daily,
                    "action": "运行 /api/admin/scheduler/run/daily_update 更新"
                })

        # 2. 检查概念30分钟数据
        concept_30m_latest = db.execute(
            text("""
                SELECT MAX(trade_time) FROM klines
                WHERE symbol_type = 'CONCEPT' AND timeframe = 'MINS_30'
            """)
        ).scalar()

        if concept_30m_latest:
            # 30分钟数据应该在今天
            if concept_30m_latest[:10] < today.isoformat():
                issues.append({
                    "type": "concept_30m_stale",
                    "severity": "warning",
                    "message": f"概念30分钟数据最新时间: {concept_30m_latest}，可能需要更新",
                    "action": "运行 /api/admin/scheduler/run/30m_update 更新"
                })

        # 3. 检查指数日线数据
        index_daily_latest = db.execute(
            text("""
                SELECT MAX(trade_time) FROM klines
                WHERE symbol_type = 'INDEX' AND timeframe = 'DAY'
            """)
        ).scalar()

        if index_daily_latest and index_daily_latest < yesterday.isoformat():
            issues.append({
                "type": "index_daily_stale",
                "severity": "warning",
                "message": f"指数日线数据最新时间: {index_daily_latest}",
                "action": "检查Tushare API是否正常"
            })

        # 4. 检查异常日期（如年份>2100）
        bad_dates_count = db.execute(
            text("""
                SELECT COUNT(*) FROM klines WHERE trade_time > '2100-01-01'
            """)
        ).scalar()

        if bad_dates_count and bad_dates_count > 0:
            issues.append({
                "type": "invalid_dates",
                "severity": "error",
                "message": f"发现 {bad_dates_count} 条日期异常的数据 (年份>2100)",
                "action": "运行 scripts/fix_concept_30m_dates.py 修复"
            })

        # 汇总结果
        is_valid = len([i for i in issues if i["severity"] == "error"]) == 0

        return {
            "is_valid": is_valid,
            "check_time": datetime.now().isoformat(),
            "today": today.isoformat(),
            "issues": issues,
            "summary": {
                "error_count": len([i for i in issues if i["severity"] == "error"]),
                "warning_count": len([i for i in issues if i["severity"] == "warning"]),
            }
        }

    except Exception as e:
        logger.exception("数据新鲜度验证失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-consistency")
async def validate_data_consistency(
    symbol_codes: Optional[str] = Query(None, description="逗号分隔的概念代码，默认检查热门概念"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    验证数据一致性

    规则：
    - 休市时间(15:30后~次日09:30前)且scheduler已更新：日线close == 30分钟close == 实时价格
    - 开市时间：验证K线时间戳是否正确
    """
    import httpx
    import re
    import json as json_lib
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    current_time = now.time()

    # 判断市场状态
    market_open = datetime.strptime("09:30", "%H:%M").time()
    market_close = datetime.strptime("15:00", "%H:%M").time()
    update_complete = datetime.strptime("15:30", "%H:%M").time()

    is_weekday = now.weekday() < 5
    is_market_hours = market_open <= current_time <= market_close and is_weekday
    is_after_update = current_time >= update_complete or current_time < market_open

    # 确定要检查的概念
    if symbol_codes:
        codes_to_check = [c.strip() for c in symbol_codes.split(",")]
    else:
        codes_to_check = ["886100", "885728", "886099", "885756", "886069"]

    results = []
    issues = []

    try:
        for code in codes_to_check:
            result = {"code": code, "checks": []}

            # 获取日线最新数据
            daily_data = db.execute(
                text("""
                    SELECT trade_time, close, symbol_name
                    FROM klines
                    WHERE symbol_type = 'CONCEPT' AND symbol_code = :code AND timeframe = 'DAY'
                    ORDER BY trade_time DESC LIMIT 1
                """),
                {"code": code}
            ).fetchone()

            # 获取30分钟最新数据
            mins30_data = db.execute(
                text("""
                    SELECT trade_time, close
                    FROM klines
                    WHERE symbol_type = 'CONCEPT' AND symbol_code = :code AND timeframe = 'MINS_30'
                    ORDER BY trade_time DESC LIMIT 1
                """),
                {"code": code}
            ).fetchone()

            if not daily_data or not mins30_data:
                result["error"] = "数据缺失"
                results.append(result)
                continue

            daily_time, daily_close, symbol_name = daily_data
            mins30_time, mins30_close = mins30_data
            result["name"] = symbol_name
            result["daily"] = {"time": daily_time, "close": float(daily_close)}
            result["mins30"] = {"time": mins30_time, "close": float(mins30_close)}

            # 获取实时价格
            realtime_price = None
            try:
                async with httpx.AsyncClient() as client:
                    url = f"http://d.10jqka.com.cn/v4/time/bk_{code}/last.js"
                    headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://q.10jqka.com.cn/"}
                    resp = await client.get(url, headers=headers, timeout=5.0)

                    match = re.search(r'\((\{.*\})\)', resp.text, re.DOTALL)
                    if match:
                        outer_data = json_lib.loads(match.group(1))
                        inner_key = f"bk_{code}"
                        if inner_key in outer_data:
                            data = outer_data[inner_key]
                            pre_close = float(data.get('pre', 0))
                            time_data = data.get('data', '')
                            if time_data:
                                items = [item for item in time_data.split(';') if item.strip()]
                                if items:
                                    last_item = items[-1].split(',')
                                    if len(last_item) >= 2 and last_item[1]:
                                        realtime_price = float(last_item[1])
                                    else:
                                        realtime_price = pre_close
                                else:
                                    realtime_price = pre_close
                            else:
                                realtime_price = pre_close
                            result["realtime"] = {"price": realtime_price, "pre_close": pre_close}
            except Exception as e:
                result["realtime"] = {"error": str(e)}

            # 执行验证
            if is_after_update and not is_market_hours:
                # 休市且更新完成：三价应该相等
                if realtime_price is not None:
                    daily_c = round(daily_close, 3)
                    mins30_c = round(mins30_close, 3)
                    realtime_c = round(realtime_price, 3)

                    # 检查是否相等
                    all_equal = (daily_c == mins30_c == realtime_c)

                    if not all_equal:
                        issue = {
                            "code": code,
                            "name": symbol_name,
                            "type": "price_mismatch",
                            "severity": "error",
                            "message": f"三价不一致: 日线={daily_c}, 30分钟={mins30_c}, 实时={realtime_c}",
                            "daily_close": daily_c,
                            "mins30_close": mins30_c,
                            "realtime_price": realtime_c,
                        }
                        issues.append(issue)
                        result["checks"].append({"name": "三价一致", "passed": False, "detail": issue["message"]})
                    else:
                        result["checks"].append({"name": "三价一致", "passed": True, "price": daily_c})
            else:
                # 开市时间：验证时间戳
                today_str = now.strftime("%Y-%m-%d")
                result["checks"].append({"name": "日线时间", "passed": True, "detail": f"最新: {daily_time}"})
                result["checks"].append({"name": "30分钟时间", "passed": True, "detail": f"最新: {mins30_time}"})

            results.append(result)

    except Exception as e:
        logger.exception("数据一致性验证失败")
        raise HTTPException(status_code=500, detail=str(e))

    is_valid = len([i for i in issues if i["severity"] == "error"]) == 0

    return {
        "is_valid": is_valid,
        "check_time": now.isoformat(),
        "market_status": {
            "is_market_hours": is_market_hours,
            "is_after_update": is_after_update,
            "current_time": current_time.strftime("%H:%M:%S"),
            "mode": "开市验证" if is_market_hours else ("休市验证(三价一致)" if is_after_update else "休市(更新中)")
        },
        "issues": issues,
        "details": results,
        "summary": {
            "checked": len(results),
            "passed": len([r for r in results if not r.get("error") and all(c.get("passed", True) for c in r.get("checks", []))]),
            "failed": len(issues),
        }
    }


@router.post("/validate-data-consistency")
async def validate_data_consistency() -> Dict[str, Any]:
    """
    手动触发数据一致性验证

    验证收盘后的数据一致性：
    - 日线收盘价
    - 30分钟收盘价
    - 实时价格（如果可用）

    返回验证结果，包括：
    - 总结信息（验证数量、不一致数量、一致性比率）
    - 指数验证详情
    - 概念验证详情
    - 不一致项目列表
    """
    from src.services.data_consistency_validator import DataConsistencyValidator

    try:
        validator = DataConsistencyValidator(tolerance=0.01)
        results = await validator.validate_all()
        return results
    except Exception as e:
        logger.exception("数据一致性验证失败")
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


@router.get("/watchlist-health")
async def watchlist_data_health(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    自选股数据健康检查

    检查348只自选股的数据完整性：
    - 日线K线是否更新到最新交易日
    - 30分钟K线是否更新到最新交易时段
    - 实时价格是否可获取
    - 三者收盘价是否一致（收盘后）
    """
    from datetime import datetime, time
    from zoneinfo import ZoneInfo
    from sqlalchemy import text

    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    today = now.strftime("%Y-%m-%d")
    is_after_close = now.time() >= time(15, 30)

    # Get latest trade date
    trade_date_row = db.execute(text(
        "SELECT MAX(date) FROM trade_calendar WHERE is_trading_day = 1 AND date <= :today"
    ), {"today": today}).fetchone()
    latest_trade_date = trade_date_row[0] if trade_date_row else today

    # Get all watchlist tickers with names from symbol_metadata
    watchlist_rows = db.execute(text(
        "SELECT w.ticker, COALESCE(m.name, w.ticker) as name "
        "FROM watchlist w LEFT JOIN symbol_metadata m ON w.ticker = m.ticker"
    )).fetchall()
    tickers = {r[0]: r[1] for r in watchlist_rows}

    # Check daily klines - latest date per stock
    daily_rows = db.execute(text("""
        SELECT symbol_code, MAX(trade_time) as latest
        FROM klines
        WHERE symbol_type = 'STOCK' AND timeframe = 'DAY'
          AND symbol_code IN (SELECT ticker FROM watchlist)
        GROUP BY symbol_code
    """)).fetchall()
    daily_map = {r[0]: r[1] for r in daily_rows}

    # Check 30m klines - latest time per stock
    m30_rows = db.execute(text("""
        SELECT symbol_code, MAX(trade_time) as latest
        FROM klines
        WHERE symbol_type = 'STOCK' AND timeframe = 'MINS_30'
          AND symbol_code IN (SELECT ticker FROM watchlist)
        GROUP BY symbol_code
    """)).fetchall()
    m30_map = {r[0]: r[1] for r in m30_rows}

    # Analyze
    missing_daily = []
    stale_daily = []
    missing_30m = []
    stale_30m = []
    price_mismatch = []

    for ticker in tickers:
        # Daily check
        if ticker not in daily_map:
            missing_daily.append(ticker)
        elif daily_map[ticker][:10] < latest_trade_date:
            stale_daily.append({"ticker": ticker, "latest": daily_map[ticker], "expected": latest_trade_date})

        # 30m check
        if ticker not in m30_map:
            missing_30m.append(ticker)
        elif is_after_close and m30_map[ticker][:10] < latest_trade_date:
            stale_30m.append({"ticker": ticker, "latest": m30_map[ticker], "expected": latest_trade_date})

    # Price consistency check (only after close, sample 10 stocks)
    if is_after_close and daily_map:
        import random
        sample_tickers = random.sample(list(set(daily_map.keys()) & set(m30_map.keys())), min(10, len(daily_map)))
        for ticker in sample_tickers:
            daily_close = db.execute(text("""
                SELECT close FROM klines
                WHERE symbol_type='STOCK' AND symbol_code=:t AND timeframe='DAY'
                ORDER BY trade_time DESC LIMIT 1
            """), {"t": ticker}).fetchone()
            m30_close = db.execute(text("""
                SELECT close FROM klines
                WHERE symbol_type='STOCK' AND symbol_code=:t AND timeframe='MINS_30'
                ORDER BY trade_time DESC LIMIT 1
            """), {"t": ticker}).fetchone()
            if daily_close and m30_close:
                diff = abs(daily_close[0] - m30_close[0]) / daily_close[0] * 100
                if diff > 0.5:  # >0.5% difference
                    price_mismatch.append({
                        "ticker": ticker,
                        "name": tickers.get(ticker, ""),
                        "daily_close": daily_close[0],
                        "m30_close": m30_close[0],
                        "diff_pct": round(diff, 2),
                    })

    total = len(tickers)
    has_daily = total - len(missing_daily)
    has_30m = total - len(missing_30m)
    is_healthy = len(missing_daily) == 0 and len(stale_daily) == 0 and len(price_mismatch) == 0

    return {
        "check_time": now.isoformat(),
        "latest_trade_date": latest_trade_date,
        "is_healthy": is_healthy,
        "summary": {
            "total": total,
            "daily_coverage": f"{has_daily}/{total}",
            "daily_stale": len(stale_daily),
            "m30_coverage": f"{has_30m}/{total}",
            "m30_stale": len(stale_30m),
            "price_mismatches": len(price_mismatch),
        },
        "issues": {
            "missing_daily": missing_daily[:20],
            "stale_daily": stale_daily[:20],
            "missing_30m": missing_30m[:20],
            "stale_30m": stale_30m[:20],
            "price_mismatch": price_mismatch,
        },
    }
