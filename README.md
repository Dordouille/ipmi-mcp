# ipmi-mcp

> An **MCP (Model Context Protocol)** server that drives a server's **BMC over IPMI** (`ipmitool`) — power control, sensors, and system event log from your MCP client, with a safety model that never changes host state without explicit approval.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![MCP SDK](https://img.shields.io/badge/mcp-2.x-6E56CF)
![IPMI](https://img.shields.io/badge/IPMI-2.0%20lanplus-informational)
![License](https://img.shields.io/badge/license-MIT-green)

Point Claude Code, Claude Desktop, or any MCP client at your server's **baseboard management controller (BMC)** and manage it out-of-band — power the machine on or off, read temperatures and fans, inspect the system event log — in natural language, safely.

```
> is the lab server up, and how warm is it?

  ipmi_power_status()  ->  Chassis Power is on
  ipmi_sensors()       ->  CPU Temp 41 °C | MB Temp 33 °C | FAN1 1800 RPM …

The server is powered on and running cool — CPU at 41 °C, all four fans nominal.
```

**Vendor-neutral:** works with any IPMI 2.0 BMC — ASUS ASMB, Supermicro, Dell iDRAC, HPE iLO in IPMI mode, ASRock Rack, Lenovo XCC…

---

## Why

The BMC is the out-of-band controller that stays alive even when the host OS is off. IPMI is its lingua franca, and `ipmitool` speaks it over LAN (RMCP+ / `lanplus`). This server wraps `ipmitool` behind MCP tools so an assistant can **read** state freely, but can only **change** it (power off, reset, clear logs…) behind an explicit confirmation gate.

That gate is the point of the project. An assistant that can accidentally power-cycle a running server is not a tool you leave connected.

---

## 🔒 Security model — nothing changes without approval

Defense in depth, two independent layers.

**1. The read/write split is visible to the client.**

* `ipmi_read` — annotated *read-only*; refuses any subcommand not recognized as safe.
* `ipmi_exec` — annotated *destructive*, so the MCP client prompts for confirmation on its own.

**2. A server-side fail-safe, `fail-safe = deny`** — in [`classifier.py`](ipmi_mcp/classifier.py).

Client-side annotations are a hint, not a guarantee, so the server does not rely on them. A subcommand is treated as read-only **only if** it matches an **allowlist** of known-safe getters (`sensor list`, `sel elist`, `chassis status`, `mc info`…). **Everything else is presumed mutating** and is never executed without `confirm=true`. Actions that power off / cycle / reset the host, or reset the BMC, require `force=true` **on top**.

```
ipmi_exec("chassis power reset")
  → 🚨 HOST-CRITICAL — refused: needs confirm=true AND force=true

ipmi_exec("sel clear", confirm=true)
  → executed, audited

ipmi_exec("chassis power on", confirm=true)
  → executed (mutating, but not host-critical)
```

Every call — executed, previewed, or refused — is appended to a JSONL **audit log**.

**Credentials never hit the process list.** The password is handed to `ipmitool` through `-E` (the `IPMI_PASSWORD` environment variable), so it never appears in `ps` output, and the server reads it from a file you mount rather than from the repo — see [Credentials](#credentials).

---

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `ipmi_read(command)` | read | Runs an ipmitool subcommand **recognized as read-only**; refuses everything else. |
| `ipmi_exec(command, confirm, force)` | **write** | Arbitrary subcommand. Mutation blocked without `confirm=true`, and `force=true` on top if host-critical. |
| `ipmi_power_status()` | read | `chassis power status` |
| `ipmi_chassis_status()` | read | `chassis status` — power, fault, intrusion… |
| `ipmi_sensors()` | read | `sensor list` — temperatures, fans, voltages |
| `ipmi_sel()` | read | `sel elist` — system event log |
| `ipmi_mc_info()` | read | `mc info` — BMC firmware and IPMI version |
| `ipmi_refresh_sdr_cache()` | read | Dumps the BMC's SDR repository to a local cache — see [Slow links](#sensor-reads-over-a-slow-link-vpn) |

Power actions deliberately have **no dedicated tool**: they go through `ipmi_exec`, so they always hit the confirmation gate.

```
ipmi_exec("chassis power on",    confirm=True)
ipmi_exec("chassis power cycle", confirm=True, force=True)
```

---

## Requirements

* **Docker** — the recommended path; the image bundles `ipmitool`, so there is nothing to install on the host.
* **Network reach to the BMC** on UDP **623** (IPMI over LAN). The BMC's own IP, not the host OS's.
* **A BMC account.** `ADMINISTRATOR` is needed for power actions; `USER` or `OPERATOR` is enough if you only want to read — and is the safer choice if that is all you need.
* **IPMI-over-LAN enabled** in the BMC (it ships disabled on some boards).

Running without Docker instead is possible — `pip install .` plus an `ipmitool` binary on `PATH` — see [Running without Docker](#running-without-docker).

---

## Quick start

### 1. Configure

Copy `.env.example` to `.env` and fill in your BMC address and account:

| Variable | Purpose | Default |
|---|---|---|
| `IPMI_HOST` | BMC address | *required* |
| `IPMI_PORT` | IPMI port | `623` |
| `IPMI_USER` | BMC user | `admin` |
| `IPMI_PASSWORD_FILE` | **Path** to the file holding the password — never the password itself | `/run/secrets/ipmi_password` |
| `IPMI_INTERFACE` | `lanplus` (IPMI 2.0, recommended) or `lan` (1.5) | `lanplus` |
| `IPMI_PRIV_LEVEL` | `CALLBACK` / `USER` / `OPERATOR` / `ADMINISTRATOR` | `ADMINISTRATOR` |
| `IPMI_CIPHER_SUITE` | Only if the BMC demands a specific one (e.g. `3`, `17`) | negotiated |
| `IPMI_SDR_CACHE` | Local SDR cache path — see [Slow links](#sensor-reads-over-a-slow-link-vpn) | `/cache/sdr.bin` |
| `IPMI_CMD_TIMEOUT` | Per-command timeout, seconds | `120` |
| `IPMI_AUDIT_LOG` | JSONL audit log path | `/audit/ipmi-mcp.audit.jsonl` |

### Credentials

The BMC password is **not** stored in `.env`, and nothing in this repo ever holds it. Put it in its own file on the host — any path and name you like, outside the repo — and mount that file into the container. `.env` only points at the **in-container path**:

```sh
mkdir -p ~/.config/ipmi-mcp
printf '%s' 'your-bmc-password' > ~/.config/ipmi-mcp/credential   # no trailing newline
chmod 600 ~/.config/ipmi-mcp/credential
```

Then mount it read-only when launching the container (below):

```
-v ~/.config/ipmi-mcp/credential:/run/secrets/ipmi_password:ro
```

Portable and dependency-free — a plain file, no OS-specific keystore. An inline `IPMI_PASSWORD` env var still works as a fallback, but puts the secret in your `.env`.

### 2. Build the image

```sh
git clone https://github.com/Dordouille/ipmi-mcp.git
cd ipmi-mcp
docker build -t ipmi-mcp .
```

### 3. Wire it into your MCP client

**Claude Code:**

```sh
claude mcp add ipmi -- \
  docker run -i --rm \
    --env-file /abs/path/to/ipmi-mcp/.env \
    -v ~/.config/ipmi-mcp/credential:/run/secrets/ipmi_password:ro \
    -v /abs/path/to/ipmi-mcp/audit:/audit \
    -v /abs/path/to/ipmi-mcp/cache:/cache \
    ipmi-mcp
```

**JSON equivalent** (`.mcp.json`, Claude Desktop config, or any MCP client):

```json
{
  "mcpServers": {
    "ipmi": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--env-file", "/abs/path/to/ipmi-mcp/.env",
        "-v", "/Users/you/.config/ipmi-mcp/credential:/run/secrets/ipmi_password:ro",
        "-v", "/abs/path/to/ipmi-mcp/audit:/audit",
        "-v", "/abs/path/to/ipmi-mcp/cache:/cache",
        "ipmi-mcp"
      ]
    }
  }
}
```

Every path must be **absolute** — the client launches this process itself, with no shell to expand `~`. On macOS, GUI apps (Claude Desktop) do not inherit your `PATH`, so use the absolute docker binary path (`/usr/local/bin/docker`, or `which docker`) for `"command"`.

### 4. Check it works

Before involving the assistant, confirm the container can reach the BMC:

```sh
docker run -i --rm \
  --env-file /abs/path/to/ipmi-mcp/.env \
  -v ~/.config/ipmi-mcp/credential:/run/secrets/ipmi_password:ro \
  --entrypoint ipmitool ipmi-mcp \
  -I lanplus -H <bmc-ip> -U <user> -E mc info
```

If that prints BMC firmware information, the transport is fine and any remaining problem is in the client wiring. Then, in your MCP client, ask for the power status — the assistant should call `ipmi_power_status` and answer without prompting you, since it is read-only.

---

## Performance and troubleshooting

### Sensor reads over a slow link (VPN)

`ipmitool` re-reads the **whole SDR repository** on every sensor call — dozens of round-trips, which reliably times out over a high-latency link. Set `IPMI_SDR_CACHE`, call `ipmi_refresh_sdr_cache` **once**, and subsequent reads reuse the local dump (`-S`) and are fast. Mount the cache directory as a volume so it survives container restarts.

This is also why `IPMI_CMD_TIMEOUT` defaults to a generous 120 s: the *first* call, before the cache exists, needs the room.

### Common failures

| Symptom | Likely cause |
|---|---|
| `Error: Unable to establish IPMI v2 / RMCP+ session` | Wrong password, or IPMI-over-LAN disabled on the BMC. Test with `ipmitool` directly (step 4). |
| `Insufficient privilege level` | `IPMI_PRIV_LEVEL` is below what the command needs — power actions want `ADMINISTRATOR`. |
| Sensor reads time out, other calls work | The SDR repository re-read — set `IPMI_SDR_CACHE` and refresh it, above. |
| `No route to host` on UDP 623 | You are pointed at the host OS instead of the BMC, or the management VLAN is not reachable. |
| Session works, then the BMC stops answering HTTP while IPMI still replies | Some BMCs leak web sessions until exhausted. A BMC-only cold reset (`mc reset cold`) recovers it without touching the host. |

### Running without Docker

```sh
pip install .
export IPMI_HOST=<bmc-ip> IPMI_USER=<user> IPMI_PASSWORD_FILE=~/.config/ipmi-mcp/credential
ipmi-mcp        # speaks MCP over stdio
```

`ipmitool` must be on `PATH`  (`apt install ipmitool`, `brew install ipmitool`). The Docker path is recommended mainly because it pins that dependency.

---

## Remote console (KVM) — separate project

This server covers the IPMI **control plane**. It does not carry video: a graphical console is an interactive stream, which does not fit MCP's request/response tool model.

If your BMC only ever shipped a **Java (JViewer) remote console** — a `.jnlp` delivered by Java Web Start, which modern JREs removed, so the console no longer launches — that is solved in a sibling project:

**→ [`megarac-jviewer-kvm`](https://github.com/Dordouille/megarac-jviewer-kvm)** — runs the legacy viewer in a container and serves it to your browser over **noVNC**, no local Java. Verified on ASUS ASMB8-iKVM / ASPEED AST2400 / AMI MegaRAC 1.14, including the single-port-mode quirk that leaves the viewer stuck on *"Connection in progress"*.

For a **text** console, SOL works straight from `ipmitool` and needs none of that:

```sh
ipmitool -I lanplus -H <bmc-ip> -U admin -E sol activate     # ~. to exit
```

SOL is an interactive stream too, so it is not an MCP tool — but `sol info` is exposed read-only, to check the configuration.

---

## Development

```sh
pip install -e ".[dev]"
pytest
```

The test suite focuses on the **classifier** — read vs mutating, host-critical detection, and anti-bypass — because that is the security-critical component. A change that widens the read-only allowlist should come with a test showing what it now admits, and why that is safe.

Issues and PRs welcome, especially reports from BMC vendors other than the ones listed above.

## License

MIT — see [LICENSE](LICENSE).
