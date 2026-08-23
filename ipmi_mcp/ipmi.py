"""ipmitool wrapper: runs the BMC subcommands as separate argv tokens.

Security notes:
  - The password is passed to ipmitool via the ``-E`` flag, which reads it from
    the ``IPMI_PASSWORD`` environment variable. It is therefore never visible on
    the command line (``ps``) of the host.
  - The subcommand is split with ``shlex`` into argv tokens and appended to a
    fixed ``ipmitool`` invocation — there is no shell, so nothing to inject into.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass

from .config import Config


@dataclass
class CommandResult:
    command: str
    exit_status: int
    stdout: str
    stderr: str


class IpmiTool:
    def __init__(self, config: Config) -> None:
        self.config = config

    def _base_args(self) -> list[str]:
        cfg = self.config
        args = [
            "ipmitool",
            "-I", cfg.interface,
            "-H", cfg.host,
            "-p", str(cfg.port),
            "-U", cfg.user,
            "-L", cfg.priv_level,
        ]
        if cfg.cipher_suite:
            args += ["-C", cfg.cipher_suite]
        if cfg.password:
            # -E reads the password from the IPMI_PASSWORD env var (see run()).
            args.append("-E")
        return args

    def run(self, command: str) -> CommandResult:
        argv = self._base_args() + shlex.split(command)
        env = {"IPMI_PASSWORD": self.config.password} if self.config.password else {}
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.config.cmd_timeout,
                env={**_os_environ(), **env},
            )
        except FileNotFoundError as error:  # ipmitool not installed
            raise RuntimeError(
                "ipmitool not found in PATH — install it (the Docker image bundles it)."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"ipmitool timed out after {self.config.cmd_timeout}s for « {command} »."
            ) from error
        return CommandResult(command, proc.returncode, proc.stdout, proc.stderr)


def _os_environ() -> dict[str, str]:
    import os

    return dict(os.environ)
