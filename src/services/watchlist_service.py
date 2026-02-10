"""
WatchlistService - 自选股业务逻辑服务

从 routes_watchlist.py 中抽取的核心业务逻辑，
路由层变为薄包装，只负责参数校验和调用服务层。
"""

from collections import defaultdict
from typing import Any, Dict, List

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from src.models import Kline, KlineTimeframe, SymbolMetadata, SymbolType, Watchlist
from src.utils.logging import get_logger

logger = get_logger(__name__)


class WatchlistService:
    """自选股业务服务"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # get_watchlist_items  (对应 GET /watchlist)
    # ------------------------------------------------------------------
    def get_watchlist_items(self) -> List[Dict[str, Any]]:
        """获取自选股列表，返回完整的股票信息和分类

        Returns:
            可直接用于 WatchlistItemResponse 序列化的 dict 列表
        """
        # 获取所有自选股的ticker
        watchlist_items = self.db.query(Watchlist).order_by(
            Watchlist.added_at.desc()
        ).all()

        if not watchlist_items:
            return []

        # 获取这些股票的完整信息
        tickers = [item.ticker for item in watchlist_items]
        symbols = self.db.query(SymbolMetadata).filter(
            SymbolMetadata.ticker.in_(tickers)
        ).all()

        # 创建映射
        ticker_to_symbol = {s.ticker: s for s in symbols}

        # 组合数据：股票信息 + 分类信息
        result = []
        for item in watchlist_items:
            if item.ticker not in ticker_to_symbol:
                continue

            symbol = ticker_to_symbol[item.ticker]
            result.append({
                "ticker": symbol.ticker,
                "name": symbol.name,
                "category": item.category or "未分类",
                "added_at": item.added_at.isoformat(),
                "is_focus": bool(item.is_focus) if hasattr(item, 'is_focus') else False,
                "positioning": item.positioning if hasattr(item, 'positioning') else None,
                "total_mv": symbol.total_mv,
                "circ_mv": symbol.circ_mv,
                "pe_ttm": symbol.pe_ttm,
                "pb": symbol.pb,
                "industry_lv1": symbol.industry_lv1,
                "sector": item.category or "未分类",  # 使用 watchlist.category 作为赛道
                "concepts": symbol.concepts or [],
            })

        return result

    # ------------------------------------------------------------------
    # calculate_portfolio_history  (对应 GET /watchlist/portfolio/history)
    # ------------------------------------------------------------------
    def calculate_portfolio_history(self) -> Dict[str, Any]:
        """计算投资组合历史净值曲线"""

        # 获取所有自选股
        watchlist_items = self.db.query(Watchlist).filter(
            Watchlist.purchase_price.isnot(None),
            Watchlist.shares.isnot(None),
        ).all()

        if not watchlist_items:
            return {
                "dates": [],
                "absolute_values": [],
                "normalized_values": [],
                "initial_investment": 0,
                "current_value": 0,
                "total_return": 0,
                "return_pct": 0,
            }

        # 计算初始投资总额
        initial_investment = len(watchlist_items) * 10000.0

        # 获取最早的买入日期
        earliest_date = min(
            item.purchase_date for item in watchlist_items if item.purchase_date
        )
        earliest_date_str = earliest_date.strftime('%Y-%m-%d')

        # 获取所有交易日（从最早买入日期到现在）
        tickers = [item.ticker for item in watchlist_items]

        # 查询这些股票的所有历史K线数据（从 klines 表）
        # 注：股票K线目前只有30分钟数据，使用MINS_30
        klines_query = self.db.query(
            Kline.trade_time,
            Kline.symbol_code,
            Kline.close,
        ).filter(
            Kline.symbol_code.in_(tickers),
            Kline.symbol_type == SymbolType.STOCK,
            Kline.timeframe == KlineTimeframe.MINS_30,
            Kline.trade_time >= earliest_date_str,
        ).order_by(Kline.trade_time).all()

        # 按日期组织数据
        date_to_prices: Dict[str, Dict[str, float]] = defaultdict(dict)

        for kline in klines_query:
            date_str = kline.trade_time[:10]  # trade_time 是字符串格式 'YYYY-MM-DD'
            date_to_prices[date_str][kline.symbol_code] = float(kline.close)

        # 创建ticker到watchlist item的映射
        ticker_to_item = {item.ticker: item for item in watchlist_items}

        # 计算每个交易日的投资组合价值
        dates: List[str] = []
        absolute_values: List[float] = []
        normalized_values: List[float] = []

        for date_str in sorted(date_to_prices.keys()):
            prices = date_to_prices[date_str]

            # 计算当日总市值
            total_value = 0.0
            valid_count = 0
            expected_count = 0  # 应该有数据的股票数量

            for ticker, shares_owned in [
                (item.ticker, item.shares) for item in watchlist_items
            ]:
                # 只计算已经买入的股票
                item = ticker_to_item[ticker]
                purchase_date_str = (
                    item.purchase_date.strftime('%Y-%m-%d')
                    if item.purchase_date
                    else None
                )

                if purchase_date_str and date_str >= purchase_date_str:
                    expected_count += 1
                    if ticker in prices:
                        total_value += prices[ticker] * shares_owned
                        valid_count += 1

            # 只在数据完整度>=70%时记录（避免数据不完整导致计算错误）
            if valid_count > 0 and (valid_count >= expected_count * 0.7):
                dates.append(date_str)
                absolute_values.append(round(total_value, 2))

                # 归一化值 = 当前总市值 / 初始投资
                normalized_value = (
                    total_value / initial_investment
                    if initial_investment > 0
                    else 1.0
                )
                normalized_values.append(round(normalized_value, 4))

        # 计算当前市值和收益
        current_value = absolute_values[-1] if absolute_values else 0
        total_return = current_value - initial_investment
        return_pct = (
            (total_return / initial_investment * 100)
            if initial_investment > 0
            else 0
        )

        return {
            "dates": dates,
            "absolute_values": absolute_values,
            "normalized_values": normalized_values,
            "initial_investment": round(initial_investment, 2),
            "current_value": round(current_value, 2),
            "total_return": round(total_return, 2),
            "return_pct": round(return_pct, 2),
            "stock_count": len(watchlist_items),
        }

    # ------------------------------------------------------------------
    # calculate_analytics  (对应 GET /watchlist/analytics)
    # ------------------------------------------------------------------
    def calculate_analytics(self) -> Dict[str, Any]:
        """计算自选股组合分析数据"""

        # 获取所有自选股及其完整信息
        watchlist_items = self.db.query(Watchlist).filter(
            Watchlist.purchase_price.isnot(None),
            Watchlist.shares.isnot(None),
        ).all()

        if not watchlist_items:
            return {
                "overview": {
                    "total_stocks": 0,
                    "up_count": 0,
                    "down_count": 0,
                    "flat_count": 0,
                    "up_pct": 0,
                    "down_pct": 0,
                },
                "industry_allocation": [],
                "industry_performance": [],
                "top_gainers": [],
                "top_losers": [],
                "style_allocation": [],
                "profit_distribution": [],
                "market_value_tree": [],
            }

        # 获取所有股票的元数据（名称、行业等）
        tickers = [item.ticker for item in watchlist_items]
        symbols = self.db.query(SymbolMetadata).filter(
            SymbolMetadata.ticker.in_(tickers)
        ).all()
        ticker_to_symbol = {s.ticker: s for s in symbols}

        # 获取最新价格 - 使用子查询避免N+1问题（从 klines 表）
        # 子查询获取每个symbol_code的最新时间戳
        # 注：股票K线目前只有30分钟数据，使用MINS_30
        subq = self.db.query(
            Kline.symbol_code,
            func.max(Kline.trade_time).label('max_ts'),
        ).filter(
            Kline.symbol_code.in_(tickers),
            Kline.symbol_type == SymbolType.STOCK,
            Kline.timeframe == KlineTimeframe.MINS_30,
        ).group_by(Kline.symbol_code).subquery()

        # 主查询获取最新K线
        latest_klines = self.db.query(Kline).join(
            subq,
            and_(
                Kline.symbol_code == subq.c.symbol_code,
                Kline.trade_time == subq.c.max_ts,
            ),
        ).filter(
            Kline.symbol_type == SymbolType.STOCK,
            Kline.timeframe == KlineTimeframe.MINS_30,
        ).all()

        latest_prices = {
            k.symbol_code: float(k.close) for k in latest_klines if k.close
        }

        # 计算每只股票的盈亏
        stock_data = []
        for item in watchlist_items:
            if item.ticker not in latest_prices or item.ticker not in ticker_to_symbol:
                continue

            symbol = ticker_to_symbol[item.ticker]
            current_price = latest_prices[item.ticker]
            purchase_price = item.purchase_price
            shares = item.shares

            current_value = current_price * shares
            purchase_value = purchase_price * shares
            profit = current_value - purchase_value
            profit_pct = (
                (profit / purchase_value * 100) if purchase_value > 0 else 0
            )

            stock_data.append({
                "ticker": item.ticker,
                "name": symbol.name,
                "industry": symbol.industry_lv1,
                "sector": item.category or "未分类",  # 使用赛道分类
                "purchase_price": purchase_price,
                "current_price": current_price,
                "shares": shares,
                "purchase_value": purchase_value,
                "current_value": current_value,
                "profit": profit,
                "profit_pct": profit_pct,
            })

        # 1. 统计概览
        total_stocks = len(stock_data)
        up_count = sum(1 for s in stock_data if s["profit"] > 0)
        down_count = sum(1 for s in stock_data if s["profit"] < 0)
        flat_count = sum(1 for s in stock_data if s["profit"] == 0)

        overview = {
            "total_stocks": total_stocks,
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "up_pct": round(up_count / total_stocks * 100, 1) if total_stocks > 0 else 0,
            "down_pct": round(down_count / total_stocks * 100, 1) if total_stocks > 0 else 0,
        }

        # 2. 行业分配
        industry_stats = defaultdict(
            lambda: {"market_value": 0, "count": 0, "profit": 0}
        )
        for stock in stock_data:
            industry = stock["industry"] or "未知"
            industry_stats[industry]["market_value"] += stock["current_value"]
            industry_stats[industry]["count"] += 1
            industry_stats[industry]["profit"] += stock["profit"]

        total_market_value = sum(s["current_value"] for s in stock_data)
        industry_allocation = [
            {
                "name": industry,
                "market_value": round(stats["market_value"], 2),
                "count": stats["count"],
                "percentage": round(
                    stats["market_value"] / total_market_value * 100, 1
                )
                if total_market_value > 0
                else 0,
            }
            for industry, stats in industry_stats.items()
        ]
        industry_allocation.sort(key=lambda x: x["market_value"], reverse=True)

        # 3. 行业表现
        industry_performance = []
        for industry, stats in industry_stats.items():
            purchase_value = sum(
                s["purchase_value"]
                for s in stock_data
                if (s["industry"] or "未知") == industry
            )
            return_pct = (
                (stats["profit"] / purchase_value * 100)
                if purchase_value > 0
                else 0
            )
            industry_performance.append({
                "name": industry,
                "return_pct": round(return_pct, 2),
                "count": stats["count"],
                "profit": round(stats["profit"], 2),
            })
        industry_performance.sort(key=lambda x: x["return_pct"], reverse=True)

        # 4. Top涨跌幅
        sorted_by_profit_pct = sorted(
            stock_data, key=lambda x: x["profit_pct"], reverse=True
        )
        top_gainers = [
            {
                "ticker": s["ticker"],
                "name": s["name"],
                "industry": s["industry"],
                "profit_pct": round(s["profit_pct"], 2),
                "profit": round(s["profit"], 2),
                "current_price": round(s["current_price"], 2),
            }
            for s in sorted_by_profit_pct[:5]
        ]
        top_losers = [
            {
                "ticker": s["ticker"],
                "name": s["name"],
                "industry": s["industry"],
                "profit_pct": round(s["profit_pct"], 2),
                "profit": round(s["profit"], 2),
                "current_price": round(s["current_price"], 2),
            }
            for s in sorted_by_profit_pct[-5:]
        ]
        top_losers.reverse()

        # 5. 风格分配（进攻型 vs 防守型）
        offensive_industries = {"计算机", "电子", "传媒", "通信", "军工", "医药生物"}
        defensive_industries = {"银行", "食品饮料", "家用电器", "公用事业", "交通运输"}

        offensive_value = sum(
            s["current_value"]
            for s in stock_data
            if s["industry"] in offensive_industries
        )
        defensive_value = sum(
            s["current_value"]
            for s in stock_data
            if s["industry"] in defensive_industries
        )
        balanced_value = total_market_value - offensive_value - defensive_value

        style_allocation = [
            {
                "style": "进攻型",
                "market_value": round(offensive_value, 2),
                "percentage": round(
                    offensive_value / total_market_value * 100, 1
                )
                if total_market_value > 0
                else 0,
            },
            {
                "style": "防守型",
                "market_value": round(defensive_value, 2),
                "percentage": round(
                    defensive_value / total_market_value * 100, 1
                )
                if total_market_value > 0
                else 0,
            },
            {
                "style": "均衡型",
                "market_value": round(balanced_value, 2),
                "percentage": round(
                    balanced_value / total_market_value * 100, 1
                )
                if total_market_value > 0
                else 0,
            },
        ]

        # 6. 盈亏分布
        bins = [
            {"range": "<-10%", "min": float("-inf"), "max": -10, "count": 0},
            {"range": "-10% ~ -5%", "min": -10, "max": -5, "count": 0},
            {"range": "-5% ~ 0%", "min": -5, "max": 0, "count": 0},
            {"range": "0% ~ 5%", "min": 0, "max": 5, "count": 0},
            {"range": "5% ~ 10%", "min": 5, "max": 10, "count": 0},
            {"range": ">10%", "min": 10, "max": float("inf"), "count": 0},
        ]

        for stock in stock_data:
            profit_pct = stock["profit_pct"]
            for bin_data in bins:
                if bin_data["min"] <= profit_pct < bin_data["max"]:
                    bin_data["count"] += 1
                    break

        profit_distribution = [
            {"range": b["range"], "count": b["count"]} for b in bins
        ]

        # 7. 市值树状图数据（按行业分组）
        market_value_tree = []
        for industry, stats in industry_stats.items():
            stocks_in_industry = [
                {
                    "name": s["name"],
                    "value": round(s["current_value"], 2),
                    "profit_pct": round(s["profit_pct"], 2),
                }
                for s in stock_data
                if (s["industry"] or "未知") == industry
            ]
            market_value_tree.append({
                "name": industry,
                "value": round(stats["market_value"], 2),
                "children": stocks_in_industry,
            })
        market_value_tree.sort(key=lambda x: x["value"], reverse=True)

        return {
            "overview": overview,
            "industry_allocation": industry_allocation,
            "industry_performance": industry_performance,
            "top_gainers": top_gainers,
            "top_losers": top_losers,
            "style_allocation": style_allocation,
            "profit_distribution": profit_distribution,
            "market_value_tree": market_value_tree,
        }
