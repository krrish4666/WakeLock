from celery import shared_task
from datetime import datetime, timedelta
import asyncio

from app.core.database import AsyncSessionLocal
from app.models.plan import AccountabilityPlan, PlanStatus, WakeSession, SessionStatus
from app.bot import send_alert
from app.services.otp import OTPService

@shared_task
def process_due_alarms():
    """ Runs every minute via Celery Beat to find active plans with alarms due right now. """
    asyncio.run(_process_due_alarms_async())

async def _process_due_alarms_async():
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, and_
        from app.models.user import UserPreference
        from zoneinfo import ZoneInfo
        
        # Fetch all active plans and their associated preferences
        result = await db.execute(
            select(AccountabilityPlan, UserPreference).join(
                UserPreference, AccountabilityPlan.user_id == UserPreference.user_id
            ).where(AccountabilityPlan.status == PlanStatus.ACTIVE)
        )
        active_plans = result.all()
        
        processed_user_ids = set()
        
        for plan, pref in active_plans:
            # Prevent duplicate alarms if user has multiple overlapping plans
            if plan.user_id in processed_user_ids:
                continue
                
            # Evaluate current time in user's specific timezone
            user_tz = ZoneInfo(pref.timezone or "Asia/Kolkata")
            user_now = datetime.now(user_tz)
            user_current_time = user_now.time().replace(second=0, microsecond=0)
            
            # Determine correct alarm time based on user's local day
            is_weekend = user_now.weekday() >= 5 # 5=Sat, 6=Sun
            assigned_alarm = pref.weekend_alarm_time if (is_weekend and pref.weekend_alarm_time) else pref.default_alarm_time
            
            if assigned_alarm != user_current_time:
                continue
                
            # Check if record already exists for user's today to ensure idempotency
            today = user_now.date()
            record_exists = await db.execute(
                select(WakeSession).where(
                    and_(
                        WakeSession.plan_id == plan.id,
                        WakeSession.date == today
                    )
                )
            )
            if record_exists.scalars().first():
                continue # Already processed
                
            processed_user_ids.add(plan.user_id)
            
            # Create Pending Record
            record = WakeSession(
                plan_id=plan.id,
                date=today,
                status=SessionStatus.PENDING
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            
            # Send initial wakeup alert
            buffer_mins = pref.buffer_duration_minutes
            window_mins = pref.otp_window_duration_minutes
            msg = f"🚨 WAKE UP! Your alarm for {user_current_time.strftime('%H:%M')} is ringing! An OTP will drop during a {window_mins}-min window AFTER your {buffer_mins}-min buffer. STAY ALERT!"
            await send_alert(plan.user_id, msg)
            
            # Calculate Randomized Drop Time
            import random
            random_window_delay = random.randint(0, window_mins * 60)
            total_delay_seconds = (buffer_mins * 60) + random_window_delay
            
            # Schedule the drop dynamically using celery countdown (safe from timezone mismatches)
            drop_random_otp.apply_async(args=[record.id, plan.user_id], countdown=total_delay_seconds)
        
@shared_task
def drop_random_otp(attendance_id: int, user_id: int):
    """ Triggered randomly inside the buffer window to drop the OTP. """
    asyncio.run(_drop_random_otp_async(attendance_id, user_id))

async def _drop_random_otp_async(attendance_id: int, user_id: int):
    # Generate OTP
    otp_code = OTPService.generate_code()
    
    # Store in Redis and persist hash in PostgreSQL
    async with AsyncSessionLocal() as db:
        await OTPService.store_otp(db, attendance_id, otp_code, ttl_minutes=2)
    
    # Send via Bot
    message = (
        f"🚨 WAKELOCK OTP DROP 🚨\n\n"
        f"Your code is: {otp_code}\n\n"
        f"You have exactly 2 MINUTES to reply to this bot with the code to save your penalty!"
    )
    await send_alert(user_id, message)
    
    # Schedule automated expiry check exactly 2 minutes (120 seconds) later
    process_expired_otp.apply_async(args=[attendance_id, user_id], countdown=120)

@shared_task
def process_expired_otp(attendance_id: int, user_id: int):
    """ Triggered exactly 2 minutes after OTP drop to check if user verified in time. """
    asyncio.run(_process_expired_otp_async(attendance_id, user_id))

async def _process_expired_otp_async(attendance_id: int, user_id: int):
    async with AsyncSessionLocal() as db:
        from app.services.verification import VerificationService
        failed = await VerificationService.process_session_failure(db, attendance_id)
        if failed:
            record = await db.get(WakeSession, attendance_id)
            plan = await db.get(AccountabilityPlan, record.plan_id) if record else None
            penalty = plan.per_day_penalty if plan else "your daily penalty"
            message = (
                f"❌ WAKELOCK FAILED ❌\n\n"
                f"Your 2-minute OTP window expired without verification!\n"
                f"A penalty of Rs. {penalty} has been deducted from your locked balance."
            )
            try:
                await send_alert(user_id, message)
            except Exception as e:
                print(f"[WARN] Could not send Telegram alert to {user_id}: {e}")

@shared_task
def check_completed_plans():
    """ Daily cron task to sweep and complete finished plans. """
    asyncio.run(_check_completed_plans_async())

async def _check_completed_plans_async():
    async with AsyncSessionLocal() as db:
        from app.services.plan import PlanService
        await PlanService.process_completed_plans(db)
