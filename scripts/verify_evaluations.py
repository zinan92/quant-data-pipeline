#!/usr/bin/env python3
"""
K线评估验证脚本
用于更新8分以上评估的1日和5日收益率验证数据
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.database import session_scope
from src.models import KlineEvaluation, Candle, Timeframe


def get_trading_days_after(ticker: str, start_date: str, days: int) -> list:
    """获取指定日期之后N个交易日的收盘价"""
    with session_scope() as session:
        # 查询该股票在start_date之后的K线数据
        query = select(Candle).where(
            Candle.ticker == ticker,
            Candle.timeframe == Timeframe.DAY,
            Candle.timestamp > datetime.fromisoformat(start_date)
        ).order_by(Candle.timestamp).limit(days + 1)  # 多取一天以防万一

        candles = session.execute(query).scalars().all()
        return [(c.timestamp.date().isoformat(), float(c.close)) for c in candles]


def verify_evaluations():
    """验证8分以上的评估，更新1日和5日收益率"""
    print(f"\n{'='*50}")
    print(f"K线评估验证")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    with session_scope() as session:
        # 查询所有8分以上且未验证的评估
        query = select(KlineEvaluation).where(
            KlineEvaluation.score >= 8,
            KlineEvaluation.verified == False
        ).order_by(KlineEvaluation.created_at)

        evaluations = session.execute(query).scalars().all()
        print(f"找到 {len(evaluations)} 条待验证的评估 (评分>=8)")

        if not evaluations:
            print("无需验证的评估")
            return

        updated_count = 0
        for eval in evaluations:
            print(f"\n处理: {eval.ticker} ({eval.stock_name}) - 评分: {eval.score}")
            print(f"  K线截止日期: {eval.kline_end_date}")
            print(f"  评估时价格: {eval.price_at_eval}")

            if not eval.price_at_eval:
                print("  ⚠ 缺少评估时价格，跳过")
                continue

            # 获取评估日期之后的交易日数据
            # 注意：ticker可能带后缀如.SZ，数据库中可能不带
            ticker_raw = eval.ticker.split('.')[0] if '.' in eval.ticker else eval.ticker
            future_prices = get_trading_days_after(ticker_raw, eval.kline_end_date, 6)

            if len(future_prices) < 1:
                print(f"  ⚠ 未找到后续交易日数据，可能数据还未更新")
                continue

            print(f"  找到 {len(future_prices)} 个后续交易日")

            # 更新1日收益率
            if len(future_prices) >= 1:
                date_1d, price_1d = future_prices[0]
                return_1d = ((price_1d - eval.price_at_eval) / eval.price_at_eval) * 100
                eval.price_1d = price_1d
                eval.return_1d = return_1d
                print(f"  1日后 ({date_1d}): ¥{price_1d:.2f}, 收益率: {return_1d:+.2f}%")

            # 更新5日收益率
            if len(future_prices) >= 5:
                date_5d, price_5d = future_prices[4]
                return_5d = ((price_5d - eval.price_at_eval) / eval.price_at_eval) * 100
                eval.price_5d = price_5d
                eval.return_5d = return_5d
                eval.verified = True
                print(f"  5日后 ({date_5d}): ¥{price_5d:.2f}, 收益率: {return_5d:+.2f}%")
                print(f"  ✓ 验证完成")
                updated_count += 1
            else:
                print(f"  ⏳ 等待更多交易日数据...")

        session.commit()
        print(f"\n{'='*50}")
        print(f"验证完成: 更新了 {updated_count} 条评估")


def show_stats():
    """显示评估统计信息"""
    print(f"\n{'='*50}")
    print("评估统计")
    print(f"{'='*50}\n")

    with session_scope() as session:
        all_evals = session.execute(select(KlineEvaluation)).scalars().all()

        total = len(all_evals)
        score_8_plus = [e for e in all_evals if e.score >= 8]
        verified = [e for e in score_8_plus if e.verified]

        print(f"总评估数: {total}")
        print(f"8分以上 (可操作): {len(score_8_plus)}")
        print(f"已验证: {len(verified)}")

        if verified:
            returns_1d = [e.return_1d for e in verified if e.return_1d is not None]
            returns_5d = [e.return_5d for e in verified if e.return_5d is not None]

            if returns_1d:
                avg_1d = sum(returns_1d) / len(returns_1d)
                win_1d = len([r for r in returns_1d if r > 0])
                print(f"\n1日平均收益率: {avg_1d:+.2f}%")
                print(f"1日胜率: {win_1d}/{len(returns_1d)} ({win_1d/len(returns_1d)*100:.1f}%)")

            if returns_5d:
                avg_5d = sum(returns_5d) / len(returns_5d)
                win_5d = len([r for r in returns_5d if r > 0])
                print(f"\n5日平均收益率: {avg_5d:+.2f}%")
                print(f"5日胜率: {win_5d}/{len(returns_5d)} ({win_5d/len(returns_5d)*100:.1f}%)")

        # 评分分布
        print("\n评分分布:")
        for score in range(11):
            count = len([e for e in all_evals if e.score == score])
            if count > 0:
                bar = "█" * min(count, 20)
                label = "买入" if score >= 8 else "观望" if score >= 5 else "不操作"
                print(f"  {score:2d}分 ({label}): {bar} {count}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="K线评估验证")
    parser.add_argument("--stats", "-s", action="store_true", help="显示统计信息")
    parser.add_argument("--verify", "-v", action="store_true", help="执行验证")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.verify:
        verify_evaluations()
        show_stats()
    else:
        # 默认执行验证
        verify_evaluations()
        show_stats()
