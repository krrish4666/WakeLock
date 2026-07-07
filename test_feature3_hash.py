import asyncio
import hashlib
from decimal import Decimal
from datetime import datetime
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.plan import AccountabilityPlan, WakeSession, SessionStatus, OTPToken
from app.services.wallet import WalletService
from app.services.plan import PlanService
from app.services.otp import OTPService

async def test_feature3():
    print("--- STARTING FEATURE 3: OTP DATABASE PERSISTENCE & SHA-256 HASHING TEST ---")
    telegram_id = 666666666 # Unique test ID for Feature 3
    
    async with AsyncSessionLocal() as db:
        # 1. Deposit and create plan and wake session
        await WalletService.deposit(db, telegram_id, Decimal("500.00"))
        plan = await PlanService.create_plan(db, telegram_id, Decimal("140.00"), 7)
        session = WakeSession(
            plan_id=plan.id,
            date=datetime.now().date(),
            status=SessionStatus.PENDING
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        session_id = session.id
        
        print(f"[INIT] Created WakeSession ID {session_id} for Plan ID {plan.id}.")
        
        # 2. Store OTP
        test_otp = "849201"
        print(f"\n[SIMULATION] Storing OTP code '{test_otp}' via OTPService.store_otp...")
        await OTPService.store_otp(db, session_id, test_otp, ttl_minutes=2)
        
    # 3. Verify PostgreSQL database persistence and SHA-256 hashing
    async with AsyncSessionLocal() as db:
        stmt = select(OTPToken).where(OTPToken.session_id == session_id)
        res = await db.execute(stmt)
        token_entry = res.scalars().first()
        
        print(f"\n[VERIFICATION] Inspecting PostgreSQL OTPToken table:")
        print(f"  Token Entry Found? {token_entry is not None}")
        print(f"  Stored Hash in DB: {token_entry.token_hash}")
        print(f"  Is Plaintext '{test_otp}'? {token_entry.token_hash == test_otp} (Expected: False)")
        
        expected_hash = hashlib.sha256(test_otp.encode("utf-8")).hexdigest()
        print(f"  Matches SHA-256('{test_otp}')? {token_entry.token_hash == expected_hash} (Expected: True)")
        print(f"  Is Used? {token_entry.is_used} (Expected: False)")
        
        assert token_entry is not None, "No OTPToken record created in PostgreSQL!"
        assert token_entry.token_hash != test_otp, "SECURITY RISK: OTP stored in plaintext!"
        assert token_entry.token_hash == expected_hash, "Hash mismatch! Did not use SHA-256 correctly."
        assert token_entry.is_used is False, "Token should not be marked used yet."
        
        print("[SUCCESS] OTP correctly persisted in PostgreSQL as a SHA-256 hash!")
        
        # 4. Test wrong code verification
        print(f"\n[SIMULATION] Attempting verification with wrong code '000000'...")
        is_valid_wrong = await OTPService.verify_otp(db, session_id, "000000")
        print(f"  Verification result: {is_valid_wrong} (Expected: False)")
        assert is_valid_wrong is False, "Accepted invalid OTP code!"
        
        # 5. Test correct code verification
        print(f"\n[SIMULATION] Attempting verification with correct code '{test_otp}'...")
        is_valid_correct = await OTPService.verify_otp(db, session_id, test_otp)
        print(f"  Verification result: {is_valid_correct} (Expected: True)")
        assert is_valid_correct is True, "Rejected valid OTP code!"
        
        # Check is_used flag in DB
        await db.refresh(token_entry)
        print(f"  After verification, Token is_used: {token_entry.is_used} (Expected: True)")
        assert token_entry.is_used is True, "Token was not marked as used in database after verification!"
        
        print("[SUCCESS] Verification correctly validated SHA-256 hash and marked token as used!")
        
        # 6. Test replay/single-use attack
        print(f"\n[SIMULATION] Attempting replay attack (submitting '{test_otp}' a second time)...")
        is_valid_replay = await OTPService.verify_otp(db, session_id, test_otp)
        print(f"  Replay result: {is_valid_replay} (Expected: False)")
        assert is_valid_replay is False, "SECURITY RISK: Replay attack succeeded! Token was reused."
        
        print("[SUCCESS] Single-use security verified! Replay attacks are blocked.")
        print("\n[SUCCESS] Feature 3 fully verified!")

asyncio.run(test_feature3())
