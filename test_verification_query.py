import asyncio
import datetime
from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal
from app.models.plan import AccountabilityPlan, AttendanceRecord, PlanStatus, AttendanceStatus
from app.models.user import User

async def debug_query():
    telegram_id = 1150153975
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(AccountabilityPlan).where(
            and_(AccountabilityPlan.user_id == telegram_id, AccountabilityPlan.status == PlanStatus.ACTIVE)
        ))
        active_plans = res.scalars().all()
        print(f"Active plans: {[p.id for p in active_plans]}")
        
        today = datetime.date.today()
        today_start = datetime.datetime.combine(today, datetime.time.min)
        print(f"Today is: {today_start}")
        
        for plan in active_plans:
            res = await db.execute(select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.plan_id == plan.id,
                    AttendanceRecord.date == today_start,
                    AttendanceRecord.status == AttendanceStatus.PENDING
                )
            ))
            found = res.scalars().first()
            if found:
                print(f"FOUND PENDING RECORD: {found.id} for plan {plan.id}")
        
asyncio.run(debug_query())
