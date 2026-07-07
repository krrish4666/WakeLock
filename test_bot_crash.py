import asyncio
import datetime
from decimal import Decimal
from app.core.database import AsyncSessionLocal
from app.services.preferences import PreferencesService
from app.services.plan import PlanService
from app.services.wallet import WalletService

async def test_commands():
    telegram_id = 1150153975 # User id from previous logs
    
    print("Testing /balance...")
    try:
        async with AsyncSessionLocal() as db:
            wallet = await WalletService.get_or_create_wallet(db, telegram_id)
            print(f"Wallet Total: {wallet.total_balance}")
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\nTesting /buffer 10...")
    try:
        async with AsyncSessionLocal() as db:
            res = await PreferencesService.set_buffer(db, telegram_id, 10)
            print(res)
    except Exception as e:
        import traceback
        traceback.print_exc()
        
    print("\nTesting /alarm 23:03...")
    try:
        alarm_time = datetime.datetime.strptime("23:03", "%H:%M").time()
        async with AsyncSessionLocal() as db:
            res = await PreferencesService.set_alarm(db, telegram_id, alarm_time)
            print(res)
    except Exception as e:
        import traceback
        traceback.print_exc()
        
    print("\nTesting /plan 100 7...")
    try:
        async with AsyncSessionLocal() as db:
            res = await PlanService.create_plan(db, telegram_id, Decimal("100"), 7)
            print("Plan:", res)
            if hasattr(res, 'alarm_time'):
                print("Wait, plan has alarm_time??")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test_commands())
