#!/usr/bin/env python3
"""
检查当前市场状态（Market On/Off）
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

# 上海时区
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def is_market_open() -> bool:
    """判断当前是否在交易时间"""
    now = datetime.now(SHANGHAI_TZ)

    # 周末不交易
    if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False

    current_time = now.time()

    # 上午: 09:30 - 11:30
    morning_start = time(9, 30)
    morning_end = time(11, 30)

    # 下午: 13:00 - 15:00
    afternoon_start = time(13, 0)
    afternoon_end = time(15, 0)

    return (morning_start <= current_time <= morning_end) or \
           (afternoon_start <= current_time <= afternoon_end)


def get_market_status() -> dict:
    """获取详细的市场状态"""
    now = datetime.now(SHANGHAI_TZ)
    current_time = now.time()
    is_open = is_market_open()

    status = {
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "is_weekend": now.weekday() >= 5,
        "is_market_open": is_open,
        "market_session": None,
        "next_session": None,
    }

    # 判断当前交易时段
    if time(9, 30) <= current_time <= time(11, 30):
        status["market_session"] = "上午交易时段 (09:30-11:30)"
    elif time(13, 0) <= current_time <= time(15, 0):
        status["market_session"] = "下午交易时段 (13:00-15:00)"
    elif time(0, 0) <= current_time < time(9, 30):
        status["market_session"] = "盘前时间"
        status["next_session"] = "09:30 开盘"
    elif time(11, 30) < current_time < time(13, 0):
        status["market_session"] = "午休时间"
        status["next_session"] = "13:00 开盘"
    elif time(15, 0) < current_time <= time(23, 59, 59):
        status["market_session"] = "盘后时间"
        if now.weekday() < 4:  # Monday-Thursday
            status["next_session"] = "明日 09:30 开盘"
        elif now.weekday() == 4:  # Friday
            status["next_session"] = "下周一 09:30 开盘"

    return status


def main():
    """主函数"""
    print("=" * 70)
    print("A股市场状态检查")
    print("=" * 70)

    status = get_market_status()

    print(f"\n当前时间: {status['timestamp']}")
    print(f"日期: {status['date']} ({status['weekday']})")
    print(f"时间: {status['time']}")
    print(f"是否周末: {'是' if status['is_weekend'] else '否'}")

    print("\n" + "=" * 70)

    if status["is_market_open"]:
        print("市场状态: ✅ Market On (交易中)")
        print(f"当前时段: {status['market_session']}")
        print("\n预期行为:")
        print("  - 实时数据: 每30秒轮询")
        print("  - 日线K线: 每30秒轮询")
        print("  - 30分钟K线: 每5分钟轮询")
        print("  - 行情详情: 每30秒轮询")
    else:
        print("市场状态: ❌ Market Off (收盘)")
        print(f"当前时段: {status['market_session']}")
        if status['next_session']:
            print(f"下次开盘: {status['next_session']}")
        print("\n预期行为:")
        print("  - 实时数据: 停止轮询（显示收盘价）")
        print("  - 日线K线: 停止轮询（显示缓存数据）")
        print("  - 30分钟K线: 停止轮询（显示缓存数据）")
        print("  - 行情详情: 停止轮询（显示缓存数据）")

    print("\n" + "=" * 70)
    print("\n提示:")
    print("  - 前端应该根据Market状态自动调整轮询行为")
    print("  - 收盘后三个价格应该一致（实时、日线、30分钟）")
    print("  - 可通过浏览器Network标签验证是否停止轮询")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
