"""
Redis connection utilities for consistent Redis client management
"""
import redis
from typing import Optional
from ..config import settings

class RedisConnectionManager:
    """Centralized Redis connection management"""
    
    _instance: Optional['RedisConnectionManager'] = None
    _redis_client: Optional[redis.Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._redis_client is None:
            self._redis_client = redis.from_url(
                settings.redis_url, 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
    
    @property
    def client(self) -> redis.Redis:
        """Get Redis client instance"""
        if self._redis_client is None:
            self.__init__()
        return self._redis_client
    
    def get_raw_client(self) -> redis.Redis:
        """Get Redis client without decode_responses for binary data"""
        return redis.from_url(
            settings.redis_url,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
    
    def ping(self) -> bool:
        """Test Redis connection"""
        try:
            return self.client.ping()
        except Exception:
            return False
    
    @classmethod
    def get_instance(cls) -> 'RedisConnectionManager':
        """Get singleton instance"""
        return cls()

# Global instance
redis_manager = RedisConnectionManager.get_instance()

def get_redis_client() -> redis.Redis:
    """Get Redis client instance"""
    return redis_manager.client

def get_raw_redis_client() -> redis.Redis:
    """Get Redis client for binary data"""
    return redis_manager.get_raw_client()