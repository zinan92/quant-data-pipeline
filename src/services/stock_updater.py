"""
股票K线更新器
从东方财富和新浪获取股票日线和30分钟数据
"""

import asyncio
import time
from typing import TYPE_CHECKING

from src.models import KlineTimeframe, SymbolType, Watchlist
from src.services.kline_service import KlineService
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.repositories.kline_repository import KlineRepository
    from src.repositories.symbol_repository import SymbolRepository

logger = get_logger(__name__)

# Circuit-breaker threshold — abort after this many consecutive None results
CIRCUIT_BREAKER_THRESHOLD = 10


class StockUpdater:
    """股票K线更新器"""

    def __init__(
        self,
        kline_repo: "KlineRepository",
        symbol_repo: "SymbolRepository",
    ):
        self.kline_repo = kline_repo
        self.symbol_repo = symbol_repo

    def _get_watchlist_tickers(self) -> list[str]:
        """获取自选股代码列表"""
        tickers = self.kline_repo.session.query(Watchlist.ticker).all()
        return [t[0] for t in tickers]

    async def update_watchlist_daily(self) -> int:
        """更新自选股日线数据 (Tushare Pro)"""
        from src.services.tushare_data_provider import TushareDataProvider
        from src.models import Timeframe as TF

        logger.info("开始更新自选股日线数据...")
        total_updated = 0
        failed_count = 0

        tickers = self._get_watchlist_tickers()
        if not tickers:
            logger.info("自选股列表为空，跳过更新")
            return 0

        logger.info(f"共 {len(tickers)} 只自选股需要更新")
        ts_provider = TushareDataProvider()
        kline_service = KlineService(self.kline_repo, self.symbol_repo)

        for i, ticker in enumerate(tickers):
            try:
                df = ts_provider.fetch_candles(ticker, TF.DAY, 120)
                if df is None or df.empty:
                    logger.debug(f"{ticker} 无日线数据")
                    continue

                klines = []
                for _, row in df.iterrows():
                    klines.append({
                        "datetime": row["timestamp"].strftime("%Y-%m-%d"),
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "amount": 0,
                    })

                count = kline_service.save_klines(
                    symbol_type=SymbolType.STOCK,
                    symbol_code=ticker,
                    symbol_name=None,
                    timeframe=KlineTimeframe.DAY,
                    klines=klines,
                )
                total_updated += count
                logger.debug(f"{ticker} 日线: {count} 条")

            except Exception as e:
                logger.warning(f"{ticker} 日线更新失败: {e}")
                failed_count += 1
                continue

            # 每50只股票打印一次进度
            if (i + 1) % 50 == 0:
                logger.info(f"  进度: {i + 1}/{len(tickers)}")

        logger.info(f"自选股日线更新完成，共 {total_updated} 条，失败 {failed_count} 个")
        return total_updated

    async def update_watchlist_30m(self) -> int:
        """更新自选股30分钟K线数据 (新浪财经)

        Runs the synchronous SinaKlineProvider in a thread so the event loop
        stays responsive.  Includes a circuit-breaker: aborts if 10+
        consecutive stocks return None (likely rate-limited).
        """
        from src.services.sina_kline_provider import SinaKlineProvider

        logger.info("开始更新自选股30分钟数据...")

        tickers = self._get_watchlist_tickers()
        if not tickers:
            logger.info("自选股列表为空，跳过更新")
            return 0

        logger.info(f"共 {len(tickers)} 只自选股需要更新")
        provider = SinaKlineProvider(delay=0.5)
        kline_service = KlineService(self.kline_repo, self.symbol_repo)

        # Offload the blocking loop to a thread
        total_updated = await asyncio.to_thread(
            self._sync_update_30m, tickers, provider, kline_service
        )
        return total_updated

    def _sync_update_30m(
        self,
        tickers: list[str],
        provider,
        kline_service,
    ) -> int:
        """Synchronous inner loop for 30-min updates (runs in a thread)."""
        total_updated = 0
        failed_count = 0
        consecutive_none = 0

        for i, ticker in enumerate(tickers):
            # Circuit breaker
            if consecutive_none >= CIRCUIT_BREAKER_THRESHOLD:
                logger.warning(
                    f"连续 {consecutive_none} 只股票返回空数据，"
                    f"中止30分钟更新 (已处理 {i}/{len(tickers)})"
                )
                break

            # Also honour the provider-level circuit breaker
            if provider.consecutive_failures >= provider.max_consecutive_failures:
                logger.warning(
                    f"SinaKlineProvider 连续 {provider.consecutive_failures} 次请求失败，"
                    f"中止30分钟更新 (已处理 {i}/{len(tickers)})"
                )
                break

            try:
                df = provider.fetch_kline(ticker, period="30m", limit=500)
                if df is None or df.empty:
                    consecutive_none += 1
                    logger.debug(f"{ticker} 无30分钟数据 (连续空: {consecutive_none})")
                    continue

                # Got data — reset streak
                consecutive_none = 0

                klines = []
                for _, row in df.iterrows():
                    klines.append({
                        "datetime": row["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "amount": 0,
                    })

                count = kline_service.save_klines(
                    symbol_type=SymbolType.STOCK,
                    symbol_code=ticker,
                    symbol_name=None,
                    timeframe=KlineTimeframe.MINS_30,
                    klines=klines,
                )
                total_updated += count
                logger.debug(f"{ticker} 30分钟: {count} 条")

            except Exception as e:
                logger.warning(f"{ticker} 30分钟更新失败: {e}")
                failed_count += 1
                continue

            # 每50只股票打印一次进度
            if (i + 1) % 50 == 0:
                logger.info(f"  进度: {i + 1}/{len(tickers)}")

        logger.info(f"自选股30分钟更新完成，共 {total_updated} 条，失败 {failed_count} 个")
        return total_updated

    async def update_all_daily(self) -> int:
        """
        更新全市场股票日线数据 (新浪财经)

        每只股票只获取最近20条日线，用于每日增量更新
        预计耗时: 5450只 × 0.1秒 ≈ 9分钟
        """
        from src.models import SymbolMetadata
        from src.services.tushare_data_provider import TushareDataProvider
        from src.models import Timeframe as TF

        logger.info("=" * 50)
        logger.info("开始更新全市场股票日线数据...")
        logger.info("=" * 50)
        total_updated = 0
        success_count = 0
        fail_count = 0
        provider = TushareDataProvider()
        kline_service = KlineService(self.kline_repo, self.symbol_repo)

        try:
            all_tickers = self.kline_repo.session.query(SymbolMetadata.ticker).all()
            tickers = [t[0] for t in all_tickers]
            total = len(tickers)

            logger.info(f"共 {total} 只股票需要更新")
            start_time = time.time()

            for i, ticker in enumerate(tickers):
                try:
                    df = provider.fetch_candles(ticker, TF.DAY, 20)
                    if df is None or df.empty:
                        fail_count += 1
                        continue

                    klines = []
                    for _, row in df.iterrows():
                        klines.append({
                            "datetime": row["timestamp"].strftime("%Y-%m-%d"),
                            "open": row["open"],
                            "high": row["high"],
                            "low": row["low"],
                            "close": row["close"],
                            "volume": row["volume"],
                            "amount": 0,
                        })

                    count = kline_service.save_klines(
                        symbol_type=SymbolType.STOCK,
                        symbol_code=ticker,
                        symbol_name=None,
                        timeframe=KlineTimeframe.DAY,
                        klines=klines,
                    )
                    total_updated += count
                    success_count += 1

                except Exception as e:
                    fail_count += 1
                    logger.debug(f"{ticker} 更新失败: {e}")
                    continue

                # 每500只股票打印一次进度
                if (i + 1) % 500 == 0:
                    elapsed = time.time() - start_time
                    rate = (i + 1) / elapsed
                    remaining = (total - i - 1) / rate if rate > 0 else 0
                    logger.info(
                        f"进度: {i + 1}/{total} ({(i+1)/total*100:.1f}%) | "
                        f"成功: {success_count} | 失败: {fail_count} | "
                        f"预计剩余: {remaining/60:.1f}分钟"
                    )

            elapsed = time.time() - start_time
            logger.info("=" * 50)
            logger.info(
                f"全市场日线更新完成 | 耗时: {elapsed/60:.1f}分钟 | "
                f"成功: {success_count} | 失败: {fail_count} | 共 {total_updated} 条"
            )
            logger.info("=" * 50)

        except Exception as e:
            logger.exception("全市场日线更新失败")
            raise

        return total_updated

    async def update_single(self, ticker: str) -> dict:
        """
        更新单只股票的日线和30分钟数据
        用于添加自选股时立即获取数据

        The Sina call is offloaded to a thread to avoid blocking the
        event loop.

        Args:
            ticker: 股票代码 (6位)

        Returns:
            {"daily": 条数, "mins30": 条数}
        """
        from src.services.sina_kline_provider import SinaKlineProvider
        from src.services.tushare_data_provider import TushareDataProvider
        from src.models import Timeframe as TF

        result = {"daily": 0, "mins30": 0}
        logger.info(f"开始更新单股 {ticker} 的K线数据...")

        # 复用同一个 service 实例
        service = KlineService(self.kline_repo, self.symbol_repo)

        # 1. 更新日线 (Tushare Pro)
        try:
            ts_provider = TushareDataProvider()
            daily_df = ts_provider.fetch_candles(ticker, TF.DAY, 120)

            if daily_df is not None and not daily_df.empty:
                if 'timestamp' in daily_df.columns:
                    daily_df = daily_df.rename(columns={'timestamp': 'datetime'})
                daily_klines = daily_df.to_dict('records')
                count = service.save_klines(
                    symbol_type=SymbolType.STOCK,
                    symbol_code=ticker,
                    symbol_name=None,
                    timeframe=KlineTimeframe.DAY,
                    klines=daily_klines,
                )
                self.kline_repo.session.commit()
                result["daily"] = count
                logger.info(f"{ticker} 日线更新: {count} 条")

        except Exception as e:
            logger.warning(f"{ticker} 日线更新失败: {e}")

        # 2. 更新30分钟 (新浪财经) — offload to thread
        try:
            sina = SinaKlineProvider()
            mins30_df = await asyncio.to_thread(
                sina.fetch_kline, ticker, "30m", 80
            )

            if mins30_df is not None and not mins30_df.empty:
                if 'timestamp' in mins30_df.columns:
                    mins30_df = mins30_df.rename(columns={'timestamp': 'datetime'})
                mins30_klines = mins30_df.to_dict('records')
                count = service.save_klines(
                    symbol_type=SymbolType.STOCK,
                    symbol_code=ticker,
                    symbol_name=None,
                    timeframe=KlineTimeframe.MINS_30,
                    klines=mins30_klines,
                )
                self.kline_repo.session.commit()
                result["mins30"] = count
                logger.info(f"{ticker} 30分钟更新: {count} 条")

        except Exception as e:
            logger.warning(f"{ticker} 30分钟更新失败: {e}")

        logger.info(
            f"单股 {ticker} 更新完成: 日线 {result['daily']} 条, "
            f"30分钟 {result['mins30']} 条"
        )
        return result
