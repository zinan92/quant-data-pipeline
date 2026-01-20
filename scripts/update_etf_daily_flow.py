#!/usr/bin/env python3
"""
更新 ETF 每日资金流入流出数据

从 Tushare Pro 获取最新的 ETF 资金流数据，更新 etf_daily_summary_filtered.csv 中的:
- 资金流入流出(亿): 基于份额变化计算 (今日份额 - 昨日份额) * 收盘价
- 当日涨幅(%)
- 成交额(亿)
- 总市值(亿)
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

import pandas as pd
from dotenv import load_dotenv

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.tushare_client import TushareClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 常量
DATA_DIR = project_root / "data"
FILTERED_FILE = DATA_DIR / "etf_daily_summary_filtered.csv"
BACKUP_FILE = DATA_DIR / "etf_daily_summary_filtered.csv.bak"


class ETFDailyFlowUpdater:
    """ETF每日资金流更新器 - 使用Tushare Pro"""

    def __init__(self, client: TushareClient):
        self.client = client
        self.pro = client.pro

    def get_fund_share_data(self, ts_code: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """
        获取基金份额数据

        Returns:
            (最新份额, 前一日份额, 最新日期)
        """
        try:
            time.sleep(0.3)
            df = self.pro.fund_share(ts_code=ts_code)
            if df is None or len(df) < 1:
                return None, None, None

            df = df.sort_values('trade_date', ascending=False)
            latest_share = df.iloc[0]['fd_share'] if len(df) > 0 else None
            prev_share = df.iloc[1]['fd_share'] if len(df) > 1 else None
            latest_date = df.iloc[0]['trade_date'] if len(df) > 0 else None

            return latest_share, prev_share, latest_date
        except Exception as e:
            logger.warning(f"获取 {ts_code} 份额数据失败: {e}")
            return None, None, None

    def get_fund_daily(self, ts_code: str) -> Optional[Dict[str, Any]]:
        """获取基金最新日线数据"""
        try:
            time.sleep(0.3)
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
            df = self.pro.fund_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df is None or len(df) < 1:
                return None

            df = df.sort_values('trade_date', ascending=False)
            latest = df.iloc[0]

            return {
                'close': latest['close'],
                'pct_chg': latest.get('pct_chg', 0),
                'amount': latest.get('amount', 0) / 100000,  # 千元 -> 亿元
                'trade_date': latest['trade_date'],
            }
        except Exception as e:
            logger.warning(f"获取 {ts_code} 日线数据失败: {e}")
            return None

    def get_etf_daily_data(self, ts_code: str) -> Optional[Dict[str, Any]]:
        """
        获取单个ETF的最新数据

        Returns:
            dict with: flow_billion, change_pct, amount_billion, market_cap_billion, trade_date
        """
        # 获取份额数据
        curr_share, prev_share, share_date = self.get_fund_share_data(ts_code)

        # 获取日线数据
        daily_data = self.get_fund_daily(ts_code)

        if daily_data is None:
            return None

        result = {
            'close': daily_data['close'],
            'change_pct': daily_data['pct_chg'],
            'amount_billion': round(daily_data['amount'], 2),
            'trade_date': daily_data['trade_date'],
            'flow_billion': None,
            'market_cap_billion': None,
        }

        # 计算资金流入流出和总市值
        if curr_share and daily_data['close']:
            # 总市值 = 份额(万份) * 收盘价 / 10000 (亿元)
            result['market_cap_billion'] = round(curr_share * daily_data['close'] / 10000, 2)

            # 资金流 = (当前份额 - 前一日份额) * 收盘价 / 10000 (亿元)
            if prev_share:
                result['flow_billion'] = round((curr_share - prev_share) * daily_data['close'] / 10000, 2)

        return result


def main():
    """主函数"""
    # 加载环境变量
    env_path = project_root / ".env"
    load_dotenv(env_path)

    token = os.getenv('TUSHARE_TOKEN')
    if not token:
        logger.error("未找到 TUSHARE_TOKEN 环境变量")
        sys.exit(1)

    if not FILTERED_FILE.exists():
        logger.error(f"ETF filtered 文件不存在: {FILTERED_FILE}")
        sys.exit(1)

    # 读取现有数据
    logger.info(f"读取 {FILTERED_FILE}")
    df = pd.read_csv(FILTERED_FILE, encoding='utf-8-sig')
    logger.info(f"共 {len(df)} 个ETF")

    # 备份原文件
    logger.info(f"备份到 {BACKUP_FILE}")
    df.to_csv(BACKUP_FILE, index=False, encoding='utf-8-sig')

    # 初始化客户端
    points = int(os.getenv('TUSHARE_POINTS', 15000))
    client = TushareClient(token=token, points=points)
    updater = ETFDailyFlowUpdater(client)

    # 更新每个ETF的数据
    success_count = 0
    error_count = 0
    latest_date = None

    for idx, row in df.iterrows():
        ticker = row['Ticker']
        etf_name = row['ETF名称']

        logger.info(f"[{idx+1}/{len(df)}] 获取 {etf_name} ({ticker}) 最新数据...")

        data = updater.get_etf_daily_data(ticker)

        if data:
            # 更新涨跌幅
            if data['change_pct'] is not None:
                df.at[idx, '当日涨幅(%)'] = data['change_pct']

            # 更新最新价格
            if data['close'] is not None:
                df.at[idx, '最新价格'] = data['close']

            # 更新成交额
            if data['amount_billion'] is not None:
                df.at[idx, '成交额(亿)'] = data['amount_billion']

            # 更新总市值
            if data['market_cap_billion'] is not None:
                df.at[idx, '总市值(亿)'] = data['market_cap_billion']

            # 更新资金流入流出
            if data['flow_billion'] is not None:
                df.at[idx, '资金流入流出(亿)'] = data['flow_billion']

                # 重新计算流入占总值比
                market_cap = data['market_cap_billion']
                if market_cap and market_cap > 0:
                    flow_ratio = round(data['flow_billion'] / market_cap * 100, 2)
                    df.at[idx, '流入占总值比(%)'] = flow_ratio

            # 记录最新交易日期
            if data['trade_date']:
                latest_date = data['trade_date']

            flow_str = f"{data['flow_billion']}亿" if data['flow_billion'] is not None else "N/A"
            logger.info(f"  资金流: {flow_str}, 涨跌: {data['change_pct']}%")
            success_count += 1
        else:
            error_count += 1

    # 保存更新后的数据
    df.to_csv(FILTERED_FILE, index=False, encoding='utf-8-sig')
    logger.info(f"保存到 {FILTERED_FILE}")

    # 统计结果
    logger.info("=" * 50)
    logger.info(f"更新完成!")
    logger.info(f"成功: {success_count} 个ETF")
    logger.info(f"失败: {error_count} 个ETF")
    if latest_date:
        logger.info(f"最新交易日: {latest_date}")

    # 计算汇总
    flows = pd.to_numeric(df['资金流入流出(亿)'], errors='coerce').fillna(0)
    inflow = flows[flows > 0].sum()
    outflow = flows[flows < 0].sum()
    net_flow = flows.sum()
    logger.info(f"净流入: {round(net_flow, 2)}亿 (流入: {round(inflow, 2)}亿, 流出: {round(outflow, 2)}亿)")


if __name__ == "__main__":
    main()
