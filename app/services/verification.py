import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.user import User
from app.models.plan import AccountabilityPlan, PlanStatus, WakeSession, SessionStatus
from app.services.otp import OTPService
from app.services.wallet import WalletService

class VerificationService:
    @staticmethod
    async def verify_user_otp(db: AsyncSession, telegram_id: int, otp_code: str) -> str:
        """
        Validates an OTP sent by the user against their active attendance record for today.
        """
        # Find user
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            return "User not found. Start a plan first."

        # Find ALL active plans for the user
        result = await db.execute(
            select(AccountabilityPlan).where(
                and_(
                    AccountabilityPlan.user_id == user.telegram_id,
                    AccountabilityPlan.status == PlanStatus.ACTIVE
                )
            )
        )
        active_plans = result.scalars().all()
        
        if not active_plans:
            return "No active OTP request found for today. Your alarm hasn't dropped a code yet, or it was already verified/failed."
            
        # Find today's AttendanceRecord (Pending) across ANY of the active plans
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time()) # Match SQLite DateTime format

        pending_records = []
        for plan in active_plans:
            records = await db.execute(
                select(WakeSession).where(
                    and_(
                        WakeSession.plan_id == plan.id,
                        WakeSession.date == today_start,
                        WakeSession.status == SessionStatus.PENDING
                    )
                )
            )
            # Add all pending records for this user's active plans
            pending_records.extend(records.scalars().all())

        if not pending_records:
            return "No active OTP request found for today. Your alarm hasn't dropped a code yet, or it was already verified/failed."
            
        # Dynamically test ALL pending records
        for rec in pending_records:
            is_valid = await OTPService.verify_otp(db, rec.id, otp_code)
            if is_valid:
                # Mark Success
                rec.status = SessionStatus.VERIFIED
                rec.processed_flag = True
                plan = await db.get(AccountabilityPlan, rec.plan_id)
                plan.days_verified += 1
                from app.services.plan import PlanService
                await PlanService.evaluate_plan_status(db, plan)
                await db.commit()
                return "[SUCCESS] verified!! You woke up on time. Your funds are safe today."
                    
        # If no pending record accepted the OTP code:
        return "[ERROR] Invalid or Expired OTP! If it expired, the penalty will be applied."

    @staticmethod
    async def process_session_failure(db: AsyncSession, session_id: int) -> bool:
        """
        Marks a specific WakeSession as FAILED if it is still unverified/pending, and applies the daily penalty.
        Idempotent via processed_flag and status check.
        """
        record = await db.get(WakeSession, session_id)
        if not record or record.status != SessionStatus.PENDING or record.processed_flag:
            return False
            
        record.status = SessionStatus.FAILED
        record.processed_flag = True
        
        plan = await db.get(AccountabilityPlan, record.plan_id)
        if plan:
            await WalletService.apply_penalty(db, plan.user_id, plan.id, plan.per_day_penalty)
            
        await db.commit()
        return True

    @staticmethod
    async def process_penalties(db: AsyncSession, date: datetime.date):
        """
        Sweep all PENDING records for a given date, mark them FAILED, and apply wallet penalties.
        Called via Celery after the buffer window ends.
        """
        # Fetch the actual pending records from the database
        pending_records = await db.execute(
            select(WakeSession).where(
                and_(
                    WakeSession.date == date,
                    WakeSession.status == SessionStatus.PENDING
                )
            )
        )
        
        for record in pending_records.scalars().all():
            record.status = SessionStatus.FAILED
            record.processed_flag = True
            
            # Fetch plan to get penalty
            plan = await db.get(AccountabilityPlan, record.plan_id)

            # Apply Penalty
            await WalletService.apply_penalty(db, plan.user_id, plan.id, plan.per_day_penalty)
            
        await db.commit()
