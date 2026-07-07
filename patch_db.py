import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def patch_db():
    async with AsyncSessionLocal() as db:
        try:
            # Recreate the ghost table so SQLAlchemy reflection doesn't crash
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
            await db.execute(text("DROP TABLE IF EXISTS wake_sessions;"))
            await db.commit()
            print("Successfully injected ghost attendance_records table.")
        except Exception as e:
            print(f"Error patching db: {e}")

asyncio.run(patch_db())
