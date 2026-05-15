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
TICK_INTERVAL_SEC: int = int(os.environ.get("TICK_INTERVAL_SEC", "5"))
TICK_TIMEOUT_SEC: int = int(os.environ.get("TICK_TIMEOUT_SEC", "8"))
MIN_OCCUPIED_TO_RUN: int = int(os.environ.get("MIN_OCCUPIED_TO_RUN", "1"))

# Restrict one faction per IP. Default False for dev (same machine multi-agent).
# Set to True in competitive/production mode to prevent multi-accounting.
ENFORCE_ONE_FACTION_PER_IP: bool = os.environ.get(
    "ENFORCE_ONE_FACTION_PER_IP", "false"
).lower() == "true"
