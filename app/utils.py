import logging
import os
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List


@dataclass
class RateLimitConfig:
    max_requests: int = 10
    window_seconds: int = 60


class InMemoryRateLimiter:
    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()
        self.requests: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.config.window_seconds
        queue = self.requests[key]
        while queue and queue[0] < window_start:
            queue.popleft()
        if len(queue) >= self.config.max_requests:
            return False
        queue.append(now)
        return True


class InMemoryConversationStore:
    def __init__(self, max_messages: int = 8) -> None:
        self.max_messages = max_messages
        self.store: Dict[str, Deque[str]] = defaultdict(deque)

    def append(self, user_id: str, message: str) -> None:
        queue = self.store[user_id]
        queue.append(message)
        while len(queue) > self.max_messages:
            queue.popleft()

    def get(self, user_id: str) -> List[str]:
        return list(self.store[user_id])


def sanitize_text(text: str) -> str:
    cleaned = re.sub(r"[\r\n\t]+", " ", text or "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def configure_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
