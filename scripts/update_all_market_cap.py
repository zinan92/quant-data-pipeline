#!/usr/bin/env python3
"""
批量更新所有股票的市值数据
"""
import sys
import json
import time
import requests

API_BASE = "http://localhost:8000"

def update_batch(tickers: list, batch_num: int, total_batches: int) -> bool:
    """更新一批股票的元数据"""
    print(f"\n[{batch_num+1}/{total_batches}] 更新 {len(tickers)} 只股票...")

    try:
        response = requests.post(
            f"{API_BASE}/api/tasks/refresh",
            json={"tickers": tickers, "timeframes": []},
            timeout=30
        )

        if response.status_code != 202:
            print(f"  错误: {response.text}")
            return False

        job_id = response.json()["job_id"]
        print(f"  任务ID: {job_id}")

        # 等待任务完成
        while True:
            time.sleep(5)
            status_resp = requests.get(f"{API_BASE}/api/tasks/refresh/{job_id}")
            status = status_resp.json()

            if status["status"] == "completed":
                print(f"  ✓ 完成")
                return True
            elif status["status"] == "failed":
                print(f"  ✗ 失败: {status.get('message', 'unknown')}")
                return False
            else:
                print(f"  进度: {status.get('progress', 0)}% - {status.get('message', '')}")

    except Exception as e:
        print(f"  异常: {e}")
        return False

def main():
    # 加载所有批次
    with open('/tmp/all_batches.json', 'r') as f:
        batches = json.load(f)

    print(f"共 {len(batches)} 批待更新")

    # 从命令行参数获取起始批次
    start_batch = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    success_count = 0
    fail_count = 0

    for i, batch in enumerate(batches[start_batch:], start=start_batch):
        success = update_batch(batch, i, len(batches))
        if success:
            success_count += 1
        else:
            fail_count += 1

        # 批次间短暂休息避免API限流
        if i < len(batches) - 1:
            print("  等待3秒...")
            time.sleep(3)

    print(f"\n完成! 成功: {success_count}, 失败: {fail_count}")

if __name__ == "__main__":
    main()
