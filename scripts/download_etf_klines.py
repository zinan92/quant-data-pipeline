#!/usr/bin/env python3
"""
下载 ETF K线数据

从 tushare 获取 ETF 的日线数据并保存到 data/etf_klines/ 目录
同时计算 7日/30日 成交量均值、涨跌幅等趋势指标
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List

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
KLINE_DIR = DATA_DIR / "etf_klines"
ETF_CSV = DATA_DIR / "etf_daily_summary_filtered.csv"
SUMMARY_OUTPUT = DATA_DIR / "etf_trend_summary.csv"


class ETFKlineDownloader:
    """ETF K线数据下载器"""

    def __init__(self, client: TushareClient):
        self.client = client
        self.pro = client.pro

    def download_etf_kline(self, ts_code: str, days: int = 200) -> Optional[pd.DataFrame]:
        """
        下载单个ETF的K线数据

        Args:
            ts_code: ETF代码，如 510300.SH
            days: 下载天数

        Returns:
            DataFrame with columns: date, open, high, low, close, volume, amount
        """
        try:
            time.sleep(0.3)  # 限流

            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days + 30)).strftime('%Y%m%d')

            df = self.pro.fund_daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df is None or len(df) < 1:
                logger.warning(f"未获取到 {ts_code} 的K线数据")
                return None

            # 重命名列并排序
            df = df.rename(columns={
                'trade_date': 'date',
                'vol': 'volume',
            })

            # 按日期升序排列
            df = df.sort_values('date', ascending=True).reset_index(drop=True)

            # 选择需要的列
            columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount',
                       'pre_close', 'change', 'pct_chg']
            df = df[[c for c in columns if c in df.columns]]

            # 将 amount 转换为亿元
            if 'amount' in df.columns:
                df['amount_billion'] = df['amount'] / 100000  # 千元 -> 亿元

            return df

        except Exception as e:
            logger.error(f"下载 {ts_code} K线失败: {e}")
            return None

    def calculate_trend_indicators(self, df: pd.DataFrame) -> Dict:
        """
        计算趋势指标

        Returns:
            dict with: change_7d, change_30d, avg_vol_7d, avg_vol_30d, vol_ratio_7d, vol_ratio_30d
        """
        if df is None or len(df) < 7:
            return {}

        result = {}

        # 当前值 (最新一行)
        current = df.iloc[-1]
        current_close = current['close']
        current_amount = current.get('amount_billion', 0)
        current_change = current.get('pct_chg', 0)

        result['current_close'] = current_close
        result['current_change'] = current_change
        result['current_amount'] = round(current_amount, 2)

        # 7日数据
        if len(df) >= 7:
            df_7d = df.iloc[-7:]
            close_7d_ago = df.iloc[-7]['close']

            # 7日涨跌幅
            result['change_7d'] = round((current_close / close_7d_ago - 1) * 100, 2)

            # 7日平均成交额
            avg_amount_7d = df_7d['amount_billion'].mean() if 'amount_billion' in df_7d.columns else 0
            result['avg_amount_7d'] = round(avg_amount_7d, 2)

            # 7日量比
            if avg_amount_7d > 0:
                result['vol_ratio_7d'] = round(current_amount / avg_amount_7d, 2)
            else:
                result['vol_ratio_7d'] = None

        # 30日数据
        if len(df) >= 30:
            df_30d = df.iloc[-30:]
            close_30d_ago = df.iloc[-30]['close']

            # 30日涨跌幅
            result['change_30d'] = round((current_close / close_30d_ago - 1) * 100, 2)

            # 30日平均成交额
            avg_amount_30d = df_30d['amount_billion'].mean() if 'amount_billion' in df_30d.columns else 0
            result['avg_amount_30d'] = round(avg_amount_30d, 2)

            # 30日量比
            if avg_amount_30d > 0:
                result['vol_ratio_30d'] = round(current_amount / avg_amount_30d, 2)
            else:
                result['vol_ratio_30d'] = None

        # MA均线
        if len(df) >= 5:
            result['ma5'] = round(df.iloc[-5:]['close'].mean(), 4)
        if len(df) >= 10:
            result['ma10'] = round(df.iloc[-10:]['close'].mean(), 4)
        if len(df) >= 20:
            result['ma20'] = round(df.iloc[-20:]['close'].mean(), 4)

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

    # 创建K线目录
    KLINE_DIR.mkdir(parents=True, exist_ok=True)

    # 读取ETF列表
    if not ETF_CSV.exists():
        logger.error(f"ETF列表文件不存在: {ETF_CSV}")
        sys.exit(1)

    df_etfs = pd.read_csv(ETF_CSV, encoding='utf-8-sig')
    logger.info(f"共 {len(df_etfs)} 个ETF需要下载")

    # 初始化客户端
    points = int(os.getenv('TUSHARE_POINTS', 15000))
    client = TushareClient(token=token, points=points)
    downloader = ETFKlineDownloader(client)

    # 下载所有ETF K线并计算指标
    trend_data = []
    success_count = 0
    error_count = 0

    for idx, row in df_etfs.iterrows():
        ts_code = row['Ticker']
        etf_name = row['ETF名称']

        logger.info(f"[{idx+1}/{len(df_etfs)}] 下载 {etf_name} ({ts_code})...")

        try:
            # 下载K线
            df_kline = downloader.download_etf_kline(ts_code, days=200)

            if df_kline is not None and len(df_kline) > 0:
                # 保存K线数据
                kline_file = KLINE_DIR / f"{ts_code.replace('.', '_')}.csv"
                df_kline.to_csv(kline_file, index=False)
                logger.info(f"  保存 {len(df_kline)} 条K线到 {kline_file.name}")

                # 计算趋势指标
                indicators = downloader.calculate_trend_indicators(df_kline)
                indicators['ticker'] = ts_code
                indicators['name'] = etf_name
                indicators['super_category'] = row.get('超级行业组', '')
                trend_data.append(indicators)

                success_count += 1
            else:
                error_count += 1

        except Exception as e:
            logger.error(f"处理 {ts_code} 失败: {e}")
            error_count += 1

            # 限流处理
            if 'limit' in str(e).lower() or '限' in str(e):
                logger.warning("遇到限流，等待60秒...")
                time.sleep(60)

    # 保存趋势汇总数据
    if trend_data:
        df_trend = pd.DataFrame(trend_data)

        # 重排列顺序
        cols_order = ['ticker', 'name', 'super_category', 'current_close', 'current_change',
                      'current_amount', 'change_7d', 'change_30d',
                      'avg_amount_7d', 'avg_amount_30d', 'vol_ratio_7d', 'vol_ratio_30d',
                      'ma5', 'ma10', 'ma20']
        df_trend = df_trend[[c for c in cols_order if c in df_trend.columns]]

        df_trend.to_csv(SUMMARY_OUTPUT, index=False, encoding='utf-8-sig')
        logger.info(f"保存趋势汇总到: {SUMMARY_OUTPUT}")

    # 统计结果
    logger.info("=" * 50)
    logger.info(f"下载完成!")
    logger.info(f"成功: {success_count} 个ETF")
    logger.info(f"失败: {error_count} 个ETF")
    logger.info(f"K线数据目录: {KLINE_DIR}")
    logger.info(f"趋势汇总文件: {SUMMARY_OUTPUT}")


if __name__ == "__main__":
    main()
