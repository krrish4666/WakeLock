import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def refresh_env():
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(text("DROP TABLE IF EXISTS wake_sessions;"))
            await db.execute(text("""
            CREATE TABLE IF NOT EXISTS attendance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                date DATETIME NOT NULL,
                status VARCHAR(10),
                processed_flag BOOLEAN,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """))
            await db.commit()
            print("Successfully refreshed pristine state.")
        except Exception as e:
            print(f"Error resetting: {e}")

asyncio.run(refresh_env())
