# Agent runner for the Agent Switch Railway template: Switch's headless agent
# controller plus the provider CLIs, so agents run on Railway instead of a laptop.
FROM node:22-bookworm-slim

ARG CONTROLLER_VERSION=0.32.2
# 0.32.2 is the last release signed with the release-2026-10 key; its own
# install.sh only trusts release-2026-11 and refuses it (upstream release notes).
# So the installer comes from the release before, which trusts the key it is signed with.
ARG INSTALLER_VERSION=0.32.1
ARG CLAUDE_CODE_VERSION=2.1.332
ARG CODEX_VERSION=0.172.0
ARG OPENCODE_VERSION=1.19.6

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gh git openssh-client procps ripgrep util-linux \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g --ignore-scripts=false \
      @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} \
      @openai/codex@${CODEX_VERSION} \
      opencode-ai@${OPENCODE_VERSION} \
    && npm cache clean --force

# Upstream's installer: downloads the pinned release and refuses it unless its
# Ed25519 signature verifies against the release keys built into the script.
RUN curl -fsSL "https://raw.githubusercontent.com/sandbox-quantum/switch/switch-agent-controller-v${INSTALLER_VERSION}/console/packages/agent-controller/install.sh" -o /tmp/install.sh \
    && sh /tmp/install.sh --version "${CONTROLLER_VERSION}" --no-service \
    && rm /tmp/install.sh && npm cache clean --force \
    && test "$(switch-agent-controller --version 2>/dev/null | head -1)" = "${CONTROLLER_VERSION}"

COPY entrypoint.sh boot.mjs connect.mjs /app/
ENV HOME=/data/home \
    SWITCH_CONTROLLER_DATA_DIR=/data/controller \
    PORT=8080
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
