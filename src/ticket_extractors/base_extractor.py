import asyncio
from typing import TypeVar, Callable, Any
from functools import wraps

T = TypeVar('T')

class BaseExtractor:
    """Base class providing sync wrapper functionality for async methods."""
    
    def _make_sync(self, async_func: Callable[..., T]) -> Callable[..., T]:
        """Convert an async method to a sync method."""
        @wraps(async_func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(async_func(*args, **kwargs))
            finally:
                loop.close()
        return sync_wrapper 