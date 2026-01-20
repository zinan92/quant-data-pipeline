"""
股票赛道分类API
"""

from fastapi import APIRouter
from pydantic import BaseModel
from src.database import SessionLocal
from sqlalchemy import text
from typing import Optional

router = APIRouter()


class SectorResponse(BaseModel):
    ticker: str
    sector: str | None


class SectorBatchResponse(BaseModel):
    sectors: dict[str, str]  # ticker -> sector


class SectorTurnoverItem(BaseModel):
    sector: str
    today_volume: float  # 今日成交量
    yesterday_volume: float  # 昨日成交量
    change_percent: Optional[float]  # 变化百分比
    stock_count: int  # 统计到的股票数量


class SectorTurnoverResponse(BaseModel):
    data: list[SectorTurnoverItem]
    today_date: str
    yesterday_date: str


def get_traded_hours():
    """
    计算当前已交易的小时数（不包含休市时间）
    交易时间: 9:30-11:30 (2小时), 13:00-15:00 (2小时), 总计4小时
    """
    from datetime import datetime
    now = datetime.now()
    hour = now.hour
    minute = now.minute

    if hour < 9 or (hour == 9 and minute < 30):
        return 0.0  # 还没开盘
    elif hour < 11 or (hour == 11 and minute <= 30):
        # 上午盘: 9:30-11:30
        return (hour - 9) + (minute - 30) / 60.0
    elif hour < 13:
        # 午休时间，按上午收盘算
        return 2.0
    elif hour < 15:
        # 下午盘: 13:00-15:00
        return 2.0 + (hour - 13) + minute / 60.0
    else:
        # 已收盘
        return 4.0


@router.get("/turnover", response_model=SectorTurnoverResponse)
async def get_sector_turnover():
    """
    获取各赛道的成交额统计

    返回每个赛道今日和昨日的总成交额，以及变化比例
    今日成交额按比例折算：今日实际成交额 vs 昨日全天成交额 × (已交易时间 / 4小时)
    """
    session = SessionLocal()
    try:
        # 1. 获取最近两个有足够成交量数据的交易日
        # 需要有超过100只股票有成交量数据才算有效
        trade_dates = session.execute(
            text("""
                SELECT trade_time, COUNT(*) as cnt
                FROM klines
                WHERE symbol_type = 'STOCK' AND timeframe = 'DAY' AND volume > 0
                GROUP BY trade_time
                HAVING cnt > 100
                ORDER BY trade_time DESC
                LIMIT 2
            """)
        ).fetchall()

        if len(trade_dates) < 2:
            return SectorTurnoverResponse(data=[], today_date="", yesterday_date="")

        today_date = trade_dates[0][0]  # 最近有数据的日期（可能是今天）
        yesterday_date = trade_dates[1][0]  # 前一个有数据的日期（昨天）

        # 计算已交易时间比例
        traded_hours = get_traded_hours()
        time_ratio = traded_hours / 4.0 if traded_hours > 0 else 1.0

        # 2. 获取所有赛道分类
        sectors_result = session.execute(
            text("SELECT ticker, sector FROM stock_sectors")
        ).fetchall()

        # ticker -> sector 映射
        ticker_to_sector = {}
        for row in sectors_result:
            # ticker格式: 000001 (不含后缀)
            ticker_to_sector[row[0]] = row[1]

        # 3. 查询今日和昨日的成交量和收盘价数据
        # 成交额 = volume * close * 100 (volume是手数，每手100股)
        volume_result = session.execute(
            text("""
                SELECT symbol_code, trade_time, volume, close
                FROM klines
                WHERE symbol_type = 'STOCK'
                AND timeframe = 'DAY'
                AND trade_time IN (:today, :yesterday)
            """),
            {"today": today_date, "yesterday": yesterday_date}
        ).fetchall()

        # 4. 按赛道汇总成交额
        # sector -> {today: amount, yesterday: amount, count: int}
        sector_data: dict[str, dict] = {}

        for row in volume_result:
            symbol_code = row[0]  # 6位代码
            trade_time = row[1]
            volume = row[2] or 0
            close = row[3] or 0
            # 计算成交额: 手数 * 收盘价 * 100
            amount = volume * close * 100

            sector = ticker_to_sector.get(symbol_code)
            if not sector:
                continue

            if sector not in sector_data:
                sector_data[sector] = {
                    "today": 0,
                    "yesterday": 0,
                    "today_stocks": set(),
                    "yesterday_stocks": set(),
                }

            if trade_time == today_date:
                sector_data[sector]["today"] += amount
                sector_data[sector]["today_stocks"].add(symbol_code)
            elif trade_time == yesterday_date:
                sector_data[sector]["yesterday"] += amount
                sector_data[sector]["yesterday_stocks"].add(symbol_code)

        # 5. 计算变化比例并构建响应（按比例折算）
        items = []
        for sector, data in sector_data.items():
            today_amount = data["today"]
            yesterday_amount = data["yesterday"]

            # 取两天都有数据的股票数量
            stock_count = len(data["today_stocks"] & data["yesterday_stocks"])

            # 计算变化比例：今日实际成交额 vs 昨日按时间比例折算的成交额
            change_percent = None
            # 只有今天有成交数据且昨天也有数据时才计算变化
            if today_amount > 0 and yesterday_amount > 0 and time_ratio > 0:
                # 昨日折算成交额 = 昨日全天成交额 × (已交易时间 / 4小时)
                yesterday_prorated = yesterday_amount * time_ratio
                change_percent = ((today_amount - yesterday_prorated) / yesterday_prorated) * 100

            items.append(SectorTurnoverItem(
                sector=sector,
                today_volume=today_amount,  # 今日实际成交额
                yesterday_volume=yesterday_amount,  # 昨日全天成交额
                change_percent=change_percent,
                stock_count=stock_count,
            ))

        # 按变化比例排序
        items.sort(key=lambda x: x.change_percent if x.change_percent is not None else -999, reverse=True)

        return SectorTurnoverResponse(
            data=items,
            today_date=today_date,
            yesterday_date=yesterday_date,
        )
    finally:
        session.close()


