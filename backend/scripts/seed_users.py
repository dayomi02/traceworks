"""예시 계정 생성 스크립트 (PM, 기획자, 개발자)

실행:
    cd backend
    uv run python scripts/seed_users.py
"""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.core.services.auth_service import hash_password
from app.db.models import User

SAMPLE_USERS = [
    {"name": "홍길동", "email": "pm@traceworks.com",      "password": "traceworks1!", "role": "pm"},
    {"name": "이수연", "email": "planner@traceworks.com", "password": "traceworks1!", "role": "planner"},
    {"name": "김철수", "email": "dev@traceworks.com",     "password": "traceworks1!", "role": "developer"},
]


async def seed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    # 테이블은 이미 DB에 존재하므로 create_all 생략
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        for u in SAMPLE_USERS:
            result = await session.execute(select(User).where(User.email == u["email"]))
            existing = result.scalar_one_or_none()
            if existing:
                print(f"[SKIP] {u['email']} - 이미 존재")
                continue
            user = User(
                id=str(uuid.uuid4()),
                email=u["email"],
                password_hash=hash_password(u["password"]),
                name=u["name"],
                role=u["role"],
                is_active=True,
            )
            session.add(user)
            print(f"[CREATE] {u['role']:10s} | {u['name']} | {u['email']}")
        await session.commit()

    await engine.dispose()
    print("\n✓ seed 완료")


if __name__ == "__main__":
    asyncio.run(seed())
