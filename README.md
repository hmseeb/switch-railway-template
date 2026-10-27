# Agent Switch on Railway

Railway template for [Agent Switch](https://github.com/sandbox-quantum/switch): a team server that puts AI coding agents into Slack, Teams, Discord, Telegram or a bundled Mattermost.

Services: `switch` (switch-core 0.31.0, API + dashboard), `postgres` (16), `mattermost` (Team Edition 11.9.0), `setup` (one-shot seeder).
Deployer guide and listing copy: [TEMPLATE_OVERVIEW.md](TEMPLATE_OVERVIEW.md).

## Files

| File | Purpose |
|---|---|
| `template.json` | Build sheet, the master copy. `$note` keys explain each non-obvious choice. |
| `boot.py` | Boot shim embedded as `SWITCH_BOOT`: creates databases and the unprivileged runtime role, makes the listener dual-stack. |
| `setup_boot.py` | Shim embedded as `SETUP_BOOT`: lets the seeder rerun when Mattermost open signup is off. |
| `upsert.py` | Writes `template.json` to the Railway template (Auromations) and asserts the read-back. |
| `build_source.py` | Materializes `template.json` into an empty live project for testing. |
| `deploy_as_stranger.py` | Deploys the template into a fresh project, as the button does. |
| `publish.py` | Sets name, icon and description, then publishes. |
| `status.py` | Deployment status per service. |
| `test/boot.sh` | Local contract test for `boot.py` against the pinned image (Docker). |
| `test/setup_boot.sh` | Contract test for `setup_boot.py` in the pinned setup image (Docker). |
| `test/journey.py` | End-to-end check on a deployed project: dashboard login, enrollment code, agent registration, Mattermost round trip, then a `setup` rerun. |

## Upgrading

Bump the `switch-core` and `setup` image tags together in `template.json`, run `SWITCH_VERSION=<new> test/boot.sh` and `test/setup_boot.sh`, then `python3 upsert.py`, deploy a scratch copy with `deploy_as_stranger.py` and run `test/journey.py` on it.
