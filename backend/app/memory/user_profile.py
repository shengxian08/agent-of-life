"""
用户画像 - 从 SQLite 读写，唯一数据源
"""
from __future__ import annotations

from typing import Any

from ..models.schemas import UserProfile
from ..models.database import get_db, User
from sqlalchemy import select


class UserProfileManager:
    """用户画像管理 — SQLite 读写"""

    async def get_profile(self, user_id: str) -> UserProfile | None:
        """从 SQLite 读取用户画像"""
        try:
            async for session in get_db():
                result = await session.execute(
                    select(User).where(User.user_id == user_id)
                )
                row = result.scalars().first()
                if row:
                    return UserProfile(
                        user_id=row.user_id,
                        name=row.name,
                        family_size=row.family_size,
                        dietary_preferences=row.dietary_preferences or [],
                        allergies=row.allergies or [],
                        disliked_foods=row.disliked_foods or [],
                        budget_monthly=row.budget_monthly or 3000,
                        preferred_supermarkets=row.preferred_supermarkets or [],
                        city=row.city or "北京",
                        location=row.location or "朝阳区",
                    )
        except Exception:
            pass
        return None

    async def get_or_create(self, user_id: str, name: str = "") -> UserProfile:
        """获取或创建用户"""
        profile = await self.get_profile(user_id)
        if profile:
            return profile
        try:
            async for session in get_db():
                session.add(User(
                    user_id=user_id,
                    name=name or f"用户{user_id[-4:]}",
                ))
                await session.commit()
        except Exception:
            pass
        return UserProfile(user_id=user_id, name=name or f"用户{user_id[-4:]}")

    async def update_preferences(
        self, user_id: str, preferences: list[str] | None = None,
        allergies: list[str] | None = None, disliked: list[str] | None = None,
    ) -> UserProfile | None:
        """更新用户偏好 → 写回 SQLite"""
        try:
            async for session in get_db():
                result = await session.execute(
                    select(User).where(User.user_id == user_id)
                )
                row = result.scalars().first()
                if not row:
                    return None
                if preferences:
                    row.dietary_preferences = list(set((row.dietary_preferences or []) + preferences))
                if allergies:
                    row.allergies = list(set((row.allergies or []) + allergies))
                if disliked:
                    row.disliked_foods = list(set((row.disliked_foods or []) + disliked))
                await session.commit()
                return await self.get_profile(user_id)
        except Exception:
            return None


_profile_manager: UserProfileManager | None = None


def get_profile_manager() -> UserProfileManager:
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = UserProfileManager()
    return _profile_manager
