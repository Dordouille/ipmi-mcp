# Legacy-TLS variant of the nojava-ipmi-kvm openjdk-7 image.
#
# Ancient AMI MegaRAC BMCs require TLS 1.0 + RC4-MD5, which modern urllib3
# refuses, breaking the HTTPS login. We append a snippet to the image's
# sitecustomize.py (the Debian one, which is the sitecustomize actually loaded —
# a copy in dist-packages is shadowed by it) that replaces urllib3's
# ssl_wrap_socket with one forcing RC4-MD5. Build it tagged as the exact image
# nojava expects so the tool uses it locally (no re-pull):
#
#   docker build --platform linux/amd64 \
#     -t sciapp/nojava-ipmi-kvm:v0.9.2-openjdk-7 console/nojava-legacy-tls
#
FROM sciapp/nojava-ipmi-kvm:v0.9.2-openjdk-7

COPY sitecustomize.py /opt/patch/legacy_tls_patch.py
RUN printf '\n# --- legacy RC4-MD5 TLS patch (appended) ---\n' >> /usr/lib/python2.7/sitecustomize.py \
 && cat /opt/patch/legacy_tls_patch.py >> /usr/lib/python2.7/sitecustomize.py \
 && rm -f /usr/lib/python2.7/sitecustomize.pyc \
 && python -c "import sitecustomize, urllib3.util.ssl_ as s; print('legacy TLS patch ->', getattr(s, '_LEGACY_RC4_PATCH', 'ABSENT'))"

# Rebuild the broken MegaRAC jviewer.jnlp (token flow + application-desc args).
COPY patch_megarac.py /opt/patch/patch_megarac.py
RUN python /opt/patch/patch_megarac.py \
 && python -c "compile(open('/usr/local/bin/get_java_viewer').read(), 'gjv', 'exec'); print('get_java_viewer compiles OK')"

# RC4 TLS bridge: JViewer (openjdk-7, no RC4) talks modern TLS to this proxy,
# which re-encrypts to the BMC over RC4-MD5. A self-signed cert secures the
# local (JViewer-facing) leg.
COPY rc4_proxy.py /opt/patch/rc4_proxy.py
RUN openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=127.0.0.1" \
      -keyout /opt/patch/proxy.key -out /opt/patch/proxy.crt 2>/dev/null \
 && cat /opt/patch/proxy.key /opt/patch/proxy.crt > /opt/patch/proxy.pem \
 && python -c "compile(open('/opt/patch/rc4_proxy.py').read(), 'p', 'exec'); print('rc4_proxy compiles OK')"
