from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from decimal import Decimal
from typing import Optional

from app.models.wallet import Wallet, WalletTransaction, TransactionType
from app.models.user import User

class WalletService:
    @staticmethod
    def record_transaction(
        db: AsyncSession,
        wallet: Wallet,
        tx_type: TransactionType,
        amount: Decimal,
        reference_id: Optional[int] = None
    ) -> WalletTransaction:
        """
        Standardized method to append append-only ledger entries for any wallet movement.
        Ensures balance_after is accurately captured inline.
        """
        tx = WalletTransaction(
            wallet_id=wallet.user_id,
            type=tx_type,
            amount=amount,
            balance_after=wallet.total_balance,
            reference_id=reference_id
        )
        db.add(tx)
        return tx

    @staticmethod
    async def get_or_create_wallet(db: AsyncSession, telegram_id: int) -> Wallet:
        stmt = select(Wallet).where(Wallet.user_id == telegram_id)
        result = await db.execute(stmt)
        wallet = result.scalars().first()
        
        if not wallet:
            # Ensure user exists before creating wallet
            user_stmt = select(User).where(User.telegram_id == telegram_id)
            user_result = await db.execute(user_stmt)
            if not user_result.scalars().first():
                new_user = User(telegram_id=telegram_id, username="simulated_user")
                db.add(new_user)
                await db.flush()

            wallet = Wallet(user_id=telegram_id, total_balance=0.0, locked_balance=0.0, available_balance=0.0)
            db.add(wallet)
            await db.flush()
            
        return wallet

    @staticmethod
    async def deposit(db: AsyncSession, telegram_id: int, amount: Decimal) -> Wallet:
        wallet = await WalletService.get_or_create_wallet(db, telegram_id)
        
        wallet.total_balance = Decimal(str(wallet.total_balance)) + amount
        wallet.available_balance = Decimal(str(wallet.available_balance)) + amount
        
        # Log Transaction via Ledger
        WalletService.record_transaction(
            db=db,
            wallet=wallet,
            tx_type=TransactionType.DEPOSIT,
            amount=amount
        )
        await db.commit()
        await db.refresh(wallet)
        return wallet

    @staticmethod
    async def manual_withdraw(db: AsyncSession, telegram_id: int) -> Optional[Wallet]:
        """
        Moves remaining locked_balance -> available_balance.
        Per Phase 4 Spec: No real payout, internal unlock only.
        """
        stmt = select(Wallet).where(Wallet.user_id == telegram_id)
        result = await db.execute(stmt)
        wallet = result.scalars().first()
        
        if not wallet or wallet.locked_balance <= 0:
            return None
            
        unlocked_amount = Decimal(str(wallet.locked_balance))
        
        wallet.available_balance = Decimal(str(wallet.available_balance)) + unlocked_amount
        wallet.locked_balance = Decimal('0.0')
        
        WalletService.record_transaction(
            db=db,
            wallet=wallet,
            tx_type=TransactionType.WITHDRAWAL,
            amount=unlocked_amount
        )
        await db.commit()
        await db.refresh(wallet)
        return wallet

    @staticmethod
    async def apply_penalty(db: AsyncSession, telegram_id: int, plan_id: int, penalty_amount: Decimal) -> Optional[Wallet]:
        """
        Deducts a penalty directly from the user's locked_balance for failing to verify attendance.
        """
        stmt = select(Wallet).where(Wallet.user_id == telegram_id)
        result = await db.execute(stmt)
        wallet = result.scalars().first()
        
        if not wallet or wallet.locked_balance < penalty_amount:
            # Cannot deduct or no balance left
            return None
            
        wallet.locked_balance = Decimal(str(wallet.locked_balance)) - Decimal(str(penalty_amount))
        wallet.total_balance = Decimal(str(wallet.total_balance)) - Decimal(str(penalty_amount))
        
        WalletService.record_transaction(
            db=db,
            wallet=wallet,
            tx_type=TransactionType.PENALTY,
            amount=penalty_amount,
            reference_id=plan_id
        )
        # We do NOT commit here because VerificationService batches the penalty execution
        # but we must flush to reflect ledger entry
        await db.flush()
        return wallet
