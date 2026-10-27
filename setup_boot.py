"""setup seeder shim for Railway, run as `printenv SETUP_BOOT > /tmp/boot.py && exec python -u /tmp/boot.py`.

Upstream's /setup.py starts every run by creating the Mattermost admin and treats
400/409 as "already exists". This template turns Mattermost open signup off, so
on every rerun Mattermost refuses with 403 `no_open_server` instead and the
seeder crashes. Rewrite exactly that refusal to 409; a wrong admin password
still fails loudly at the login that follows.
"""
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

if __name__ == "__main__":
    runpy.run_path("/setup.py", run_name="__main__")
