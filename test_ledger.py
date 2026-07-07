import asyncio
from decimal import Decimal
from sqlalchemy.future import select

# To test on fresh DB cleanly
from app.core.database import AsyncSessionLocal, Base, engine
from app.models.wallet import Wallet, WalletTransaction, TransactionType
from app.services.wallet import WalletService
from app.services.plan import PlanService

async def test_ledger_reconciliation():
    telegram_id = 999999999 # Unique Test ID
    
    # Phase 1: Simulate the Flow
    async with AsyncSessionLocal() as db:
        print(f"--- INIT SIMULATION FOR USER {telegram_id} ---")
        
        # 1. Deposit 1000
        wallet = await WalletService.deposit(db, telegram_id, Decimal("1000.00"))
        print(f"Deposited 1000. Balances -> Avail: {wallet.available_balance}, Locked: {wallet.locked_balance}, Total: {wallet.total_balance}")
        
        # 2. Purchase Plan for 300
        try:
            plan = await PlanService.create_plan(db, telegram_id, Decimal("300.00"), 7)
            print(f"Plan created. Balances -> Avail: {wallet.available_balance}, Locked: {wallet.locked_balance}, Total: {wallet.total_balance}")
        except Exception as e:
            print(f"Plan error: {e}")
            
        # 3. Process Penalty of 42.85
        penalty_amount = Decimal("42.85")
        await WalletService.apply_penalty(db, telegram_id, plan.id, penalty_amount)
        # Flush/Commit done externally in verification, so we commit here
        await db.commit()
        await db.refresh(wallet)
        print(f"Penalty applied. Balances -> Avail: {wallet.available_balance}, Locked: {wallet.locked_balance}, Total: {wallet.total_balance}")
        
        # 4. Manual Withdraw (Unlock remaining)
        await WalletService.manual_withdraw(db, telegram_id)
        await db.refresh(wallet)
        print(f"Withdraw/Unlock applied. Balances -> Avail: {wallet.available_balance}, Locked: {wallet.locked_balance}, Total: {wallet.total_balance}")

    # Phase 2: Reconciliation
    async with AsyncSessionLocal() as db:
        print(f"\n--- INITIATING RECONCILIATION ---")
        wallet_stmt = select(Wallet).where(Wallet.user_id == telegram_id)
        res = await db.execute(wallet_stmt)
        wallet = res.scalars().first()
        
        tx_stmt = select(WalletTransaction).where(WalletTransaction.wallet_id == telegram_id).order_by(WalletTransaction.id.asc())
        res = await db.execute(tx_stmt)
        transactions = res.scalars().all()
        
        # Calculate manually from Ledger
        sum_deposit = sum([tx.amount for tx in transactions if tx.type == TransactionType.DEPOSIT])
        sum_plan_lock = sum([tx.amount for tx in transactions if tx.type == TransactionType.PLAN_LOCK])
        sum_penalty = sum([tx.amount for tx in transactions if tx.type == TransactionType.PENALTY])
        sum_withdraw = sum([tx.amount for tx in transactions if tx.type == TransactionType.WITHDRAWAL])
        
        recon_total = sum_deposit - sum_penalty
        recon_locked = sum_plan_lock - sum_penalty - sum_withdraw
        recon_avail = sum_deposit - sum_plan_lock + sum_withdraw
        
        print(f"DB Wallet State:")
        print(f"  Total: {wallet.total_balance}")
        print(f"  Available: {wallet.available_balance}")
        print(f"  Locked: {wallet.locked_balance}")
        
        print(f"\nLedger Ledger Reconstruction:")
        print(f"  Sum Deposits: +{sum_deposit}")
        print(f"  Sum Locks: +{sum_plan_lock} (Locked) / -{sum_plan_lock} (Avail)")
        print(f"  Sum Penalties: -{sum_penalty}")
        print(f"  Sum Withdraws: -{sum_withdraw} (Locked) / +{sum_withdraw} (Avail)")
        print(f"  ---------------------------")
        print(f"  Recon Total: {recon_total}")
        print(f"  Recon Available: {recon_avail}")
        print(f"  Recon Locked: {recon_locked}")
        
        # Check last transaction balance_after
        last_tx = transactions[-1]
        print(f"\nLast TX balance_after: {last_tx.balance_after}")
        
        assert wallet.total_balance == recon_total, "TOTAL BALANCE MISMATCH!"
        assert wallet.available_balance == recon_avail, "AVAILABLE BALANCE MISMATCH!"
        assert wallet.locked_balance == recon_locked, "LOCKED BALANCE MISMATCH!"
        assert wallet.total_balance == last_tx.balance_after, "BALANCE_AFTER MISMATCH!"
        
        print("\n[SUCCESS] LEDGER RECONCILIATION PERFECT! No silent bugs found.")

asyncio.run(test_ledger_reconciliation())
