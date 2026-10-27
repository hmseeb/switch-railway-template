"""setup seeder shim for Railway, run as `printenv SETUP_BOOT > /tmp/boot.py && exec python -u /tmp/boot.py`.

Upstream's /setup.py starts every run by creating the Mattermost admin and treats
400/409 as "already exists". This template turns Mattermost open signup off, so
on every rerun Mattermost refuses with 403 `no_open_server` instead and the
seeder crashes. Rewrite exactly that refusal to 409; a wrong admin password
still fails loudly at the login that follows.

After seeding, it switches Mattermost Calls on for everyone (the plugin's
DefaultEnabled has no env variable), once: an admin who turns it off later keeps
it off. Config lives in Postgres (MM_CONFIG), so it survives redeploys.
"""
import os
import runpy

import httpx

_post = httpx.Client.post


def _post_tolerating_closed_signup(self, url, *args, **kwargs):
    resp = _post(self, url, *args, **kwargs)
    if (resp.status_code == 403 and str(url).endswith("/api/v4/users")
            and "no_open_server" in resp.text):
        print("setup-boot: Mattermost signup is closed, so the admin already exists", flush=True)
        resp.status_code = 409
    return resp


httpx.Client.post = _post_tolerating_closed_signup



def enable_calls_by_default():
    mm = httpx.Client(base_url=os.environ["MATTERMOST_URL"] + "/api/v4", timeout=30)
    r = mm.post("/users/login", json={"login_id": os.environ["MATTERMOST_ADMIN_USER"], "password": os.environ["MATTERMOST_ADMIN_PASSWORD"]})
    r.raise_for_status()
    mm.headers["Authorization"] = "Bearer " + r.headers["Token"]
    cfg = mm.get("/config")
    cfg.raise_for_status()
    cfg = cfg.json()
    calls = cfg["PluginSettings"].setdefault("Plugins", {}).setdefault("com.mattermost.calls", {})
    if "defaultenabled" in calls:
        return print(f"setup-boot: Calls default left as {calls['defaultenabled']}", flush=True)
    calls["defaultenabled"] = True
    mm.put("/config", json=cfg).raise_for_status()
    print("setup-boot: Calls enabled for everyone", flush=True)


if __name__ == "__main__":
    runpy.run_path("/setup.py", run_name="__main__")
    enable_calls_by_default()
