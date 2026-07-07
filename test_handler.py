import asyncio
from app.core.database import AsyncSessionLocal
from app.services.wallet import WalletService

async def main():
    # simulate the handler
    async with AsyncSessionLocal() as db:
        try:
            telegram_id = 718305018 # fake internal id
            amount = 70
            wallet = await WalletService.deposit(db, telegram_id, amount)
            print("Finished deposit.")
            print(f"[SUCCESS] Deposited {amount}. New Balance: {wallet.available_balance}")
        except Exception as e:
            print("ERROR IN HANDLER:", str(e))

asyncio.run(main())
