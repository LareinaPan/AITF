"""Sanitize performance test error log messages before persistence or API output."""

from __future__ import annotations

import re

_SENSITIVE_HEADER_NAMES = (
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
)

_SENSITIVE_HEADER_PATTERN = re.compile(
    rf"(?i)\b({'|'.join(_SENSITIVE_HEADER_NAMES)})\s*[:=]\s*(?:Bearer\s+)?\S+(?:\s+\S+)*"
)
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)(Bearer\s+)([^\s,;]+)")
_JWT_LIKE_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)


def sanitize_error_message(message: str | None) -> str:
    """Redact sensitive header values and bearer tokens from error summaries."""
    if not message:
        return ""

    sanitized = _SENSITIVE_HEADER_PATTERN.sub(
        lambda match: f"{match.group(1)}: ***",
        message,
    )
    sanitized = _BEARER_TOKEN_PATTERN.sub(r"\1***", sanitized)
    sanitized = _JWT_LIKE_PATTERN.sub("***", sanitized)
    return sanitized
