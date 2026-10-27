# Agent runner for the Agent Switch Railway template: Switch's headless agent
# controller plus the provider CLIs, so agents run on Railway instead of a laptop.
FROM node:22-bookworm-slim

ARG CONTROLLER_VERSION=0.31.0
ARG CLAUDE_CODE_VERSION=2.1.311
ARG CODEX_VERSION=0.164.0
ARG OPENCODE_VERSION=1.19.4

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
RUN curl -fsSL "https://raw.githubusercontent.com/sandbox-quantum/switch/switch-agent-controller-v${CONTROLLER_VERSION}/console/packages/agent-controller/install.sh" -o /tmp/install.sh \
    && sh /tmp/install.sh --version "${CONTROLLER_VERSION}" --no-service \
    && rm /tmp/install.sh && npm cache clean --force \
    && switch-agent-controller --help >/dev/null

COPY entrypoint.sh boot.mjs connect.mjs /app/
ENV HOME=/data/home \
    SWITCH_CONTROLLER_DATA_DIR=/data/controller \
    PORT=8080
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
