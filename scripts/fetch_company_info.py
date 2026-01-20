"""
从 Tushare 获取所有股票的公司基本信息
"""

from pathlib import Path
import sys
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import tushare as ts
from src.config import get_settings
from src.database import SessionLocal
from src.models import SymbolMetadata

settings = get_settings()


def fetch_company_info():
    """从Tushare获取公司信息并更新数据库"""
    # 初始化 Tushare
    pro = ts.pro_api(settings.tushare_token)

    session = SessionLocal()
    try:
        # 获取所有股票代码
        symbols = session.query(SymbolMetadata).all()
        total = len(symbols)
        print(f"开始获取 {total} 只股票的公司信息...")

        success_count = 0
        error_count = 0

        for idx, symbol in enumerate(symbols, 1):
            try:
                # 从Tushare获取公司信息
                df = pro.stock_company(
                    ts_code=f"{symbol.ticker}.{'SH' if symbol.ticker.startswith('6') else 'SZ'}",
                    fields='ts_code,chairman,manager,secretary,reg_capital,setup_date,province,city,'
                           'introduction,website,email,office,employees,main_business,business_scope'
                )

                if df.empty:
                    print(f"[{idx}/{total}] ⚠ {symbol.ticker} {symbol.name}: 无数据")
                    error_count += 1
                    time.sleep(0.3)  # API限速
                    continue

                # 更新数据库
                row = df.iloc[0]
                symbol.introduction = row.get('introduction')
                symbol.main_business = row.get('main_business')
                symbol.business_scope = row.get('business_scope')
                symbol.chairman = row.get('chairman')
                symbol.manager = row.get('manager')
                symbol.reg_capital = row.get('reg_capital')
                symbol.setup_date = row.get('setup_date')
                symbol.province = row.get('province')
                symbol.city = row.get('city')
                symbol.employees = row.get('employees')
                symbol.website = row.get('website')

                session.commit()

                print(f"[{idx}/{total}] ✓ {symbol.ticker} {symbol.name}")
                success_count += 1

                # API限速：每分钟120次
                time.sleep(0.5)

                # 每50条保存一次
                if idx % 50 == 0:
                    session.commit()
                    print(f"\n已保存进度: {idx}/{total}\n")

            except Exception as e:
                print(f"[{idx}/{total}] ✗ {symbol.ticker} {symbol.name}: {e}")
                error_count += 1
                session.rollback()
                time.sleep(1)  # 出错后等待更长时间

        session.commit()
        print(f"\n✅ 完成！成功: {success_count}, 失败: {error_count}")

    finally:
        session.close()


if __name__ == "__main__":
    fetch_company_info()
