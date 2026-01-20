"""测试增量更新功能"""

from datetime import datetime, timezone, timedelta
import pytest

from src.database import SessionLocal
from src.models import Candle, Timeframe
from src.services.data_pipeline import should_update_timeframe, MarketDataService


class TestShouldUpdateTimeframe:
    """测试 should_update_timeframe 函数"""

    def test_day_timeframe_always_updates(self):
        """日线每天都应该更新"""
        # 测试周一到周日
        for weekday in range(7):
            test_date = datetime(2025, 11, 17 + weekday, tzinfo=timezone.utc)
            assert should_update_timeframe(Timeframe.DAY, test_date) is True

    def test_week_timeframe_only_monday(self):
        """周线仅周一更新"""
        # 周一（11月17日是周一）
        monday = datetime(2025, 11, 17, tzinfo=timezone.utc)
        assert should_update_timeframe(Timeframe.WEEK, monday) is True

        # 周二到周日不更新
        for day_offset in range(1, 7):
            test_date = monday + timedelta(days=day_offset)
            assert should_update_timeframe(Timeframe.WEEK, test_date) is False

    def test_month_timeframe_only_first_day(self):
        """月线仅每月1号更新"""
        # 11月1号
        first_day = datetime(2025, 11, 1, tzinfo=timezone.utc)
        assert should_update_timeframe(Timeframe.MONTH, first_day) is True

        # 其他日期不更新
        for day in [2, 15, 30]:
            test_date = datetime(2025, 11, day, tzinfo=timezone.utc)
            assert should_update_timeframe(Timeframe.MONTH, test_date) is False


