from django.conf import settings
from django.core.cache import cache


class CacheService:
    def __init__(self, prefix: str, ttl: int):
        self._prefix = prefix
        self._ttl = ttl

    def _key(self, identifier: str) -> str:
        return f"{self._prefix}:{identifier}"

    def get(self, identifier: str):
        return cache.get(self._key(identifier))

    def set(self, identifier: str, data) -> None:
        cache.set(self._key(identifier), data, timeout=self._ttl)

    def invalidate(self, identifier: str) -> None:
        cache.delete(self._key(identifier))


deployment_cache = CacheService(
    "deployment", ttl=settings.DEPLOYMENT_CACHE_TTL
)
