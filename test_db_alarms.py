import asyncio
from datetime import datetime
from app.core.database import AsyncSessionLocal
from app.models.plan import AccountabilityPlan, PlanStatus
from app.models.user import UserPreference

async def diagnose_alarms():
    now = datetime.now()
    current_time = now.time().replace(second=0, microsecond=0)
    print(f"Current System Time: {now}")
    print(f"Target matching time: {current_time}")

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        
        # 1. Check all active plans
        result = await db.execute(
            select(AccountabilityPlan, UserPreference).join(
                UserPreference, AccountabilityPlan.user_id == UserPreference.user_id
            ).where(AccountabilityPlan.status == PlanStatus.ACTIVE)
        )
        active_plans = result.all()
        print(f"Found {len(active_plans)} Active Plans.")
        
        for plan, pref in active_plans:
            print(f"  Plan ID: {plan.id}, User ID: {plan.user_id}")
            print(f"  Pref ID: {pref.id}, Default Alarm: {pref.default_alarm_time}, Weekend Alarm: {pref.weekend_alarm_time}")
            
            is_weekend = now.weekday() >= 5
            assigned_alarm = pref.weekend_alarm_time if (is_weekend and pref.weekend_alarm_time) else pref.default_alarm_time
            
            print(f"  Calculated Assigned Alarm for today: {assigned_alarm}")
            print(f"  Matches current time? {assigned_alarm == current_time}")

asyncio.run(diagnose_alarms())
