# Deploy and Host Agent Switch on Railway

Agent Switch puts AI coding agents (Claude Code, Codex, OpenCode, Cursor, Gemini CLI and more) into your team's chat as teammates. People mention an agent in a room, the agent works on its owner's machine, and its answer, files and progress come back to the same room in Slack, Microsoft Teams, Discord, Telegram or Mattermost.

## About Hosting Agent Switch

This template runs a Switch team server: the one address everyone's Switch Console and agent machines connect to. It deploys five services:

- **switch**: the Switch server (API, agent event streams, MCP server and the admin dashboard on one URL)
- **postgres**: rooms, messages, files and accounts
- **mattermost**: a bundled chat app, already connected, so there is a working room on day one without a Slack admin
- **setup**: a one-shot job that creates your Mattermost accounts and team, connects Mattermost to Switch, and links your accounts. It shows Completed when done.
- **agents**: a machine that runs your agents on Railway, around the clock, with Claude Code, Codex and OpenCode installed. It enrolls itself with Switch as the machine `railway`, and you sign it in to your own Claude or ChatGPT subscription from a web page. No terminal on the server, no laptop that has to stay awake.

Every image is pinned to Switch 0.31.0, so a redeploy never pulls a surprise upgrade.

## Common Use Cases

- Ask a coding agent for a fix in a team channel and review its answer where the discussion already is
- Run several agents (one per repo or role) in shared rooms, with humans approving their work from chat
- Give a remote team one always-on Switch server instead of servers that stop when a laptop closes
- Bridge agents into an existing Slack, Teams, Discord or Telegram workspace from your own infrastructure

## Dependencies for Agent Switch Hosting

- PostgreSQL 16 on a Railway volume
- The agent runner image (Switch agent controller 0.31.0, Claude Code, Codex, OpenCode), built from the template repository
- Mattermost Team Edition 11.9 on a Railway volume
- Switch server images from GitHub Container Registry

### Deployment Dependencies

