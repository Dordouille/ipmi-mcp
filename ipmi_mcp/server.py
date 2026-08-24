"""MCP server exposing a BMC over IPMI (ipmitool).

Two generic tools form the foundation:
  - ``ipmi_read``  : read-only (refuses any mutating subcommand).
  - ``ipmi_exec``  : arbitrary subcommands, but no mutation without confirm=true
                     (and force=true on top for host-critical actions such as
                     power off/cycle/reset or a BMC reset).
Typed read helpers sit on top for convenience.
"""

from __future__ import annotations

import time

from mcp.server import MCPServer

try:  # annotations available depending on the SDK version
    from mcp.types import ToolAnnotations
except Exception:  # pragma: no cover
    ToolAnnotations = None  # type: ignore[assignment]

from . import audit
from .classifier import Kind, classify
from .config import Config
from .ipmi import IpmiTool

mcp = MCPServer("ipmi-mcp")

_config: Config | None = None
_ipmi: IpmiTool | None = None


def _get_ipmi() -> IpmiTool:
    """Instantiate config + ipmitool wrapper on first use (lazy)."""
    global _config, _ipmi
    if _ipmi is None:
        _config = Config.from_env()
        _ipmi = IpmiTool(_config)
    return _ipmi


def _audit_path() -> str | None:
    return _config.audit_log if _config else None


def _host() -> str:
    return _config.host if _config else "?"


def _ann(**kwargs):
    return ToolAnnotations(**kwargs) if ToolAnnotations else None


def _run_and_format(command: str, tool: str, kind: Kind, **extra) -> str:
    ipmi = _get_ipmi()
    start = time.time()
    try:
        result = ipmi.run(command)
    except Exception as error:  # noqa: BLE001 - we return the error to the client
        audit.log(_audit_path(), tool=tool, command=command, kind=kind.value,
                  executed=True, error=str(error), **extra)
        return f"❌ IPMI error while running « {command} »: {error}"
    duration = round(time.time() - start, 3)
    audit.log(_audit_path(), tool=tool, command=command, kind=kind.value,
              executed=True, exit_status=result.exit_status, duration_s=duration, **extra)
    lines = [f"ipmitool {command}", f"(exit={result.exit_status}, {duration}s)"]
    if result.stdout.strip():
        lines.append("--- stdout ---\n" + result.stdout.rstrip())
    if result.stderr.strip():
        lines.append("--- stderr ---\n" + result.stderr.rstrip())
    return "\n".join(lines)


@mcp.tool(
    annotations=_ann(
        title="IPMI — read-only",
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=True,
    )
)
def ipmi_read(command: str) -> str:
    """Run a READ-ONLY ipmitool subcommand against the BMC (e.g. "sensor list").

    Refuses any subcommand not recognized as safe. For a mutating action,
    use ``ipmi_exec`` (which will require confirm=true).
    """
    _get_ipmi()
    verdict = classify(command)
    if verdict.kind is not Kind.READ:
        audit.log(_audit_path(), tool="ipmi_read", command=command,
                  kind=verdict.kind.value, executed=False, reason=verdict.reason)
        return (
            f"⛔ REFUSED: « {command} » is not recognized as read-only "
            f"({verdict.reason}).\n"
            f"Use ipmi_exec (with confirm=true) for a mutating action."
        )
    return _run_and_format(command, tool="ipmi_read", kind=Kind.READ)


@mcp.tool(
    annotations=_ann(
        title="IPMI — exec (potentially mutating)",
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=True,
    )
)
def ipmi_exec(command: str, confirm: bool = False, force: bool = False) -> str:
    """Run an arbitrary ipmitool subcommand against the BMC.

    Security (fail-safe):
      - a recognized read subcommand runs directly;
      - any mutating subcommand is NOT executed without ``confirm=true``;
      - a host-critical action (power off/cycle/reset/soft, mc reset) requires
        ``force=true`` ON TOP.
    Without confirmation, the tool only returns a preview of what would run.
    """
    _get_ipmi()
    verdict = classify(command)

    if verdict.kind is Kind.READ:
        return _run_and_format(command, tool="ipmi_exec", kind=Kind.READ)

    if verdict.host_critical and not force:
        audit.log(_audit_path(), tool="ipmi_exec", command=command, kind="mutating",
                  host_critical=True, executed=False, confirm=confirm, force=force)
        return (
            "🚨 HOST-CRITICAL COMMAND — NOT executed.\n"
            f"This could POWER OFF / CYCLE / RESET host {_host()}:\n    ipmitool {command}\n"
            "Re-run ipmi_exec with confirm=true AND force=true if this is truly intended."
        )

    if not confirm:
        audit.log(_audit_path(), tool="ipmi_exec", command=command, kind="mutating",
                  executed=False, confirm=False)
        return (
            "⚠️ CONFIRMATION REQUIRED — NOT executed.\n"
            f"This WILL CHANGE the BMC/host {_host()}:\n    ipmitool {command}\n"
            f"Reason: {verdict.reason}.\n"
            "Re-run ipmi_exec with confirm=true to execute."
        )

    return _run_and_format(command, tool="ipmi_exec", kind=Kind.MUTATING,
                           confirm=True, force=force)


# --- Typed read helpers (convenience) ----------------------------------------

@mcp.tool(annotations=_ann(title="IPMI — power status", readOnlyHint=True))
def ipmi_power_status() -> str:
    """Current chassis power state (ipmitool chassis power status)."""
    return _run_and_format("chassis power status", tool="ipmi_power_status", kind=Kind.READ)


@mcp.tool(annotations=_ann(title="IPMI — chassis status", readOnlyHint=True))
def ipmi_chassis_status() -> str:
    """Detailed chassis status (power, fault, intrusion…)."""
    return _run_and_format("chassis status", tool="ipmi_chassis_status", kind=Kind.READ)


@mcp.tool(annotations=_ann(title="IPMI — sensors", readOnlyHint=True))
def ipmi_sensors() -> str:
    """List all sensor readings (temperatures, fans, voltages)."""
    return _run_and_format("sensor list", tool="ipmi_sensors", kind=Kind.READ)


@mcp.tool(annotations=_ann(title="IPMI — event log (SEL)", readOnlyHint=True))
def ipmi_sel() -> str:
    """List the System Event Log (ipmitool sel elist)."""
    return _run_and_format("sel elist", tool="ipmi_sel", kind=Kind.READ)


@mcp.tool(annotations=_ann(title="IPMI — BMC info", readOnlyHint=True))
def ipmi_mc_info() -> str:
    """Management controller info (firmware version, IPMI version…)."""
    return _run_and_format("mc info", tool="ipmi_mc_info", kind=Kind.READ)
