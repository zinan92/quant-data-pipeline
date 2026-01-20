#!/usr/bin/env python3
"""
API服务验证器
验证所有API服务对新添加股票的响应
"""

import sys
from pathlib import Path
from typing import Dict, Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from scripts.templates.stock_template import StockTemplate
from scripts.validators.data_validator import ValidationResult


class APIValidator:
    """API服务验证器"""

    def __init__(self, stock: StockTemplate, base_url: str = "http://localhost:5173"):
        self.stock = stock
        self.base_url = base_url

    def validate_all(self) -> ValidationResult:
        """验证所有API端点"""
        result = ValidationResult()

        # 1. 检查watchlist API
        self._check_watchlist_api(result)

        # 2. 检查watchlist check API
        self._check_watchlist_check_api(result)

        # 3. 检查K线数据API
        self._check_kline_api(result)

        # 4. 检查实时价格API（如果支持）
        if self.stock.is_supported():
            self._check_realtime_price_api(result)
        else:
            result.add_warning(f"Realtime price API skipped (BSE stock not supported)")

        # 5. 检查评估数据API
        self._check_evaluation_api(result)

        # 6. 检查赛道API
        self._check_sector_api(result)

        return result

    def _make_request(self, endpoint: str, result: ValidationResult, check_name: str) -> Optional[dict]:
        """发起HTTP请求并处理错误"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                result.add_fail(check_name, f"HTTP {response.status_code}: {url}")
                return None
        except requests.exceptions.RequestException as e:
            result.add_fail(check_name, f"Request failed: {str(e)}")
            return None

    def _check_watchlist_api(self, result: ValidationResult):
        """检查watchlist列表API"""
        data = self._make_request("/api/watchlist", result, "Watchlist API")
        if data:
            # 检查股票是否在列表中
            found = any(item['ticker'] == self.stock.get_full_ticker() for item in data)
            if found:
                result.add_pass("Stock found in /api/watchlist")
            else:
                result.add_fail("Watchlist API", f"Stock {self.stock.ticker} not in watchlist response")

    def _check_watchlist_check_api(self, result: ValidationResult):
        """检查watchlist check API"""
        endpoint = f"/api/watchlist/check/{self.stock.ticker}"
        data = self._make_request(endpoint, result, "Watchlist Check API")
        if data:
            if data.get('inWatchlist'):
                result.add_pass(f"Watchlist check returns true: {endpoint}")
            else:
                result.add_fail("Watchlist Check API", "inWatchlist is false")

    def _check_kline_api(self, result: ValidationResult):
        """检查K线数据API"""
        # 日线
        endpoint = f"/api/candles/{self.stock.ticker}?timeframe=day&limit=120"
        data = self._make_request(endpoint, result, "Daily K-line API")
        if data and isinstance(data, list):
            if len(data) > 0:
                result.add_pass(f"Daily K-line data available: {len(data)} candles")
            else:
                result.add_warning("Daily K-line API returns empty array")

        # 30分钟线
        endpoint = f"/api/candles/{self.stock.ticker}?timeframe=30m&limit=120"
        data = self._make_request(endpoint, result, "30-min K-line API")
        if data and isinstance(data, list):
            if len(data) > 0:
                result.add_pass(f"30-min K-line data available: {len(data)} candles")
            else:
                result.add_warning("30-min K-line API returns empty array")

    def _check_realtime_price_api(self, result: ValidationResult):
        """检查实时价格API"""
        endpoint = f"/api/realtime/prices?tickers={self.stock.ticker}"
        try:
            response = requests.get(f"{self.base_url}{endpoint}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    response_data = data['data']
                    # 检查是否包含股票数据
                    if self.stock.ticker in response_data and 'FAILED' not in response_data:
                        result.add_pass(f"Realtime price API works: {endpoint}")
                    else:
                        result.add_fail("Realtime Price API", "Response contains FAILED or no data")
                else:
                    result.add_fail("Realtime Price API", "Response missing 'data' field")
            else:
                result.add_fail("Realtime Price API", f"HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            result.add_fail("Realtime Price API", str(e))

    def _check_evaluation_api(self, result: ValidationResult):
        """检查评估数据API"""
        endpoint = f"/api/evaluations?ticker={self.stock.ticker}&limit=1"
        data = self._make_request(endpoint, result, "Evaluation API")
        if data:
            if isinstance(data, list):
                if len(data) > 0:
                    result.add_pass("Evaluation data exists")
                else:
                    result.add_warning("No evaluation data (may be generated later)")
            else:
                result.add_fail("Evaluation API", "Response is not an array")

    def _check_sector_api(self, result: ValidationResult):
        """检查赛道API"""
        endpoint = "/api/sectors/"
        data = self._make_request(endpoint, result, "Sectors API")
        if data and 'sectors' in data:
            sectors = data['sectors']
            if self.stock.ticker in sectors:
                sector = sectors[self.stock.ticker]
                if sector == self.stock.sector:
                    result.add_pass(f"Sector API returns correct sector: {sector}")
                else:
                    result.add_warning(f"Sector mismatch in API: Expected '{self.stock.sector}', got '{sector}'")
            else:
                result.add_fail("Sectors API", f"Ticker {self.stock.ticker} not in sectors response")


if __name__ == "__main__":
    # 测试用例
    from scripts.templates.stock_template import create_stock_template

    test_stock = create_stock_template("600519", "贵州茅台", "消费")

    print(f"Validating API services for: {test_stock.name} ({test_stock.ticker})")
    print("Make sure the backend server is running on http://localhost:5173\n")

    validator = APIValidator(test_stock)
    result = validator.validate_all()
    result.print_report()
