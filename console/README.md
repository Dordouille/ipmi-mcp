# Remote console (KVM)

The BMC (ASUS ASMB8-iKVM, ASPEED AST2400, AMI MegaRAC, firmware 1.14) ships only
a **Java (JViewer) remote console**, delivered as a `.jnlp` via Java Web Start --
a mechanism removed from modern JREs -- and its last firmware (1.14.51, 2017)
never added an HTML5 console. So the console cannot be opened from a current
desktop without help.

The approach below runs the legacy viewer inside a container and serves it to
your browser over noVNC. **It works**, but only after three firmware quirks are
worked around. They are worth reading before touching anything, because each one
fails in a way that points somewhere else entirely.

## The three quirks

### 1. The launch file needs two query parameters

`Java/jviewer.jnlp` on its own returns an error page where the launch arguments
should be. Both parameters are mandatory:

```
Java/jviewer.jnlp?EXTRNIP=<bmc-ip>&JNLPSTR=JViewer
```

* `JNLPSTR=JViewer` -- without it the body reads *"Unable to find JNLP String"*.
* `EXTRNIP` -- copied **verbatim** into JViewer's `-hostname` argument. It must
  be the BMC's own address. Point it at the client by mistake and the BMC
  cheerfully builds a launch file telling the viewer to connect to the client.

The response also declares `Content-Length: 4134` while sending ~3154 bytes. The
document is nevertheless **complete** (`</application-desc></jnlp>`); only the
header is wrong. An HTTP client that treats a short read as fatal will discard a
perfectly good file -- read the partial body instead
(`http.client.IncompleteRead.partial`).

### 2. The KVM stream runs on port 80, not 7578

This BMC runs in **single-port mode** (`-singleportenabled 1`). Video redirection
and virtual media are multiplexed onto the **web server port**. Ports
7578/7582/5120/5123 answer with TCP RST and are never used, even though the
*Configuration -> Services* page still lists them:

```
2  kvm  Active  both  7578  7582  1800  4  View
```

That display is the stored configuration; single-port mode overrides it. A viewer
aimed at 7578 sits at *"Connection in progress"* forever, which reads like an
authentication or privilege problem and is neither.

Which port the BMC hands out depends on **the scheme of the session that asked**:

| Login over | `-kvmsecure` | `-kvmport` |
|------------|--------------|------------|
| HTTPS      | `1`          | `443`      |
| HTTP       | `0`          | `80`       |

The BMC's HTTPS side only negotiates **TLS 1.0 + RC4-MD5**, which no current JRE
will do -- so asking over HTTPS hands the viewer a transport it cannot open. The
BMC serves its **entire web UI in the clear on port 80** with no redirect, so
asking over HTTP yields a plaintext video stream and the TLS problem disappears.
`megarac-patch` therefore forces the container to speak HTTP.

### 3. The launch file has no `main-class`

The firmware emits a bare `<application-desc>` and relies on the jar manifest
(which does carry `Main-Class: com.ami.kvm.jviewer.JViewer`). This netx build
does not cope, and dies with a `NullPointerException` before JViewer's `main()`
runs. The patch injects the attribute. It also repairs the
`codebase="http://(null):80/Java"` the firmware emits, without which the jars
cannot be resolved.

## Usage

### 1. Install (pinned)

```sh
# Python 3.13, NOT 3.14 (3.14 breaks the tool's asyncio.get_event_loop()).
# Pin 0.9.2: 0.9.3 has no matching image on Docker Hub.
pipx install --python python3.13 nojava-ipmi-kvm==0.9.2
cp console/nojava-ipmi-kvmrc.example.yaml ~/.nojava-ipmi-kvmrc.yaml
```

Set `login_user` to your BMC account and keep the `EXTRNIP` in
`download_endpoint` in sync with `full_hostname`. The password is prompted at
runtime and never written to disk.

### 2. Build the patched image

Tagged as the image nojava expects, so it is used locally without a re-pull:

```sh
docker build --platform linux/amd64 \
  -t sciapp/nojava-ipmi-kvm:v0.9.2-openjdk-7 console/megarac-patch
```

The patch is idempotent -- rebuilding on top of an already-patched image
replaces its own block rather than stacking onto it.

### 3. Run

```sh
nojava-ipmi-kvm --debug myserver      # prompts for the BMC password
```

Then open the `http://localhost:<port>/vnc.html?...` URL it prints. Keep the
terminal open: it holds the container, and closing stdin is read as "shut down".

To verify the video transport really came up, rather than trusting the window:

```sh
docker exec <container> netstat -tn | grep :80    # expect ESTABLISHED to the BMC
```

## Operational notes

**The MegaRAC web server is fragile.** It allows roughly 4-5 concurrent web
sessions and leaks them on each failed console attempt. Once exhausted it still
*accepts* TCP in ~0.00 s but never answers HTTP, while IPMI keeps replying
normally -- a combination that looks like a network fault and is not. Recover
with a BMC-only cold reset (does **not** touch the host, ~1-2 min):

```sh
ipmitool -I lanplus -H 192.0.2.10 -U <user> -f <passwordfile> mc reset cold
```

Keep failed attempts few, and log out (`rpc/logout.asp`) when scripting against
the BMC.

**The BMC has SSH** (port 22, OpenSSH 6.0p1, RSA/DSS host keys only) giving a
restricted SMASH-CLP shell:

```sh
ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    -o KexAlgorithms=+diffie-hellman-group1-sha1 -o Ciphers=+aes128-cbc \
    <user>@192.0.2.10
```

Open TCP ports on the BMC: 22, 80, 427, 443, 555, 623, 5988, 5989.

**A black console is a separate problem.** If the viewer connects (traffic settles
to a trickle of keep-alives) but the screen is black, the transport is fine and
the BMC simply has no video to capture -- the AST2400 only captures the onboard
VGA it is attached to. On a board where a discrete GPU sits at a lower PCI bus
number, the firmware may have made that card the primary display, in which case
nothing is ever rendered to the ASPEED.

## SOL (Serial-over-LAN), text console

A lightweight text console (BIOS + OS, when serial redirection is enabled in the
BIOS), straight from `ipmitool`:

```sh
ipmitool -I lanplus -H 192.0.2.10 -U admin -E sol activate     # ~. to exit
ipmitool -I lanplus -H 192.0.2.10 -U admin -E sol deactivate   # if stuck
```

SOL is an interactive stream, so it lives here as a documented command rather
than an MCP tool -- the request/response tool model does not fit a live console.
The server still exposes `sol info` (read-only) to check SOL configuration.

## Why not a firmware update, Redfish, or a native client

The AST2400/ASMB8 generation never received an HTML5 iKVM (that arrived with the
AST2500/ASMB9 boards), and its Redfish support is absent or too limited to drive
a console. Flashing the 2017 beta firmware would add neither.

If you would rather drop Java altogether, the protocol has been reimplemented
clean-room: [`rd450x-console`](https://github.com/BadCoder1337/rd450x-console) is
a single Go binary that speaks IVTP, decodes the ASPEED VQ+JPEG video codec and
serves noVNC itself. It targets a newer MegaRAC (firmware 2.36) over TLS on 7582,
so it would need adapting to single-port-over-80 before it could talk to this
BMC -- but its `docs/kvm-protocol.md` is the best available description of the
wire format. (`mcxBMCView` is not applicable: it drives the HTML5 SPA that this
firmware generation does not have.)
