#!/usr/bin/env python
"""Patch the container's get_java_viewer for broken AMI MegaRAC jviewer.jnlp.

Some MegaRAC BMCs (ASUS ASMB8 / ASPEED AST2400) return a jnlp with a "(null)"
codebase and an <application-desc> that is an HTML error ("Unable to find JNLP
String") instead of the launch arguments. The complete jnlp must be built
client-side: fix the codebase host, fetch a session token from
rpc/getsessiontoken.asp, and write an <application-desc> with the four JViewer
arguments (IP, 7578, token, cookie). See:
  https://gist.github.com/ashevchuk/74f7273e5f8e9868d36b1757e18f9d69

This injects that fixup right before get_java_viewer writes the jnlp file.
"""
from __future__ import print_function

PATH = "/usr/local/bin/get_java_viewer"
TARGET = '    with open(download_location, "w", encoding="utf-8") as f:'

FIX = '''    # --- MegaRAC broken-jnlp fix (ASUS ASMB8 / AST2400) ---
    jnlp_filecontent = jnlp_filecontent.replace("(null)", hostname)
    if ("Unable to find JNLP String" in jnlp_filecontent
            or "Access Error" in jnlp_filecontent):
        import re as _re
        _token = ""
        try:
            _tr = session.get(
                urllib.parse.urljoin(base_url, "rpc/getsessiontoken.asp"),
                verify=ssl_verify,
            )
            _m = (_re.search(r"'STOKEN'\\s*:\\s*'([^']+)'", _tr.text)
                  or _re.search(r"'SESSION_TOKEN'\\s*:\\s*'([^']+)'", _tr.text))
            if _m:
                _token = _m.group(1)
        except Exception:
            pass
        _cookie = session.cookies.get(session_cookie_key) if session_cookie_key else None
        if not _cookie and session.cookies:
            _cookie = list(session.cookies.values())[0]
        _head = jnlp_filecontent.split("<application-desc>")[0]
        jnlp_filecontent = _head + (
            "    <application-desc>\\n"
            "        <argument>{ip}</argument>\\n"
            "        <argument>7578</argument>\\n"
            "        <argument>{tok}</argument>\\n"
            "        <argument>{cok}</argument>\\n"
            "    </application-desc>\\n"
            "</jnlp>\\n"
        ).format(ip=hostname, tok=_token, cok=_cookie or "")
        logging.info("Rebuilt JViewer application-desc (token=%s)",
                     "yes" if _token else "EMPTY")
'''


def main():
    with open(PATH) as f:
        src = f.read()
    if "MegaRAC broken-jnlp fix" in src:
        print("get_java_viewer already patched")
        return
    if TARGET not in src:
        raise SystemExit("target line not found in get_java_viewer")
    src = src.replace(TARGET, FIX + TARGET, 1)
    with open(PATH, "w") as f:
        f.write(src)
    print("patched get_java_viewer with MegaRAC jnlp fix")


if __name__ == "__main__":
    main()
