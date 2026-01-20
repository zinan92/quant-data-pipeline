from __future__ import annotations

import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import select, func

from src.config import Settings, get_settings
from src.database import session_scope
from src.models import SymbolMetadata
from src.schemas import SymbolMeta
from src.services.tushare_data_provider import TushareDataProvider
from src.utils.logging import LOGGER
from src.utils.ticker_utils import TickerNormalizer


class MarketDataService:
    """Coordinates external data fetching and database persistence for metadata."""

    # 类级别缓存，用于交易日期缓存
    _trade_date_cache: Optional[str] = None
    _trade_date_cache_time: Optional[datetime] = None
    _trade_date_cache_ttl = timedelta(minutes=5)  # 缓存5分钟

    def __init__(
        self,
        provider: TushareDataProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.provider = provider or TushareDataProvider()
        self.settings = settings or get_settings()
        self._super_category_map = self._load_super_category_map()

    def _get_latest_trade_date_cached(self) -> Optional[str]:
        """获取最新交易日期（带缓存，5分钟TTL）"""
        now = datetime.now(timezone.utc)

        # 检查缓存是否有效
        if (
            MarketDataService._trade_date_cache is not None
            and MarketDataService._trade_date_cache_time is not None
            and now - MarketDataService._trade_date_cache_time < self._trade_date_cache_ttl
        ):
            return MarketDataService._trade_date_cache

        # 缓存失效，重新获取
        try:
            trade_date = self.provider.client.get_latest_trade_date()
            MarketDataService._trade_date_cache = trade_date
            MarketDataService._trade_date_cache_time = now
            return trade_date
        except Exception as exc:
            LOGGER.warning("Failed to get latest trade date | %s", exc)
            # 如果获取失败但有旧缓存，返回旧缓存
            return MarketDataService._trade_date_cache

    def _load_super_category_map(self) -> dict[str, str]:
        """
        行业 → 超级行业组映射（如果缺失文件则返回空字典）
        """
        mapping_path = Path(__file__).parent.parent.parent / "data" / "super_category_mapping.csv"
        if not mapping_path.exists():
            LOGGER.warning("Super category mapping file not found; super_category will remain empty")
            return {}

        lookup: dict[str, str] = {}
        with mapping_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                industry = row.get("行业名称")
                super_category = row.get("超级行业组")
                if industry and super_category:
                    lookup[industry] = super_category
        return lookup

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def refresh_metadata(self, tickers: list[str]) -> None:
        """刷新股票元数据"""
        tickers = TickerNormalizer.normalize_batch(list(tickers))
        if not tickers:
            LOGGER.info("No valid tickers provided for refresh; skipping.")
            return

        LOGGER.info("Begin metadata refresh | tickers=%s", len(tickers))

        try:
            metadata_df = self.provider.fetch_symbol_metadata(tickers)
        except Exception as exc:
            LOGGER.exception("Metadata fetch failed | error=%s", exc)
            metadata_df = None

        if metadata_df is not None:
            with session_scope() as session:
                self._persist_metadata(session, metadata_df)

    def list_symbols(self) -> list[SymbolMeta]:
        stmt = select(SymbolMetadata).order_by(
            SymbolMetadata.total_mv.desc(),
            SymbolMetadata.ticker.asc(),
        )
        with session_scope() as session:
            result = session.scalars(stmt).all()
        return [SymbolMeta.model_validate(row) for row in result]

    def last_refresh_time(self) -> datetime | None:
        stmt = select(func.max(SymbolMetadata.last_sync))
        with session_scope() as session:
            value = session.execute(stmt).scalar()
        return value

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _persist_metadata(self, session, dataframe) -> None:
        if dataframe is None or dataframe.empty:
            LOGGER.warning("Metadata dataframe empty; skipping persist.")
            return

        LOGGER.info("Persist metadata | rows=%s", len(dataframe))

        # OPTIMIZATION: Pre-load all existing tickers (chunk to avoid SQLite 999-param limit)
        tickers_in_df = dataframe['ticker'].tolist()
        existing_records = {}

        CHUNK_SIZE = 500
        for i in range(0, len(tickers_in_df), CHUNK_SIZE):
            ticker_chunk = tickers_in_df[i:i + CHUNK_SIZE]
            chunk_stmt = select(SymbolMetadata).where(
                SymbolMetadata.ticker.in_(ticker_chunk)
            )
            for rec in session.scalars(chunk_stmt).all():
                existing_records[rec.ticker] = rec

        LOGGER.debug("Found %d existing records", len(existing_records))

        # Split into inserts and updates
        insert_rows = []
        update_rows = []

        for row in dataframe.itertuples(index=False):
            if row.ticker in existing_records:
                update_rows.append(row)
            else:
                insert_rows.append(row)

        # OPTIMIZATION: Bulk insert new records
        if insert_rows:
            insert_records = []
            for row in insert_rows:
                insert_records.append({
                    'ticker': row.ticker,
                    'name': row.name,
                    'total_mv': getattr(row, "total_mv", None),
                    'circ_mv': getattr(row, "circ_mv", None),
                    'pe_ttm': getattr(row, "pe_ttm", None),
                    'pb': getattr(row, "pb", None),
                    'list_date': getattr(row, "list_date", None),
                    'industry_lv1': getattr(row, "industry_lv1", None),
                    'industry_lv2': getattr(row, "industry_lv2", None),
                    'industry_lv3': getattr(row, "industry_lv3", None),
                    'super_category': self._super_category_map.get(getattr(row, "industry_lv1", None)),
                    'concepts': getattr(row, "concepts", []),
                    'last_sync': getattr(row, "last_sync", datetime.now(timezone.utc))
                })
            session.bulk_insert_mappings(SymbolMetadata, insert_records)
            LOGGER.debug("Bulk inserted %d new records", len(insert_records))

        # Update existing records
        if update_rows:
            for row in update_rows:
                instance = existing_records[row.ticker]
                instance.name = row.name
                instance.total_mv = getattr(row, "total_mv", None)
                instance.circ_mv = getattr(row, "circ_mv", None)
                instance.pe_ttm = getattr(row, "pe_ttm", None)
                instance.pb = getattr(row, "pb", None)
                instance.list_date = getattr(row, "list_date", None)
                # 注意: 不再覆盖 industry_lv1/lv2/lv3
                # 这些字段由 update_industry_daily.py 从同花顺成分股关系写入
                instance.concepts = getattr(row, "concepts", [])
                instance.last_sync = getattr(row, "last_sync", datetime.now(timezone.utc))
            LOGGER.debug("Updated %d existing records", len(update_rows))
