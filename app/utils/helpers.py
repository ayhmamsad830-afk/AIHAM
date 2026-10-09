import time
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def generate_id() -> str:
    """Generate a unique ID for documents."""
    return uuid.uuid4().hex

class Timer:
    """Simple context manager for timing operations."""
    
    def __init__(self, name: Optional[str] = None):
        self.name = name
        self.start_time = None
        self.end_time = None
        self.interval = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.interval = self.end_time - self.start_time
        
        if self.name:
            logger.info(f"{self.name} took {self.interval:.2f} seconds")
        
        return False  # Don't suppress exceptions