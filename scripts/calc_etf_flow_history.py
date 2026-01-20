#!/usr/bin/env python3
"""
计算 ETF 7日/30日累计资金流入数据

从 akshare 获取 ETF 历史资金流，计算累计流入并更新 etf_trend_summary.csv
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Optional, Dict

import pandas as pd
import akshare as ak

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 常量
DATA_DIR = project_root / "data"
ETF_CSV = DATA_DIR / "etf_daily_summary_filtered.csv"
TREND_CSV = DATA_DIR / "etf_trend_summary.csv"


def get_etf_fund_flow(ticker: str) -> Optional[Dict[str, float]]:
    """
    获取单个ETF的7日/30日累计资金流入

    Args:
        ticker: ETF代码，如 510300.SH

    Returns:
        dict with flow_7d, flow_30d (单位: 亿元)
    """
    try:
        # 解析股票代码和市场
        code = ticker.split('.')[0]
        market = 'sh' if ticker.endswith('.SH') else 'sz'

        time.sleep(0.5)  # 限流

        df = ak.stock_individual_fund_flow(stock=code, market=market)

        if df is None or len(df) < 7:
            logger.warning(f"未获取到 {ticker} 的资金流数据或数据不足")
            return None

        # 按日期降序（最新在前），取最近的数据
        df = df.sort_values('日期', ascending=False).reset_index(drop=True)

        # 主力净流入-净额 是以元为单位
        main_flow_col = '主力净流入-净额'

        if main_flow_col not in df.columns:
            logger.warning(f"{ticker} 缺少主力净流入列")
            return None

        result = {}

        # 7日累计（最近7条数据）
        if len(df) >= 7:
            flow_7d = df.head(7)[main_flow_col].sum()
            result['flow_7d'] = round(flow_7d / 1e8, 2)  # 转换为亿元
        else:
            result['flow_7d'] = None

        # 30日累计
        if len(df) >= 30:
            flow_30d = df.head(30)[main_flow_col].sum()
            result['flow_30d'] = round(flow_30d / 1e8, 2)  # 转换为亿元
        else:
            # 如果不足30天，用全部数据
            flow_30d = df[main_flow_col].sum()
            result['flow_30d'] = round(flow_30d / 1e8, 2)

        return result

    except Exception as e:
        logger.error(f"获取 {ticker} 资金流失败: {e}")
        return None


def main():
    """主函数"""
    # 读取ETF列表
    if not ETF_CSV.exists():
        logger.error(f"ETF列表文件不存在: {ETF_CSV}")
        sys.exit(1)

    df_etfs = pd.read_csv(ETF_CSV, encoding='utf-8-sig')
    logger.info(f"共 {len(df_etfs)} 个ETF需要获取资金流")

    # 读取现有趋势数据
    if TREND_CSV.exists():
        df_trend = pd.read_csv(TREND_CSV, encoding='utf-8-sig')
    else:
        logger.error(f"趋势汇总文件不存在: {TREND_CSV}")
        sys.exit(1)

    # 确保有 flow_7d 和 flow_30d 列
    if 'flow_7d' not in df_trend.columns:
        df_trend['flow_7d'] = None
    if 'flow_30d' not in df_trend.columns:
        df_trend['flow_30d'] = None

    # 获取每个ETF的资金流数据
    success_count = 0
    error_count = 0

    for idx, row in df_etfs.iterrows():
        ticker = row['Ticker']
        etf_name = row['ETF名称']

        logger.info(f"[{idx+1}/{len(df_etfs)}] 获取 {etf_name} ({ticker}) 资金流...")

        flow_data = get_etf_fund_flow(ticker)

        if flow_data:
            # 更新趋势数据
            mask = df_trend['ticker'] == ticker
            if mask.any():
                df_trend.loc[mask, 'flow_7d'] = flow_data.get('flow_7d')
                df_trend.loc[mask, 'flow_30d'] = flow_data.get('flow_30d')
                logger.info(f"  7日: {flow_data.get('flow_7d')}亿, 30日: {flow_data.get('flow_30d')}亿")
                success_count += 1
            else:
                logger.warning(f"  {ticker} 不在趋势数据中")
                error_count += 1
        else:
            error_count += 1

    # 保存更新后的趋势数据
    df_trend.to_csv(TREND_CSV, index=False, encoding='utf-8-sig')
    logger.info(f"保存更新后的趋势数据到: {TREND_CSV}")

    # 统计结果
    logger.info("=" * 50)
    logger.info(f"完成!")
    logger.info(f"成功: {success_count} 个ETF")
    logger.info(f"失败: {error_count} 个ETF")


if __name__ == "__main__":
    main()
