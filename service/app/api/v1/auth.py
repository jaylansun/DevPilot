from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.config import get_settings
from app.database import get_db_session
from app.errors import ApiError
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.security import create_access_token
from app.services.auth import UsernameAlreadyExistsError, authenticate_user, register_user


router = APIRouter(prefix="/auth", tags=["认证"])
settings = get_settings()
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/me", response_model=UserResponse, summary="获取当前用户")
async def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="注册普通用户",
)
async def register(payload: RegisterRequest, session: DatabaseSession) -> UserResponse:
    try:
        user = await register_user(session, payload.username, payload.password)
    except UsernameAlreadyExistsError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="username_exists",
            message="用户名已存在",
        ) from exc

    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(payload: LoginRequest, session: DatabaseSession) -> TokenResponse:
    user = await authenticate_user(session, payload.username, payload.password)
    if user is None:
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
            message="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )
