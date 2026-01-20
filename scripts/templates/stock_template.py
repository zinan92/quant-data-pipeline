#!/usr/bin/env python3
"""
标准化股票模版
定义添加股票到自选列表时需要的所有数据和服务
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class StockExchange(Enum):
    """股票交易所"""
    SHANGHAI = "SH"  # 上海证券交易所 (6开头)
    SHENZHEN = "SZ"  # 深圳证券交易所 (0/3开头)
    BEIJING = "BJ"   # 北京证券交易所 (8/9开头，不支持)
    UNKNOWN = "UNKNOWN"


@dataclass
class StockTemplate:
    """
    标准化股票模版

    所有字段说明：
    - ticker: 6位股票代码（必需）
    - name: 股票名称（必需）
    - sector: 赛道/行业分类（可选，默认"未分类"）
    - exchange: 交易所（自动推断）
    - add_to_watchlist: 是否添加到自选列表（默认True）
    - add_to_simulated: 是否添加到模拟组合（默认False）
    """
    ticker: str
    name: str
    sector: str = "未分类"
    exchange: StockExchange = StockExchange.UNKNOWN
    add_to_watchlist: bool = True
    add_to_simulated: bool = False

    def __post_init__(self):
        """验证和规范化数据"""
        # 验证ticker格式
        if not self.ticker or len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError(f"Invalid ticker: {self.ticker}. Must be 6-digit number.")

        # 自动推断交易所
        if self.exchange == StockExchange.UNKNOWN:
            self.exchange = self._infer_exchange()

        # 验证股票名称
        if not self.name or not self.name.strip():
            raise ValueError(f"Stock name cannot be empty for ticker {self.ticker}")

    def _infer_exchange(self) -> StockExchange:
        """根据ticker推断交易所"""
        if self.ticker.startswith('6'):
            return StockExchange.SHANGHAI
        elif self.ticker.startswith(('0', '3')):
            return StockExchange.SHENZHEN
        elif self.ticker.startswith(('8', '9')):
            return StockExchange.BEIJING
        return StockExchange.UNKNOWN

    def get_full_ticker(self) -> str:
        """获取带交易所后缀的完整ticker"""
        return f"{self.ticker}.{self.exchange.value}"

    def is_supported(self) -> bool:
        """检查是否支持该股票（北交所不支持实时行情）"""
        return self.exchange != StockExchange.BEIJING

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'ticker': self.ticker,
            'name': self.name,
            'sector': self.sector,
            'exchange': self.exchange.value,
            'full_ticker': self.get_full_ticker(),
            'supported': self.is_supported()
        }


# 预定义的赛道分类
STANDARD_SECTORS = {
    "创新药": "创新药物研发与生产",
    "AI应用": "人工智能应用",
    "半导体": "半导体芯片制造",
    "新能源": "新能源汽车与电池",
    "医疗服务": "医疗健康服务",
    "消费电子": "消费电子产品",
    "未分类": "未分类"
}


def create_stock_template(
    ticker: str,
    name: str,
    sector: str = "未分类",
    **kwargs
) -> StockTemplate:
    """
    工厂函数：创建标准化股票模版

    Args:
        ticker: 6位股票代码
        name: 股票名称
        sector: 赛道分类（可选）
        **kwargs: 其他可选参数

    Returns:
        StockTemplate实例

    Example:
        >>> stock = create_stock_template("600519", "贵州茅台", "消费")
        >>> stock.get_full_ticker()
        '600519.SH'
    """
    # 验证赛道分类是否在标准列表中
    if sector not in STANDARD_SECTORS and sector != "未分类":
        print(f"Warning: Non-standard sector '{sector}'. Consider using one of: {list(STANDARD_SECTORS.keys())}")

    return StockTemplate(
        ticker=ticker,
        name=name,
        sector=sector,
        **kwargs
    )


if __name__ == "__main__":
    # 示例用法
    examples = [
        ("600519", "贵州茅台", "消费"),
        ("000001", "平安银行", "金融"),
        ("300750", "宁德时代", "新能源"),
        ("920670", "数字人", "创新药"),  # 北交所，不支持
    ]

    print("Stock Template Examples:")
    print("=" * 60)

    for ticker, name, sector in examples:
        try:
            stock = create_stock_template(ticker, name, sector)
            print(f"\n✓ {stock.name} ({stock.ticker})")
            print(f"  Full Ticker: {stock.get_full_ticker()}")
            print(f"  Exchange: {stock.exchange.value}")
            print(f"  Sector: {stock.sector}")
            print(f"  Supported: {'Yes' if stock.is_supported() else 'No (BSE)'}")
        except ValueError as e:
            print(f"\n✗ Error: {e}")