- [Switch repository](https://github.com/sandbox-quantum/switch)
- [Switch documentation](https://docs.switchagents.ai)
- [Self-hosting guide](https://docs.switchagents.ai/flintai/switch/deploy/self-host)
- [Switch Console download](https://docs.switchagents.ai/flintai/switch/getting-started/install-switch-console)
- [Template source, agent runner image and tests](https://github.com/hmseeb/switch-railway-template)

### Implementation Details

**The only question at deploy time** is `GATEWAY_ADMIN_EMAIL`, the email you sign in with. Everything else (database passwords, signing keys, admin passwords, the agent registration token) is generated per deploy.

**First login (about 3 minutes after deploy)**

Wait until `switch` and `mattermost` are green and `setup` shows Completed. Your logins, with each password in that service's Variables tab:

| Sign in to | URL | User | Password variable |
|---|---|---|---|
| Switch dashboard | `switch` service URL | your email | `switch` → `GATEWAY_ADMIN_PASSWORD` |
| Mattermost (chat here) | `mattermost` service URL | your email or `owner` | `setup` → `MATTERMOST_USER_PASSWORD` |
| Mattermost system admin | `mattermost` service URL | `admin` | `setup` → `MATTERMOST_ADMIN_PASSWORD` |

**Chat as `owner`, never as `admin`.** Switch connects to Mattermost as the `admin` account and ignores that account's own posts, so agents never see anything you write as `admin`. Use `admin` only to create accounts and invite links (open signup is off because the URL is public).

**Connect Switch Console (each teammate)**

Install Switch Console, choose **Add a server**, then **Connect to an existing server**, and enter the `switch` public URL as both the Gateway URL and the API URL. Teammates need a dashboard account (invite them from the dashboard) and a Mattermost account (create it as the Mattermost admin, or connect Slack instead).

**Run agents on Railway (the `agents` service)**

1. Open the `agents` service's public URL and sign in with your Switch dashboard email and password.
2. Claude subscription: on your own computer run `claude setup-token` once, paste the `sk-ant-oat…` token, and save. Codex: click **Sign in with ChatGPT**, open the link, and enter the code shown. Either takes effect within seconds.
3. In Switch Console, create an agent, choose the provider you signed in, and pick **railway** as its machine. Invite it to a room and mention it.

Prefer pay-per-use API keys? Add `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` to the `agents` service's variables instead. Agents work in folders on the `agents` volume; give them a GitHub connection in Switch to clone and push. Delete the `agents` service if everyone runs agents on their own computers.

**Run agents on your own machines too**

The dashboard's **Machines** page has an **Add machine** button that prints a one-line install command with a 10-minute enrollment code. Run it on any Linux or macOS box that has the agent CLIs you want (Claude Code, Codex, OpenCode) and it runs your agents as a service. Agent management is already switched on in this template.

**Voice calls in Mattermost**

Calls are on for everyone: open a direct message and click **Start call**. They connect over UDP straight to Railway, with no extra setup.

- Mattermost Team Edition allows calls in 1:1 direct messages only. Calls in channels and group messages need a Mattermost Professional license.
- A network that blocks outgoing UDP (some offices and VPNs) needs a TURN relay. Add `MM_CALLS_ICE_SERVERS_CONFIGS` to the `mattermost` service with your TURN provider's details, for example `[{"urls":["turn:turn.example.com:443?transport=tcp"],"username":"...","credential":"..."}]`, and redeploy.
- To turn calls off, disable the Calls plugin in the System Console.

**Connect Slack, Teams, Discord or Telegram (optional, any time)**

Add the app's variables to the `switch` service and redeploy. Callbacks go to the `switch` public URL, which this template already sets as `MESSAGING_PUBLIC_URL`.

- Slack: `SLACK_APP_CLIENT_ID`, `SLACK_APP_CLIENT_SECRET`, `SLACK_APP_SIGNING_SECRET`
- Discord: `DISCORD_APP_CLIENT_ID`, `DISCORD_APP_CLIENT_SECRET`, `DISCORD_APP_BOT_TOKEN`, `DISCORD_APP_APPLICATION_ID`
- Teams: `TEAMS_APP_CLIENT_ID`, `TEAMS_APP_TENANT_ID`, `TEAMS_APP_CLIENT_SECRET`
- Telegram: `TELEGRAM_APP_BOT_TOKEN`, `TELEGRAM_APP_WEBHOOK_SECRET`

Each app's setup is in the [messaging apps guide](https://docs.switchagents.ai/flintai/switch/deploy/messaging-apps). You can remove the `mattermost` and `setup` services afterwards if you do not want the bundled chat.

**After the first deploy: change things in the apps, not in variables**

Most variables are first-boot seeds. Once Switch and Mattermost have created your accounts, they keep their own copy in the database, so editing a variable afterwards does not change the real login.

- Change your dashboard password or email in the Switch dashboard. Editing `GATEWAY_ADMIN_PASSWORD` does nothing, and editing `GATEWAY_ADMIN_EMAIL` creates a second admin account.
- Mattermost's own settings live in its database, so System Console changes survive redeploys. Change Mattermost passwords in Mattermost. Leave the `admin` password alone: Switch stored it when it connected, so changing it in Mattermost disconnects Switch until you update the Mattermost connector in the dashboard.
- Safe to edit and redeploy: `DB_PASSWORD`, `AGENT_REGISTRATION_TOKEN`, `FEATURE_FLAGS_ENABLED`, and the Slack, Teams, Discord and Telegram variables.
- Never change `POSTGRES_PASSWORD` (Postgres keeps the original in its volume) or `ID_SERVER_NAME`. Rotate `SECRET_KEYS` by putting a new key first, `k2:<new>,k1:<old>`, never by replacing it.
- `setup` variables are labelled "First deploy only". Editing one reruns `setup`, which only creates what is missing (a different `MATTERMOST_USER` or `MATTERMOST_TEAM_NAME` adds a second user or team; the existing connection keeps the old one). You can delete the `setup` service once it shows Completed.

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
- An agent on `railway` says it could not start a session: open the `agents` URL and check the provider shows Connected. A token that Anthropic revoked needs a fresh `claude setup-token`.
- `agents` logs `enrollment not done yet: dashboard sign-in refused`: it signs in once with `GATEWAY_ADMIN_EMAIL` and `GATEWAY_ADMIN_PASSWORD` to enroll. If you changed the dashboard password before it enrolled, set the new one on the `agents` service.
- A call never connects (spins on Connecting): your network probably blocks UDP. See Voice calls above for the TURN setting. No Start call button in a channel: Team Edition only allows calls in 1:1 direct messages.
- You posted in Mattermost and no agent answered: check you are signed in as `owner`, not `admin` (see above), and that the agent is a member of that room.
- Sign-in loops back to the login page: open the dashboard on its `https://` URL. Session cookies are Secure.

**Scaling and upgrades**

The Switch server runs as a single replica by design. To upgrade, change the image tag on `switch` and `setup` to the same newer version and redeploy them; migrations run on boot. Keep Mattermost on the version Switch pins, because Switch Console embeds its web UI.

**License**

Switch is Apache 2.0 with a Commons Clause: you may run it for your own team, not sell it as a hosted service.

## Why Deploy Agent Switch on Railway?

Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you don't have to deal with configuration, while allowing you to vertically and horizontally scale it.

By deploying Agent Switch on Railway, you are one step closer to supporting a complete full-stack application with minimal burden. Host your servers, databases, AI agents, and more on Railway.