class TestIncrementalUpdate:
    """测试增量更新逻辑"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """清理测试数据"""
        session = SessionLocal()
        try:
            # 清理测试ticker的数据
            session.query(Candle).filter(
                Candle.ticker == "000001"
            ).delete()
            session.commit()
        finally:
            session.close()

        yield

        # 清理
        session = SessionLocal()
        try:
            session.query(Candle).filter(
                Candle.ticker == "000001"
            ).delete()
            session.commit()
        finally:
            session.close()

    def test_get_latest_candle_timestamp_no_data(self):
        """测试查询最新K线时间戳（无数据）"""
        service = MarketDataService()
        session = SessionLocal()

        try:
            latest = service._get_latest_candle_timestamp(
                session, "000001", Timeframe.DAY
            )
            assert latest is None
        finally:
            session.close()

    def test_get_latest_candle_timestamp_with_data(self):
        """测试查询最新K线时间戳（有数据）"""
        service = MarketDataService()
        session = SessionLocal()

        try:
            # 插入测试数据
            test_candles = [
                Candle(
                    ticker="000001",
                    timeframe=Timeframe.DAY,
                    timestamp=datetime(2025, 11, 10, tzinfo=timezone.utc),
                    open=10.0,
                    high=11.0,
                    low=9.0,
                    close=10.5,
                ),
                Candle(
                    ticker="000001",
                    timeframe=Timeframe.DAY,
                    timestamp=datetime(2025, 11, 11, tzinfo=timezone.utc),
                    open=10.5,
                    high=11.5,
                    low=10.0,
                    close=11.0,
                ),
            ]
            session.add_all(test_candles)
            session.commit()

            # 查询最新时间戳
            latest = service._get_latest_candle_timestamp(
                session, "000001", Timeframe.DAY
            )

            assert latest is not None
            # 比较日期和时间，忽略时区差异
            expected = datetime(2025, 11, 11, tzinfo=timezone.utc)
            assert latest.replace(tzinfo=timezone.utc) == expected

        finally:
            session.close()

    def test_persist_candles_upsert_mode(self):
        """测试 upsert 模式持久化K线数据"""
        import pandas as pd
        from src.services.data_pipeline import MarketDataService

        service = MarketDataService()
        session = SessionLocal()

        try:
            # 插入初始数据
            initial_candles = [
                Candle(
                    ticker="000001",
                    timeframe=Timeframe.DAY,
                    timestamp=datetime(2025, 11, 10, tzinfo=timezone.utc),
                    open=10.0,
                    high=11.0,
                    low=9.0,
                    close=10.5,
                ),
                Candle(
                    ticker="000001",
                    timeframe=Timeframe.DAY,
                    timestamp=datetime(2025, 11, 11, tzinfo=timezone.utc),
                    open=10.5,
                    high=11.5,
                    low=10.0,
                    close=11.0,
                ),
            ]
            session.add_all(initial_candles)
            session.commit()

            # 准备新数据（包含重复的11月11日和新的11月12日）
            new_data = pd.DataFrame([
                {
                    'timestamp': pd.Timestamp('2025-11-11', tz='UTC'),
                    'open': 10.5,
                    'high': 12.0,  # 修改值
                    'low': 10.0,
                    'close': 11.5,  # 修改值
                    'volume': 1000.0,
                    'turnover': 10000.0,
                    'ma5': 11.0,
                    'ma10': 10.5,
                    'ma20': 10.0,
                    'ma50': 9.5,
                },
                {
                    'timestamp': pd.Timestamp('2025-11-12', tz='UTC'),
                    'open': 11.5,
                    'high': 12.5,
                    'low': 11.0,
                    'close': 12.0,
                    'volume': 1200.0,
                    'turnover': 12000.0,
                    'ma5': 11.5,
                    'ma10': 11.0,
                    'ma20': 10.5,
                    'ma50': 10.0,
                },
            ])

            # 使用 upsert 模式持久化
            service._persist_candles(
                session, "000001", Timeframe.DAY, new_data, mode="upsert"
            )
            session.commit()

            # 验证结果
            candles = session.query(Candle).filter(
                Candle.ticker == "000001",
                Candle.timeframe == Timeframe.DAY
            ).order_by(Candle.timestamp).all()

            # 应该有3根K线（10号、11号更新版、12号新增）
            assert len(candles) == 3

            # 验证11月10日的数据未改变
            assert candles[0].timestamp.replace(tzinfo=timezone.utc) == datetime(2025, 11, 10, tzinfo=timezone.utc)
            assert candles[0].close == 10.5

            # 验证11月11日的数据已更新
            assert candles[1].timestamp.replace(tzinfo=timezone.utc) == datetime(2025, 11, 11, tzinfo=timezone.utc)
            assert candles[1].close == 11.5  # 新值
            assert candles[1].high == 12.0  # 新值

            # 验证11月12日的数据已新增
            assert candles[2].timestamp.replace(tzinfo=timezone.utc) == datetime(2025, 11, 12, tzinfo=timezone.utc)
            assert candles[2].close == 12.0

        finally:
            session.close()

    def test_persist_candles_replace_mode(self):
        """测试 replace 模式持久化K线数据（全量替换）"""
        import pandas as pd
        from src.services.data_pipeline import MarketDataService

        service = MarketDataService()
        session = SessionLocal()

        try:
            # 插入初始数据
            initial_candles = [
                Candle(
                    ticker="000001",
                    timeframe=Timeframe.DAY,
                    timestamp=datetime(2025, 11, 10, tzinfo=timezone.utc),
                    open=10.0,
                    high=11.0,
                    low=9.0,
                    close=10.5,
                ),
                Candle(
                    ticker="000001",
                    timeframe=Timeframe.DAY,
                    timestamp=datetime(2025, 11, 11, tzinfo=timezone.utc),
                    open=10.5,
                    high=11.5,
                    low=10.0,
                    close=11.0,
                ),
            ]
            session.add_all(initial_candles)
            session.commit()

            # 准备全新数据（完全不同的日期）
            new_data = pd.DataFrame([
                {
                    'timestamp': pd.Timestamp('2025-11-15', tz='UTC'),
                    'open': 15.0,
                    'high': 16.0,
                    'low': 14.0,
                    'close': 15.5,
                    'volume': 1500.0,
                    'turnover': 15000.0,
                    'ma5': 15.0,
                    'ma10': 14.5,
                    'ma20': 14.0,
                    'ma50': 13.5,
                },
            ])

            # 使用 replace 模式持久化
            service._persist_candles(
                session, "000001", Timeframe.DAY, new_data, mode="replace"
            )
            session.commit()

            # 验证结果
            candles = session.query(Candle).filter(
                Candle.ticker == "000001",
                Candle.timeframe == Timeframe.DAY
            ).order_by(Candle.timestamp).all()

            # 应该只有1根K线（旧数据被删除）
            assert len(candles) == 1
            assert candles[0].timestamp.replace(tzinfo=timezone.utc) == datetime(2025, 11, 15, tzinfo=timezone.utc)
            assert candles[0].close == 15.5

        finally:
            session.close()
