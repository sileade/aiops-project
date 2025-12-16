"""
Redis-based caching service for AI responses and frequently accessed data.

Features:
- TTL-based caching
- Hash-based cache keys for complex queries
- Automatic serialization/deserialization
- Cache invalidation patterns
"""

import asyncio
import hashlib
import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from app.utils.logger import logger
from config.settings import settings

# Lazy import redis
redis_client = None
Redis = None


def _get_redis():
    """Lazy initialization of Redis client."""
    global redis_client, Redis

    if redis_client is not None:
        return redis_client

    try:
        import redis.asyncio as aioredis

        Redis = aioredis.Redis

        redis_client = aioredis.Redis(
            host=getattr(settings, "redis_host", "localhost"),
            port=getattr(settings, "redis_port", 6379),
            db=getattr(settings, "redis_cache_db", 1),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        logger.info("Redis cache client initialized")
        return redis_client
    except ImportError:
        logger.warning("redis package not installed. Caching disabled.")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        return None


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a unique cache key from arguments."""
    key_data = json.dumps(
        {"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in sorted(kwargs.items())}}, sort_keys=True
    )

    hash_value = hashlib.md5(key_data.encode()).hexdigest()[:16]
    return f"aiops:{prefix}:{hash_value}"


class CacheService:
    """
    Async Redis cache service with automatic fallback.

    Usage:
        cache = CacheService()

        # Direct usage
        await cache.set("key", {"data": "value"}, ttl=300)
        data = await cache.get("key")

        # Decorator usage
        @cache.cached("analysis", ttl=600)
        async def analyze_logs(logs):
            ...
    """

    def __init__(self):
        self._local_cache: dict = {}  # Fallback in-memory cache
        self._local_cache_ttl: dict = {}

    @property
    def redis(self):
        return _get_redis()

    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        # Try Redis first
        if self.redis:
            try:
                value = await self.redis.get(key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")

        # Fallback to local cache
        if key in self._local_cache:
            import time

            if self._local_cache_ttl.get(key, 0) > time.time():
                return self._local_cache[key]
            else:
                del self._local_cache[key]
                self._local_cache_ttl.pop(key, None)

        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in cache with TTL (seconds)."""
        serialized = json.dumps(value)

        # Try Redis first
        if self.redis:
            try:
                await self.redis.setex(key, ttl, serialized)
                return True
            except Exception as e:
                logger.warning(f"Redis set error: {e}")

        # Fallback to local cache
        import time

        self._local_cache[key] = value
        self._local_cache_ttl[key] = time.time() + ttl

        # Cleanup old entries (simple LRU-like behavior)
        if len(self._local_cache) > 1000:
            oldest_key = min(self._local_cache_ttl, key=self._local_cache_ttl.get)
            del self._local_cache[oldest_key]
            del self._local_cache_ttl[oldest_key]

        return True

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if self.redis:
            try:
                await self.redis.delete(key)
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")

        self._local_cache.pop(key, None)
        self._local_cache_ttl.pop(key, None)
        return True

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        deleted = 0

        if self.redis:
            try:
                async for key in self.redis.scan_iter(match=pattern):
                    await self.redis.delete(key)
                    deleted += 1
            except Exception as e:
                logger.warning(f"Redis delete_pattern error: {e}")

        # Also clean local cache
        keys_to_delete = [k for k in self._local_cache if k.startswith(pattern.replace("*", ""))]
        for key in keys_to_delete:
            del self._local_cache[key]
            self._local_cache_ttl.pop(key, None)
            deleted += 1

        return deleted

    async def get_or_set(self, key: str, factory: Callable, ttl: int = 300) -> Any:
        """Get from cache or compute and store."""
        value = await self.get(key)
        if value is not None:
            logger.debug(f"Cache hit: {key}")
            return value

        logger.debug(f"Cache miss: {key}")

        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()

        await self.set(key, value, ttl)
        return value

    def cached(self, prefix: str, ttl: int = 300):
        """
        Decorator for caching function results.

        Usage:
            @cache.cached("analysis", ttl=600)
            async def analyze_logs(logs: str):
                ...
        """

        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key = generate_cache_key(prefix, *args, **kwargs)

                # Try to get from cache
                cached_value = await self.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                    return cached_value

                # Execute function
                logger.debug(f"Cache miss for {func.__name__}: {cache_key}")

                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Store in cache
                await self.set(cache_key, result, ttl)

                return result

            return wrapper

        return decorator

    async def health_check(self) -> dict:
        """Check cache health status."""
        status = {
            "redis_available": False,
            "local_cache_size": len(self._local_cache),
        }

        if self.redis:
            try:
                await self.redis.ping()
                status["redis_available"] = True
                status["redis_info"] = await self.redis.info("memory")
            except Exception as e:
                status["redis_error"] = str(e)

        return status


# Global cache instance
cache = CacheService()


# Convenience functions
async def get_cached(key: str) -> Any | None:
    """Get value from cache."""
    return await cache.get(key)


async def set_cached(key: str, value: Any, ttl: int = 300) -> bool:
    """Set value in cache."""
    return await cache.set(key, value, ttl)


async def invalidate_cache(pattern: str) -> int:
    """Invalidate cache entries matching pattern."""
    return await cache.delete_pattern(pattern)
