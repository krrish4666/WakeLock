import secrets
import string
from redis.asyncio import Redis
from app.core.config import settings

class OTPService:
    @staticmethod
    def generate_code(length: int = 6) -> str:
        """Cryptographically secure numeric OTP."""
        return "".join(secrets.choice(string.digits) for _ in range(length))

    @staticmethod
    async def store_otp(attendance_id: int, otp_code: str, ttl_minutes: int = 2) -> None:
        """Stores OTP in Redis with an exact TTL pipeline."""
        async with Redis.from_url(settings.REDIS_URL, decode_responses=True) as client:
            key = f"wakelock:otp:{attendance_id}"
            await client.setex(key, ttl_minutes * 60, otp_code)

    @staticmethod
    async def verify_otp(attendance_id: int, provided_code: str) -> bool:
        """Validates the OTP and deletes it on success (single-use)."""
        async with Redis.from_url(settings.REDIS_URL, decode_responses=True) as client:
            key = f"wakelock:otp:{attendance_id}"
            expected_code = await client.get(key)
            
            if expected_code and expected_code == provided_code:
                await client.delete(key) # Invalidate immediately
                return True
                
            return False
