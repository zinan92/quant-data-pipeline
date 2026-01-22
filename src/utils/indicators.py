"""
技术指标计算工具

提供常用的技术指标计算函数，如MACD、MA等
"""
import numpy as np


def calculate_macd(
    close_prices: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, list[float | None]]:
    """
    计算MACD指标（Moving Average Convergence Divergence）

    MACD = DIF线 + DEA线 + MACD柱
    - DIF (差离值): 快线EMA - 慢线EMA
    - DEA (信号线): DIF的EMA
    - MACD柱: (DIF - DEA) * 2

    Args:
        close_prices: 收盘价列表
        fast_period: 快线周期，默认12
        slow_period: 慢线周期，默认26
        signal_period: 信号线周期，默认9

    Returns:
        包含 dif, dea, macd(柱状图) 的字典

    Example:
        >>> prices = [10.0, 10.5, 11.0, 10.8, 11.2]
        >>> result = calculate_macd(prices)
        >>> result.keys()
        dict_keys(['dif', 'dea', 'macd'])
    """
    # 数据量不足时返回None值
    if len(close_prices) < slow_period:
        return {
            "dif": [None] * len(close_prices),
            "dea": [None] * len(close_prices),
            "macd": [None] * len(close_prices),
        }

    closes = np.array(close_prices, dtype=float)

    def ema(data: np.ndarray, period: int) -> np.ndarray:
        """
        计算指数移动平均 (Exponential Moving Average)

        EMA[i] = (Price[i] - EMA[i-1]) * multiplier + EMA[i-1]
        其中 multiplier = 2 / (period + 1)
        """
        result = np.zeros(len(data))
        multiplier = 2 / (period + 1)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
        return result

    # 计算快线和慢线EMA
    ema_fast = ema(closes, fast_period)
    ema_slow = ema(closes, slow_period)

    # DIF = 快线EMA - 慢线EMA
    dif = ema_fast - ema_slow

    # DEA = DIF的EMA (信号线)
    dea = ema(dif, signal_period)

    # MACD柱状图 = (DIF - DEA) * 2
    macd_bar = (dif - dea) * 2

    return {
        "dif": [round(v, 4) for v in dif.tolist()],
        "dea": [round(v, 4) for v in dea.tolist()],
        "macd": [round(v, 4) for v in macd_bar.tolist()],
    }
