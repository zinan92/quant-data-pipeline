#!/usr/bin/env python3
"""
数据完整性验证器
验证股票数据在数据库中的完整性
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import sqlite3
from src.config import get_settings
from scripts.templates.stock_template import StockTemplate

settings = get_settings()
database_path = settings.database_url.replace("sqlite:///", "")


class ValidationResult:
    """验证结果"""
    def __init__(self):
        self.passed: List[str] = []
        self.failed: List[Tuple[str, str]] = []  # (check_name, error_message)
        self.warnings: List[str] = []

    def add_pass(self, check_name: str):
        self.passed.append(check_name)

    def add_fail(self, check_name: str, error: str):
        self.failed.append((check_name, error))

    def add_warning(self, message: str):
        self.warnings.append(message)

    def is_success(self) -> bool:
        return len(self.failed) == 0

    def print_report(self):
        """打印验证报告"""
        print("\n" + "=" * 70)
        print("VALIDATION REPORT")
        print("=" * 70)

        if self.passed:
            print(f"\n✅ PASSED ({len(self.passed)}):")
            for check in self.passed:
                print(f"   ✓ {check}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   ⚠ {warning}")

        if self.failed:
            print(f"\n❌ FAILED ({len(self.failed)}):")
            for check, error in self.failed:
                print(f"   ✗ {check}")
                print(f"     Error: {error}")

        print("\n" + "=" * 70)
        if self.is_success():
            print("RESULT: ✅ ALL CHECKS PASSED")
        else:
            print(f"RESULT: ❌ {len(self.failed)} CHECKS FAILED")
        print("=" * 70 + "\n")


class DataValidator:
    """数据完整性验证器"""

    def __init__(self, stock: StockTemplate):
        self.stock = stock
        self.conn = sqlite3.connect(database_path)
        self.cursor = self.conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()

    def validate_all(self) -> ValidationResult:
        """执行所有验证检查"""
        result = ValidationResult()

        # 1. 检查watchlist表
        self._check_watchlist(result)

        # 2. 检查stock_sectors表
        self._check_sectors(result)

        # 3. 检查K线数据
        self._check_kline_data(result)

        # 4. 检查基本信息
        self._check_basic_info(result)

        return result

    def _check_watchlist(self, result: ValidationResult):
        """检查股票是否在watchlist表中"""
        try:
            self.cursor.execute(
                "SELECT ticker, name, category FROM watchlist WHERE ticker = ?",
                (self.stock.ticker,)
            )
            row = self.cursor.fetchone()

            if row:
                result.add_pass(f"Watchlist entry exists: {row[1]} ({row[0]})")
                if row[2] and row[2] != "未分类":
                    result.add_pass(f"Category set: {row[2]}")
            else:
                result.add_fail("Watchlist entry", f"Ticker {self.stock.ticker} not found in watchlist")

        except Exception as e:
            result.add_fail("Watchlist check", str(e))

    def _check_sectors(self, result: ValidationResult):
        """检查赛道分类"""
        try:
            self.cursor.execute(
                "SELECT sector FROM stock_sectors WHERE ticker = ?",
                (self.stock.ticker,)
            )
            row = self.cursor.fetchone()

            if row:
                sector = row[0]
                if sector == self.stock.sector:
                    result.add_pass(f"Sector matches: {sector}")
                else:
                    result.add_warning(
                        f"Sector mismatch: Expected '{self.stock.sector}', got '{sector}'"
                    )
            else:
                result.add_fail("Sector classification", f"No sector entry for {self.stock.ticker}")

        except Exception as e:
            result.add_fail("Sector check", str(e))

    def _check_kline_data(self, result: ValidationResult):
        """检查K线数据是否存在"""
        try:
            # 检查日线数据
            self.cursor.execute(
                """
                SELECT COUNT(*) FROM klines
                WHERE ticker = ? AND timeframe = 'day'
                """,
                (self.stock.ticker,)
            )
            day_count = self.cursor.fetchone()[0]

            if day_count > 0:
                result.add_pass(f"Daily K-line data exists: {day_count} records")
            else:
                result.add_fail("Daily K-line data", "No daily K-line data found")

            # 检查30分钟数据
            self.cursor.execute(
                """
                SELECT COUNT(*) FROM klines
                WHERE ticker = ? AND timeframe = '30m'
                """,
                (self.stock.ticker,)
            )
            min30_count = self.cursor.fetchone()[0]

            if min30_count > 0:
                result.add_pass(f"30-min K-line data exists: {min30_count} records")
            else:
                result.add_warning("No 30-minute K-line data (may be fetched on-demand)")

        except Exception as e:
            result.add_fail("K-line data check", str(e))

    def _check_basic_info(self, result: ValidationResult):
        """检查基本信息（市值、PE等）"""
        try:
            self.cursor.execute(
                "SELECT total_mv, pe_ttm FROM watchlist WHERE ticker = ?",
                (self.stock.ticker,)
            )
            row = self.cursor.fetchone()

            if row:
                total_mv, pe_ttm = row
                if total_mv and total_mv > 0:
                    result.add_pass(f"Market value exists: {total_mv/1e4:.2f}亿")
                else:
                    result.add_warning("Market value missing or zero")

                if pe_ttm:
                    result.add_pass(f"PE ratio exists: {pe_ttm}")
                else:
                    result.add_warning("PE ratio missing")
            else:
                result.add_fail("Basic info check", "No basic info found")

        except Exception as e:
            result.add_fail("Basic info check", str(e))


if __name__ == "__main__":
    # 测试用例
    from scripts.templates.stock_template import create_stock_template

    test_stock = create_stock_template("600519", "贵州茅台", "消费")

    print(f"Validating stock: {test_stock.name} ({test_stock.ticker})")

    with DataValidator(test_stock) as validator:
        result = validator.validate_all()
        result.print_report()
