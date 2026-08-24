"""ipmitool wrapper: runs the BMC subcommands as separate argv tokens.

Security notes:
  - The password is passed to ipmitool via the ``-E`` flag, which reads it from
    the ``IPMI_PASSWORD`` environment variable. It is therefore never visible on
    the command line (``ps``) of the host.
  - The subcommand is split with ``shlex`` into argv tokens and appended to a
    fixed ``ipmitool`` invocation — there is no shell, so nothing to inject into.
"""

from __future__ import annotations

import os
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

    def _base_args(self, use_cache: bool = True) -> list[str]:
        cfg = self.config
        args = [
            "ipmitool",
            "-I", cfg.interface,
            "-H", cfg.host,
            "-p", str(cfg.port),
            "-U", cfg.user,
            "-L", cfg.priv_level,
        ]
        # Local SDR cache (-S): skip re-reading the SDR repository from the BMC
        # on every call — decisive on high-latency links. Populate it once with
        # `sdr dump <path>` (see IpmiTool.dump_sdr_cache / IPMI_SDR_CACHE).
        if use_cache and cfg.sdr_cache and os.path.exists(cfg.sdr_cache):
            args += ["-S", cfg.sdr_cache]
        if cfg.cipher_suite:
            args += ["-C", cfg.cipher_suite]
        if cfg.password:
            # -E reads the password from the IPMI_PASSWORD env var (see run()).
            args.append("-E")
        return args

    def run(self, command: str, use_cache: bool = True) -> CommandResult:
        argv = self._base_args(use_cache) + shlex.split(command)
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

    def dump_sdr_cache(self) -> CommandResult:
        """Populate the local SDR cache (``sdr dump <IPMI_SDR_CACHE>``).

        This is the one slow, round-trip-heavy call; afterwards every sensor
        read reuses the cache via ``-S`` and is fast even over a VPN. Runs
        without ``-S`` itself (we are (re)building the cache).
        """
        if not self.config.sdr_cache:
            raise RuntimeError(
                "IPMI_SDR_CACHE is not set — cannot build an SDR cache."
            )
        directory = os.path.dirname(self.config.sdr_cache)
        if directory:
            os.makedirs(directory, exist_ok=True)
        return self.run(f"sdr dump {self.config.sdr_cache}", use_cache=False)


def _os_environ() -> dict[str, str]:
    return dict(os.environ)