class SectorUpdateRequest(BaseModel):
    sector: str


class SectorListResponse(BaseModel):
    sectors: list[str]


class SectorCreateRequest(BaseModel):
    name: str


class SectorCreateResponse(BaseModel):
    name: str
    message: str


@router.get("/list/available", response_model=SectorListResponse)
async def get_available_sectors():
    """获取所有可用赛道列表（从数据库读取）"""
    session = SessionLocal()
    try:
        result = session.execute(
            text("SELECT name FROM available_sectors ORDER BY display_order")
        ).fetchall()
        sectors = [row[0] for row in result]
        return SectorListResponse(sectors=sectors)
    finally:
        session.close()


@router.post("/list/available", response_model=SectorCreateResponse)
async def create_sector(request: SectorCreateRequest):
    """创建新的赛道分类"""
    session = SessionLocal()
    try:
        from datetime import datetime
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 检查是否已存在
        existing = session.execute(
            text("SELECT name FROM available_sectors WHERE name = :name"),
            {"name": request.name}
        ).fetchone()

        if existing:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"赛道 '{request.name}' 已存在")

        # 获取最大display_order
        max_order = session.execute(
            text("SELECT MAX(display_order) FROM available_sectors")
        ).fetchone()[0] or 0

        # 插入新赛道
        session.execute(
            text("""
                INSERT INTO available_sectors (name, display_order, created_at)
                VALUES (:name, :order, :created_at)
            """),
            {"name": request.name, "order": max_order + 1, "created_at": now}
        )

        session.commit()
        return SectorCreateResponse(
            name=request.name,
            message=f"成功创建赛道 '{request.name}'"
        )
    except Exception as e:
        session.rollback()
        from fastapi import HTTPException
        if "HTTPException" in str(type(e)):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.put("/{ticker}", response_model=SectorResponse)
async def update_sector(ticker: str, request: SectorUpdateRequest):
    """更新单个股票的赛道分类"""
    session = SessionLocal()
    try:
        from datetime import datetime
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 检查是否已存在
        existing = session.execute(
            text("SELECT ticker FROM stock_sectors WHERE ticker = :ticker"),
            {"ticker": ticker}
        ).fetchone()

        if existing:
            # 更新
            session.execute(
                text("UPDATE stock_sectors SET sector = :sector, updated_at = :now WHERE ticker = :ticker"),
                {"ticker": ticker, "sector": request.sector, "now": now}
            )
        else:
            # 插入
            session.execute(
                text("INSERT INTO stock_sectors (ticker, sector, created_at, updated_at) VALUES (:ticker, :sector, :now, :now)"),
                {"ticker": ticker, "sector": request.sector, "now": now}
            )

        session.commit()
        return SectorResponse(ticker=ticker, sector=request.sector)
    finally:
        session.close()


@router.get("/{ticker}", response_model=SectorResponse)
async def get_sector(ticker: str):
    """获取单个股票的赛道分类"""
    session = SessionLocal()
    try:
        result = session.execute(
            text("SELECT sector FROM stock_sectors WHERE ticker = :ticker"),
            {"ticker": ticker}
        ).fetchone()

        return SectorResponse(
            ticker=ticker,
            sector=result[0] if result else None
        )
    finally:
        session.close()


@router.post("/batch", response_model=SectorBatchResponse)
async def get_sectors_batch(tickers: list[str]):
    """批量获取股票的赛道分类"""
    session = SessionLocal()
    try:
        if not tickers:
            return SectorBatchResponse(sectors={})

        # 使用IN查询
        placeholders = ",".join([f":t{i}" for i in range(len(tickers))])
        params = {f"t{i}": t for i, t in enumerate(tickers)}

        result = session.execute(
            text(f"SELECT ticker, sector FROM stock_sectors WHERE ticker IN ({placeholders})"),
            params
        ).fetchall()

        sectors = {row[0]: row[1] for row in result}
        return SectorBatchResponse(sectors=sectors)
    finally:
        session.close()


@router.get("/", response_model=SectorBatchResponse)
async def get_all_sectors():
    """获取所有股票的赛道分类"""
    session = SessionLocal()
    try:
        result = session.execute(
            text("SELECT ticker, sector FROM stock_sectors")
        ).fetchall()

        sectors = {row[0]: row[1] for row in result}
        return SectorBatchResponse(sectors=sectors)
    finally:
        session.close()
