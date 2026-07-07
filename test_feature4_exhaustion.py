import asyncio
from decimal import Decimal
from datetime import datetime
from app.core.database import AsyncSessionLocal
from app.models.plan import AccountabilityPlan, WakeSession, SessionStatus, PlanStatus
from app.services.wallet import WalletService
from app.services.plan import PlanService
from app.services.verification import VerificationService

async def test_feature4():
    print("--- STARTING FEATURE 4: PLAN STATE MACHINE & EXHAUSTION TEST ---")
    telegram_id = 555555555 # Unique test ID for Feature 4
    
    async with AsyncSessionLocal() as db:
        # 1. Deposit and create a 7-day plan locking Rs. 70 (Rs. 10/day penalty)
        await WalletService.deposit(db, telegram_id, Decimal("100.00"))
        plan = await PlanService.create_plan(db, telegram_id, Decimal("70.00"), 7)
        
        print(f"[INIT] Created Plan ID {plan.id}. Status: {plan.status}, Locked: Rs. {plan.remaining_balance}, Penalty: Rs. {plan.per_day_penalty}/day.")
        
        # 2. Simulate prior deductions leaving only Rs. 15.00 in locked balance (Rs. 5.00 dust above 1 penalty)
        plan.remaining_balance = Decimal("15.00")
        wallet = await WalletService.get_or_create_wallet(db, telegram_id)
        wallet.locked_balance = Decimal("15.00")
        wallet.available_balance = Decimal("30.00") # Rs. 30 available + Rs. 15 locked = Rs. 45 total
        wallet.total_balance = Decimal("45.00")
        
        session = WakeSession(
            plan_id=plan.id,
            date=datetime.now().date(),
            status=SessionStatus.PENDING
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        session_id = session.id
        
        print(f"[SIMULATION] Adjusted balances to simulate near exhaustion:")
        print(f"  Available Balance: Rs. {wallet.available_balance}")
        print(f"  Locked Balance: Rs. {wallet.locked_balance}")
        print(f"  Plan Remaining Balance: Rs. {plan.remaining_balance} (Only enough for 1 penalty + Rs. 5.00 dust!)")
        
    # 3. Trigger session failure! This deducts Rs. 10.00, leaving Rs. 5.00 (< Rs. 10.00 penalty) -> EXHAUSTED!
    print(f"\n[SIMULATION] Triggering session failure (deducts Rs. 10.00 penalty)...")
    async with AsyncSessionLocal() as db:
        await VerificationService.process_session_failure(db, session_id)
        
    # 4. Verify Exhaustion and Dust Unlocking
    async with AsyncSessionLocal() as db:
        plan = await db.get(AccountabilityPlan, plan.id)
        wallet = await WalletService.get_or_create_wallet(db, telegram_id)
        
        print(f"\n[VERIFICATION] After Penalty & State Machine Evaluation:")
        print(f"  Plan Status: {plan.status} (Expected: PlanStatus.EXHAUSTED)")
        print(f"  Plan Remaining Balance: Rs. {plan.remaining_balance} (Expected: Rs. 0.00)")
        print(f"  Wallet Locked Balance: Rs. {wallet.locked_balance} (Expected: Rs. 0.00)")
        print(f"  Wallet Available Balance: Rs. {wallet.available_balance} (Expected: Rs. 35.00 [30 original + 5 unlocked dust])")
        print(f"  Wallet Total Balance: Rs. {wallet.total_balance} (Expected: Rs. 35.00 [45 original - 10 penalty])")
        
        assert plan.status == PlanStatus.EXHAUSTED, f"Expected EXHAUSTED status, got {plan.status}"
        assert plan.remaining_balance == Decimal("0.00"), f"Expected 0.00 remaining balance, got {plan.remaining_balance}"
        assert wallet.locked_balance == Decimal("0.00"), f"Expected 0.00 locked balance, got {wallet.locked_balance}"
        assert wallet.available_balance == Decimal("35.00"), f"Expected 35.00 available balance, got {wallet.available_balance}"
        assert wallet.total_balance == Decimal("35.00"), f"Expected 35.00 total balance, got {wallet.total_balance}"
        
        print("\n[SUCCESS] Feature 4 verified! Plan automatically transitioned to EXHAUSTED and released leftover dust to available balance.")

asyncio.run(test_feature4())
