"""Rate limiting utilities for API calls."""
import time
import logging
import asyncio
import random
from typing import TypeVar, Callable, Any, Optional
from functools import wraps
from dataclasses import dataclass
import aiohttp

logger = logging.getLogger(__name__)

T = TypeVar('T')

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    calls_per_second: float = 1.0  # Default to 1 call per second
    max_retries: int = 3
    initial_retry_delay: float = 1.0  # seconds
    max_retry_delay: float = 60.0  # seconds
    jitter: float = 0.1  # Random jitter factor

class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded and retries are exhausted."""
    pass

class APIRateLimiter:
    """Rate limiter for API calls with retry logic."""
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        """Initialize rate limiter.
        
        Args:
            config: Rate limit configuration
        """
        self.config = config or RateLimitConfig()
        self.last_call_time = 0.0
        self.min_interval = 1.0 / self.config.calls_per_second
    
    async def _wait_if_needed(self):
        """Wait if necessary to respect rate limits."""
        now = time.time()
        time_since_last_call = now - self.last_call_time
        
        if time_since_last_call < self.min_interval:
            wait_time = self.min_interval - time_since_last_call
            logger.debug(f"Rate limiting: waiting {wait_time:.2f} seconds")
            await asyncio.sleep(wait_time)
        
        self.last_call_time = time.time()
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt with exponential backoff and jitter.
        
        Args:
            attempt: Current retry attempt number
            
        Returns:
            Delay in seconds
        """
        delay = min(
            self.config.initial_retry_delay * (2 ** (attempt - 1)),
            self.config.max_retry_delay
        )
        
        # Add jitter
        jitter_amount = delay * self.config.jitter
        delay += random.uniform(-jitter_amount, jitter_amount)
        
        return max(0, delay)  # Ensure non-negative delay

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Make an API call with rate limiting and retries.
        
        Args:
            func: Async function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from func
            
        Raises:
            RateLimitExceeded: If rate limit is exceeded and retries are exhausted
            Exception: Any exception from func after retries
        """
        last_error = None
        
        for attempt in range(1, self.config.max_retries + 1):
            try:
                await self._wait_if_needed()
                return await func(*args, **kwargs)
                
            except aiohttp.ClientResponseError as e:
                if e.status == 429:  # Too Many Requests
                    retry_after = float(e.headers.get('Retry-After', self._calculate_retry_delay(attempt)))
                    logger.warning(f"Rate limit exceeded, waiting {retry_after} seconds (attempt {attempt}/{self.config.max_retries})")
                    await asyncio.sleep(retry_after)
                    last_error = e
                else:
                    raise
                    
            except Exception as e:
                if attempt == self.config.max_retries:
                    raise
                delay = self._calculate_retry_delay(attempt)
                logger.warning(f"API call failed, retrying in {delay:.2f} seconds (attempt {attempt}/{self.config.max_retries}): {str(e)}")
                await asyncio.sleep(delay)
                last_error = e
        
        raise RateLimitExceeded("Rate limit exceeded and retries exhausted") from last_error

def rate_limited(config: Optional[RateLimitConfig] = None):
    """Decorator for rate-limited async functions.
    
    Args:
        config: Rate limit configuration
        
    Returns:
        Decorated function
    """
    rate_limiter = APIRateLimiter(config)
    
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await rate_limiter.call(func, *args, **kwargs)
        return wrapper
    return decorator 