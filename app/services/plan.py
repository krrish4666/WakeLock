from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta, time
from decimal import Decimal
import logging

from app.models.plan import AccountabilityPlan, PlanStatus
from app.models.wallet import Wallet, WalletTransaction, TransactionType
from app.services.wallet import WalletService
from app.services.preferences import PreferencesService

class PlanService:
    @staticmethod
    async def create_plan(
        db: AsyncSession, 
        telegram_id: int, 
        amount: Decimal, 
        duration_days: int
    ) -> AccountabilityPlan | str:
        
        if duration_days < 7:
            return "Minimum plan duration is 7 days."
        if amount < 70:
            return "Minimum amount to lock is ₹70."

        wallet = await WalletService.get_or_create_wallet(db, telegram_id)
        # Ensure preference record exists for inner joins
        await PreferencesService.get_or_create_preferences(db, telegram_id)
        
        if wallet.available_balance < amount:
            return "Insufficient available balance. Please deposit funds first."

        # Calculate penalty
        per_day_penalty = Decimal(amount) / Decimal(duration_days)

        # Update wallet
        wallet.available_balance = Decimal(str(wallet.available_balance)) - amount
        wallet.locked_balance = Decimal(str(wallet.locked_balance)) + amount

        # Log LOCK transaction via Ledger
        WalletService.record_transaction(
            db=db,
            wallet=wallet,
            tx_type=TransactionType.PLAN_LOCK,
            amount=amount,
            reference_id=None # Optionally tie to new_plan.id after flush, but leaving generic for now
        )

        # Create Plan
        start_date = datetime.now()
        end_date = start_date + timedelta(days=duration_days)

        new_plan = AccountabilityPlan(
            user_id=telegram_id,
            start_date=start_date,
            end_date=end_date,
            total_amount_locked=amount,
            per_day_penalty=per_day_penalty,
            remaining_balance=amount,
            status=PlanStatus.ACTIVE
        )
        db.add(new_plan)
        
        await db.commit()
        await db.refresh(new_plan)
        return new_plan

    @staticmethod
    async def evaluate_plan_status(db: AsyncSession, plan: AccountabilityPlan) -> PlanStatus:
        """
        Evaluates an active plan after a verification or failure event.
        Transitions to EXHAUSTED if remaining balance cannot cover a penalty.
        Transitions to COMPLETED if all duration days are accounted for.
        Releases any leftover locked funds (dust) back to available_balance.
        """
        if plan.status != PlanStatus.ACTIVE:
            return plan.status
            
        # Check Exhaustion
        if Decimal(str(plan.remaining_balance)) < Decimal(str(plan.per_day_penalty)):
            plan.status = PlanStatus.EXHAUSTED
            
            # Release any leftover dust from locked to available balance
            wallet = await WalletService.get_or_create_wallet(db, plan.user_id)
            if wallet and Decimal(str(wallet.locked_balance)) > 0:
                dust = Decimal(str(wallet.locked_balance))
                wallet.available_balance = Decimal(str(wallet.available_balance)) + dust
                wallet.locked_balance = Decimal("0.00")
                
                WalletService.record_transaction(
                    db=db,
                    wallet=wallet,
                    tx_type=TransactionType.WITHDRAWAL,
                    amount=dust,
                    reference_id=plan.id
                )
            plan.remaining_balance = Decimal("0.00")
            
            from app.bot import send_alert
            try:
                await send_alert(
                    plan.user_id,
                    f"⚠️ WAKELOCK PLAN EXHAUSTED ⚠️\n\n"
                    f"Your plan (ID: {plan.id}) has run out of funds to cover penalties.\n"
                    f"Status changed to EXHAUSTED. Any leftover locked dust has been returned to your available balance."
                )
            except Exception:
                pass
            return PlanStatus.EXHAUSTED
            
        # Check Completion
        now = datetime.now()
        end = plan.end_date.replace(tzinfo=None) if plan.end_date.tzinfo else plan.end_date
        if (plan.days_verified + plan.days_missed) >= plan.duration_days or now >= end:
            plan.status = PlanStatus.COMPLETED
            
            # Release all remaining locked balance back to available balance
            wallet = await WalletService.get_or_create_wallet(db, plan.user_id)
            if wallet and Decimal(str(wallet.locked_balance)) > 0:
                remaining = Decimal(str(wallet.locked_balance))
                wallet.available_balance = Decimal(str(wallet.available_balance)) + remaining
                wallet.locked_balance = Decimal("0.00")
                
                WalletService.record_transaction(
                    db=db,
                    wallet=wallet,
                    tx_type=TransactionType.WITHDRAWAL,
                    amount=remaining,
                    reference_id=plan.id
                )
                
            from app.bot import send_alert
            try:
                await send_alert(
                    plan.user_id,
                    f"🎉 WAKELOCK PLAN COMPLETED! 🎉\n\n"
                    f"Congratulations! You completed your {plan.duration_days}-day accountability plan.\n"
                    f"All remaining locked funds (Rs. {plan.remaining_balance}) have been unlocked to your available balance!"
                )
            except Exception:
                pass
            return PlanStatus.COMPLETED
            
        return PlanStatus.ACTIVE

    @staticmethod
    async def process_completed_plans(db: AsyncSession):
        """
        Cron sweep to check all ACTIVE plans. If their end_date is reached or duration_days completed,
        transitions them to COMPLETED and releases remaining locked balance.
        """
        stmt = select(AccountabilityPlan).where(AccountabilityPlan.status == PlanStatus.ACTIVE)
        res = await db.execute(stmt)
        active_plans = res.scalars().all()
        
        for plan in active_plans:
            await PlanService.evaluate_plan_status(db, plan)
        await db.commit()
