"""
业绩预告和业绩快报API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import tushare as ts
import os
from datetime import datetime
from dotenv import load_dotenv

router = APIRouter()

# 延迟初始化Tushare
_pro = None

def get_pro():
    global _pro
    if _pro is None:
        load_dotenv()
        token = os.getenv("TUSHARE_TOKEN", "")
        ts.set_token(token)
        _pro = ts.pro_api()
    return _pro


class ForecastItem(BaseModel):
    """业绩预告"""
    ann_date: str  # 公告日期
    end_date: str  # 报告期
    type: Optional[str] = None  # 预告类型（预增/预减/扭亏等）
    p_change_min: Optional[float] = None  # 预计净利润变动幅度下限(%)
    p_change_max: Optional[float] = None  # 预计净利润变动幅度上限(%)
    net_profit_min: Optional[float] = None  # 预计净利润下限（万元）
    net_profit_max: Optional[float] = None  # 预计净利润上限（万元）
    last_parent_net: Optional[float] = None  # 上年同期净利润（万元）
    summary: Optional[str] = None  # 业绩变动原因
    change_reason: Optional[str] = None  # 变动原因


class ExpressItem(BaseModel):
    """业绩快报"""
    ann_date: str  # 公告日期
    end_date: str  # 报告期
    revenue: Optional[float] = None  # 营业收入（元）
    operate_profit: Optional[float] = None  # 营业利润（元）
    total_profit: Optional[float] = None  # 利润总额（元）
    n_income: Optional[float] = None  # 净利润（元）
    total_assets: Optional[float] = None  # 总资产（元）
    total_hldr_eqy_exc_min_int: Optional[float] = None  # 股东权益（元）
    diluted_eps: Optional[float] = None  # 每股收益（摊薄）
    diluted_roe: Optional[float] = None  # 净资产收益率（摊薄）
    yoy_net_profit: Optional[float] = None  # 净利润同比增长(%)
    yoy_sales: Optional[float] = None  # 营业收入同比增长(%)


class EarningsResponse(BaseModel):
    ticker: str
    forecasts: list[ForecastItem]
    expresses: list[ExpressItem]


@router.get("/{ticker}", response_model=EarningsResponse)
async def get_earnings(ticker: str):
    """
    获取股票的业绩预告和业绩快报数据
    只返回2025年及以后的数据
    """
    # 转换为tushare格式的代码
    ts_code = f"{ticker}.SZ" if ticker.startswith(("0", "3")) else f"{ticker}.SH"

    forecasts = []
    expresses = []

    try:
        # 获取业绩预告 - 只获取2025年以后的数据
        # end_date格式: 20250331, 20250630, 20250930, 20251231
        df_forecast = get_pro().forecast(
            ts_code=ts_code,
            fields='ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,last_parent_net,summary,change_reason'
        )

        if df_forecast is not None and len(df_forecast) > 0:
            for _, row in df_forecast.iterrows():
                end_date = str(row.get('end_date', ''))
                # 只保留2025年及以后的数据
                if end_date and end_date >= '20250101':
                    forecasts.append(ForecastItem(
                        ann_date=str(row.get('ann_date', '')),
                        end_date=end_date,
                        type=row.get('type'),
                        p_change_min=row.get('p_change_min') if row.get('p_change_min') is not None and str(row.get('p_change_min')) != 'nan' else None,
                        p_change_max=row.get('p_change_max') if row.get('p_change_max') is not None and str(row.get('p_change_max')) != 'nan' else None,
                        net_profit_min=row.get('net_profit_min') if row.get('net_profit_min') is not None and str(row.get('net_profit_min')) != 'nan' else None,
                        net_profit_max=row.get('net_profit_max') if row.get('net_profit_max') is not None and str(row.get('net_profit_max')) != 'nan' else None,
                        last_parent_net=row.get('last_parent_net') if row.get('last_parent_net') is not None and str(row.get('last_parent_net')) != 'nan' else None,
                        summary=row.get('summary') if row.get('summary') and str(row.get('summary')) != 'nan' else None,
                        change_reason=row.get('change_reason') if row.get('change_reason') and str(row.get('change_reason')) != 'nan' else None,
                    ))
    except Exception as e:
        print(f"获取业绩预告失败: {e}")

    try:
        # 获取业绩快报
        df_express = get_pro().express(
            ts_code=ts_code,
            fields='ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets,total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe,yoy_net_profit,yoy_sales'
        )

        if df_express is not None and len(df_express) > 0:
            for _, row in df_express.iterrows():
                end_date = str(row.get('end_date', ''))
                # 只保留2025年及以后的数据
                if end_date and end_date >= '20250101':
                    expresses.append(ExpressItem(
                        ann_date=str(row.get('ann_date', '')),
                        end_date=end_date,
                        revenue=row.get('revenue') if row.get('revenue') is not None and str(row.get('revenue')) != 'nan' else None,
                        operate_profit=row.get('operate_profit') if row.get('operate_profit') is not None and str(row.get('operate_profit')) != 'nan' else None,
                        total_profit=row.get('total_profit') if row.get('total_profit') is not None and str(row.get('total_profit')) != 'nan' else None,
                        n_income=row.get('n_income') if row.get('n_income') is not None and str(row.get('n_income')) != 'nan' else None,
                        total_assets=row.get('total_assets') if row.get('total_assets') is not None and str(row.get('total_assets')) != 'nan' else None,
                        total_hldr_eqy_exc_min_int=row.get('total_hldr_eqy_exc_min_int') if row.get('total_hldr_eqy_exc_min_int') is not None and str(row.get('total_hldr_eqy_exc_min_int')) != 'nan' else None,
                        diluted_eps=row.get('diluted_eps') if row.get('diluted_eps') is not None and str(row.get('diluted_eps')) != 'nan' else None,
                        diluted_roe=row.get('diluted_roe') if row.get('diluted_roe') is not None and str(row.get('diluted_roe')) != 'nan' else None,
                        yoy_net_profit=row.get('yoy_net_profit') if row.get('yoy_net_profit') is not None and str(row.get('yoy_net_profit')) != 'nan' else None,
                        yoy_sales=row.get('yoy_sales') if row.get('yoy_sales') is not None and str(row.get('yoy_sales')) != 'nan' else None,
                    ))
    except Exception as e:
        print(f"获取业绩快报失败: {e}")

    # 按公告日期排序（最新的在前）
    forecasts.sort(key=lambda x: x.ann_date, reverse=True)
    expresses.sort(key=lambda x: x.ann_date, reverse=True)

    return EarningsResponse(
        ticker=ticker,
        forecasts=forecasts,
        expresses=expresses
    )
