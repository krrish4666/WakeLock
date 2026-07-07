import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.sql import func
from app.core.database import AsyncSessionLocal
from app.models.plan import AccountabilityPlan, WakeSession, SessionStatus
from app.models.wallet import PlatformRevenue
from app.services.wallet import WalletService
from app.services.plan import PlanService
from app.services.verification import VerificationService

async def test_feature2():
    print("--- STARTING FEATURE 2: PLATFORM REVENUE & PLAN FAILURE STATS TEST ---")
    telegram_id = 777777777 # Unique test ID for Feature 2
    
    async with AsyncSessionLocal() as db:
        # 1. Deposit and create plan
        await WalletService.deposit(db, telegram_id, Decimal("500.00"))
        plan = await PlanService.create_plan(db, telegram_id, Decimal("140.00"), 7) # Rs 20/day penalty
        
        print(f"[INIT] Plan ID {plan.id} created. Locked Balance: Rs. 140.00, Penalty Rate: Rs. {plan.per_day_penalty}/day")
        print(f"[INIT] Initial Plan Stats -> Days Missed: {plan.days_missed}, Remaining Balance: Rs. {plan.remaining_balance}")
        
        # Check initial platform revenue from this plan
        rev_res = await db.execute(select(func.sum(PlatformRevenue.total_collected)).where(PlatformRevenue.source_plan_id == plan.id))
        initial_rev = rev_res.scalar() or Decimal("0.00")
        print(f"[INIT] Initial Platform Revenue for Plan {plan.id}: Rs. {initial_rev}")
        
        # 2. Create Day 1 wake session and fail it
        session1 = WakeSession(
            plan_id=plan.id,
            date=datetime.now().date(),
            status=SessionStatus.PENDING
        )
        db.add(session1)
        await db.commit()
        await db.refresh(session1)
        
    print("\n[SIMULATION] Day 1: Triggering session failure and penalty deduction...")
    async with AsyncSessionLocal() as db:
        await VerificationService.process_session_failure(db, session1.id)
        
        plan = await db.get(AccountabilityPlan, plan.id)
        wallet = await WalletService.get_or_create_wallet(db, telegram_id)
        rev_res = await db.execute(select(func.sum(PlatformRevenue.total_collected)).where(PlatformRevenue.source_plan_id == plan.id))
        day1_rev = rev_res.scalar() or Decimal("0.00")
        
        print(f"[VERIFICATION Day 1]:")
        print(f"  Plan Days Missed: {plan.days_missed} (Expected: 1)")
        print(f"  Plan Remaining Balance: Rs. {plan.remaining_balance} (Expected: Rs. 120.00)")
        print(f"  Wallet Locked Balance: Rs. {wallet.locked_balance} (Expected: Rs. 120.00)")
        print(f"  Platform Revenue Collected from Plan: Rs. {day1_rev} (Expected: Rs. 20.00)")
        
        assert plan.days_missed == 1, f"Expected 1 day missed, got {plan.days_missed}"
        assert plan.remaining_balance == Decimal("120.00"), f"Expected 120.00 remaining balance, got {plan.remaining_balance}"
        assert wallet.locked_balance == Decimal("120.00"), f"Expected 120.00 locked balance, got {wallet.locked_balance}"
        assert day1_rev == Decimal("20.00"), f"Expected 20.00 platform revenue, got {day1_rev}"
        
        print("[SUCCESS] Day 1 failure correctly updated plan stats and credited platform revenue!")
        
        # 3. Create Day 2 wake session and fail it
        session2 = WakeSession(
            plan_id=plan.id,
            date=datetime.now().date() + timedelta(days=1),
            status=SessionStatus.PENDING
        )
        db.add(session2)
        await db.commit()
        await db.refresh(session2)
        session2_id = session2.id

    print("\n[SIMULATION] Day 2: Triggering second session failure...")
    async with AsyncSessionLocal() as db:
        await VerificationService.process_session_failure(db, session2_id)
        
        plan = await db.get(AccountabilityPlan, plan.id)
        wallet = await WalletService.get_or_create_wallet(db, telegram_id)
        rev_res = await db.execute(select(func.sum(PlatformRevenue.total_collected)).where(PlatformRevenue.source_plan_id == plan.id))
        day2_rev = rev_res.scalar() or Decimal("0.00")
        
        print(f"[VERIFICATION Day 2]:")
        print(f"  Plan Days Missed: {plan.days_missed} (Expected: 2)")
        print(f"  Plan Remaining Balance: Rs. {plan.remaining_balance} (Expected: Rs. 100.00)")
        print(f"  Wallet Locked Balance: Rs. {wallet.locked_balance} (Expected: Rs. 100.00)")
        print(f"  Platform Revenue Collected from Plan: Rs. {day2_rev} (Expected: Rs. 40.00)")
        
        assert plan.days_missed == 2, f"Expected 2 days missed, got {plan.days_missed}"
        assert plan.remaining_balance == Decimal("100.00"), f"Expected 100.00 remaining balance, got {plan.remaining_balance}"
        assert wallet.locked_balance == Decimal("100.00"), f"Expected 100.00 locked balance, got {wallet.locked_balance}"
        assert day2_rev == Decimal("40.00"), f"Expected 40.00 platform revenue, got {day2_rev}"
        
        print("\n[SUCCESS] Feature 2 verified! Platform revenue and plan failure stats are atomically tracked across multiple failures.")

asyncio.run(test_feature2())
