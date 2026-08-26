#!/usr/bin/env python
"""Patch the container's get_java_viewer for the AMI MegaRAC console (ASUS ASMB8 / AST2400).

Three fixes, all verified live against firmware 1.14:

1. **Talk HTTP, not HTTPS.** This is the important one. The BMC hands the KVM
   transport parameters to JViewer inside the jnlp, and derives them from the
   scheme of the session that asked for it:

       over HTTPS -> -kvmsecure 1  -kvmport 443
       over HTTP  -> -kvmsecure 0  -kvmport 80

   The BMC only negotiates TLS 1.0 + RC4-MD5, which no current JRE will do, so
   the HTTPS variant sends JViewer into a wall it cannot climb. Over HTTP the
   video stream is plaintext and the TLS problem disappears entirely. This BMC
   serves its full web UI on port 80 with no redirect to HTTPS.

2. **Fix the (null) codebase.** The firmware emits
   codebase="http://(null):80/Java", leaving the jars unresolvable.

3. **Add the missing main-class.** The firmware emits a bare <application-desc>
   and relies on the jar manifest. This netx build does not cope, and dies with a
   NullPointerException before JViewer's main() ever runs.

Not done here but required -- see the README: the download endpoint must carry
``?EXTRNIP=<bmc-ip>&JNLPSTR=JViewer``. Without JNLPSTR the BMC returns an error
page instead of the launch arguments; EXTRNIP is copied verbatim into
``-hostname``, so it must be the BMC's address, never the client's.

Idempotent and self-correcting: it strips any previous version of the fix block
(including the old one that hardcoded the unused port 7578) before inserting.
"""
from __future__ import print_function

import re

PATH = "/usr/local/bin/get_java_viewer"
ANCHOR = '    with open(download_location, "w", encoding="utf-8") as f:'
MARK = "# --- MegaRAC console fix"

FIX = '''    {mark} (ASUS ASMB8 / AST2400) ---
    # codebase="http://(null):80/Java" -> the jars are unresolvable as-is.
    jnlp_filecontent = jnlp_filecontent.replace("(null)", hostname)
    # A bare <application-desc> makes this netx build throw a NullPointerException.
    jnlp_filecontent = jnlp_filecontent.replace(
        "<application-desc>",
        '<application-desc main-class="com.ami.kvm.jviewer.JViewer">',
    )
    # Fail loudly rather than launching a viewer that could only hang.
    if "Unable to find JNLP String" in jnlp_filecontent:
        raise DownloadFailedError(
            "The BMC returned an error page instead of the launch arguments. "
            "The download endpoint must carry ?EXTRNIP=<bmc-ip>&JNLPSTR=JViewer"
        )
    if "<argument>" not in jnlp_filecontent:
        raise DownloadFailedError("The jnlp carries no launch arguments.")
'''.format(mark=MARK)


def main():
    with open(PATH) as f:
        src = f.read()

    # 1. Force HTTP so the BMC hands out -kvmsecure 0 / -kvmport 80.
    before = src
    src = src.replace(
        'base_url = "https://{}".format(hostname)',
        'base_url = "http://{}".format(hostname)  # MegaRAC: keeps KVM plaintext on :80',
    )
    print("base_url -> http:", "changed" if src != before else "already http")

    # 2. Drop any earlier fix block (including the old, harmful 7578 rebuild).
    start = src.find("    # --- MegaRAC")
    if start != -1:
        end = src.find(ANCHOR, start)
        if end == -1:
            raise SystemExit("found an old fix block but not the anchor after it")
        src = src[:start] + src[end:]
        print("removed previous fix block")

    # 3. Insert the current fix.
    if ANCHOR not in src:
        raise SystemExit("anchor line not found in get_java_viewer")
    src = src.replace(ANCHOR, FIX + ANCHOR, 1)

    with open(PATH, "w") as f:
        f.write(src)

    assert src.count(MARK) == 1, "fix block inserted more than once"
    assert 'base_url = "http://' in src, "http rewrite missing"
    assert not re.search(r"<argument>7578</argument>", src), "stale 7578 rebuild left behind"
    print("patched", PATH)


if __name__ == "__main__":
    main()
