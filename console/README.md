# Remote console (KVM) — plan

The target BMC (ASUS ASMB8-iKVM, ASPEED AST2400) only ships a **Java (JViewer)**
remote console delivered as a `.jnlp` (Java Web Start). Modern JREs removed Java
Web Start, so the console no longer launches, and the last firmware for this
generation (1.14.51, 2017) never added an HTML5 console.

## Approach 1 — Browser (HTML5) KVM via noVNC  *(preferred)*

Run the legacy Java viewer inside a container and expose it through the browser,
so no Java is needed on the client:

```
BMC  ──(HTTPS, downloads JViewer)──►  container
                                        ├─ old JRE + IcedTea-Web (javaws) → runs JViewer
                                        ├─ headless X server (Xvfb) + window manager
                                        ├─ x11vnc  → serves the viewer's display over VNC
                                        └─ noVNC + websockify → HTML5 in the browser
```

Result: open `http://<docker-host>:<port>/` → the full graphical KVM console.

Open questions to resolve when implementing:
- Exact JRE version the ASMB8 firmware 1.14 requires (the firmware notes say
  "JAVA 8 update 131 or later"), and whether IcedTea-Web can launch its `.jnlp`.
- Whether the viewer authenticates against the BMC directly or needs a session
  token fetched from the web UI first.

## Approach 2 — SOL (Serial-over-LAN)  *(complementary, text)*

```
ipmitool -I lanplus -H <bmc> -U <user> -E sol activate
```

A text console (BIOS + OS) when serial console redirection is enabled in the
BIOS. Simple and robust; candidate for integration as an MCP tool, though SOL is
an interactive stream and needs care to fit the request/response tool model.

## Status

Not implemented yet — the initial `ipmi-mcp` release covers the IPMI control
plane (power, sensors, SEL). This directory holds the console work.
