"""Centralised configuration — all env vars in one place."""

import os

# Server URL used when generating agent "接入指令" and API docs
ARENA_SERVER_URL: str = os.environ.get(
    "ARENA_SERVER_URL", "http://localhost:8000"
)

# Frontend URL for CORS origins (may differ from server in dev)
ARENA_FRONTEND_URL: str = os.environ.get(
    "ARENA_FRONTEND_URL", "http://localhost:5173"
)

# Environment label
ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development")

# CORS origins — comma-separated, or "*" to allow all
ARENA_CORS_ORIGINS: str = os.environ.get(
    "ARENA_CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8000",
)

# Admin token for protected endpoints
ADMIN_TOKEN: str = os.environ.get("ADMIN_TOKEN", "admin-dev-token")

# Alternative server URL env var (used by engine.py)
BASE_URL: str = os.environ.get("BASE_URL", ARENA_SERVER_URL)

# Tick advancement timing
TICK_INTERVAL_SEC: int = int(os.environ.get("TICK_INTERVAL_SEC", "15"))
TICK_TIMEOUT_SEC: int = int(os.environ.get("TICK_TIMEOUT_SEC", "20"))
MIN_OCCUPIED_TO_RUN: int = int(os.environ.get("MIN_OCCUPIED_TO_RUN", "1"))

# Restrict one faction per IP. Default False for dev (same machine multi-agent).
# Set to True in competitive/production mode to prevent multi-accounting.
ENFORCE_ONE_FACTION_PER_IP: bool = os.environ.get(
    "ENFORCE_ONE_FACTION_PER_IP", "false"
).lower() == "true"

# Occupation reward: grain awarded when capturing a city
OCCUPATION_REWARD_GRAIN: int = int(os.environ.get("OCCUPATION_REWARD_GRAIN", "200"))

# Economic catch-up: bonus grain for factions behind in city count.
# Disabled by default — enable after observing occupation reward effects.
ECONOMIC_CATCHUP_ENABLED: bool = os.environ.get(
    "ECONOMIC_CATCHUP_ENABLED", "false"
).lower() == "true"
ECONOMIC_CATCHUP_PER_CITY_BEHIND: float = float(
    os.environ.get("ECONOMIC_CATCHUP_PER_CITY_BEHIND", "0.10")
)

# Managed AI: when enabled, empty faction slots are filled by rule-based AI agents.
# Disable to require all-human lobbies.
ENABLE_MANAGED_AI: bool = os.environ.get("ENABLE_MANAGED_AI", "true").lower() == "true"

# Managed AI aggression: 0.0 = purely defensive, 1.0 = very aggressive.
MANAGED_AI_AGGRESSION: float = float(os.environ.get("MANAGED_AI_AGGRESSION", "0.3"))

# Managed AI recruit ratio: fraction of grain to spend on recruitment per tick.
MANAGED_AI_RECRUIT_RATIO: float = float(os.environ.get("MANAGED_AI_RECRUIT_RATIO", "0.3"))

# Countdown: seconds from all-3-ready to game start.
COUNTDOWN_SEC: int = int(os.environ.get("COUNTDOWN_SEC", "5"))
