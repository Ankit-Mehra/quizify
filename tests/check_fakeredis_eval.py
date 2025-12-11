import asyncio
from fakeredis import aioredis as fakeredis
import redis.asyncio as redis

async def check_eval():
    client = await fakeredis.FakeRedis(decode_responses=True)
    try:
        result = await client.eval("return 1", 0)
        print(f"Eval result: {result}")
    except Exception as e:
        print(f"Eval failed: {e}")
    await client.close()

if __name__ == "__main__":
    asyncio.run(check_eval())
