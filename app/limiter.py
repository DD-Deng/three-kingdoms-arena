import os
from slowapi import Limiter
from slowapi.util import get_remote_address

_rate_limit = os.environ.get("ARENA_RATE_LIMIT", "5000/minute")
limiter = Limiter(key_func=get_remote_address, default_limits=[_rate_limit])
