"""
Base Repository - 通用Repository基类

提供所有Repository的通用功能和接口规范。
"""

from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.database import Base

# Generic type for model
T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Repository基类，提供通用CRUD操作"""

    def __init__(self, session: Session, model_class: Type[T]):
        """
        初始化Repository

        Args:
            session: SQLAlchemy Session对象
            model_class: 数据模型类
        """
        self.session = session
        self.model_class = model_class

    def find_by_id(self, id_value: any) -> Optional[T]:
        """
        根据主键ID查询单条记录

        Args:
            id_value: 主键值

        Returns:
            模型实例或None
        """
        return self.session.get(self.model_class, id_value)

    def find_all(self, limit: Optional[int] = None) -> List[T]:
        """
        查询所有记录

        Args:
            limit: 限制返回数量

        Returns:
            模型实例列表
        """
        stmt = select(self.model_class)
        if limit:
            stmt = stmt.limit(limit)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def save(self, entity: T) -> T:
        """
        保存单条记录（新增或更新）

        Args:
            entity: 模型实例

        Returns:
            保存后的模型实例
        """
        self.session.add(entity)
        self.session.flush()  # 刷新获取ID，但不提交事务
        return entity

    def save_all(self, entities: List[T]) -> List[T]:
        """
        批量保存记录

        Args:
            entities: 模型实例列表

        Returns:
            保存后的模型实例列表
        """
        self.session.add_all(entities)
        self.session.flush()
        return entities

    def delete_by_id(self, id_value: any) -> bool:
        """
        根据ID删除记录

        Args:
            id_value: 主键值

        Returns:
            是否删除成功
        """
        entity = self.find_by_id(id_value)
        if entity:
            self.session.delete(entity)
            self.session.flush()
            return True
        return False

    def delete(self, entity: T) -> None:
        """
        删除记录

        Args:
            entity: 要删除的模型实例
        """
        self.session.delete(entity)
        self.session.flush()

    def delete_all(self, entities: List[T]) -> None:
        """
        批量删除记录

        Args:
            entities: 要删除的模型实例列表
        """
        for entity in entities:
            self.session.delete(entity)
        self.session.flush()

    def count(self) -> int:
        """
        统计记录总数

        Returns:
            记录数量
        """
        stmt = select(func.count()).select_from(self.model_class)
        return self.session.execute(stmt).scalar() or 0

    def exists(self, id_value: any) -> bool:
        """
        检查记录是否存在

        Args:
            id_value: 主键值

        Returns:
            是否存在
        """
        return self.find_by_id(id_value) is not None

    def commit(self) -> None:
        """提交当前事务"""
        self.session.commit()

    def rollback(self) -> None:
        """回滚当前事务"""
        self.session.rollback()

    def flush(self) -> None:
        """刷新session（不提交事务）"""
        self.session.flush()
