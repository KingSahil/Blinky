import hashlib
import time
from typing import Dict, Tuple, Optional

class FastLocatorCache:
    def __init__(self, ttl_seconds: float = 2.0):
        self._cache: Dict[str, Tuple[float, dict]] = {}
        self.ttl = ttl_seconds

    def compute_frame_hash(self, image_bytes: bytes) -> str:
        return hashlib.md5(image_bytes).hexdigest()

    def get(self, frame_hash: str, query: str) -> Optional[dict]:
        key = f"{frame_hash}:{query.lower().strip()}"
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < self.ttl:
                return data
        return None

    def set(self, frame_hash: str, query: str, data: dict):
        key = f"{frame_hash}:{query.lower().strip()}"
        self._cache[key] = (time.time(), data)
