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
import random
import time
import base64
import io
import string

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from sqlalchemy import select

from ...config import settings
from ...models.schemas import (
    LoginRequest, RegisterRequest, TokenResponse, UserProfile,
)
from ...models.database import get_db, User

router = APIRouter(prefix="/auth", tags=["Auth"])

security = HTTPBearer(auto_error=False)

# 验证码缓存：{captcha_id: {"answer": "A3B7", "expires": timestamp}}
_captcha_store: dict[str, dict] = {}


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


def _clean_expired_captchas():
    """清理过期验证码"""
    now = time.time()
    expired = [k for k, v in _captcha_store.items() if v["expires"] < now]
    for k in expired:
        del _captcha_store[k]


def _generate_captcha_image(text: str) -> str:
    """生成图形验证码，返回 base64 图片"""
    w, h = 140, 50
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 噪点
    for _ in range(200):
        x, y = random.randint(0, w - 1), random.randint(0, h - 1)
        draw.point((x, y), fill=(random.randint(160, 220), random.randint(160, 220), random.randint(160, 220)))

    # 干扰线
    for _ in range(4):
        x1, y1 = random.randint(0, w // 3), random.randint(0, h)
        x2, y2 = random.randint(w * 2 // 3, w), random.randint(0, h)
        draw.line((x1, y1, x2, y2), fill=(random.randint(180, 220), random.randint(180, 220), random.randint(180, 220)), width=2)

    # 尝试用系统字体，找不到就用默认
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        try:
            font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 32)
        except Exception:
            font = ImageFont.load_default()

    # 逐字绘制，每个字颜色、角度不同
    for i, ch in enumerate(text):
        x = 15 + i * 30 + random.randint(-3, 3)
        y = random.randint(2, 10)
        color = (random.randint(0, 100), random.randint(0, 100), random.randint(150, 255))
        # 单个字符旋转
        char_img = Image.new("RGBA", (40, 45), (255, 255, 255, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_draw.text((5, 0), ch, font=font, fill=color)
        char_img = char_img.rotate(random.randint(-25, 25), expand=False, fillcolor=(255, 255, 255, 0))
        img.paste(char_img, (x, y), char_img)

    # 模糊
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@router.get("/captcha")
async def get_captcha():
    """获取图形验证码"""
    _clean_expired_captchas()
    # 生成4位随机字符（去掉容易混淆的 0O1Il）
    chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    code = "".join(random.choice(chars) for _ in range(4))

    captcha_id = f"cap_{random.randint(100000, 999999)}"
    _captcha_store[captcha_id] = {"answer": code, "expires": time.time() + 300}

    img_b64 = _generate_captcha_image(code)
    return {"captcha_id": captcha_id, "image": f"data:image/png;base64,{img_b64}"}


def verify_captcha(captcha_id: str, answer: str) -> bool:
    """验证图形验证码（不区分大小写）"""
    _clean_expired_captchas()
    data = _captcha_store.pop(captcha_id, None)
    if not data:
        return False
    return data["answer"].upper() == answer.strip().upper()


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    if not verify_captcha(req.captcha_id, req.captcha_answer):
        raise HTTPException(status_code=400, detail="验证码错误")
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


async def require_admin(
    user_id: str = Depends(get_current_user),
) -> str:
    """验证当前用户是否为管理员"""
    if user_id != settings.admin_user_id:
        raise HTTPException(status_code=403, detail="无权操作：仅管理员可用")
    return user_id


@router.post("/admin/reset-password")
async def admin_reset_password(user_id: str, new_password: str, admin: str = Depends(require_admin)):
    """管理员重置用户密码"""
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6位")
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        user.password_hash = hash_password(new_password)
        await session.commit()
        logger.warning(f"Admin reset password for {user_id} ({user.name})")
        return {"status": "ok", "user_id": user_id, "name": user.name, "new_password": new_password}


@router.get("/admin/users")
async def admin_list_users(admin: str = Depends(require_admin)):
    """管理员查看所有用户详细信息（含邮箱、注册时间、最后登录）"""
    async for session in get_db():
        result = await session.execute(select(User))
        users = result.scalars().all()
        return {
            "total": len(users),
            "users": [
                {
                    "user_id": u.user_id,
                    "name": u.name,
                    "email": u.email,
                    "family_size": u.family_size,
                    "dietary_preferences": u.dietary_preferences,
                    "allergies": u.allergies,
                    "disliked_foods": u.disliked_foods,
                    "budget_monthly": u.budget_monthly,
                    "city": u.city,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "last_login": u.last_login.isoformat() if u.last_login else None,
                }
                for u in users
            ],
        }
