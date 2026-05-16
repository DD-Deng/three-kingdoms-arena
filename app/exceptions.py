"""Structured error codes for the Three Kingdoms Arena API.

Taxonomy:
  - tactical   — invalid game action (can learn & retry)
  - protocol   — game/protocol state violation (retry with care)
  - auth       — authentication or session issue
  - rate_limit — rate-limited, back off
"""

from enum import Enum


class ErrorCategory(str, Enum):
    tactical = "tactical"
    protocol = "protocol"
    auth = "auth"
    rate_limit = "rate_limit"


# ── Error code registry ───────────────────────────────────────
# (error_code, category, retry_safe)
_ERROR_DEFS: dict[str, tuple[ErrorCategory, bool]] = {
    # ── tactical ──────────────────────────────────────────
    "TACTICAL_INVALID_ACTION":        (ErrorCategory.tactical, True),
    "TACTICAL_INSUFFICIENT_TROOPS":   (ErrorCategory.tactical, True),
    "TACTICAL_INSUFFICIENT_GRAIN":    (ErrorCategory.tactical, True),
    "TACTICAL_NOT_YOUR_CITY":         (ErrorCategory.tactical, True),
    "TACTICAL_NOT_ADJACENT":          (ErrorCategory.tactical, True),
    "TACTICAL_CANNOT_ATTACK_OWN":     (ErrorCategory.tactical, True),
    "TACTICAL_CANNOT_ATTACK_ALLY":    (ErrorCategory.tactical, True),
    "TACTICAL_DIPLOMACY_TARGET_SELF":  (ErrorCategory.tactical, True),
    "TACTICAL_INVALID_DIPLOMACY_TYPE": (ErrorCategory.tactical, True),
    "TACTICAL_TRUST_TOO_LOW":         (ErrorCategory.tactical, True),
    "TACTICAL_BETRAYAL_COOLDOWN":     (ErrorCategory.tactical, True),
    "TACTICAL_ALREADY_ALLIED":        (ErrorCategory.tactical, True),
    "TACTICAL_NOT_ALLIED":            (ErrorCategory.tactical, True),
    "TACTICAL_NO_PENDING_ALLIANCE":   (ErrorCategory.tactical, True),
    "TACTICAL_ACTIONS_EMPTY":         (ErrorCategory.tactical, True),
    "TACTICAL_NO_VALID_ACTIONS":      (ErrorCategory.tactical, False),
    "TACTICAL_FACTION_ELIMINATED":    (ErrorCategory.tactical, False),
    "TACTICAL_RECRUIT_EXCEEDS_MAX":   (ErrorCategory.tactical, True),
    "TACTICAL_MESSAGE_TOO_LONG":      (ErrorCategory.tactical, True),
    "TACTICAL_RENEW_TOO_EARLY":       (ErrorCategory.tactical, True),
    "TACTICAL_AT_WAR":                (ErrorCategory.tactical, True),
    # ── protocol ──────────────────────────────────────────
    "PROTOCOL_GAME_NOT_FOUND":        (ErrorCategory.protocol, True),
    "PROTOCOL_GAME_FINISHED":         (ErrorCategory.protocol, False),
    "PROTOCOL_GAME_PAUSED":           (ErrorCategory.protocol, True),
    "PROTOCOL_DUPLICATE_SUBMIT":      (ErrorCategory.protocol, True),
    "PROTOCOL_ALREADY_STARTED":       (ErrorCategory.protocol, False),
    "PROTOCOL_GAME_STILL_IN_PROGRESS": (ErrorCategory.protocol, True),
    "PROTOCOL_SLOT_DISCONNECTED":     (ErrorCategory.protocol, True),
    # ── auth ──────────────────────────────────────────────
    "AUTH_INVALID_TOKEN":             (ErrorCategory.auth, False),
    "AUTH_SESSION_EXPIRED":           (ErrorCategory.auth, False),
    "AUTH_SESSION_KICKED":            (ErrorCategory.auth, False),
    "AUTH_SESSION_DISCONNECTED":      (ErrorCategory.auth, True),
    "AUTH_FACTION_OCCUPIED":          (ErrorCategory.auth, True),
    "AUTH_NOT_AUTHORIZED":            (ErrorCategory.auth, False),
    "AUTH_AGENT_NOT_REGISTERED":      (ErrorCategory.auth, False),
    "AUTH_SECRET_INCORRECT":          (ErrorCategory.auth, False),
    # ── rate_limit ────────────────────────────────────────
    "RATE_LIMIT_ONE_PER_IP":          (ErrorCategory.rate_limit, True),
}


class ArenaException(Exception):
    """Base exception for structured API errors."""

    def __init__(self, error_code: str, detail: str = "", status_code: int = 400):
        cat, retry = _ERROR_DEFS.get(error_code, (ErrorCategory.protocol, True))
        self.error_code = error_code
        self.category = cat
        self.retry_safe = retry
        self.detail = detail or error_code
        self.status_code = status_code
        super().__init__(detail or error_code)

    def as_response(self) -> dict:
        return {
            "error_code": self.error_code,
            "category": self.category.value,
            "detail": self.detail,
            "retry_safe": self.retry_safe,
        }


# ── Convenience constructors ──────────────────────────────────


def tactical(code: str, detail: str = "") -> ArenaException:
    return ArenaException(code, detail, status_code=400)


def protocol(code: str, detail: str = "") -> ArenaException:
    status = 409
    if code == "PROTOCOL_GAME_FINISHED":
        status = 410
    elif code == "PROTOCOL_GAME_NOT_FOUND":
        status = 404
    return ArenaException(code, detail, status_code=status)


def auth_error(code: str, detail: str = "") -> ArenaException:
    return ArenaException(code, detail, status_code=401)


def rate_limit(code: str, detail: str = "") -> ArenaException:
    return ArenaException(code, detail, status_code=429)
