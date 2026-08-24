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

```sh
python3 -m pip install nojava-ipmi-kvm      # Python 3.5+, needs Docker/Podman
cp console/nojava-ipmi-kvmrc.example.yaml ~/.nojava-ipmi-kvmrc.yaml
nojava-ipmi-kvm lszengine                   # prompts for the BMC password
```

It opens the KVM console in your browser. The provided config
([`nojava-ipmi-kvmrc.example.yaml`](nojava-ipmi-kvmrc.example.yaml)) is tuned for
this BMC — the AMI MegaRAC login (`rpc/WEBSES/create.asp`) and `Java/jviewer.jnlp`
endpoints were verified live against it.

Notes:
- The password is **prompted at runtime** — never written to disk.
- Over a VPN the console is usable but laggy (BMC RTT can reach ~0.5–0.7 s).
- If the applet fails to load, try another `java_version` in the config
  (`8u91`, `7u79`) — AMI/JViewer builds are picky about the exact JRE.

## Approach 2 — SOL (Serial-over-LAN), text console  *(complementary)*

A lightweight text console (BIOS + OS, when serial console redirection is enabled
in the BIOS), straight from `ipmitool`:

```sh
ipmitool -I lanplus -H 192.0.2.10 -U admin -E sol activate     # ~. to exit
# (export IPMI_PASSWORD or pass -f <file>; deactivate a stuck session with:)
ipmitool -I lanplus -H 192.0.2.10 -U admin -E sol deactivate
```

SOL is an interactive stream, so it lives here as a documented command rather
than an MCP tool — the request/response tool model doesn't fit a live console.
The MCP server still exposes `sol info` (read-only) to check SOL configuration.

## Why not a firmware update or Redfish

The AST2400/ASMB8 generation never received an HTML5 iKVM (that arrived with the
AST2500/ASMB9 boards), and its Redfish support is absent/too limited to drive a
console. Flashing the 2017 beta firmware would neither add HTML5 nor help — hence
the containerized-viewer approach above.
