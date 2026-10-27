# Deploy and Host Agent Switch on Railway

Agent Switch puts AI coding agents (Claude Code, Codex, OpenCode, Cursor, Gemini CLI and more) into your team's chat as teammates. People mention an agent in a room, the agent works on its owner's machine, and its answer, files and progress come back to the same room in Slack, Microsoft Teams, Discord, Telegram or Mattermost.

## About Hosting Agent Switch

This template runs a Switch team server: the one address everyone's Switch Console and agent machines connect to. It deploys four services:

- **switch**: the Switch server (API, agent event streams, MCP server and the admin dashboard on one URL)
- **postgres**: rooms, messages, files and accounts
- **mattermost**: a bundled chat app, already connected, so there is a working room on day one without a Slack admin
- **setup**: a one-shot job that creates your Mattermost accounts and team, connects Mattermost to Switch, and links your accounts. It shows Completed when done.

Agents do not run on Railway. They run on each person's own computer (or a build box) through Switch Console or the headless agent controller, using that person's own model subscription or API key. Railway hosts only the shared server, so it stays small.

Every image is pinned to Switch 0.31.0, so a redeploy never pulls a surprise upgrade.

## Common Use Cases

- Ask a coding agent for a fix in a team channel and review its answer where the discussion already is
- Run several agents (one per repo or role) in shared rooms, with humans approving their work from chat
- Give a remote team one always-on Switch server instead of servers that stop when a laptop closes
- Bridge agents into an existing Slack, Teams, Discord or Telegram workspace from your own infrastructure

## Dependencies for Agent Switch Hosting

- PostgreSQL 16 on a Railway volume
- Mattermost Team Edition 11.9 on a Railway volume
- Switch server images from GitHub Container Registry

### Deployment Dependencies

- [Switch repository](https://github.com/sandbox-quantum/switch)
- [Switch documentation](https://docs.switchagents.ai)
- [Self-hosting guide](https://docs.switchagents.ai/flintai/switch/deploy/self-host)
- [Switch Console download](https://docs.switchagents.ai/flintai/switch/getting-started/install-switch-console)

### Implementation Details

**The only question at deploy time** is `GATEWAY_ADMIN_EMAIL`, the email you sign in with. Everything else (database passwords, signing keys, admin passwords, the agent registration token) is generated per deploy.

**First login (about 3 minutes after deploy)**

1. Wait until `switch` and `mattermost` are green and `setup` shows Completed.
2. Open the `switch` service's Variables tab and copy `GATEWAY_ADMIN_PASSWORD`.
3. Open the `switch` service's public URL and sign in with your email and that password. This is the admin dashboard.
4. Your Mattermost login is user `owner` with the password in the `setup` service's `MATTERMOST_USER_PASSWORD` variable, at the `mattermost` service's URL. The Mattermost system admin is `admin` with `MATTERMOST_ADMIN_PASSWORD`.

**Connect Switch Console (each teammate)**

Install Switch Console, choose **Add a server**, then **Connect to an existing server**, and enter the `switch` public URL as both the Gateway URL and the API URL. Teammates need a dashboard account (invite them from the dashboard) and a Mattermost account (create it as the Mattermost admin, or connect Slack instead).

**Run agents on a machine that stays up**

The dashboard's **Machines** page has an **Add machine** button that prints a one-line install command with a 10-minute enrollment code. Run it on any Linux or macOS box that has the agent CLIs you want (Claude Code, Codex, OpenCode) and it runs your agents as a service. Agent management is already switched on in this template.

**Connect Slack, Teams, Discord or Telegram (optional, any time)**

Add the app's variables to the `switch` service and redeploy. Callbacks go to the `switch` public URL, which this template already sets as `MESSAGING_PUBLIC_URL`.

- Slack: `SLACK_APP_CLIENT_ID`, `SLACK_APP_CLIENT_SECRET`, `SLACK_APP_SIGNING_SECRET`
- Discord: `DISCORD_APP_CLIENT_ID`, `DISCORD_APP_CLIENT_SECRET`, `DISCORD_APP_BOT_TOKEN`, `DISCORD_APP_APPLICATION_ID`
- Teams: `TEAMS_APP_CLIENT_ID`, `TEAMS_APP_TENANT_ID`, `TEAMS_APP_CLIENT_SECRET`
- Telegram: `TELEGRAM_APP_BOT_TOKEN`, `TELEGRAM_APP_WEBHOOK_SECRET`

Each app's setup is in the [messaging apps guide](https://docs.switchagents.ai/flintai/switch/deploy/messaging-apps). You can remove the `mattermost` and `setup` services afterwards if you do not want the bundled chat.

**Back these up**

- The `postgres` volume holds everything: rooms, messages, files, accounts.
- `SECRET_KEYS` on the `switch` service encrypts stored agent API keys. Keep a copy; a deployment restored with a different value cannot read them back.
- Do not change `ID_SERVER_NAME` after the first boot. It is part of every account and room id.

**What this template changes from upstream's Docker Compose**

- Switch serves its dashboard itself, so there is no separate nginx gateway service.
- Mattermost open signup is off. Upstream turns it on because its compose binds to localhost; on a public URL it would let anyone register. Invite people as the Mattermost admin instead.
- The database role setup that upstream runs in an `init-db` container runs in the `switch` service before the server starts (the `SWITCH_BOOT` variable). Leave that variable alone.

**Troubleshooting**

- `mattermost` may restart once on the first deploy if it starts before `switch` has created its database. That is expected.
- `setup` shows a single `502 ... Invalid or expired session` line while the Mattermost connection warms up, then continues. Only worry if it ends in Failed after 10 retries; redeploying `setup` is safe, it is idempotent.
- Sign-in loops back to the login page: open the dashboard on its `https://` URL. Session cookies are Secure.

**Scaling and upgrades**

The Switch server runs as a single replica by design. To upgrade, change the image tag on `switch` and `setup` to the same newer version and redeploy them; migrations run on boot. Keep Mattermost on the version Switch pins, because Switch Console embeds its web UI.

**License**

Switch is Apache 2.0 with a Commons Clause: you may run it for your own team, not sell it as a hosted service.

## Why Deploy Agent Switch on Railway?

Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you don't have to deal with configuration, while allowing you to vertically and horizontally scale it.

By deploying Agent Switch on Railway, you are one step closer to supporting a complete full-stack application with minimal burden. Host your servers, databases, AI agents, and more on Railway.
