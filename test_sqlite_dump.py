import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.plan import AccountabilityPlan, AttendanceRecord
from app.models.user import User

async def investigate_db():
    async with AsyncSessionLocal() as db:
        print("====== ACTIVE PLANS ======")
        res = await db.execute(select(AccountabilityPlan))
        plans = res.scalars().all()
        for p in plans:
            print(f"Plan ID: {p.id}, User ID: {p.user_id}, Status: {p.status}, Alarm: {p.alarm_time}")
            
        print("\n====== ATTENDANCE RECORDS ======")
        res = await db.execute(select(AttendanceRecord))
        records = res.scalars().all()
        for r in records:
            print(f"Record ID: {r.id}, Plan ID: {r.plan_id}, Date: {r.date}, Status: {r.status}")
            
asyncio.run(investigate_db())
