from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from src.config import get_settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    """验证 API Key。若 settings.api_key 为空则跳过验证（开发模式）。"""
    settings = get_settings()
    if not settings.api_key:
        return  # 未配置 key = 允许所有请求（开发模式）
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
