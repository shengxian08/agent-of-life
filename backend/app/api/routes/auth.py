"""
认证路由 v5.2 — JWT 注册/登录/刷新 + 用户信息
"""
import uuid
import bcrypt
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from loguru import logger

from sqlalchemy import select

from ...config import settings
from ...models.schemas import (
    LoginRequest, RegisterRequest, TokenResponse, UserProfile,
)
from ...models.database import get_db, User

router = APIRouter(prefix="/auth", tags=["Auth"])

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload if payload.get("type") == "access" else None
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
) -> str:
    """获取当前用户ID。优先JWT，降级X-User-ID（兼容旧版）。"""
    if credentials and credentials.credentials:
        payload = verify_token(credentials.credentials)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                return user_id
    if x_user_id:
        return x_user_id
    return "user_001"


async def get_current_user_strict(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """严格认证 — 无有效JWT直接401"""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效认证")
    return user_id


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    async for session in get_db():
        result = await session.execute(select(User).where(User.email == req.email))
        if result.scalars().first():
            raise HTTPException(status_code=409, detail="该邮箱已注册")
        user = User(
            user_id=user_id, name=req.name, email=req.email,
            password_hash=hash_password(req.password),
            family_size=req.family_size, created_at=datetime.now(),
        )
        session.add(user)
        await session.commit()
    access_token = create_access_token({"sub": user_id, "name": req.name})
    logger.success(f"New user registered: {req.email} → {user_id}")
    return TokenResponse(access_token=access_token, user_id=user_id, name=req.name, expires_in=settings.jwt_expire_minutes * 60)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    identifier = req.email or req.username
    if not identifier:
        raise HTTPException(status_code=400, detail="请输入邮箱或用户名")
    async for session in get_db():
        result = await session.execute(
            select(User).where((User.email == identifier) | (User.name == identifier) | (User.user_id == identifier))
        )
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=401, detail="账号或密码错误")
        if not user.password_hash:
            user.password_hash = hash_password(req.password)
            await session.commit()
        elif not verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="账号或密码错误")
        user.last_login = datetime.now()
        await session.commit()
        access_token = create_access_token({"sub": user.user_id, "name": user.name})
        return TokenResponse(access_token=access_token, user_id=user.user_id, name=user.name, expires_in=settings.jwt_expire_minutes * 60)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(user_id: str = Depends(get_current_user_strict)):
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalars().first()
        if not user: raise HTTPException(status_code=404, detail="用户不存在")
        access_token = create_access_token({"sub": user_id, "name": user.name})
        return TokenResponse(access_token=access_token, user_id=user_id, name=user.name, expires_in=settings.jwt_expire_minutes * 60)


@router.get("/me", response_model=UserProfile)
async def get_me(user_id: str = Depends(get_current_user)):
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalars().first()
        if not user: raise HTTPException(status_code=404, detail="用户不存在")
        return UserProfile(
            user_id=user.user_id, name=user.name, family_size=user.family_size,
            dietary_preferences=user.dietary_preferences or [], allergies=user.allergies or [],
            disliked_foods=user.disliked_foods or [], budget_monthly=user.budget_monthly or 3000,
            preferred_supermarkets=user.preferred_supermarkets or [],
            city=user.city or "北京", location=user.location or "朝阳区",
        )
