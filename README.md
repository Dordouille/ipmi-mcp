# ipmi-mcp

> An **MCP (Model Context Protocol)** server that drives a server **BMC over IPMI** (`ipmitool`) — power control, sensors, and event log from your MCP client, with a safety model that never changes host state without explicit approval.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![MCP SDK](https://img.shields.io/badge/mcp-2.x-6E56CF)
![IPMI](https://img.shields.io/badge/IPMI-2.0%20lanplus-informational)
![License](https://img.shields.io/badge/license-MIT-green)

Point Claude Code, Claude Desktop, or any MCP client at your server's **baseboard management controller (BMC)** and manage it out-of-band — power the machine on/off, read temperatures and fans, inspect the system event log — through natural language, safely.

Sibling project to [`esxi-ssh-mcp`](https://github.com/Dordouille/esxi-ssh-mcp): same fail-safe security model, applied to the IPMI layer *below* the hypervisor.

---

## Why

The BMC is the out-of-band controller that stays alive even when the host OS is off. IPMI is its lingua franca, and `ipmitool` speaks it over LAN (RMCP+/`lanplus`). This server wraps `ipmitool` behind two MCP tools so an assistant can **read** state freely but can only **change** it (power off, reset, clear logs…) behind an explicit confirmation gate.

Vendor-neutral: works with any IPMI 2.0 BMC (ASUS ASMB, Supermicro, Dell iDRAC, HPE iLO in IPMI mode, ASRock Rack…).

---

## 🔒 Security model — nothing is changed without approval

Defense in depth, two layers:

**1. Read/write split into two MCP tools**
- `ipmi_read` — annotated *read-only*; refuses any subcommand not recognized as safe.
- `ipmi_exec` — annotated *destructive*; handles everything else, so the MCP client prompts for confirmation.

**2. Server-side fail-safe (`fail-safe = deny`)** — in [`classifier.py`](ipmi_mcp/classifier.py)

A subcommand is treated as **read-only** *only if* it matches an **allowlist** of safe getters (`sensor list`, `sel elist`, `chassis status`, `mc info`, …). **Everything else is presumed mutating** and is **never executed** without `confirm=true`. Actions that **power off / cycle / reset** the host, or **reset the BMC**, require `force=true` **on top**.

```
ipmi_exec("chassis power reset")
  → 🚨 HOST-CRITICAL — needs confirm=true AND force=true

ipmi_exec("sel clear", confirm=true)
  → executed, audited

ipmi_exec("chassis power on", confirm=true)
  → executed (mutating but not host-critical)
```

Every call — executed, previewed, or refused — is recorded in a JSONL **audit log**. The BMC password is passed to `ipmitool` via `-E` (the `IPMI_PASSWORD` env var), so it never appears on the host's process list.

---

## Tools

| Tool | Kind | Description |
|---|---|---|
| `ipmi_read(command)` | read | Runs an ipmitool subcommand **recognized as read-only**; refuses the rest. |
| `ipmi_exec(command, confirm, force)` | write | Arbitrary subcommand; mutation blocked without `confirm=true` (and `force=true` if host-critical). |
| `ipmi_power_status()` | read | `chassis power status` |
| `ipmi_chassis_status()` | read | `chassis status` (power, fault, intrusion…) |
| `ipmi_sensors()` | read | `sensor list` (temperatures, fans, voltages) |
| `ipmi_sel()` | read | `sel elist` (system event log) |
| `ipmi_mc_info()` | read | `mc info` (BMC firmware / IPMI version) |

Common power actions go through `ipmi_exec` (so they hit the confirmation gate), e.g.:
```
ipmi_exec("chassis power on", confirm=True)
ipmi_exec("chassis power cycle", confirm=True, force=True)
```

---

## Quick start

### 1. Configure

Copy `.env.example` to `.env` and fill in the BMC address and credentials:

| Variable | Purpose |
|---|---|
| `IPMI_HOST` / `IPMI_PORT` | BMC address (default IPMI port 623) |
| `IPMI_USER` | BMC user |
| `IPMI_PASSWORD_FILE` | **Path** to a secret file holding the password (the file is mounted in; the password is never in `.env`). `IPMI_PASSWORD` remains as an inline fallback. |
| `IPMI_INTERFACE` | `lanplus` (IPMI 2.0, recommended) or `lan` |
| `IPMI_PRIV_LEVEL` | `ADMINISTRATOR` / `OPERATOR` / `USER` |
| `IPMI_CIPHER_SUITE` | Optional (e.g. `3` or `17`) if the BMC requires one |
| `IPMI_SDR_CACHE` | Path to a local SDR cache (see below) |
| `IPMI_CMD_TIMEOUT` | Per-command timeout (s) |
| `IPMI_AUDIT_LOG` | JSONL audit log file |

**Credentials.** The BMC password is **not** stored in `.env` or anywhere in
this repo. Put it in its own file on the host — any path and name you like,
outside the repo — and mount that file into the container. `.env` only points at
the in-container path (`IPMI_PASSWORD_FILE`), never at the secret itself.
```sh
# create the credential file (in your own shell — keep it out of logs)
mkdir -p ~/.config/ipmi-mcp
printf '%s' 'your-bmc-password' > ~/.config/ipmi-mcp/credential
chmod 600 ~/.config/ipmi-mcp/credential
# then mount it read-only when launching the container (see wiring below):
#   -v ~/.config/ipmi-mcp/credential:/run/secrets/ipmi_password:ro
```
Portable and dependency-free — a plain file, no OS-specific keystore. The server
reads `IPMI_PASSWORD_FILE`; an inline `IPMI_PASSWORD` env var still works as a
fallback.

**Sensor reads over a slow link (VPN).** `ipmitool` re-reads the whole SDR
repository on every sensor call — dozens of round-trips, which times out over a
high-latency link. Set `IPMI_SDR_CACHE` and call the `ipmi_refresh_sdr_cache`
tool once to dump the SDR locally; subsequent reads reuse it (`-S`) and are fast.

### 2. Build the image

```sh
docker build -t ipmi-mcp .
```
(The image bundles `ipmitool` — nothing to install on the host.)

### 3. Wire it into your MCP client

```sh
claude mcp add ipmi -- \
  docker run -i --rm \
    --env-file /abs/path/to/ipmi_mcp/.env \
    -v ~/.config/ipmi-mcp/credential:/run/secrets/ipmi_password:ro \
    -v /abs/path/to/ipmi_mcp/audit:/audit \
    -v /abs/path/to/ipmi_mcp/cache:/cache \
    ipmi-mcp
```

JSON equivalent (`.mcp.json` / Claude Desktop config; on macOS GUI apps use the absolute docker path):
```json
{
  "mcpServers": {
    "ipmi": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--env-file", "/abs/path/to/ipmi_mcp/.env",
        "-v", "/Users/you/.config/ipmi-mcp/credential:/run/secrets/ipmi_password:ro",
        "-v", "/abs/path/to/ipmi_mcp/audit:/audit",
        "-v", "/abs/path/to/ipmi_mcp/cache:/cache",
        "ipmi-mcp"
      ]
    }
  }
}
```

---

## Remote console (roadmap)

Many older BMCs (e.g. ASPEED AST2400-based ASUS ASMB8) only ever shipped a **Java (JViewer) remote console**, delivered as a `.jnlp` via Java Web Start — which modern JREs have removed, so the console no longer launches. Firmware updates for that generation never added an HTML5 console.

Planned approach, tracked in [`console/`](console/):
- **Browser (HTML5) KVM** — run the legacy Java viewer inside a container (old JRE + IcedTea-Web) exposed through **noVNC**, so the graphical console opens in a browser with no local Java.
- **SOL (Serial-over-LAN)** — a text console via `ipmitool ... sol activate`, for BIOS/OS access when serial redirection is enabled.

Neither is wired into the MCP yet; this initial release covers the IPMI control plane.

---

## Development & tests

```sh
pip install -e ".[dev]"
pytest
```

The test suite focuses on the **classifier** (read vs mutating, host-critical, anti-bypass) — the security-critical component.

---

## License

MIT — see [LICENSE](LICENSE).
