from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.config import get_settings
from app.database import get_db_session
from app.errors import ApiError
from app.schemas.auth_qo import LoginQO
from app.schemas.auth_vo import TokenVO, UserVO
from app.security import create_access_token
from app.services.auth_service import authenticate_user


router = APIRouter(tags=["认证"])
settings = get_settings()
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/me", response_model=UserVO, summary="获取当前用户")
async def get_me(current_user: CurrentUser) -> UserVO:
    return UserVO.model_validate(current_user)


@router.post("/auth/token", response_model=TokenVO, summary="用户登录")
async def login(payload: LoginQO, session: DatabaseSession) -> TokenVO:
    user = await authenticate_user(session, payload.username, payload.password)
    if user is None:
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
            message="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenVO(
        access_token=create_access_token(user.id),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserVO.model_validate(user),
    )
