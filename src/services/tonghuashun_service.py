"""
Tonghuashun board data service using AKShare
"""
import akshare as ak
import pandas as pd
from typing import Dict, List, Optional
import time
from datetime import datetime


class TonghuashunService:
    """Service for fetching Tonghuashun concept and industry board data via AKShare"""

    def __init__(self, rate_limit_delay: float = 0.5):
        """
        Initialize the service

        Args:
            rate_limit_delay: Delay in seconds between API calls to avoid rate limiting
        """
        self.rate_limit_delay = rate_limit_delay

    def get_all_concept_boards(self) -> pd.DataFrame:
        """
        Get list of all concept boards

        Returns:
            DataFrame with columns: name, code
        """
        try:
            df = ak.stock_board_concept_name_ths()
            return df
        except Exception as e:
            print(f"Error fetching concept board list: {e}")
            return pd.DataFrame(columns=['name', 'code'])

    def get_all_industry_boards(self) -> pd.DataFrame:
        """
        Get list of all industry boards

        Returns:
            DataFrame with columns: name, code
        """
        try:
            df = ak.stock_board_industry_name_ths()
            return df
        except Exception as e:
            print(f"Error fetching industry board list: {e}")
            return pd.DataFrame(columns=['name', 'code'])

    def get_concept_board_info(self, symbol: str) -> Optional[Dict]:
        """
        Get detailed real-time data for a single concept board

        Args:
            symbol: Board name (e.g., "先进封装")

        Returns:
            Dictionary with board data or None if error
        """
        try:
            df = ak.stock_board_concept_info_ths(symbol=symbol)

            # Convert DataFrame to dict for easier access
            data = {}
            for _, row in df.iterrows():
                data[row['项目']] = row['值']

            return data
        except Exception as e:
            print(f"Error fetching concept board info for {symbol}: {e}")
            return None

    def get_industry_board_info(self, symbol: str) -> Optional[Dict]:
        """
        Get detailed real-time data for a single industry board

        Args:
            symbol: Board name (e.g., "半导体")

        Returns:
            Dictionary with board data or None if error
        """
        try:
            df = ak.stock_board_industry_info_ths(symbol=symbol)

            # Convert DataFrame to dict for easier access
            data = {}
            for _, row in df.iterrows():
                data[row['项目']] = row['值']

            return data
        except Exception as e:
            print(f"Error fetching industry board info for {symbol}: {e}")
            return None

    def parse_board_data(self, code: str, name: str, raw_data: Dict) -> Dict:
        """
        Parse raw board data into standardized format

        Args:
            code: Board code
            name: Board name
            raw_data: Raw data from AKShare

        Returns:
            Standardized board data dictionary
        """
        # Parse 涨跌家数 (format: "120/22")
        up_down = raw_data.get('涨跌家数', '0/0')
        try:
            up_count, down_count = up_down.split('/')
            up_count = int(up_count.strip())
            down_count = int(down_count.strip())
        except:
            up_count = 0
            down_count = 0

        # Parse percentage values
        change_pct_str = raw_data.get('板块涨幅', '0%')
        try:
            change_pct = float(change_pct_str.replace('%', '').strip())
        except:
            change_pct = 0.0

        # Parse money inflow (亿元)
        money_inflow_str = raw_data.get('资金净流入(亿)', '0')
        try:
            money_inflow = float(money_inflow_str)
        except:
            money_inflow = 0.0

        # Parse turnover (亿元)
        turnover_str = raw_data.get('成交额(亿)', '0')
        try:
            turnover = float(turnover_str)
        except:
            turnover = 0.0

        # Parse OHLC data
        try:
            open_price = float(raw_data.get('今开', 0))
            high_price = float(raw_data.get('最高', 0))
            low_price = float(raw_data.get('最低', 0))
            prev_close = float(raw_data.get('昨收', 0))
        except:
            open_price = high_price = low_price = prev_close = 0.0

        # Parse volume (万手)
        volume_str = raw_data.get('成交量(万手)', '0')
        try:
            volume = float(volume_str)
        except:
            volume = 0.0

        # Parse ranking (format: "3/390")
        rank_str = raw_data.get('涨幅排名', '0/0')
        try:
            rank, total = rank_str.split('/')
            rank = int(rank.strip())
            total = int(total.strip())
        except:
            rank = 0
            total = 0

        return {
            'code': code,
            'name': name,
            'change_pct': change_pct,  # 涨幅
            'money_inflow': money_inflow,  # 主力金额 (亿元)
            'up_count': up_count,  # 涨家数
            'down_count': down_count,  # 跌家数
            'turnover': turnover,  # 成交额 (亿元)
            'volume': volume,  # 成交量 (万手)
            'open': open_price,  # 今开
            'high': high_price,  # 最高
            'low': low_price,  # 最低
            'prev_close': prev_close,  # 昨收
            'rank': rank,  # 涨幅排名
            'total_boards': total,  # 板块总数
            'update_time': datetime.now().isoformat(),
        }

    def get_all_concept_realtime_data(self) -> List[Dict]:
        """
        Get real-time data for all concept boards

        Returns:
            List of board data dictionaries

        Note:
            This operation is slow (~5-10 minutes for 372 boards)
            Consider caching the results
        """
        # Get all concept boards
        df_names = self.get_all_concept_boards()

        results = []
        total = len(df_names)

        for idx, row in df_names.iterrows():
            concept_name = row['name']
            concept_code = row['code']

            print(f"Fetching concept board {idx + 1}/{total}: {concept_name}")

            try:
                # Get detailed data
                raw_data = self.get_concept_board_info(concept_name)

                if raw_data:
                    # Parse and add to results
                    parsed_data = self.parse_board_data(concept_code, concept_name, raw_data)
                    results.append(parsed_data)

                # Rate limiting
                if idx < total - 1:
                    time.sleep(self.rate_limit_delay)

            except Exception as e:
                print(f"Error processing {concept_name}: {e}")
                continue

        return results

    def get_all_industry_realtime_data(self) -> List[Dict]:
        """
        Get real-time data for all industry boards

        Returns:
            List of board data dictionaries

        Note:
            This operation takes ~1-2 minutes for 90 boards
        """
        # Get all industry boards
        df_names = self.get_all_industry_boards()

        results = []
        total = len(df_names)

        for idx, row in df_names.iterrows():
            industry_name = row['name']
            industry_code = row['code']

            print(f"Fetching industry board {idx + 1}/{total}: {industry_name}")

            try:
                # Get detailed data
                raw_data = self.get_industry_board_info(industry_name)

                if raw_data:
                    # Parse and add to results
                    parsed_data = self.parse_board_data(industry_code, industry_name, raw_data)
                    results.append(parsed_data)

                # Rate limiting
                if idx < total - 1:
                    time.sleep(self.rate_limit_delay)

            except Exception as e:
                print(f"Error processing {industry_name}: {e}")
                continue

        return results


# Global service instance
tonghuashun_service = TonghuashunService()
