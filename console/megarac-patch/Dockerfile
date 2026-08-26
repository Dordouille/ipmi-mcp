# JViewer console image for the ASUS ASMB8-iKVM BMC (AMI MegaRAC, ASPEED AST2400).
#
# The upstream nojava-ipmi-kvm image runs the legacy Java Web Start viewer and
# serves it over noVNC, but three quirks of this firmware stop it from ever
# reaching the host's video. patch_megarac.py fixes all three -- see its
# docstring; the short version is that the viewer must reach the BMC over HTTP,
# because the BMC picks the KVM transport from the scheme of the session that
# requests the launch file, and its HTTPS side only speaks TLS 1.0 + RC4-MD5.
#
# Build it under the exact tag nojava expects, so the tool uses it locally
# without pulling over it:
#
#   docker build --platform linux/amd64 \
#     -t sciapp/nojava-ipmi-kvm:v0.9.2-openjdk-7 console/megarac-patch
#
# The patch is idempotent, so rebuilding on top of an already-built image is
# safe -- it replaces its own previous block rather than stacking onto it.
#
FROM sciapp/nojava-ipmi-kvm:v0.9.2-openjdk-7

COPY patch_megarac.py /opt/patch/patch_megarac.py
RUN python /opt/patch/patch_megarac.py \
 && python -c "compile(open('/usr/local/bin/get_java_viewer').read(), 'gjv', 'exec'); print('get_java_viewer compiles OK')"
