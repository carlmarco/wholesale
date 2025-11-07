"""
Redis Caching Layer

Provides caching decorators and utilities for API endpoints.
"""
import asyncio
import json
import hashlib
from typing import Optional, Callable, Any
from functools import wraps
import redis
from redis.exceptions import ConnectionError as RedisConnectionError

from config.settings import settings

# Redis client configuration
redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get Redis client instance.

    Returns:
        Redis client if available, None if connection fails
    """
    global redis_client

    if redis_client is None:
        redis_url = settings.redis_url

        if not redis_url:
            print("Redis connection skipped: redis_url not configured")
            return None

        try:
            redis_client = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Test connection
            redis_client.ping()
        except (RedisConnectionError, Exception) as e:
            print(f"Redis connection failed: {e}")
            redis_client = None

    return redis_client


def make_cache_key(prefix: str, *args, **kwargs) -> str:
    """
    Generate cache key from function arguments.

    Args:
        prefix: Cache key prefix
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Cache key string
    """
    # Create deterministic key from arguments
    key_data = {
        "args": [str(arg) for arg in args],
        "kwargs": {k: str(v) for k, v in sorted(kwargs.items())}
    }
    key_string = json.dumps(key_data, sort_keys=True)
    key_hash = hashlib.md5(key_string.encode()).hexdigest()
    return f"{prefix}:{key_hash}"


def cache_result(prefix: str, ttl: int = 300):
    """
    Decorator to cache function results in Redis.

    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds (default 5 minutes)

    Returns:
        Decorated function with caching
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            client = get_redis_client()

            # If Redis is unavailable, call function directly
            if client is None:
                return await func(*args, **kwargs)

            # Generate cache key
            cache_key = make_cache_key(prefix, *args, **kwargs)

            try:
                # Try to get cached result without blocking event loop
                cached = await asyncio.to_thread(client.get, cache_key)
                if cached is not None:
                    return json.loads(cached)
            except Exception as e:
                print(f"Cache read error: {e}")

            # Call function and cache result
            result = await func(*args, **kwargs)

            try:
                # Cache the result without blocking
                payload = json.dumps(result, default=str)
                await asyncio.to_thread(client.setex, cache_key, ttl, payload)
            except Exception as e:
                print(f"Cache write error: {e}")

            return result

        return wrapper
    return decorator


def invalidate_cache(prefix: str) -> int:
    """
    Invalidate all cache keys with given prefix.

    Args:
        prefix: Cache key prefix to invalidate

    Returns:
        Number of keys deleted
    """
    client = get_redis_client()

    if client is None:
        return 0

    try:
        # Find all keys with prefix
        pattern = f"{prefix}:*"
        keys = client.keys(pattern)

        if keys:
            return client.delete(*keys)
        return 0
    except Exception as e:
        print(f"Cache invalidation error: {e}")
        return 0


def get_cache_stats() -> dict:
    """
    Get Redis cache statistics.

    Returns:
        Dictionary with cache stats
    """
    client = get_redis_client()

    if client is None:
        return {
            "available": False,
            "error": "Redis connection unavailable"
        }

    try:
        info = client.info("stats")
        return {
            "available": True,
            "total_keys": client.dbsize(),
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate": info.get("keyspace_hits", 0) / max(
                info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1
            ) * 100,
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e)
        }
