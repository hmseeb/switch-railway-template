#!/usr/bin/env python3
"""Version contract: every image in template.json is on the target release, the
wrapper images' build files agree with their tags, and every pinned image exists in
its registry (anonymous pull, as Railway pulls it).

Usage: test/versions.py   (targets below; override with SWITCH=/MATTERMOST=/REV=)
"""
import json
import os
import pathlib
import re
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent
SWITCH = os.environ.get("SWITCH", "0.32.2")
MATTERMOST = os.environ.get("MATTERMOST", "12.1.0")
REV = os.environ.get("REV", "r1")
WANT = {
    "switch": f"ghcr.io/sandbox-quantum/switch-core:{SWITCH}",
    "setup": f"ghcr.io/hmseeb/switch-railway-setup:{SWITCH}-{REV}",
    "agents": f"ghcr.io/hmseeb/switch-railway-agents:{SWITCH}-{REV}",
    "mattermost": f"mattermost/mattermost-team-edition:{MATTERMOST}",
    "postgres": "ghcr.io/railwayapp-templates/postgres-ssl:16",
}
fails = []


def check(ok, msg):
    print(("ok   " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def exists(image):
    repo, tag = image.rsplit(":", 1)
    if repo.startswith("ghcr.io/"):
        name = repo[len("ghcr.io/"):]
        tok = json.load(urllib.request.urlopen(f"https://ghcr.io/token?scope=repository:{name}:pull"))["token"]
        url, auth = f"https://ghcr.io/v2/{name}/manifests/{tag}", f"Bearer {tok}"
    else:
        tok = json.load(urllib.request.urlopen(
            f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"))["token"]
        url, auth = f"https://registry-1.docker.io/v2/{repo}/manifests/{tag}", f"Bearer {tok}"
    req = urllib.request.Request(url, method="HEAD", headers={"Authorization": auth, "Accept": ",".join([
        "application/vnd.oci.image.index.v1+json", "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json"])})
    try:
        return urllib.request.urlopen(req).status == 200
    except urllib.error.HTTPError:
        return False


services = json.loads((HERE / "template.json").read_text())["services"]
for svc, image in WANT.items():
    got = services[svc]["source"]["image"]
    check(got == image, f"{svc} image {got} == {image}")
    check(exists(got), f"{got} pullable")

agents = (HERE / "image/Dockerfile").read_text()
check(f"ARG CONTROLLER_VERSION={SWITCH}\n" in agents, f"image/Dockerfile CONTROLLER_VERSION={SWITCH}")
check((HERE / "image/VERSION").read_text().strip() == f"{SWITCH}-{REV}", f"image/VERSION == {SWITCH}-{REV}")
setup = (HERE / "setup-image/Dockerfile").read_text() if (HERE / "setup-image/Dockerfile").exists() else ""
check(f"ARG SWITCH_VERSION={SWITCH}\n" in setup, f"setup-image/Dockerfile SWITCH_VERSION={SWITCH}")
sv = HERE / "setup-image/VERSION"
check(sv.exists() and sv.read_text().strip() == f"{SWITCH}-{REV}", f"setup-image/VERSION == {SWITCH}-{REV}")
readme = (HERE / "README.md").read_text()
check(f"switch-core {SWITCH}" in readme and f"Team Edition {MATTERMOST}" in readme, "README names the versions")
stale = [p for p in ("README.md", "TEMPLATE_OVERVIEW.md") if re.search(r"\b0\.31\.0\b|\b11\.9\.0\b", (HERE / p).read_text())]
check(not stale, f"no 0.31.0 / 11.9.0 left in {stale or 'docs'}")

print("PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
