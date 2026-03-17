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
