# Remote console (KVM)

The BMC (ASUS ASMB8-iKVM, ASPEED AST2400, AMI MegaRAC) only ships a **Java
(JViewer) remote console** delivered as a `.jnlp` via Java Web Start — removed
from modern JREs — and its last firmware (1.14.51, 2017) never added an HTML5
console. On top of that, the BMC only negotiates **legacy TLS**, which modern
local browsers/JREs refuse outright. So the console cannot be opened directly
from a current desktop.

## Approach 1 — Browser (HTML5) console, no local Java  *(recommended)*

Use [`nojava-ipmi-kvm`](https://github.com/sciapp/nojava-ipmi-kvm) (based on
`solarkennedy/ipmi-kvm-docker`): it runs the legacy Java Web Start viewer inside
a **Docker container** (old Java + old TLS stack) and serves it in your browser
through **noVNC**. Nothing old is installed on your machine; the container talks
to the BMC's legacy stack for you.

### 1. Install (pinned)

```sh
# Python 3.13, NOT 3.14 (3.14 breaks the tool's asyncio.get_event_loop()).
# Pin 0.9.2: 0.9.3 has no matching Docker image on Docker Hub.
pipx install --python python3.13 nojava-ipmi-kvm==0.9.2
cp console/nojava-ipmi-kvmrc.example.yaml ~/.nojava-ipmi-kvmrc.yaml
```

The config ([`nojava-ipmi-kvmrc.example.yaml`](nojava-ipmi-kvmrc.example.yaml)) is
tuned for this BMC — AMI MegaRAC login (`rpc/WEBSES/create.asp`) + `Java/jviewer.jnlp`,
verified live. Set `login_user` to your BMC account; the password is **prompted at
runtime** (never written to disk).

### 2. Build the legacy-TLS image (required for this BMC)

This BMC only speaks **TLS 1.0 + RC4-MD5**. Modern OpenSSL/Python — including the
one inside nojava's own container — refuses RC4, so the HTTPS login fails with
`SSLV3_ALERT_HANDSHAKE_FAILURE`. The image in
[`nojava-legacy-tls/`](nojava-legacy-tls/) re-enables RC4-MD5 (it replaces
urllib3's `ssl_wrap_socket`). Build it tagged as the image the tool expects, so it
is used locally without a re-pull:

```sh
docker build --platform linux/amd64 \
  -t sciapp/nojava-ipmi-kvm:v0.9.2-openjdk-7 console/nojava-legacy-tls
```

### 3. Run

```sh
nojava-ipmi-kvm --debug lszesxi          # prompts for the BMC password
```

nojava prints a URL using the **container's internal hostname and port 8080**, e.g.
`http://<container-id>:8080/vnc.html?...`, which your browser can't reach. Find the
published port with `docker ps` (it maps 8080 to a random host port), then open:

```
http://localhost:<mapped-port>/vnc.html?host=localhost&port=<mapped-port>
```

Keep the `nojava-ipmi-kvm` terminal open — it holds the container (and the port).

**If the BMC web UI is unresponsive** (MegaRAC web servers hang while IPMI still
answers — HTTP times out but `ipmi_mc_info` works), cold-reset the BMC (restarts
the controller, **not** the host; ~1–2 min):
```sh
ipmitool -I lanplus -H 192.168.1.12 -U <user> -f <passwordfile> mc reset cold
```

## Approach 2 — SOL (Serial-over-LAN), text console  *(complementary)*

A lightweight text console (BIOS + OS, when serial console redirection is enabled
in the BIOS), straight from `ipmitool`:

```sh
ipmitool -I lanplus -H 192.168.1.12 -U admin -E sol activate     # ~. to exit
# (export IPMI_PASSWORD or pass -f <file>; deactivate a stuck session with:)
ipmitool -I lanplus -H 192.168.1.12 -U admin -E sol deactivate
```

SOL is an interactive stream, so it lives here as a documented command rather
than an MCP tool — the request/response tool model doesn't fit a live console.
The MCP server still exposes `sol info` (read-only) to check SOL configuration.

## Why not a firmware update or Redfish

The AST2400/ASMB8 generation never received an HTML5 iKVM (that arrived with the
AST2500/ASMB9 boards), and its Redfish support is absent/too limited to drive a
console. Flashing the 2017 beta firmware would neither add HTML5 nor help — hence
the containerized-viewer approach above.
