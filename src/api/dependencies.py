from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.services.data_pipeline import MarketDataService
from src.repositories.symbol_repository import SymbolRepository


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库Session（依赖注入）

    用法:
        @router.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            # 使用 db 进行数据库操作
            pass

    Yields:
        SQLAlchemy Session，自动管理生命周期（请求结束时关闭）
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_data_service(db: Session = Depends(get_db)) -> MarketDataService:
    """
    获取 MarketDataService（每请求一个实例，共享请求级 Session）

    Session 由 get_db 管理生命周期，请求结束自动关闭。
    """
    symbol_repo = SymbolRepository(db)
    return MarketDataService(symbol_repo=symbol_repo)
