"""
异动实时监控 API
"""
from fastapi import APIRouter, Query
from typing import Dict, List, Optional
from pydantic import BaseModel

from src.config import get_settings
from src.exceptions import DatabaseError
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/anomaly", tags=["anomaly"])


class AnomalyItem(BaseModel):
    ticker: str
    type: str
    type_name: str
    price: Optional[float]
    pct_change: Optional[float]
    volume: Optional[float]
    details: dict
    time: str


class ScanSummary(BaseModel):
    limit_up: int
    limit_down: int
    near_limit_up: int
    near_limit_down: int
    volume_spike: int


class ScanResult(BaseModel):
    scanned_at: str
    summary: ScanSummary


@router.get("/scan")
async def scan_anomalies():
    """
    扫描自选股异动
    
    检测:
    - 涨停/跌停
    - 触及涨停/跌停 (7%+)
    - 放量异动 (3倍以上)
    """
    try:
        from src.services.anomaly_monitor import scan_anomalies
        return scan_anomalies()
    except Exception as e:
        logger.exception("扫描自选股异动失败")
        raise DatabaseError(operation="scan_anomalies", reason=str(e) if get_settings().debug else "Internal server error")


@router.get("/today", response_model=List[AnomalyItem])
async def get_today_anomalies():
    """
    获取今日所有异动记录
    """
    try:
        from src.services.anomaly_monitor import get_today_anomalies
        return get_today_anomalies()
    except Exception as e:
        logger.exception("获取今日异动记录失败")
        raise DatabaseError(operation="get_today_anomalies", reason=str(e) if get_settings().debug else "Internal server error")


@router.get("/alerts")
async def get_alert_summary():
    """
    获取异动预警摘要 (用于推送)
    """
    try:
        from src.services.anomaly_monitor import scan_anomalies
        result = scan_anomalies()
        
        alerts = []
        
        # 涨停
        for a in result['results'].get('limit_up', []):
            alerts.append({
                'level': 'high',
                'emoji': '🔴',
                'message': f"{a['ticker']} 涨停 +{a['pct_change']:.1f}%"
            })
        
        # 跌停
        for a in result['results'].get('limit_down', []):
            alerts.append({
                'level': 'high',
                'emoji': '🟢',
                'message': f"{a['ticker']} 跌停 {a['pct_change']:.1f}%"
            })
        
        # 触及涨停
        for a in result['results'].get('near_limit_up', []):
            alerts.append({
                'level': 'medium',
                'emoji': '📈',
                'message': f"{a['ticker']} 触及涨停 +{a['pct_change']:.1f}%"
            })
        
        # 放量
        for a in result['results'].get('volume_spike', []):
            alerts.append({
                'level': 'low',
                'emoji': '📊',
                'message': f"{a['ticker']} 放量 {a['ratio']:.1f}倍"
            })
        
        return {
            'alert_count': len(alerts),
            'alerts': alerts,
            'scanned_at': result['scanned_at']
        }
        
    except Exception as e:
        logger.exception("获取异动预警摘要失败")
        raise DatabaseError(operation="get_alert_summary", reason=str(e) if get_settings().debug else "Internal server error")
