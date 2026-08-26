#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tiny TLS-terminating proxy that re-encrypts to a legacy RC4-MD5 endpoint.

Ancient AMI MegaRAC BMCs (ASUS ASMB8 / AST2400) only accept TLS 1.0 + RC4-MD5.
Modern JViewer (running on the container's openjdk-7) refuses RC4, so its HTTPS
login fails. This proxy accepts a *modern* TLS connection from JViewer on
127.0.0.1 and forwards it to the BMC using RC4-MD5 (which the container's
OpenSSL 1.0.1 still supports). Point JViewer at 127.0.0.1:<port> instead of the
BMC and the RC4 wall disappears — no need for an old Java.

Usage: rc4_proxy.py <listen_port> <target_host> <target_port> <cert.pem>
"""
from __future__ import print_function

import socket
import ssl
import sys
import threading


def _pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        for s in (src, dst):
            try:
                s.close()
            except Exception:
                pass


def _handle(client, target_host, target_port):
    try:
        raw = socket.create_connection((target_host, target_port), 15)
        ctx = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers("RC4-MD5:ALL:!aNULL:!eNULL")
        upstream = ctx.wrap_socket(raw)
    except Exception as error:
        sys.stderr.write("upstream connect failed: %s\n" % error)
        try:
            client.close()
        except Exception:
            pass
        return
    threading.Thread(target=_pipe, args=(client, upstream)).start()
    threading.Thread(target=_pipe, args=(upstream, client)).start()


def main():
    listen_port = int(sys.argv[1])
    target_host = sys.argv[2]
    target_port = int(sys.argv[3])
    cert = sys.argv[4]

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", listen_port))
    srv.listen(64)

    server_ctx = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    server_ctx.load_cert_chain(cert)

    print("RC4 proxy: 127.0.0.1:%d -> %s:%d (RC4-MD5 upstream)"
          % (listen_port, target_host, target_port))
    sys.stdout.flush()
    while True:
        try:
            conn, _ = srv.accept()
            tls_conn = server_ctx.wrap_socket(conn, server_side=True)
            threading.Thread(
                target=_handle, args=(tls_conn, target_host, target_port)
            ).start()
        except Exception as error:
            sys.stderr.write("accept/handshake error: %s\n" % error)


if __name__ == "__main__":
    main()
