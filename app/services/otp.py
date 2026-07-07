import secrets
import string
import hashlib
from datetime import datetime, timedelta
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.plan import OTPToken

class OTPService:
    @staticmethod
    def generate_code(length: int = 6) -> str:
        """Cryptographically secure numeric OTP."""
        return "".join(secrets.choice(string.digits) for _ in range(length))

    @staticmethod
    async def store_otp(db: AsyncSession, attendance_id: int, otp_code: str, ttl_minutes: int = 2) -> None:
        """Stores OTP in Redis and persists SHA-256 hash in PostgreSQL OTPToken table."""
        async with Redis.from_url(settings.REDIS_URL, decode_responses=True) as client:
            key = f"wakelock:otp:{attendance_id}"
            await client.setex(key, ttl_minutes * 60, otp_code)
            
        token_hash = hashlib.sha256(otp_code.encode("utf-8")).hexdigest()
        now = datetime.now()
        expires_at = now + timedelta(minutes=ttl_minutes)
        
        stmt = select(OTPToken).where(OTPToken.session_id == attendance_id)
        res = await db.execute(stmt)
        token_entry = res.scalars().first()
        
        if token_entry:
            token_entry.token_hash = token_hash
            token_entry.drop_time = now
            token_entry.expires_at = expires_at
            token_entry.is_used = False
        else:
            token_entry = OTPToken(
                session_id=attendance_id,
                token_hash=token_hash,
                drop_time=now,
                expires_at=expires_at,
                is_used=False
            )
            db.add(token_entry)
        await db.commit()

    @staticmethod
    async def verify_otp(db: AsyncSession, attendance_id: int, provided_code: str) -> bool:
        """Validates against PostgreSQL hash and Redis TTL, marking token as used on success."""
        stmt = select(OTPToken).where(OTPToken.session_id == attendance_id)
        res = await db.execute(stmt)
        token_entry = res.scalars().first()
        
        if not token_entry or token_entry.is_used:
            return False
            
        provided_hash = hashlib.sha256(provided_code.encode("utf-8")).hexdigest()
        if provided_hash != token_entry.token_hash:
            return False
            
        async with Redis.from_url(settings.REDIS_URL, decode_responses=True) as client:
            key = f"wakelock:otp:{attendance_id}"
            expected_code = await client.get(key)
            if not expected_code or expected_code != provided_code:
                return False
            await client.delete(key) # Invalidate immediately in Redis
            
        token_entry.is_used = True
        await db.commit()
        return True
