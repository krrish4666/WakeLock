import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def cleanup_db():
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(text("DROP TABLE wake_sessions;"))
            await db.commit()
            print("Successfully dropped orphaned wake_sessions table.")
        except Exception as e:
            print(f"Error dropping table: {e}")

asyncio.run(cleanup_db())
