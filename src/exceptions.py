"""
自定义异常层次结构

定义业务层异常，用于区分业务错误和系统错误。
所有自定义异常都继承自 AShareBaseException。
"""

from typing import Any, Optional


class AShareBaseException(Exception):
    """
    基础业务异常

    所有自定义异常的基类，提供统一的错误码和消息格式。
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None
    ):
        """
        Args:
            message: 错误消息
            code: 错误码（用于API响应）
            details: 额外的错误详情
        """
        self.message = message
        self.code = code or self.__class__.__name__.upper()
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式（用于API响应）"""
        result = {
            "error": self.code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


# ==================== 数据访问相关异常 ====================

class DataNotFoundError(AShareBaseException):
    """数据未找到"""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            code="DATA_NOT_FOUND",
            details={"resource": resource, "identifier": identifier}
        )
        self.resource = resource
        self.identifier = identifier


class DatabaseError(AShareBaseException):
    """数据库操作失败"""

    def __init__(self, operation: str, reason: str):
        super().__init__(
            message=f"Database {operation} failed: {reason}",
            code="DATABASE_ERROR",
            details={"operation": operation, "reason": reason}
        )


class DataIntegrityError(AShareBaseException):
    """数据完整性错误"""

    def __init__(self, table: str, constraint: str):
        super().__init__(
            message=f"Data integrity violation in {table}: {constraint}",
            code="DATA_INTEGRITY_ERROR",
            details={"table": table, "constraint": constraint}
        )


# ==================== 外部API相关异常 ====================

class ExternalAPIError(AShareBaseException):
    """外部API调用失败"""

    def __init__(self, provider: str, details: str, status_code: Optional[int] = None):
        super().__init__(
            message=f"External API error from {provider}: {details}",
            code="EXTERNAL_API_ERROR",
            details={"provider": provider, "status_code": status_code}
        )
        self.provider = provider
        self.status_code = status_code


class TushareAPIError(ExternalAPIError):
    """Tushare API错误"""

    def __init__(self, details: str, status_code: Optional[int] = None):
        super().__init__(provider="Tushare", details=details, status_code=status_code)


class RateLimitExceededError(ExternalAPIError):
    """API速率限制超出"""

    def __init__(self, provider: str, retry_after: Optional[int] = None):
        super().__init__(
            provider=provider,
            details=f"Rate limit exceeded, retry after {retry_after}s" if retry_after else "Rate limit exceeded"
        )
        self.retry_after = retry_after


# ==================== 数据验证相关异常 ====================

class ValidationError(AShareBaseException):
    """数据验证失败"""

    def __init__(self, field: str, reason: str, value: Any = None):
        super().__init__(
            message=f"Validation failed for {field}: {reason}",
            code="VALIDATION_ERROR",
            details={"field": field, "reason": reason, "value": value}
        )
        self.field = field
        self.reason = reason


class InvalidSymbolError(ValidationError):
    """无效的股票代码"""

    def __init__(self, symbol: str, reason: str = "Invalid format"):
        super().__init__(
            field="symbol",
            reason=reason,
            value=symbol
        )


class InvalidTimeframeError(ValidationError):
    """无效的时间周期"""

    def __init__(self, timeframe: str):
        super().__init__(
            field="timeframe",
            reason=f"Unsupported timeframe: {timeframe}",
            value=timeframe
        )


class InvalidDateRangeError(ValidationError):
    """无效的日期范围"""

    def __init__(self, start_date: str, end_date: str, reason: str = "Invalid date range"):
        super().__init__(
            field="date_range",
            reason=reason,
            value={"start": start_date, "end": end_date}
        )


# ==================== 业务逻辑相关异常 ====================

class BusinessLogicError(AShareBaseException):
    """业务逻辑错误"""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="BUSINESS_LOGIC_ERROR",
            details=details
        )


class InsufficientDataError(BusinessLogicError):
    """数据不足（无法进行计算）"""

    def __init__(self, operation: str, required: int, actual: int):
        super().__init__(
            message=f"Insufficient data for {operation}: required {required}, got {actual}",
            details={"operation": operation, "required": required, "actual": actual}
        )


class DataStaleError(BusinessLogicError):
    """数据过期"""

    def __init__(self, resource: str, last_update: str):
        super().__init__(
            message=f"{resource} data is stale, last update: {last_update}",
            details={"resource": resource, "last_update": last_update}
        )


# ==================== 配置相关异常 ====================

class ConfigurationError(AShareBaseException):
    """配置错误"""

    def __init__(self, key: str, reason: str):
        super().__init__(
            message=f"Configuration error for {key}: {reason}",
            code="CONFIGURATION_ERROR",
            details={"key": key, "reason": reason}
        )


class MissingConfigError(ConfigurationError):
    """缺少必需的配置"""

    def __init__(self, key: str):
        super().__init__(
            key=key,
            reason="Required configuration is missing"
        )


# ==================== 认证授权相关异常 ====================

class AuthenticationError(AShareBaseException):
    """认证失败"""

    def __init__(self, reason: str = "Authentication failed"):
        super().__init__(
            message=reason,
            code="AUTHENTICATION_ERROR"
        )


class AuthorizationError(AShareBaseException):
    """授权失败（权限不足）"""

    def __init__(self, resource: str, action: str):
        super().__init__(
            message=f"Not authorized to {action} {resource}",
            code="AUTHORIZATION_ERROR",
            details={"resource": resource, "action": action}
        )


# ==================== 服务相关异常 ====================

class ServiceUnavailableError(AShareBaseException):
    """服务不可用"""

    def __init__(self, service: str, reason: str):
        super().__init__(
            message=f"Service {service} is unavailable: {reason}",
            code="SERVICE_UNAVAILABLE",
            details={"service": service, "reason": reason}
        )


class OperationTimeoutError(AShareBaseException):
    """操作超时"""

    def __init__(self, operation: str, timeout: float):
        super().__init__(
            message=f"Operation {operation} timed out after {timeout}s",
            code="TIMEOUT_ERROR",
            details={"operation": operation, "timeout": timeout}
        )
