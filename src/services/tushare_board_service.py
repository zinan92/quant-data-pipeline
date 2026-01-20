"""
Tushare Board Service
板块数据服务 - 同步同花顺概念板块
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Dict, Optional, Generator

from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.database import session_scope
from src.models import BoardMapping
from src.services.tushare_client import TushareClient
from src.utils.ticker_utils import TickerNormalizer

logger = logging.getLogger(__name__)


@contextmanager
def _optional_session(session: Optional[Session] = None) -> Generator[Session, None, None]:
    """
    如果传入 session，直接使用它（调用者负责管理）；
    否则使用 session_scope 创建和管理 session。
    """
    if session is not None:
        yield session
    else:
        with session_scope() as new_session:
            yield new_session


class TushareBoardService:
    """
    Tushare 板块服务

    功能：
    - 同步同花顺概念板块
    - 查询股票所属板块
    - 管理板块-成分股映射关系
    """

    def __init__(self, settings: Settings | None = None):
        """
        初始化板块服务

        Args:
            settings: 应用配置
        """
        self.settings = settings or get_settings()

        # 初始化 Tushare 客户端
        self.client = TushareClient(
            token=self.settings.tushare_token,
            points=self.settings.tushare_points,
            delay=self.settings.tushare_delay,
            max_retries=self.settings.tushare_max_retries
        )

        logger.info("TushareBoardService 已初始化")

    def sync_concept_boards(self, session: Optional[Session] = None) -> int:
        """
        同步同花顺概念板块到数据库

        Args:
            session: 数据库会话（可选，未提供时自动创建）

        Returns:
            int: 同步的板块数量

        注意：
        - 需要 5000+ 积分
        - 会删除旧的概念板块数据并重新导入
        """
        if not self.settings.enable_concept_boards:
            logger.info("概念板块功能已禁用，跳过同步")
            return 0

        logger.info("开始同步同花顺概念板块...")

        # 获取所有概念板块列表
        concept_boards_df = self.client.fetch_ths_index(
            exchange='A',
            type='N'  # N = 概念
        )

        if concept_boards_df.empty:
            logger.warning("未获取到概念板块数据")
            return 0

        logger.info(f"获取到 {len(concept_boards_df)} 个概念板块")

        with _optional_session(session) as sess:
            synced_count = 0

            # 删除旧的概念板块数据（保留行业板块）
            deleted = sess.query(BoardMapping).filter(
                BoardMapping.board_type == 'concept'
            ).delete()

            logger.info(f"删除了 {deleted} 条旧概念板块记录")

            # 遍历每个概念板块，获取成分股
            for idx, row in concept_boards_df.iterrows():
                board_code = row['ts_code']  # 如 885800.TI
                board_name = row['name']
                count = row.get('count', 0)

                logger.debug(
                    f"处理概念板块 [{idx + 1}/{len(concept_boards_df)}]: "
                    f"{board_name} (code={board_code}, count={count})"
                )

                try:
                    # 获取成分股
                    members_df = self.client.fetch_ths_member(ts_code=board_code)

                    if members_df.empty:
                        logger.warning(f"板块 {board_name} 没有成分股数据")
                        continue

                    # 转换成分股代码（从 Tushare 格式转为6位代码）
                    # ths_member API 返回的字段是 'con_code'
                    code_field = 'con_code' if 'con_code' in members_df.columns else 'code'
                    constituents = [
                        self.client.denormalize_ts_code(code)
                        for code in members_df[code_field].dropna().tolist()
                    ]

                    # 标准化代码
                    constituents = TickerNormalizer.normalize_batch(constituents)

                    if not constituents:
                        logger.warning(f"板块 {board_name} 成分股为空")
                        continue

                    # 保存到数据库
                    board_mapping = BoardMapping(
                        board_name=board_name,
                        board_type='concept',
                        board_code=board_code,
                        constituents=constituents,
                        last_updated=datetime.now(timezone.utc)
                    )

                    sess.add(board_mapping)
                    synced_count += 1

                    logger.debug(
                        f"同步板块: {board_name} | 成分股数量: {len(constituents)}"
                    )

                except Exception as e:
                    logger.error(f"同步板块 {board_name} 失败: {e}")
                    continue

            logger.info(f"概念板块同步完成！成功同步 {synced_count} 个板块")

            return synced_count

    def get_stock_concepts(
        self,
        ticker: str,
        session: Optional[Session] = None
    ) -> List[str]:
        """
        获取某只股票所属的所有概念板块

        Args:
            ticker: 股票代码（6位）
            session: 数据库会话（可选）

        Returns:
            List[str]: 概念板块名称列表
        """
        ticker = TickerNormalizer.normalize(ticker)

        with _optional_session(session) as sess:
            # 查询包含该股票的所有概念板块
            boards = sess.query(BoardMapping).filter(
                BoardMapping.board_type == 'concept'
            ).all()

            concepts = []

            for board in boards:
                if ticker in board.constituents:
                    concepts.append(board.board_name)

            logger.debug(f"股票 {ticker} 属于 {len(concepts)} 个概念板块")

            return concepts

    def get_industry_boards(
        self,
        session: Optional[Session] = None
    ) -> List[Dict[str, any]]:
        """
        获取所有行业板块（保留的90个行业）

        Args:
            session: 数据库会话（可选）

        Returns:
            List[Dict]: 行业板块信息列表
                [
                    {
                        'board_name': str,
                        'board_code': str,
                        'constituents': List[str],
                        'count': int
                    },
                    ...
                ]
        """
        with _optional_session(session) as sess:
            boards = sess.query(BoardMapping).filter(
                BoardMapping.board_type == 'industry'
            ).all()

            result = []

            for board in boards:
                result.append({
                    'board_name': board.board_name,
                    'board_code': board.board_code,
                    'constituents': board.constituents,
                    'count': len(board.constituents) if board.constituents else 0,
                    'last_updated': board.last_updated
                })

            logger.debug(f"获取到 {len(result)} 个行业板块")

            return result

    def get_concept_boards(
        self,
        session: Optional[Session] = None
    ) -> List[Dict[str, any]]:
        """
        获取所有概念板块（同花顺）

        Args:
            session: 数据库会话（可选）

        Returns:
            List[Dict]: 概念板块信息列表
        """
        with _optional_session(session) as sess:
            boards = sess.query(BoardMapping).filter(
                BoardMapping.board_type == 'concept'
            ).all()

            result = []

            for board in boards:
                result.append({
                    'board_name': board.board_name,
                    'board_code': board.board_code,
                    'constituents': board.constituents,
                    'count': len(board.constituents) if board.constituents else 0,
                    'last_updated': board.last_updated
                })

            logger.debug(f"获取到 {len(result)} 个概念板块")

            return result

    def get_board_constituents(
        self,
        board_name: str,
        board_type: str = 'industry',
        session: Optional[Session] = None
    ) -> List[str]:
        """
        获取某个板块的成分股列表

        Args:
            board_name: 板块名称
            board_type: 板块类型（industry/concept）
            session: 数据库会话（可选）

        Returns:
            List[str]: 股票代码列表（6位）
        """
        with _optional_session(session) as sess:
            board = sess.query(BoardMapping).filter(
                BoardMapping.board_name == board_name,
                BoardMapping.board_type == board_type
            ).first()

            if not board:
                logger.warning(
                    f"未找到板块: name={board_name}, type={board_type}"
                )
                return []

            constituents = board.constituents or []

            logger.debug(
                f"板块 {board_name} ({board_type}) 包含 {len(constituents)} 只股票"
            )

            return constituents

    def update_stock_concepts(
        self,
        ticker: str,
        session: Optional[Session] = None
    ) -> List[str]:
        """
        更新某只股票的概念板块列表（到 symbol_metadata 表）

        Args:
            ticker: 股票代码
            session: 数据库会话

        Returns:
            List[str]: 更新后的概念列表
        """
        from src.models import SymbolMetadata

        ticker = TickerNormalizer.normalize(ticker)

        # 获取股票所属的概念板块
        concepts = self.get_stock_concepts(ticker, session=session)

        with _optional_session(session) as sess:
            # 更新 symbol_metadata 表
            symbol = sess.query(SymbolMetadata).filter(
                SymbolMetadata.ticker == ticker
            ).first()

            if symbol:
                symbol.concepts = concepts
                # session_scope 会自动 commit

                logger.debug(
                    f"更新股票 {ticker} 的概念板块: {concepts}"
                )

            return concepts
