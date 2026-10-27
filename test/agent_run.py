#!/usr/bin/env python3
"""Real agent turn on a deployed project: a managed Claude agent placed on an enrolled
machine answers the owner's Mattermost question with an actual model reply.

Usage: agent_run.py <projectId> <machine name> [model]
Needs the machine signed in to Claude (ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN / connect page).
"""
import json
import pathlib
import sys
import time
import uuid

import httpx

sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402

pid, machine = sys.argv[1], sys.argv[2]
model = sys.argv[3] if len(sys.argv) > 3 else "haiku"
p = rw.gql("query($id:String!){project(id:$id){environments{edges{node{id}}} services{edges{node{id name}}}}}", {"id": pid})["project"]
env = p["environments"]["edges"][0]["node"]["id"]
svc = {e["node"]["name"]: e["node"]["id"] for e in p["services"]["edges"]}
var = lambda n: rw.gql("query($p:String!,$e:String!,$s:String!){variables(projectId:$p,environmentId:$e,serviceId:$s)}",  # noqa: E731
                       {"p": pid, "e": env, "s": svc[n]})["variables"]
sw, setup, mmv = var("switch"), var("setup"), var("mattermost")
API, MM = sw["GATEWAY_PUBLIC_URL"], mmv["MM_SERVICESETTINGS_SITEURL"]
step = lambda s: print(f"--- {s}", flush=True)  # noqa: E731

gw = httpx.Client(base_url=API, timeout=30)
r = gw.post("/gateway/auth/login", json={"email": sw["GATEWAY_ADMIN_EMAIL"], "password": sw["GATEWAY_ADMIN_PASSWORD"]})
gw.cookies.set("switch_auth", r.cookies["switch_auth"])

step(f"find machine {machine!r}")
ctrls = gw.get("/gateway/management/controllers").json()
ctrls = ctrls.get("controllers", ctrls) if isinstance(ctrls, dict) else ctrls
ctrl = next(c for c in ctrls if c.get("name") == machine)
print("controller", ctrl["id"], {k: ctrl.get(k) for k in ("status", "connected", "online") if k in ctrl})

step("create a managed Claude agent on it")
name = f"railway-claude-{uuid.uuid4().hex[:5]}"
r = gw.post("/gateway/management/agents", json={
    "name": name, "description": "template agent-run test", "controller_id": ctrl["id"], "desired_state": "running",
    "definition": {"provider": "claude", "model": model, "instructions": "Answer in one short sentence."}})
assert r.status_code == 201, (r.status_code, r.text[:500])
agent = r.json()
agent_id = agent.get("id") or agent.get("agent_id") or agent["agent"]["id"]
print("agent", name, agent_id)

step("room with the owner and the agent (created by a throwaway registered agent)")
r = httpx.post(API + "/agents/register-known", timeout=30, headers={"Authorization": f"Bearer {sw['AGENT_REGISTRATION_TOKEN']}"},
               json={"agent_type": "claude-code", "name": f"helper-{uuid.uuid4().hex[:5]}", "description": "room creator"})
helper_id, key = r.json()["id"], r.json()["api_key"]
r = httpx.post(f"{API}/agents/{helper_id}/ops/create_room", timeout=30, headers={"Authorization": f"Bearer {key}"},
               json={"name": name, "description": "agent run test", "agent_names": [name], "user_names": [setup["MATTERMOST_USER"]]})
assert r.is_success, (r.status_code, r.text[:400])
print("room", r.json().get("id"))

step("owner asks in Mattermost")
mm = httpx.Client(base_url=MM, timeout=30)
r = mm.post("/api/v4/users/login", json={"login_id": setup["MATTERMOST_USER"], "password": setup["MATTERMOST_USER_PASSWORD"]})
mm.headers["Authorization"] = "Bearer " + r.headers["Token"]
team = mm.get(f"/api/v4/teams/name/{setup['MATTERMOST_TEAM_NAME']}").json()["id"]
for _ in range(20):
    chan = next((c for c in mm.get(f"/api/v4/users/me/teams/{team}/channels").json() if name in c["name"]), None)
    if chan:
        break
    time.sleep(3)
bot = mm.get(f"/api/v4/users/username/{name}")
mention = "@" + (bot.json()["username"] if bot.is_success else name)
asked = time.time() * 1000
assert mm.post("/api/v4/posts", json={"channel_id": chan["id"], "message": f"{mention} What is the capital of France? One word."}).is_success
print("asked as", setup["MATTERMOST_USER"], "mentioning", mention)

step("wait for the agent's answer")
me = mm.get("/api/v4/users/me").json()["id"]
reply = None
for _ in range(60):
    posts = mm.get(f"/api/v4/channels/{chan['id']}/posts", params={"since": int(asked)}).json()["posts"].values()
    reply = next((x for x in sorted(posts, key=lambda x: x["create_at"]) if x["user_id"] != me and not x.get("type")
                  and "paris" in x["message"].lower()), None)
    if reply:
        break
    time.sleep(5)
if not reply:
    print("no answer; channel says:", json.dumps([x["message"][:120] for x in posts])[:800])
    sys.exit(1)
print("answer:", reply["message"][:200])
print("AGENT RUN PASS")
