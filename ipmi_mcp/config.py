"""Configuration read from the environment (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


@dataclass
class Config:
    host: str
    port: int
    user: str
    password: str | None
    interface: str
    priv_level: str
    cipher_suite: str | None
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
            password=_get("IPMI_PASSWORD"),
            interface=_get("IPMI_INTERFACE", "lanplus"),
            priv_level=_get("IPMI_PRIV_LEVEL", "ADMINISTRATOR"),
            cipher_suite=_get("IPMI_CIPHER_SUITE"),
            cmd_timeout=int(_get("IPMI_CMD_TIMEOUT", "30")),
            audit_log=_get("IPMI_AUDIT_LOG"),
        )
