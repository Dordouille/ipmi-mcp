# Legacy RC4-MD5 TLS patch (ASCII only; appended to the image's sitecustomize).
#
# Ancient AMI MegaRAC BMCs (ASUS ASMB8 / ASPEED AST2400) only offer TLS 1.0 with
# the RC4-MD5 cipher. Python's default cipher list drops RC4, so the HTTPS login
# nojava-ipmi-kvm performs fails with SSLV3_ALERT_HANDSHAKE_FAILURE.
#
# This image ships requests 2.4.3 / urllib3 1.9.1, whose ssl_wrap_socket() builds
# an SSLContext but never calls set_ciphers() and has no ciphers parameter. We
# replace it with a copy that forces RC4-MD5 (still supported by OpenSSL 1.0.1),
# and bind it in every module that references it (connection imports it by name).
import ssl as _ssl


def _legacy_ssl_wrap_socket(sock, keyfile=None, certfile=None, cert_reqs=None,
                            ca_certs=None, server_hostname=None, ssl_version=None):
    from urllib3.util.ssl_ import SSLContext, HAS_SNI
    context = SSLContext(ssl_version)
    context.verify_mode = _ssl.CERT_NONE if cert_reqs is None else cert_reqs
    try:
        context.set_ciphers("RC4-MD5:ALL:!aNULL:!eNULL")
    except Exception:
        pass
    context.options |= 0x20000
    if ca_certs:
        context.load_verify_locations(ca_certs)
    if certfile:
        context.load_cert_chain(certfile, keyfile)
    if HAS_SNI:
        return context.wrap_socket(sock, server_hostname=server_hostname)
    return context.wrap_socket(sock)


_legacy_patched = []
for _modname in ("urllib3.util.ssl_", "urllib3.connection",
                 "urllib3.connectionpool"):
    try:
        _m = __import__(_modname, fromlist=["ssl_wrap_socket"])
        if hasattr(_m, "ssl_wrap_socket"):
            _m.ssl_wrap_socket = _legacy_ssl_wrap_socket
            _legacy_patched.append(_modname)
    except Exception:
        pass

try:
    import urllib3.util.ssl_ as _u
    _u._LEGACY_RC4_PATCH = _legacy_patched
except Exception:
    pass
