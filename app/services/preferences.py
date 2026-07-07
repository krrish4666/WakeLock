from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import time

from app.models.user import UserPreference

class PreferencesService:
    @staticmethod
    async def get_or_create_preferences(db: AsyncSession, telegram_id: int) -> UserPreference:
        result = await db.execute(select(UserPreference).where(UserPreference.user_id == telegram_id))
        pref = result.scalar_one_or_none()
        
        if not pref:
            pref = UserPreference(user_id=telegram_id)
            db.add(pref)
            await db.commit()
            await db.refresh(pref)
            
        return pref

    @staticmethod
    async def set_alarm(db: AsyncSession, telegram_id: int, alarm_time: time) -> str:
        pref = await PreferencesService.get_or_create_preferences(db, telegram_id)
        pref.default_alarm_time = alarm_time
        await db.commit()
        return f"Alarm successfully set to {alarm_time.strftime('%H:%M')}."

    @staticmethod
    async def set_buffer(db: AsyncSession, telegram_id: int, buffer_minutes: int) -> str:
        if buffer_minutes < 0 or buffer_minutes > 120:
            return "Buffer must be between 0 and 120 minutes."
            
        pref = await PreferencesService.get_or_create_preferences(db, telegram_id)
        pref.buffer_duration_minutes = buffer_minutes
        await db.commit()
        return f"Buffer duration successfully set to {buffer_minutes} minutes."
