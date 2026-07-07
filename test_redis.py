import asyncio
from redis.asyncio import Redis
from app.core.config import settings

async def test_redis():
    print("Testing Redis connection...")
    try:
        async with Redis.from_url(settings.REDIS_URL, decode_responses=True) as client:
            await client.set("test_key", "hello")
            val = await client.get("test_key")
            print("Redis returned:", val)
            print("[SUCCESS] Redis connection test passed!")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test_redis())
