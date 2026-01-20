"""
将行业板块CSV中的所有股票添加到监控列表

特点:
1. 从industry_board_constituents.csv读取所有股票
2. 去重获取唯一的股票代码
3. 批量添加到数据库（SymbolMetadata表）
4. 初始化K线数据（可选，耗时较长）
5. 慢速获取：每只股票间隔5-8秒，避免IP被封

注意: 5525只股票的完整初始化可能需要很长时间
"""

import sys
import time
import random
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import session_scope, init_db
from src.models import SymbolMetadata, Timeframe
from src.services.data_pipeline import MarketDataService
from src.utils.logging import LOGGER


def extract_all_tickers_from_csv() -> list[str]:
    """从行业板块CSV提取所有唯一的股票代码"""
    csv_file = Path("data/industry_board_constituents.csv")

    if not csv_file.exists():
        raise FileNotFoundError(f"CSV文件不存在: {csv_file}")

    df = pd.read_csv(csv_file)

    # 提取所有股票代码
    all_tickers = set()
    for stocks in df[df['成分股数量'] > 0]['成分股列表']:
        if pd.notna(stocks):
            ticker_list = [t.strip() for t in str(stocks).split(',')]
            all_tickers.update(ticker_list)

    # 过滤掉错误标记
    all_tickers = {t for t in all_tickers if t and 'ERROR' not in t}

    return sorted(list(all_tickers))


def main():
    print("=" * 70)
    print("将全部行业板块股票添加到监控列表")
    print("=" * 70)

    # 1. 初始化数据库
    print("\n步骤1: 初始化数据库...")
    init_db()
    print("  ✓ 数据库已初始化")

    # 2. 提取所有股票代码
    print("\n步骤2: 从CSV提取股票代码...")
    tickers = extract_all_tickers_from_csv()
    print(f"  ✓ 共提取 {len(tickers)} 只唯一股票")

    # 3. 检查数据库中已有的股票
    print("\n步骤3: 检查数据库现有股票...")
    with session_scope() as session:
        existing_tickers = set(
            ticker for (ticker,) in session.query(SymbolMetadata.ticker).all()
        )
    print(f"  ✓ 数据库已有 {len(existing_tickers)} 只股票")

    # 4. 确定需要添加的新股票
    new_tickers = [t for t in tickers if t not in existing_tickers]
    print(f"  ✓ 需要添加 {len(new_tickers)} 只新股票")

    if len(new_tickers) == 0:
        print("\n✓ 所有股票已在数据库中，无需添加")
        print(f"\n当前监控列表: {len(existing_tickers)} 只股票")
        return

    # 5. 逐个添加股票（带延迟避免IP封禁）
    print("\n步骤4: 逐个获取股票数据...")

    # 计算预估时间（每只股票15秒平均延迟 + 5秒获取时间）
    avg_time_per_stock = 20  # 秒
    estimated_hours = len(new_tickers) * avg_time_per_stock / 3600
    print(f"  警告: 这将需要很长时间（约 {estimated_hours:.1f} 小时）")
    print(f"  - 每只股票间隔: 10-15秒（随机）")
    print(f"  - 每10只股票额外暂停: 60秒")
    print(f"  - 支持断点续跑: Ctrl+C 中断后可重新运行")

    service = MarketDataService()

    success_count = 0
    failed_count = 0
    consecutive_failures = 0  # 连续失败计数

    try:
        for idx, ticker in enumerate(new_tickers, start=1):
            try:
                # 获取单只股票的数据
                service.refresh_universe(
                    tickers=[ticker],
                    timeframes=(Timeframe.DAY, Timeframe.WEEK, Timeframe.MONTH)
                )

                success_count += 1
                consecutive_failures = 0  # 重置连续失败计数

                # 每10只股票显示一次进度
                if idx % 10 == 0 or idx == len(new_tickers):
                    progress = idx / len(new_tickers) * 100
                    print(f"  [{idx}/{len(new_tickers)}] ({progress:.1f}%) - 成功: {success_count}, 失败: {failed_count}")

                    # 每10只股票后额外暂停60秒，降低请求频率
                    if idx % 10 == 0 and idx < len(new_tickers):
                        print(f"    暂停60秒...")
                        time.sleep(60)

                # 添加随机延迟（10-15秒）
                if idx < len(new_tickers):
                    delay = random.uniform(10.0, 15.0)
                    time.sleep(delay)

            except Exception as e:
                failed_count += 1
                consecutive_failures += 1

                error_msg = str(e)
                LOGGER.warning(f"Failed to fetch ticker {ticker}: {error_msg}")

                # 检测IP封禁
                if "Connection aborted" in error_msg or "Remote end closed" in error_msg:
                    print(f"\n  ⚠️  警告: 检测到连接被拒绝 (可能IP被封)")
                    print(f"      已处理: {idx}/{len(new_tickers)}")
                    print(f"      成功: {success_count}, 失败: {failed_count}")

                    if consecutive_failures >= 3:
                        print(f"\n  ✗ 连续失败 {consecutive_failures} 次，可能IP已被封禁")
                        print(f"  建议:")
                        print(f"    1. 检查VPN是否连接到中国/香港节点")
                        print(f"    2. 切换VPN节点")
                        print(f"    3. 等待一段时间后重新运行")
                        print(f"\n  💡 可重新运行脚本继续添加剩余 {len(new_tickers) - idx} 只股票")
                        return

                    # 增加等待时间
                    print(f"      等待60秒后继续...")
                    time.sleep(60)
                else:
                    # 其他错误，等待3秒
                    time.sleep(3)
                continue

        print(f"\n  ✓ 处理完成")
        print(f"    成功: {success_count} 只")
        print(f"    失败: {failed_count} 只")

    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作")
        print(f"  已处理: {success_count + failed_count}/{len(new_tickers)} 只股票")
        print(f"  成功: {success_count} 只")
        print(f"  失败: {failed_count} 只")
        print(f"\n  💡 可重新运行脚本继续添加剩余股票")
        return

    # 6. 最终统计
    print("\n" + "=" * 70)
    print("✅ 完成")
    print("=" * 70)

    with session_scope() as session:
        total = session.query(SymbolMetadata).count()

    print(f"\n当前监控列表: {total} 只股票")
    print(f"  - 原有: {len(existing_tickers)} 只")
    print(f"  - 新增: {len(new_tickers)} 只")

    print("\n💡 提示:")
    print("  - 前端会自动显示所有股票")
    print("  - 数据每日16:30自动更新（交易日）")
    print("  - 也可通过API手动触发更新")


if __name__ == "__main__":
    main()
