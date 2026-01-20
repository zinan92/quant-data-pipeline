"""
模拟交易服务
处理模拟买入/卖出、持仓管理、收益计算等逻辑
"""

from datetime import datetime, date
from typing import Optional, Dict, Any, List

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from src.database import SessionLocal, session_scope
from src.models import (
    SimulatedAccount,
    SimulatedTrade,
    SimulatedPosition,
    TradeType,
    SymbolMetadata,
    Kline,
    KlineTimeframe,
    SymbolType,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

# 默认初始资金
DEFAULT_INITIAL_CAPITAL = 10_000_000  # 1000万


class SimulatedService:
    """模拟交易服务"""

    def __init__(self):
        self._ensure_account_exists()

    def _ensure_account_exists(self):
        """确保账户存在，如果不存在则创建"""
        with session_scope() as session:
            account = session.query(SimulatedAccount).first()
            if not account:
                account = SimulatedAccount(initial_capital=DEFAULT_INITIAL_CAPITAL)
                session.add(account)
                logger.info(f"创建模拟账户，初始资金: {DEFAULT_INITIAL_CAPITAL:,.0f}")

    def get_account(self) -> Dict[str, Any]:
        """
        获取账户概览

        Returns:
            账户信息字典
        """
        with session_scope() as session:
            account = session.query(SimulatedAccount).first()
            if not account:
                return {"error": "账户不存在"}

            initial_capital = account.initial_capital

            # 计算已用资金（持仓成本）
            positions = session.query(SimulatedPosition).all()
            total_cost = sum(p.cost_amount for p in positions)

            # 计算当前持仓市值
            position_value = 0
            for pos in positions:
                current_price = self._get_current_price(session, pos.ticker)
                if current_price:
                    position_value += pos.shares * current_price
                else:
                    # 如果获取不到当前价格，用成本价估算
                    position_value += pos.cost_amount

            # 可用现金 = 初始资金 - 已用资金 + 已实现盈亏
            realized_pnl = self._get_total_realized_pnl(session)
            cash = initial_capital - total_cost + realized_pnl

            # 总资产 = 现金 + 持仓市值
            total_value = cash + position_value

            # 总盈亏 = 总资产 - 初始资金
            total_pnl = total_value - initial_capital
            total_pnl_pct = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0

            return {
                "initial_capital": initial_capital,
                "cash": cash,
                "position_value": position_value,
                "total_value": total_value,
                "total_pnl": total_pnl,
                "total_pnl_pct": round(total_pnl_pct, 2),
                "position_count": len(positions),
            }

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        获取当前持仓列表

        Returns:
            持仓列表
        """
        with session_scope() as session:
            positions = session.query(SimulatedPosition).all()
            result = []

            for pos in positions:
                current_price = self._get_current_price(session, pos.ticker)
                current_value = pos.shares * current_price if current_price else pos.cost_amount
                pnl = current_value - pos.cost_amount
                pnl_pct = (pnl / pos.cost_amount) * 100 if pos.cost_amount > 0 else 0

                # 计算持有天数
                first_buy = datetime.strptime(pos.first_buy_date, "%Y-%m-%d").date()
                holding_days = (date.today() - first_buy).days

                # 计算仓位百分比
                account = self.get_account()
                total_value = account.get("total_value", DEFAULT_INITIAL_CAPITAL)
                position_pct = (current_value / total_value) * 100 if total_value > 0 else 0

                result.append({
                    "ticker": pos.ticker,
                    "stock_name": pos.stock_name,
                    "shares": pos.shares,
                    "cost_price": pos.cost_price,
                    "cost_amount": pos.cost_amount,
                    "current_price": current_price,
                    "current_value": current_value,
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "position_pct": round(position_pct, 2),
                    "first_buy_date": pos.first_buy_date,
                    "holding_days": holding_days,
                })

            return result

    def buy(
        self,
        ticker: str,
        price: float,
        position_pct: float,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        模拟买入

        Args:
            ticker: 股票代码
            price: 买入价格
            position_pct: 仓位百分比（基于剩余现金）
            note: 备注

        Returns:
            交易结果
        """
        with session_scope() as session:
            # 获取账户信息
            account_info = self.get_account()
            cash = account_info["cash"]

            if cash <= 0:
                return {"success": False, "error": "可用资金不足"}

            # 计算买入金额
            buy_amount = cash * (position_pct / 100)
            if buy_amount <= 0:
                return {"success": False, "error": "买入金额无效"}

            # 计算股数（向下取整到100股的整数倍）
            shares = int(buy_amount / price / 100) * 100
            if shares <= 0:
                return {"success": False, "error": "资金不足以购买100股"}

            # 实际买入金额
            actual_amount = shares * price

            # 检查是否超过总仓位100%
            total_position_value = account_info["position_value"] + actual_amount
            if total_position_value > account_info["initial_capital"]:
                return {"success": False, "error": "超过最大仓位限制(100%)"}

            # 获取股票名称
            stock_name = self._get_stock_name(session, ticker)

            # 创建交易记录
            trade = SimulatedTrade(
                ticker=ticker,
                stock_name=stock_name,
                trade_type=TradeType.BUY,
                trade_date=date.today().isoformat(),
                trade_price=price,
                shares=shares,
                amount=actual_amount,
                position_pct=position_pct,
                note=note,
            )
            session.add(trade)

            # 更新持仓
            position = session.query(SimulatedPosition).filter(
                SimulatedPosition.ticker == ticker
            ).first()

            if position:
                # 加仓：计算新的加权平均成本
                total_shares = position.shares + shares
                total_cost = position.cost_amount + actual_amount
                position.shares = total_shares
                position.cost_price = total_cost / total_shares
                position.cost_amount = total_cost
                position.last_trade_date = date.today().isoformat()
            else:
                # 新建持仓
                position = SimulatedPosition(
                    ticker=ticker,
                    stock_name=stock_name,
                    shares=shares,
                    cost_price=price,
                    cost_amount=actual_amount,
                    first_buy_date=date.today().isoformat(),
                    last_trade_date=date.today().isoformat(),
                )
                session.add(position)

            session.flush()

            logger.info(f"模拟买入: {ticker} {stock_name} {shares}股 @ {price}")

            return {
                "success": True,
                "trade_id": trade.id,
                "ticker": ticker,
                "stock_name": stock_name,
                "shares": shares,
                "price": price,
                "amount": actual_amount,
                "message": f"买入成功：{stock_name} {shares}股，成交价¥{price:,.2f}",
            }

    def sell(
        self,
        ticker: str,
        price: float,
        sell_pct: float,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        模拟卖出

        Args:
            ticker: 股票代码
            price: 卖出价格
            sell_pct: 卖出比例（基于持仓，100表示全部卖出）
            note: 备注

        Returns:
            交易结果
        """
        with session_scope() as session:
            # 获取持仓
            position = session.query(SimulatedPosition).filter(
                SimulatedPosition.ticker == ticker
            ).first()

            if not position:
                return {"success": False, "error": f"未持有 {ticker}"}

            # 计算卖出股数
            sell_shares = int(position.shares * (sell_pct / 100) / 100) * 100
            if sell_pct == 100:
                # 全部卖出时，直接使用全部股数
                sell_shares = position.shares

            if sell_shares <= 0:
                return {"success": False, "error": "卖出数量无效"}

            if sell_shares > position.shares:
                return {"success": False, "error": "卖出数量超过持仓"}

            # 计算卖出金额和盈亏
            sell_amount = sell_shares * price
            cost_of_sold = (sell_shares / position.shares) * position.cost_amount
            realized_pnl = sell_amount - cost_of_sold
            realized_pnl_pct = (realized_pnl / cost_of_sold) * 100 if cost_of_sold > 0 else 0

            stock_name = position.stock_name

            # 创建交易记录
            trade = SimulatedTrade(
                ticker=ticker,
                stock_name=stock_name,
                trade_type=TradeType.SELL,
                trade_date=date.today().isoformat(),
                trade_price=price,
                shares=sell_shares,
                amount=sell_amount,
                note=note,
                realized_pnl=realized_pnl,
                realized_pnl_pct=realized_pnl_pct,
            )
            session.add(trade)

            # 更新或删除持仓
            remaining_shares = position.shares - sell_shares
            if remaining_shares <= 0:
                # 清仓
                session.delete(position)
            else:
                # 部分卖出
                position.shares = remaining_shares
                position.cost_amount = position.cost_amount - cost_of_sold
                position.last_trade_date = date.today().isoformat()

            session.flush()

            pnl_sign = "+" if realized_pnl >= 0 else ""
            logger.info(
                f"模拟卖出: {ticker} {stock_name} {sell_shares}股 @ {price}, "
                f"盈亏: {pnl_sign}{realized_pnl:,.2f} ({pnl_sign}{realized_pnl_pct:.2f}%)"
            )

            return {
                "success": True,
                "trade_id": trade.id,
                "ticker": ticker,
                "stock_name": stock_name,
                "shares": sell_shares,
                "price": price,
                "amount": sell_amount,
                "pnl": round(realized_pnl, 2),
                "pnl_pct": round(realized_pnl_pct, 2),
                "message": f"卖出成功：{stock_name} {sell_shares}股，"
                          f"盈利¥{realized_pnl:,.2f} ({pnl_sign}{realized_pnl_pct:.2f}%)",
            }

    def get_trades(
        self,
        limit: int = 50,
        offset: int = 0,
        ticker: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取交易历史

        Args:
            limit: 返回数量
            offset: 偏移量
            ticker: 筛选股票代码

        Returns:
            交易记录列表
        """
        with session_scope() as session:
            query = session.query(SimulatedTrade).order_by(desc(SimulatedTrade.created_at))

            if ticker:
                query = query.filter(SimulatedTrade.ticker == ticker)

            total = query.count()
            trades = query.offset(offset).limit(limit).all()

            return {
                "trades": [
                    {
                        "id": t.id,
                        "ticker": t.ticker,
                        "stock_name": t.stock_name,
                        "trade_type": t.trade_type.value,
                        "trade_date": t.trade_date,
                        "trade_price": t.trade_price,
                        "shares": t.shares,
                        "amount": t.amount,
                        "position_pct": t.position_pct,
                        "realized_pnl": t.realized_pnl,
                        "realized_pnl_pct": t.realized_pnl_pct,
                        "note": t.note,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                    }
                    for t in trades
                ],
                "total": total,
            }

    def check_position(self, ticker: str) -> Dict[str, Any]:
        """
        检查是否持有某只股票

        Args:
            ticker: 股票代码

        Returns:
            持仓状态
        """
        with session_scope() as session:
            position = session.query(SimulatedPosition).filter(
                SimulatedPosition.ticker == ticker
            ).first()

            if not position:
                return {"has_position": False, "position": None}

            current_price = self._get_current_price(session, ticker)
            pnl_pct = 0
            if current_price and position.cost_price > 0:
                pnl_pct = ((current_price - position.cost_price) / position.cost_price) * 100

            return {
                "has_position": True,
                "position": {
                    "shares": position.shares,
                    "cost_price": position.cost_price,
                    "current_price": current_price,
                    "pnl_pct": round(pnl_pct, 2),
                },
            }

    def get_performance(self, days: int = 30) -> Dict[str, Any]:
        """
        获取收益表现对比

        Args:
            days: 统计天数

        Returns:
            收益对比数据
        """
        # TODO: 实现收益对比逻辑
        # 需要获取沪深300指数、自选股平均收益等数据
        account = self.get_account()

        return {
            "period": f"{days}d",
            "my_return": account["total_pnl_pct"],
            "benchmark": {
                "hs300": None,  # TODO: 获取沪深300收益
                "watchlist_avg": None,  # TODO: 获取自选股平均收益
            },
            "excess_return": None,
            "win_rate": None,
            "avg_holding_days": None,
        }

    def _get_current_price(self, session: Session, ticker: str) -> Optional[float]:
        """获取股票当前价格（最近收盘价）"""
        kline = (
            session.query(Kline)
            .filter(
                Kline.symbol_code == ticker,
                Kline.symbol_type == SymbolType.STOCK,
                Kline.timeframe == KlineTimeframe.DAY,
            )
            .order_by(desc(Kline.trade_time))
            .first()
        )
        return kline.close if kline else None

    def _get_stock_name(self, session: Session, ticker: str) -> str:
        """获取股票名称"""
        meta = session.query(SymbolMetadata).filter(
            SymbolMetadata.ticker == ticker
        ).first()
        return meta.name if meta else ticker

    def _get_total_realized_pnl(self, session: Session) -> float:
        """获取总已实现盈亏"""
        trades = session.query(SimulatedTrade).filter(
            SimulatedTrade.trade_type == TradeType.SELL,
            SimulatedTrade.realized_pnl.isnot(None),
        ).all()
        return sum(t.realized_pnl for t in trades)


# 全局服务实例
_service: Optional[SimulatedService] = None


def get_simulated_service() -> SimulatedService:
    """获取模拟交易服务单例"""
    global _service
    if _service is None:
        _service = SimulatedService()
    return _service
