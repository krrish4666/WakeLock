import asyncio
import datetime
from app.core.database import AsyncSessionLocal
from app.services.verification import VerificationService

async def trace_otp_crash():
    try:
        telegram_id = 718305018  # using any id
        async with AsyncSessionLocal() as db:
            result = await VerificationService.verify_user_otp(db, telegram_id, "174037")
            print("RESULT:", result)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(trace_otp_crash())
