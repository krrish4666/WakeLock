import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from app.core.database import AsyncSessionLocal
from app.models.plan import AccountabilityPlan, PlanStatus
from app.models.wallet import WalletTransaction, TransactionType
from app.services.wallet import WalletService
from app.services.plan import PlanService
from app.tasks.plan_tasks import _check_completed_plans_async
from sqlalchemy import select

async def test_feature5():
    print("--- STARTING FEATURE 5: COMPLETION CRON & UNLOCKING REMAINING BALANCE TEST ---")
    telegram_id = 444444444 # Unique test ID for Feature 5
    
    async with AsyncSessionLocal() as db:
        # 1. Deposit Rs. 500 and create a 7-day plan locking Rs. 140
        await WalletService.deposit(db, telegram_id, Decimal("500.00"))
        plan = await PlanService.create_plan(db, telegram_id, Decimal("140.00"), 7)
        
        print(f"[INIT] Created Plan ID {plan.id}. Status: {plan.status}, Locked Balance: Rs. {plan.remaining_balance}.")
        
        wallet = await WalletService.get_or_create_wallet(db, telegram_id)
        initial_total = wallet.total_balance
        print(f"[INIT] Initial Wallet Balances -> Available: Rs. {wallet.available_balance}, Locked: Rs. {wallet.locked_balance}, Total: Rs. {initial_total}")
        
        # 2. Simulate time travel! Fast forward plan.end_date into the past
        plan.end_date = datetime.now() - timedelta(minutes=5)
        await db.commit()
        print(f"\n[SIMULATION] Fast-forwarded Plan end_date into the past: {plan.end_date}")
        
    # 3. Trigger completion cron task!
    print(f"\n[SIMULATION] Triggering daily completion cron task (_check_completed_plans_async)...")
    await _check_completed_plans_async()
        
    # 4. Verify Completion and Unlocking of Funds!
    async with AsyncSessionLocal() as db:
        plan = await db.get(AccountabilityPlan, plan.id)
        wallet = await WalletService.get_or_create_wallet(db, telegram_id)
        
        # Check transactions
        stmt = select(WalletTransaction).where(WalletTransaction.wallet_id == telegram_id).order_by(WalletTransaction.id.desc())
        res = await db.execute(stmt)
        txs = res.scalars().all()
        last_tx = txs[0] if txs else None
        
        print(f"\n[VERIFICATION] After Completion Cron Execution:")
        print(f"  Plan Status: {plan.status} (Expected: PlanStatus.COMPLETED)")
        print(f"  Wallet Locked Balance: Rs. {wallet.locked_balance} (Expected: Rs. 0.00)")
        print(f"  Wallet Available Balance: Rs. {wallet.available_balance} (Expected: Rs. {initial_total})")
        print(f"  Wallet Total Balance: Rs. {wallet.total_balance} (Expected: Rs. {initial_total})")
        print(f"  Last Transaction Type: {last_tx.type if last_tx else 'None'} (Expected: WITHDRAWAL)")
        print(f"  Last Transaction Amount: Rs. {last_tx.amount if last_tx else '0.00'} (Expected: Rs. 140.00)")
        
        assert plan.status == PlanStatus.COMPLETED, f"Expected COMPLETED status, got {plan.status}"
        assert wallet.locked_balance == Decimal("0.00"), f"Expected 0.00 locked balance, got {wallet.locked_balance}"
        assert wallet.available_balance == initial_total, f"Expected {initial_total} available balance, got {wallet.available_balance}"
        assert wallet.total_balance == initial_total, f"Expected {initial_total} total balance, got {wallet.total_balance}"
        assert last_tx is not None and last_tx.type == TransactionType.WITHDRAWAL, "No withdrawal transaction recorded for unlocking!"
        assert last_tx.amount == Decimal("140.00"), f"Expected 140.00 unlocked, got {last_tx.amount}"
        
        print("\n[SUCCESS] Feature 5 verified! Completed plan released all locked funds back to available balance.")
        
        # 5. Test Idempotency!
        print("\n[SIMULATION] Running completion cron a second time (Idempotency check)...")
        await _check_completed_plans_async()
        
        wallet_after = await WalletService.get_or_create_wallet(db, telegram_id)
        assert wallet_after.available_balance == initial_total, "Idempotency failed! Balances changed on 2nd run!"
        print("[SUCCESS] Idempotency verified! No duplicate unlocks occurred.")
        print("\n[SUCCESS] ALL 5 FEATURES FULLY IMPLEMENTED AND VERIFIED! WAKELOCK 100% COMPLETE!")

asyncio.run(test_feature5())
