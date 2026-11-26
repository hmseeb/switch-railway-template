# Setup seeder for the Agent Switch Railway template: upstream's own seeder
# (deploy/shared_resources/setup.py), built the way upstream's
# Dockerfile.setup builds it. Upstream stopped publishing ghcr.io/sandbox-quantum/setup
# at 0.32.0, when it dropped the bundled Mattermost, but still runs this seeder in its
# Mattermost e2e stack against the same release. 0.32 needs it: identity links have to
# be confirmed (CHOO-3881), and only the 0.32 seeder confirms the owner's link.
FROM python:3.12-slim

ARG SWITCH_VERSION=0.32.2
ARG SETUP_SHA256=2a579831b141922b226e61f2efab16301fe7c4508d003ca85bc0c281eb46a57b

RUN pip install --no-cache-dir --quiet httpx==0.28.1 \
    && python - <<PY
import hashlib, urllib.request
url = "https://raw.githubusercontent.com/sandbox-quantum/switch/switch-v${SWITCH_VERSION}/deploy/shared_resources/setup.py"
data = urllib.request.urlopen(url).read()
assert hashlib.sha256(data).hexdigest() == "${SETUP_SHA256}", "setup.py checksum mismatch"
open("/setup.py", "wb").write(data)
PY

CMD ["python", "/setup.py"]
