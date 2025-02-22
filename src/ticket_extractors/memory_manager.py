"""Memory management utilities for handling large data sets."""
import os
import psutil
import logging
import gc
from typing import Optional, Dict, Any, Generator
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class MemoryConfig:
    """Configuration for memory management."""
    max_memory_percent: float = 80.0  # Maximum memory usage as percentage of system memory
    cleanup_threshold: float = 70.0  # Threshold to trigger cleanup
    chunk_size: int = 1000  # Number of items to process in each chunk
    enable_monitoring: bool = True

class MemoryError(Exception):
    """Raised when memory limits are exceeded."""
    pass

class MemoryManager:
    """Memory manager for handling large data sets."""
    
    def __init__(self, config: Optional[MemoryConfig] = None):
        """Initialize memory manager.
        
        Args:
            config: Memory management configuration
        """
        self.config = config or MemoryConfig()
        self._process = psutil.Process(os.getpid())
    
    def get_memory_usage(self) -> float:
        """Get current memory usage as percentage.
        
        Returns:
            Memory usage percentage
        """
        return self._process.memory_percent()
    
    def check_memory(self) -> None:
        """Check memory usage and cleanup if needed.
        
        Raises:
            MemoryError: If memory usage exceeds maximum limit
        """
        if not self.config.enable_monitoring:
            return
            
        usage = self.get_memory_usage()
        
        if usage > self.config.max_memory_percent:
            raise MemoryError(f"Memory usage ({usage:.1f}%) exceeds maximum limit ({self.config.max_memory_percent}%)")
            
        if usage > self.config.cleanup_threshold:
            logger.warning(f"Memory usage high ({usage:.1f}%), triggering cleanup")
            self.cleanup()
    
    def cleanup(self) -> None:
        """Perform memory cleanup."""
        gc.collect()
    
    def chunk_generator(self, data: list) -> Generator[list, None, None]:
        """Generate chunks of data for processing.
        
        Args:
            data: List of items to chunk
            
        Yields:
            Chunks of data
        """
        for i in range(0, len(data), self.config.chunk_size):
            yield data[i:i + self.config.chunk_size]
    
    def process_in_chunks(self, data: list, processor: callable) -> list:
        """Process data in chunks to manage memory usage.
        
        Args:
            data: List of items to process
            processor: Function to process each chunk
            
        Returns:
            List of processed results
            
        Raises:
            MemoryError: If memory limits are exceeded
        """
        results = []
        
        for chunk in self.chunk_generator(data):
            self.check_memory()
            chunk_result = processor(chunk)
            results.extend(chunk_result)
            
        return results

class MemoryMonitor:
    """Context manager for monitoring memory usage during operations."""
    
    def __init__(self, manager: MemoryManager, operation_name: str):
        """Initialize memory monitor.
        
        Args:
            manager: Memory manager instance
            operation_name: Name of the operation being monitored
        """
        self.manager = manager
        self.operation_name = operation_name
        self.start_usage = 0.0
    
    def __enter__(self):
        """Enter context and record starting memory usage."""
        self.start_usage = self.manager.get_memory_usage()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and log memory usage."""
        end_usage = self.manager.get_memory_usage()
        delta = end_usage - self.start_usage
        
        if delta > 5.0:  # Only log significant changes
            logger.info(
                f"Memory usage for {self.operation_name}: "
                f"Start: {self.start_usage:.1f}%, "
                f"End: {end_usage:.1f}%, "
                f"Delta: {delta:+.1f}%"
            )

def memory_managed(operation_name: str):
    """Decorator for memory-managed operations.
    
    Args:
        operation_name: Name of the operation for logging
        
    Returns:
        Decorated function
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            manager = getattr(args[0], '_memory_manager', MemoryManager())
            with MemoryMonitor(manager, operation_name):
                return func(*args, **kwargs)
        return wrapper
    return decorator 