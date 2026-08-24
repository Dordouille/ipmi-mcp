"""Read / write classification of IPMI (ipmitool) subcommands — SECURITY CORE.

Principle: *fail-safe = deny*. A subcommand is classified as "read" only if it
matches the allowlist below. **Everything else is presumed mutating** and is
never executed without explicit approval.

The ``command`` here is the ipmitool *subcommand* (e.g. "chassis power status",
"sel list"), NOT a shell line — it is passed to ipmitool as separate argv tokens
by the ipmitool wrapper, so there is no shell to inject into. We still reject any
shell metacharacter defensively.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Kind(str, Enum):
    READ = "read"
    MUTATING = "mutating"


@dataclass(frozen=True)
class Classification:
    kind: Kind
    reason: str
    host_critical: bool = False


# Defensive: no shell metacharacter is ever legitimate in an ipmitool subcommand.
_SHELL_META = re.compile(r"(;|&&|\|\||\||>|<|`|\$\(|\n|\r)")

# READ-ONLY allowlist. Anchored patterns, matched on the normalized subcommand.
_READ_PATTERNS: list[re.Pattern[str]] = [
    # Power / chassis state (read only — NOT on/off/cycle/reset).
    re.compile(r"^(?:chassis\s+)?power\s+status$", re.I),
    re.compile(r"^chassis\s+status$", re.I),
    re.compile(r"^chassis\s+(?:restart_cause|poh|selftest)$", re.I),
    re.compile(r"^chassis\s+bootparam\s+get\b.*$", re.I),
    # Sensors / SDR (all read; NOT "sensor thresh").
    re.compile(r"^sdr(?:\s+(?:list|elist|info|get|type|entity)\b.*)?$", re.I),
    re.compile(r"^sensor(?:\s+(?:list|get|reading)\b.*)?$", re.I),
    # System Event Log — read only. NOTE: "sel clear" is mutating (excluded).
    re.compile(r"^sel(?:\s+(?:list|elist|info|get|time\s+get)\b.*)?$", re.I),
    # Management controller / BMC info (NOT "mc reset", "mc setenables").
    re.compile(r"^(?:mc|bmc)\s+(?:info|guid|getenables|getsysinfo\b.*|watchdog\s+get)$", re.I),
    re.compile(r"^(?:mc|bmc)\s+info$", re.I),
    # FRU inventory (read; NOT "fru write").
    re.compile(r"^fru(?:\s+(?:print|list|read)\b.*)?$", re.I),
    # LAN / channel / user / SOL — getters only.
    re.compile(r"^lan\s+(?:print|stats\s+get)\b.*$", re.I),
    re.compile(r"^channel\s+(?:info|getaccess|getciphers)\b.*$", re.I),
    re.compile(r"^user\s+(?:list|summary)\b.*$", re.I),
    re.compile(r"^sol\s+info\b.*$", re.I),
    re.compile(r"^session\s+info\b.*$", re.I),
    # DCMI power/thermal readings.
    re.compile(r"^dcmi\s+(?:power\s+get_limit|power\s+reading|get_temp_reading|discover|sensors)\b.*$", re.I),
]

# Commands that STOP / REBOOT / power-cycle the host, or reset the BMC: on top of
# confirm=true they also require force=true.
_HOST_CRITICAL = re.compile(
    r"^(?:chassis\s+)?power\s+(?:off|cycle|reset|soft)\b"
    r"|^chassis\s+power\s+(?:off|cycle|reset|soft)\b"
    r"|^mc\s+reset\b"
    r"|^bmc\s+reset\b",
    re.I,
)


def _normalize(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip())


def classify(command: str) -> Classification:
    """Return the classification (read/mutating) of an ipmitool subcommand."""
    norm = _normalize(command)
    if not norm:
        return Classification(Kind.MUTATING, "empty command")

    host_critical = bool(_HOST_CRITICAL.search(norm))

    if _SHELL_META.search(command):
        return Classification(
            Kind.MUTATING,
            "shell metacharacter — presumed mutating",
            host_critical,
        )

    for pattern in _READ_PATTERNS:
        if pattern.match(norm):
            return Classification(Kind.READ, "matches the read allowlist", host_critical)

    return Classification(
        Kind.MUTATING,
        "outside the read allowlist — presumed mutating (fail-safe)",
        host_critical,
    )


def is_read(command: str) -> bool:
    return classify(command).kind is Kind.READ
