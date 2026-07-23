import asyncio
from contextlib import asynccontextmanager

from fastapi import HTTPException, status
from redis.asyncio import Redis

from core.config import settings


class LocalSemaphore:
    def __init__(self, limit: int) -> None:
        self._semaphore = asyncio.Semaphore(limit)

    @asynccontextmanager
    async def acquire(self):
        await self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()


redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
local_gate = LocalSemaphore(settings.CHAT_CONCURRENCY_LIMIT)
CHAT_GATE_KEY = "chat:concurrency:active"


@asynccontextmanager
async def redis_concurrency_gate():
    acquired = False
    try:
        active = await redis_client.incr(CHAT_GATE_KEY)
        acquired = True
        await redis_client.expire(CHAT_GATE_KEY, settings.CHAT_RUNTIME_STATE_TTL_SECONDS)
        if active > settings.CHAT_CONCURRENCY_LIMIT:
            await redis_client.decr(CHAT_GATE_KEY)
            acquired = False
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Hệ thống đang bận, vui lòng thử lại sau.",
            )
        yield
    except HTTPException:
        raise
    except Exception:
        async with local_gate.acquire():
            yield
    finally:
        if acquired:
            await redis_client.decr(CHAT_GATE_KEY)


async def set_runtime_state(key: str, value: str) -> None:
    await redis_client.setex(key, settings.CHAT_RUNTIME_STATE_TTL_SECONDS, value)
