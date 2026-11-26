# Agent Switch on Railway

Railway template for [Agent Switch](https://github.com/sandbox-quantum/switch): a team server that puts AI coding agents into Slack, Teams, Discord, Telegram or a bundled Mattermost.

Services: `switch` (switch-core 0.32.2, API + dashboard), `postgres` (16), `mattermost` (Team Edition 12.1.0), `setup` (one-shot seeder, upstream's `setup.py` 0.32.2, image built from `setup-image/`), `agents` (agent runner: Switch agent controller 0.32.2 with Claude Code, Codex and OpenCode, image built from `image/`).
Deployer guide and listing copy: [TEMPLATE_OVERVIEW.md](TEMPLATE_OVERVIEW.md).

## Files

| File | Purpose |
|---|---|
| `template.json` | Build sheet, the master copy. `$note` keys explain each non-obvious choice. |
| `boot.py` | Boot shim embedded as `SWITCH_BOOT`: creates databases and the unprivileged runtime role, makes the listener dual-stack. |
| `setup_boot.py` | Shim embedded as `SETUP_BOOT`: lets the seeder rerun when Mattermost open signup is off. |
| `setup-image/` | Setup seeder image: upstream's `deploy/shared_resources/setup.py` at the pinned release, checksum-verified. Upstream stopped publishing `ghcr.io/sandbox-quantum/setup` when it dropped the bundled Mattermost in 0.32. `VERSION` is the GHCR tag. |
| `image/` | Agent runner image: `Dockerfile`, `entrypoint.sh` (volume ownership, drop root), `boot.mjs` (auto-enroll, supervise the controller), `connect.mjs` (admin-only sign-in page for Claude and Codex subscriptions). `VERSION` is the GHCR tag; pushing to `main` rebuilds it. |
| `upsert.py` | Writes `template.json` to the Railway template (Auromations) and asserts the read-back. |
| `build_source.py` | Materializes `template.json` into an empty live project for testing. |
| `deploy_as_stranger.py` | Deploys the template into a fresh project, as the button does. |
| `publish.py` | Sets name, icon and description, then publishes. |
| `status.py` | Deployment status per service. |
| `test/versions.py` | Version contract: every image on the target release and pullable, build files agree with tags. |
| `test/boot.sh` | Local contract test for `boot.py` against the pinned image (Docker). |
| `test/setup_boot.sh` | Contract test for `setup_boot.py` in the pinned setup image (Docker). |
| `test/mattermost_race.sh` | Boot race (Docker): mattermost started before Postgres must wait, not crash (crashes cost template health), and a System Console change must survive a restart. |
| `test/agent_run.py` | Real agent turn: creates a managed Claude agent on a machine and asserts its Mattermost answer. Needs the machine signed in to Claude. |
| `test/calls.py` | Mattermost Calls: two headless browsers hold a 1:1 call and must exchange audio (usage in its header). |
| `test/journey.py` | End-to-end check on a deployed project: dashboard login, enrollment code, agent registration, Mattermost round trip, then a `setup` rerun. |

## Upgrading

Bump together: the `switch-core` tag in `template.json`, `SWITCH_VERSION` and `SETUP_SHA256` in `setup-image/Dockerfile`, `CONTROLLER_VERSION` in `image/Dockerfile` (check upstream's release notes for a signing-key change: 0.32.2 has to be installed with 0.32.1's `install.sh`), both `VERSION` files and the two wrapper tags in `template.json`. Run `test/versions.py` (red until the images are pushed), `SWITCH_VERSION=<new> test/boot.sh`, `test/setup_boot.sh` and `test/mattermost_race.sh`. Push to `main` to build the wrapper images (a `VERSION` already on GHCR is skipped, never rebuilt). Then `python3 upsert.py`, `python3 deploy_as_stranger.py <template code> <My Projects id>`, `test/journey.py <project>`, and `test/agent_run.py <project> railway` after giving `agents` an `ANTHROPIC_API_KEY`.
