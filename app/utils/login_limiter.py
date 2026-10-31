import threading
import time
from collections import deque

from config import LOGIN_BLOCK_MINUTES, LOGIN_MAX_ATTEMPTS

_lock = threading.Lock()
_failures: dict = {}  # ip -> deque of failure timestamps inside the window
_blocked_until: dict = {}  # ip -> unix time the block ends


def _enabled() -> bool:
    return LOGIN_MAX_ATTEMPTS > 0 and LOGIN_BLOCK_MINUTES > 0


def blocked_for(ip: str) -> int:
    """Seconds left on this IP's block, 0 if it may try to log in."""
    if not _enabled():
        return 0
    with _lock:
        until = _blocked_until.get(ip)
        if not until:
            return 0
        left = until - time.time()
        if left <= 0:
            del _blocked_until[ip]
            return 0
        return int(left) + 1


def record_failure(ip: str) -> bool:
    """Count a failed login; True when it just got this IP blocked."""
    if not _enabled():
        return False
    window = LOGIN_BLOCK_MINUTES * 60
    now = time.time()
    with _lock:
        # drop IPs that went quiet so the dicts don't grow with every scanner
        for stale in [k for k, v in _failures.items() if not v or v[-1] < now - window]:
            del _failures[stale]
        for stale in [k for k, v in _blocked_until.items() if v <= now]:
            del _blocked_until[stale]

        attempts = _failures.setdefault(ip, deque())
        attempts.append(now)
        while attempts and attempts[0] < now - window:
            attempts.popleft()
        if len(attempts) >= LOGIN_MAX_ATTEMPTS:
            _blocked_until[ip] = now + window
            del _failures[ip]
            return True
        return False


def record_success(ip: str):
    with _lock:
        _failures.pop(ip, None)
