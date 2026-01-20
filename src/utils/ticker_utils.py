"""Ticker code validation and normalization utilities for A-share stocks."""

import re
from typing import List

from src.utils.logging import LOGGER


class TickerValidationError(ValueError):
    """Raised when a ticker code cannot be validated or normalized."""

    pass


class TickerNormalizer:
    """
    Validates and normalizes Chinese A-share ticker codes.

    Supports multiple input formats:
    - Pure 6-digit codes: 600519, 000001, 300750
    - Market-prefixed codes: SH600519, SZ000001, sh600519, sz000001
    - Short codes (auto-padded): 1 -> 000001, 528 -> 000528

    Standard A-share formats:
    - Shanghai Main Board: 600xxx, 601xxx, 603xxx, 605xxx
    - Shenzhen Main Board: 000xxx
    - SME Board (Shenzhen): 002xxx
    - ChiNext (Growth): 300xxx
    - STAR Market (SSE): 688xxx, 689xxx
    - Beijing Stock Exchange: 4xxxxx, 8xxxxx
    """

    # Market prefixes (case-insensitive)
    MARKET_PREFIXES = ["sh", "sz", "bj"]

    # Valid A-share ticker patterns (6 digits starting with specific prefixes)
    VALID_PATTERNS = [
        r"^60[0135]\d{3}$",  # Shanghai Main Board (600xxx, 601xxx, 603xxx, 605xxx)
        r"^000\d{3}$",  # Shenzhen Main Board
        r"^002\d{3}$",  # SME Board
        r"^300\d{3}$",  # ChiNext
        r"^68[89]\d{3}$",  # STAR Market
        r"^[48]\d{5}$",  # Beijing Stock Exchange
    ]

    @classmethod
    def normalize(cls, ticker: str) -> str:
        """
        Normalize a ticker code to standard 6-digit format.

        Args:
            ticker: Raw ticker code (may have market prefix, be padded, etc.)

        Returns:
            Normalized 6-digit ticker code

        Raises:
            TickerValidationError: If ticker cannot be normalized or validated

        Examples:
            >>> TickerNormalizer.normalize("600519")
            "600519"
            >>> TickerNormalizer.normalize("SH600519")
            "600519"
            >>> TickerNormalizer.normalize("000001")
            "000001"
            >>> TickerNormalizer.normalize("1")
            "000001"
            >>> TickerNormalizer.normalize("528")
            "000528"
        """
        if not ticker:
            raise TickerValidationError("Ticker code cannot be empty")

        # Step 1: Strip whitespace and convert to uppercase
        ticker = ticker.strip().upper()

        # Step 2: Remove market prefix if present (SH/SZ/BJ)
        for prefix in cls.MARKET_PREFIXES:
            if ticker.upper().startswith(prefix.upper()):
                ticker = ticker[len(prefix) :]
                break

        # Step 3: Extract only digits
        ticker = "".join(c for c in ticker if c.isdigit())

        if not ticker:
            raise TickerValidationError("No valid digits found in ticker code")

        # Step 4: Pad with leading zeros to 6 digits
        if len(ticker) < 6:
            ticker = ticker.zfill(6)
            LOGGER.debug("Padded ticker to 6 digits: %s", ticker)
        elif len(ticker) > 6:
            raise TickerValidationError(
                f"Ticker code too long (>{6} digits): {ticker}"
            )

        # Step 5: Validate against known A-share patterns
        if not cls.is_valid(ticker):
            LOGGER.warning(
                "Ticker %s does not match standard A-share patterns, "
                "but will be processed anyway",
                ticker,
            )

        return ticker

    @classmethod
    def is_valid(cls, ticker: str) -> bool:
        """
        Check if a ticker matches valid A-share patterns.

        Args:
            ticker: 6-digit ticker code

        Returns:
            True if ticker matches any known A-share pattern
        """
        if not ticker or len(ticker) != 6 or not ticker.isdigit():
            return False

        return any(re.match(pattern, ticker) for pattern in cls.VALID_PATTERNS)

    @classmethod
    def normalize_batch(cls, tickers: List[str]) -> List[str]:
        """
        Normalize a list of ticker codes, filtering out invalid ones.

        Args:
            tickers: List of raw ticker codes

        Returns:
            List of normalized valid ticker codes (duplicates removed)
        """
        normalized = []
        seen = set()

        for raw_ticker in tickers:
            try:
                ticker = cls.normalize(raw_ticker)
                if ticker not in seen:
                    normalized.append(ticker)
                    seen.add(ticker)
            except TickerValidationError as e:
                LOGGER.error("Failed to normalize ticker '%s': %s", raw_ticker, e)
                continue

        return normalized

    @classmethod
    def identify_market(cls, ticker: str) -> str:
        """
        Identify which market/board a ticker belongs to.

        Args:
            ticker: 6-digit normalized ticker code

        Returns:
            Market name (e.g., "SSE", "SZSE", "ChiNext", "STAR", "BSE")
        """
        if not ticker or len(ticker) != 6:
            return "Unknown"

        first_three = ticker[:3]
        first_two = ticker[:2]

        if first_three in ["600", "601", "603", "605"]:
            return "SSE"  # Shanghai Stock Exchange
        elif first_three == "000":
            return "SZSE"  # Shenzhen Stock Exchange (Main Board)
        elif first_three == "002":
            return "SME"  # Small and Medium Enterprise Board
        elif first_three == "300":
            return "ChiNext"  # Growth Enterprise Market
        elif first_two in ["68"]:
            return "STAR"  # Science and Technology Innovation Board
        elif ticker[0] in ["4", "8"]:
            return "BSE"  # Beijing Stock Exchange
        else:
            return "Unknown"
