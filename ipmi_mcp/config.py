"""Configuration read from the environment (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _read_password() -> str | None:
    """Resolve the BMC password, preferring a secret *file* over an env var.

    ``IPMI_PASSWORD_FILE`` holds a *path* (never the secret itself) — mount the
    secret file into the container and point this at it. Falls back to the
    ``IPMI_PASSWORD`` env var for convenience.
    """
    path = _get("IPMI_PASSWORD_FILE")
    if path:
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read().strip() or None
        except OSError as error:
            raise RuntimeError(
                f"Cannot read IPMI_PASSWORD_FILE ({path}): {error}"
            ) from error
    return _get("IPMI_PASSWORD")


@dataclass
class Config:
    host: str
    port: int
    user: str
    password: str | None
    interface: str
    priv_level: str
    cipher_suite: str | None
    sdr_cache: str | None
    cmd_timeout: int
    audit_log: str | None

    @classmethod
    def from_env(cls) -> "Config":
        host = _get("IPMI_HOST")
        if not host:
            raise RuntimeError(
                "IPMI_HOST missing: set the BMC address (see .env.example)."
            )
        return cls(
            host=host,
            port=int(_get("IPMI_PORT", "623")),
            user=_get("IPMI_USER", "admin"),
            password=_read_password(),
            interface=_get("IPMI_INTERFACE", "lanplus"),
            priv_level=_get("IPMI_PRIV_LEVEL", "ADMINISTRATOR"),
            cipher_suite=_get("IPMI_CIPHER_SUITE"),
            sdr_cache=_get("IPMI_SDR_CACHE"),
            # 120s default: over a high-latency link (VPN) ipmitool needs many
            # round-trips to read the SDR repository; see IPMI_SDR_CACHE.
            cmd_timeout=int(_get("IPMI_CMD_TIMEOUT", "120")),
            audit_log=_get("IPMI_AUDIT_LOG"),
        )
