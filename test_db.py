import asyncio
from app.core.database import AsyncSessionLocal
from app.services.wallet import WalletService

async def main():
    async with AsyncSessionLocal() as db:
        try:
            wallet = await WalletService.deposit(db, 123456, 70)
            print("DEPOSIT SUCCESS:", wallet.available_balance)
        except Exception as e:
            print("ERROR:", str(e))

asyncio.run(main())
