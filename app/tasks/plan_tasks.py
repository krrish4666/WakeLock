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
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Number of active plans returned by the query: {len(active_plans)}")
        
        processed_user_ids = set()
        
        for plan, pref in active_plans:
            try:
                logger.info(f"Processing plan: plan.id={plan.id}, plan.user_id={plan.user_id}, plan.status={plan.status}")
                logger.info(f"User preference values: default_alarm_time={pref.default_alarm_time}, weekend_alarm_time={pref.weekend_alarm_time}, timezone={pref.timezone}, buffer_duration_minutes={pref.buffer_duration_minutes}, otp_window_duration_minutes={pref.otp_window_duration_minutes}")
                
                # Prevent duplicate alarms if user has multiple overlapping plans
                if plan.user_id in processed_user_ids:
                    logger.info(
                        f"ALARM SKIPPED: user_id={plan.user_id} already processed in this sweep"
                    )
                    continue
                    
                # Evaluate current time in user's specific timezone
                user_tz = ZoneInfo(pref.timezone or "Asia/Kolkata")
                user_now = datetime.now(user_tz)
                user_current_time = user_now.time().replace(second=0, microsecond=0)
                
                # Determine correct alarm time based on user's local day
                is_weekend = user_now.weekday() >= 5 # 5=Sat, 6=Sun
                assigned_alarm = pref.weekend_alarm_time if (is_weekend and pref.weekend_alarm_time) else pref.default_alarm_time
                
                logger.info(f"Computed local time: user_now={user_now}, user_current_time={user_current_time}, user_now.date()={user_now.date()}, is_weekend={is_weekend}")
                logger.info(f"Selected assigned_alarm: {assigned_alarm}")
                logger.info(f"ALARM CHECK: assigned_alarm={assigned_alarm} current_time={user_current_time} MATCH={assigned_alarm == user_current_time}")
                
                if assigned_alarm != user_current_time:
                    logger.info("ALARM SKIPPED: time mismatch")
                    continue
                    
                logger.info("ALARM MATCHED: proceeding to WakeSession lookup")
                
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
                existing_session = record_exists.scalars().first()
                logger.info(f"WakeSession lookup: already exists={existing_session is not None}, existing session ID={existing_session.id if existing_session else None}, existing session status={existing_session.status if existing_session else None}")
                if existing_session:
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
                
                logger.info(f"WAKE SESSION CREATED: id={record.id}")
                
                # Send initial wakeup alert
                buffer_mins = pref.buffer_duration_minutes
                window_mins = pref.otp_window_duration_minutes
                msg = f"🚨 WAKE UP! Your alarm for {user_current_time.strftime('%H:%M')} is ringing! An OTP will drop during a {window_mins}-min window AFTER your {buffer_mins}-min buffer. STAY ALERT!"
                
                logger.info(f"ABOUT TO SEND WAKE-UP ALERT: user_id={plan.user_id}")
                await send_alert(plan.user_id, msg)
                logger.info(f"WAKE-UP ALERT SENT: user_id={plan.user_id}")
                
                # Calculate Randomized Drop Time
                import random
                random_window_delay = random.randint(0, window_mins * 60)
                total_delay_seconds = (buffer_mins * 60) + random_window_delay
                
                # Store the absolute future time in PostgreSQL
                drop_time = user_now + timedelta(seconds=total_delay_seconds)
                record.scheduled_otp_drop_time = drop_time
                await db.commit()
            except Exception as e:
                logger.exception(f"Exception occurred during processing for plan.id={plan.id}")
            
        # Sweep for pending scheduled OTP drops
        from app.models.plan import OTPToken
        from sqlalchemy import func
        due_otps = await db.execute(
            select(WakeSession, AccountabilityPlan)
            .join(AccountabilityPlan, WakeSession.plan_id == AccountabilityPlan.id)
            .outerjoin(OTPToken, WakeSession.id == OTPToken.session_id)
            .where(
                and_(
                    AccountabilityPlan.status == PlanStatus.ACTIVE,
                    WakeSession.scheduled_otp_drop_time <= func.now(),
                    WakeSession.status == SessionStatus.PENDING,
                    OTPToken.id.is_(None)
                )
            )
        )
        
        for session, plan in due_otps.all():
            otp_code = OTPService.generate_code()
            
            # Store the expiry time for the sweep BEFORE storing OTP so it commits together
            from datetime import timezone
            session.otp_expiry_time = datetime.now(timezone.utc) + timedelta(minutes=2)
            
            await OTPService.store_otp(db, session.id, otp_code, ttl_minutes=2)
            
            message = (
                f"🚨 WAKELOCK OTP DROP 🚨\n\n"
                f"Your code is: {otp_code}\n\n"
                f"You have exactly 2 MINUTES to reply to this bot with the code to save your penalty!"
            )
            try:
                await send_alert(plan.user_id, message)
            except Exception as e:
                print(f"[ERROR] Failed to send Telegram alert for OTP drop to {plan.user_id}: {e}")
            
        # Sweep for pending expired OTPs
        expired_sessions = await db.execute(
            select(WakeSession).where(
                and_(
                    WakeSession.otp_expiry_time <= func.now(),
                    WakeSession.status == SessionStatus.PENDING,
                    WakeSession.processed_flag == False
                )
            )
        )
        
        for record in expired_sessions.scalars().all():
            from app.services.verification import VerificationService
            failed = await VerificationService.process_session_failure(db, record.id)
            if failed:
                plan = await db.get(AccountabilityPlan, record.plan_id)
                penalty = plan.per_day_penalty if plan else "your daily penalty"
                message = (
                    f"❌ WAKELOCK FAILED ❌\n\n"
                    f"Your 2-minute OTP window expired without verification!\n"
                    f"A penalty of Rs. {penalty} has been deducted from your locked balance."
                )
                try:
                    await send_alert(plan.user_id, message)
                except Exception as e:
                    print(f"[WARN] Could not send Telegram alert for failed session {record.id}: {e}")

@shared_task
def check_completed_plans():
    """ Daily cron task to sweep and complete finished plans. """
    asyncio.run(_check_completed_plans_async())

async def _check_completed_plans_async():
    async with AsyncSessionLocal() as db:
        from app.services.plan import PlanService
        await PlanService.process_completed_plans(db)

