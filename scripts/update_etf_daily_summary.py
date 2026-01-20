#!/usr/bin/env python3
"""
补全 ETF Daily Summary 数据

从 tushare 获取以下缺失数据:
- 总市值(亿): fund_share * close / 10000
- 资金流入流出(亿): (今日份额 - 昨日份额) * close / 10000
- 流入占总值比(%): 资金流入流出 / 总市值 * 100
- TOP3持仓: fund_portfolio 前3大持仓股票名称
- TOP3占比(%): 前3大持仓占比之和
- 持仓数量: fund_portfolio 持仓数量 (取10的整数)
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, List

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
CSV_FILE = DATA_DIR / "etf_daily_summary.csv"
BACKUP_FILE = DATA_DIR / "etf_daily_summary.csv.bak"


class ETFDataUpdater:
    """ETF数据补全器"""

    def __init__(self, client: TushareClient):
        self.client = client
        self.pro = client.pro
        self._stock_name_cache: Dict[str, str] = {}
        self._load_stock_names()

    def _load_stock_names(self):
        """加载股票名称映射表"""
        logger.info("加载股票名称映射表...")
        try:
            df = self.pro.stock_basic(fields='ts_code,name')
            self._stock_name_cache = dict(zip(df['ts_code'], df['name']))
            logger.info(f"加载了 {len(self._stock_name_cache)} 个股票名称")
        except Exception as e:
            logger.error(f"加载股票名称失败: {e}")

    def get_stock_name(self, ts_code: str) -> str:
        """获取股票名称"""
        return self._stock_name_cache.get(ts_code, ts_code.split('.')[0])

    def get_fund_share_data(self, ts_code: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """
        获取基金份额数据

        Returns:
            (最新份额, 前一日份额, 最新日期)
        """
        try:
            time.sleep(0.3)  # 限流
            df = self.pro.fund_share(ts_code=ts_code)
            if df is None or len(df) < 1:
                return None, None, None

            # 按日期排序
            df = df.sort_values('trade_date', ascending=False)
            latest_share = df.iloc[0]['fd_share'] if len(df) > 0 else None
            prev_share = df.iloc[1]['fd_share'] if len(df) > 1 else None
            latest_date = df.iloc[0]['trade_date'] if len(df) > 0 else None

            return latest_share, prev_share, latest_date
        except Exception as e:
            logger.warning(f"获取 {ts_code} 份额数据失败: {e}")
            return None, None, None

    def get_fund_daily_close(self, ts_code: str, trade_date: str = None) -> Optional[float]:
        """获取基金收盘价"""
        try:
            time.sleep(0.3)
            if trade_date:
                df = self.pro.fund_daily(ts_code=ts_code, trade_date=trade_date)
            else:
                # 获取最近的交易日数据
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
                df = self.pro.fund_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df is None or len(df) < 1:
                return None

            # 取最新的收盘价
            df = df.sort_values('trade_date', ascending=False)
            return df.iloc[0]['close']
        except Exception as e:
            logger.warning(f"获取 {ts_code} 收盘价失败: {e}")
            return None

    def get_fund_portfolio(self, ts_code: str) -> Tuple[Optional[str], Optional[float], Optional[int]]:
        """
        获取基金持仓数据

        Returns:
            (TOP3持仓名称, TOP3占比, 持仓数量)
        """
        try:
            time.sleep(0.3)
            df = self.pro.fund_portfolio(ts_code=ts_code)
            if df is None or len(df) < 1:
                return None, None, None

            # 获取最新一期持仓
            latest_date = df['end_date'].max()
            latest_holdings = df[df['end_date'] == latest_date]

            # 过滤有效持仓 (占比 > 0.01%)
            valid_holdings = latest_holdings[latest_holdings['stk_mkv_ratio'] > 0.01]

            if len(valid_holdings) < 1:
                return None, None, None

            # 按持仓占比排序取TOP3
            top3 = valid_holdings.nlargest(3, 'stk_mkv_ratio')

            # 获取股票名称
            top3_names = []
            for _, row in top3.iterrows():
                name = self.get_stock_name(row['symbol'])
                top3_names.append(name)

            top3_str = ", ".join(top3_names)
            top3_ratio = top3['stk_mkv_ratio'].sum()

            # 持仓数量取整到10
            holding_count = len(valid_holdings)
            holding_count_rounded = round(holding_count / 10) * 10 if holding_count >= 5 else holding_count

            return top3_str, round(top3_ratio, 2), holding_count_rounded
        except Exception as e:
            logger.warning(f"获取 {ts_code} 持仓数据失败: {e}")
            return None, None, None

    def calculate_market_value(self, share: float, close: float) -> float:
        """计算总市值 (亿元)"""
        # share 单位是万份，close 是元
        # 总市值 = share * close / 10000 (亿元)
        return round(share * close / 10000, 2)

    def calculate_fund_flow(self, curr_share: float, prev_share: float, close: float) -> float:
        """计算资金流入流出 (亿元)"""
        # 资金流 = (当前份额 - 前一日份额) * 收盘价 / 10000
        return round((curr_share - prev_share) * close / 10000, 2)

    def update_etf_record(self, row: pd.Series) -> Dict:
        """更新单条ETF记录"""
        ts_code = row['Ticker']
        result = {
            '总市值(亿)': row.get('总市值(亿)', ''),
            '资金流入流出(亿)': row.get('资金流入流出(亿)', ''),
            '流入占总值比(%)': row.get('流入占总值比(%)', ''),
            'TOP3持仓': row.get('TOP3持仓', ''),
            'TOP3占比(%)': row.get('TOP3占比(%)', ''),
            '持仓数量': row.get('持仓数量', '')
        }

        # 检查是否需要更新总市值相关数据
        needs_mv_update = pd.isna(row.get('总市值(亿)')) or row.get('总市值(亿)') == ''
        needs_holding_update = pd.isna(row.get('TOP3持仓')) or row.get('TOP3持仓') == ''

        if not needs_mv_update and not needs_holding_update:
            return result  # 数据完整，无需更新

        logger.info(f"更新 {ts_code} ({row['ETF名称']})...")

        # 更新总市值和资金流向
        if needs_mv_update:
            curr_share, prev_share, share_date = self.get_fund_share_data(ts_code)
            close = self.get_fund_daily_close(ts_code)

            if curr_share and close:
                total_mv = self.calculate_market_value(curr_share, close)
                result['总市值(亿)'] = total_mv

                if prev_share:
                    fund_flow = self.calculate_fund_flow(curr_share, prev_share, close)
                    result['资金流入流出(亿)'] = fund_flow

                    if total_mv > 0:
                        flow_ratio = round(fund_flow / total_mv * 100, 2)
                        result['流入占总值比(%)'] = flow_ratio

        # 更新持仓信息
        if needs_holding_update:
            top3_str, top3_ratio, holding_count = self.get_fund_portfolio(ts_code)

            if top3_str:
                result['TOP3持仓'] = top3_str
                result['TOP3占比(%)'] = top3_ratio
                result['持仓数量'] = holding_count

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

    # 读取现有CSV
    if not CSV_FILE.exists():
        logger.error(f"CSV文件不存在: {CSV_FILE}")
        sys.exit(1)

    logger.info(f"读取CSV文件: {CSV_FILE}")
    df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
    logger.info(f"共 {len(df)} 条ETF记录")

    # 统计缺失数据
    missing_mv = df['总市值(亿)'].isna().sum() + (df['总市值(亿)'] == '').sum()
    missing_holding = df['TOP3持仓'].isna().sum() + (df['TOP3持仓'] == '').sum()
    logger.info(f"缺失总市值: {missing_mv} 条")
    logger.info(f"缺失持仓信息: {missing_holding} 条")

    if missing_mv == 0 and missing_holding == 0:
        logger.info("所有数据已完整，无需更新")
        return

    # 备份原文件
    logger.info(f"备份原文件到: {BACKUP_FILE}")
    df.to_csv(BACKUP_FILE, index=False, encoding='utf-8-sig')

    # 初始化客户端
    points = int(os.getenv('TUSHARE_POINTS', 15000))
    client = TushareClient(token=token, points=points)
    updater = ETFDataUpdater(client)

    # 更新数据
    updated_count = 0
    error_count = 0

    for idx, row in df.iterrows():
        try:
            # 检查是否需要更新
            needs_update = (
                pd.isna(row.get('总市值(亿)')) or row.get('总市值(亿)') == '' or
                pd.isna(row.get('TOP3持仓')) or row.get('TOP3持仓') == ''
            )

            if not needs_update:
                continue

            result = updater.update_etf_record(row)

            # 更新DataFrame
            for col, val in result.items():
                if val != '' and not pd.isna(val):
                    df.at[idx, col] = val

            updated_count += 1

            # 每50条保存一次
            if updated_count % 50 == 0:
                logger.info(f"已更新 {updated_count} 条，保存中间结果...")
                df.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')

            # 每100条打印进度
            if updated_count % 100 == 0:
                logger.info(f"进度: {updated_count}/{missing_mv + missing_holding}")

        except Exception as e:
            logger.error(f"更新 {row['Ticker']} 失败: {e}")
            error_count += 1

            # 遇到限流错误，等待更长时间
            if 'limit' in str(e).lower() or '限' in str(e):
                logger.warning("遇到限流，等待60秒...")
                time.sleep(60)

    # 保存最终结果
    logger.info(f"保存最终结果到: {CSV_FILE}")
    df.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')

    # 统计结果
    logger.info("=" * 50)
    logger.info(f"更新完成!")
    logger.info(f"成功更新: {updated_count} 条")
    logger.info(f"失败: {error_count} 条")

    # 检查剩余缺失
    final_missing_mv = df['总市值(亿)'].isna().sum() + (df['总市值(亿)'] == '').sum()
    final_missing_holding = df['TOP3持仓'].isna().sum() + (df['TOP3持仓'] == '').sum()
    logger.info(f"剩余缺失总市值: {final_missing_mv} 条")
    logger.info(f"剩余缺失持仓: {final_missing_holding} 条")


if __name__ == "__main__":
    main()
