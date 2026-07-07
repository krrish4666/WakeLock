import asyncio
from decimal import Decimal
from datetime import datetime
from app.core.database import AsyncSessionLocal
from app.models.plan import AccountabilityPlan, WakeSession, SessionStatus
from app.services.wallet import WalletService
from app.services.plan import PlanService
from app.services.verification import VerificationService
from app.tasks.plan_tasks import _process_expired_otp_async

async def test_feature1():
    print("--- STARTING FEATURE 1: AUTOMATIC EXPIRY & PENALTY DEDUCTION TEST ---")
    telegram_id = 888888888 # Unique test ID for Feature 1
    
    async with AsyncSessionLocal() as db:
        # 1. Deposit and create plan
        await WalletService.deposit(db, telegram_id, Decimal("500.00"))
        plan = await PlanService.create_plan(db, telegram_id, Decimal("140.00"), 7) # Rs 20/day penalty
        
        print(f"[INIT] Plan created. Locked Balance: Rs. 140.00, Penalty Rate: Rs. {plan.per_day_penalty}/day")
        
        # 2. Create a pending wake session (simulate alarm drop)
        session = WakeSession(
            plan_id=plan.id,
            date=datetime.now().date(),
            status=SessionStatus.PENDING
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        session_id = session.id
        print(f"[SIMULATION] OTP dropped for Session ID {session_id}. Status: {session.status}, Processed Flag: {session.processed_flag}")
        
    # 3. Simulate 2 minutes passing without user verification! Trigger _process_expired_otp_async
    print("\n[SIMULATION] 2 minutes elapsed! Triggering automated expiry check task...")
    await _process_expired_otp_async(session_id, telegram_id)
        
    # 4. Verify results!
    async with AsyncSessionLocal() as db:
        session = await db.get(WakeSession, session_id)
        wallet = await WalletService.get_or_create_wallet(db, telegram_id)
        
        print(f"\n[VERIFICATION] After Expiry Task:")
        print(f"  Session Status: {session.status} (Expected: FAILED)")
        print(f"  Processed Flag: {session.processed_flag} (Expected: True)")
        print(f"  Wallet Locked Balance: Rs. {wallet.locked_balance} (Expected: Rs. 120.00)")
        
        assert session.status == SessionStatus.FAILED, "Status did not transition to FAILED!"
        assert session.processed_flag is True, "Processed flag was not set to True!"
        assert wallet.locked_balance == Decimal("120.00"), f"Expected 120.00 locked balance, got {wallet.locked_balance}"
        
        print("\n[SUCCESS] Feature 1 verified! Expiry task automatically failed unverified session and deducted penalty.")
        
        # 5. Test Idempotency! Running expiry check again should NOT deduct another penalty!
        print("\n[SIMULATION] Running expiry task a second time (Idempotency check)...")
        await _process_expired_otp_async(session_id, telegram_id)
            
        wallet_after = await WalletService.get_or_create_wallet(db, telegram_id)
        print(f"  Wallet Locked Balance after 2nd run: Rs. {wallet_after.locked_balance} (Expected: Rs. 120.00)")
        assert wallet_after.locked_balance == Decimal("120.00"), "Idempotency failed! Deducted twice!"
        
        print("[SUCCESS] Idempotency verified! No duplicate deduction occurred.")

asyncio.run(test_feature1())
