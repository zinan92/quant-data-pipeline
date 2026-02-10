"""保持向后兼容的 thin wrapper。新代码请直接使用 NormalizedTicker。"""

from src.schemas.normalized import NormalizedTicker


class TickerValidationError(ValueError):
    """Raised when a ticker code cannot be validated or normalized."""

    pass


class TickerNormalizer:
    """
    Validates and normalizes Chinese A-share ticker codes.

    .. deprecated::
        Use :class:`~src.schemas.normalized.NormalizedTicker` directly.
    """

    VALID_PATTERNS = NormalizedTicker.VALID_PATTERNS

    @classmethod
    def normalize(cls, ticker: str) -> str:
        return NormalizedTicker(raw=ticker).raw

    @classmethod
    def is_valid(cls, ticker: str) -> bool:
        return NormalizedTicker.is_valid_ashare(ticker)

    @classmethod
    def normalize_batch(cls, tickers: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for raw in tickers:
            try:
                t = NormalizedTicker(raw=raw).raw
                if t not in seen:
                    result.append(t)
                    seen.add(t)
            except ValueError:
                continue
        return result

    @classmethod
    def identify_market(cls, ticker: str) -> str:
        return NormalizedTicker(raw=ticker).identify_market()
