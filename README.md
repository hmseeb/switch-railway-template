# Agent Switch on Railway

Railway template for [Agent Switch](https://github.com/sandbox-quantum/switch): a team server that puts AI coding agents into Slack, Teams, Discord, Telegram or a bundled Mattermost.

Services: `switch` (switch-core 0.31.0, API + dashboard), `postgres` (16), `mattermost` (Team Edition 11.9.0), `setup` (one-shot seeder), `agents` (agent runner: Switch agent controller 0.31.0 with Claude Code, Codex and OpenCode, image built from `image/`).
Deployer guide and listing copy: [TEMPLATE_OVERVIEW.md](TEMPLATE_OVERVIEW.md).

## Files

| File | Purpose |
|---|---|
| `template.json` | Build sheet, the master copy. `$note` keys explain each non-obvious choice. |
| `boot.py` | Boot shim embedded as `SWITCH_BOOT`: creates databases and the unprivileged runtime role, makes the listener dual-stack. |
| `setup_boot.py` | Shim embedded as `SETUP_BOOT`: lets the seeder rerun when Mattermost open signup is off. |
| `image/` | Agent runner image: `Dockerfile`, `entrypoint.sh` (volume ownership, drop root), `boot.mjs` (auto-enroll, supervise the controller), `connect.mjs` (admin-only sign-in page for Claude and Codex subscriptions). `VERSION` is the GHCR tag; pushing to `main` rebuilds it. |
| `upsert.py` | Writes `template.json` to the Railway template (Auromations) and asserts the read-back. |
| `build_source.py` | Materializes `template.json` into an empty live project for testing. |
| `deploy_as_stranger.py` | Deploys the template into a fresh project, as the button does. |
| `publish.py` | Sets name, icon and description, then publishes. |
| `status.py` | Deployment status per service. |
| `test/boot.sh` | Local contract test for `boot.py` against the pinned image (Docker). |
| `test/setup_boot.sh` | Contract test for `setup_boot.py` in the pinned setup image (Docker). |
| `test/agent_run.py` | Real agent turn: creates a managed Claude agent on a machine and asserts its Mattermost answer. Needs the machine signed in to Claude. |
| `test/calls.py` | Mattermost Calls: two headless browsers hold a 1:1 call and must exchange audio (usage in its header). |
| `test/journey.py` | End-to-end check on a deployed project: dashboard login, enrollment code, agent registration, Mattermost round trip, then a `setup` rerun. |

## Upgrading

Bump the `switch-core` and `setup` image tags and `CONTROLLER_VERSION` in `image/Dockerfile` (bump `image/VERSION` too) together in `template.json`, run `SWITCH_VERSION=<new> test/boot.sh` and `test/setup_boot.sh`, then `python3 upsert.py`, test on a private copy first (`TEMPLATE_WS=<My Projects id> TEMPLATE_IDFILE=template-id.test python3 upsert.py`), deploy it with `deploy_as_stranger.py`, run `test/journey.py`, and `test/agent_run.py <project> railway` after giving `agents` an `ANTHROPIC_API_KEY`.
