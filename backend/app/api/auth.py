from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.services.auth_service import authenticate, create_access_token
from app.db.models import User
from app.db.postgres import get_db as get_session
from app.schemas.auth import LoginRequest, TokenResponse, UserMe

router = APIRouter(prefix="/auth", tags=["인증"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_session)):
    """
    **[로그인 페이지]** 이메일/비밀번호로 로그인하여 JWT 토큰을 발급합니다.

    - 발급된 `access_token`을 이후 모든 인증 필요 API의 `Authorization: Bearer <token>` 헤더에 사용합니다.
    - 테스트 계정: `pm@traceworks.com` / `planner@traceworks.com` / `dev@traceworks.com` (비밀번호: `traceworks1!`)
    """
    user = await authenticate(body.email, body.password, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user_id=user.id, name=user.name, role=user.role)


@router.get("/me", response_model=UserMe)
async def me(current_user: User = Depends(get_current_user)):
    """
    **[공통 - 헤더/GNB]** 현재 로그인한 사용자 정보를 반환합니다.

    - 페이지 최초 진입 시 사용자 이름·역할을 표시하기 위해 호출합니다.
    - `role` 값에 따라 메뉴 접근 권한을 분기할 수 있습니다. (`pm` / `planner` / `developer`)
    """
    return UserMe(
        user_id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
        is_active=current_user.is_active,
    )
