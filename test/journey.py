#!/usr/bin/env python3
"""End-to-end message path on a deployed project, no LLM needed:
dashboard login -> register an agent -> agent creates a Mattermost room and adds the
owner -> owner posts in Mattermost -> agent receives it on its SSE stream -> agent
replies -> the reply is read back from Mattermost. Credentials come from the
project's Railway variables and are never printed.

Usage: journey.py <projectId>
"""
import json
import pathlib
import sys
import threading
import time
import uuid

import httpx

sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402

pid = sys.argv[1]
p = rw.gql("query($id:String!){project(id:$id){environments{edges{node{id}}} services{edges{node{id name}}}}}", {"id": pid})["project"]
env = p["environments"]["edges"][0]["node"]["id"]
svc = {e["node"]["name"]: e["node"]["id"] for e in p["services"]["edges"]}


def variables(name):
    return rw.gql("query($p:String!,$e:String!,$s:String!){variables(projectId:$p,environmentId:$e,serviceId:$s)}",
                  {"p": pid, "e": env, "s": svc[name]})["variables"]


sw, setup, mmv = variables("switch"), variables("setup"), variables("mattermost")
API = sw["GATEWAY_PUBLIC_URL"]
MM = mmv["MM_SERVICESETTINGS_SITEURL"]
step = lambda s: print(f"--- {s}", flush=True)  # noqa: E731

step("dashboard login")
gw = httpx.Client(base_url=API, timeout=30)
r = gw.post("/gateway/auth/login", json={"email": sw["GATEWAY_ADMIN_EMAIL"], "password": sw["GATEWAY_ADMIN_PASSWORD"]})
assert r.is_success and r.cookies.get("switch_auth"), (r.status_code, r.text[:200])
gw.cookies.set("switch_auth", r.cookies["switch_auth"])
me = gw.get("/gateway/auth/me")
print("dashboard:", me.status_code, me.text[:120])
print("dashboard html:", httpx.get(API + "/", timeout=30).text[:60].replace("\n", " "))

step("agent management: mint a machine enrollment code")
r = gw.post("/gateway/management/enrollment-codes")
assert r.status_code == 201 and r.json()["server_url"].rstrip("/") == API.rstrip("/"), (r.status_code, r.text[:200])
print("enrollment code minted, server_url matches")

step("register agent")
name = f"journey-{uuid.uuid4().hex[:6]}"
r = httpx.post(API + "/agents/register-known", timeout=30, headers={"Authorization": f"Bearer {sw['AGENT_REGISTRATION_TOKEN']}"},
               json={"agent_type": sys.argv[2] if len(sys.argv) > 2 else "claude-code", "name": name, "description": "template journey test"})
assert r.is_success, (r.status_code, r.text[:400])
agent_id, key = r.json()["id"], r.json()["api_key"]
ag = httpx.Client(base_url=API, timeout=30, headers={"Authorization": f"Bearer {key}"})
print("agent", name, agent_id)


def op(name_, args, conn=None):
    r = ag.post(f"/agents/{agent_id}/ops/{name_}", json=args, headers={"X-Switch-Connection-Id": conn} if conn else {})
    assert r.is_success, (name_, r.status_code, r.text[:400])
    return r.json()["result"]


ops = ag.get(f"/agents/{agent_id}/ops").json()["operations"]
assert {"create_room", "post_message"} <= set(ops), sorted(ops)

step("agent creates a room with the owner in it")
room = op("create_room", {"name": name, "description": "journey test room", "agent_names": [name],
                          "user_names": [setup["MATTERMOST_USER"]]})
print("room:", json.dumps(room)[:300])
room_id = room.get("room_id") or room.get("id") or room["room"]["id"]

step("agent opens its event stream")
conn = str(uuid.uuid4())
seen, ready = [], threading.Event()


def stream():
    with httpx.Client(base_url=API, timeout=None, headers={"Authorization": f"Bearer {key}", "Accept": "text/event-stream"}) as c:
        with c.stream("GET", f"/agents/{agent_id}/events", params={"connection_id": conn, "scope": "single",
                                                                   "rooms": room_id, "start_from": "head"}) as r:
            if r.status_code != 200:
                seen.append({"open_error": r.status_code, "body": r.read().decode()[:300]})
                ready.set()
                return
            for line in r.iter_lines():
                if line and not line.startswith("data:"):
                    print("sse:", line[:120], flush=True)
                if line.startswith("data:"):
                    seen.append(json.loads(line[5:]))
                    ready.set()


threading.Thread(target=stream, daemon=True).start()
assert ready.wait(30), "no connection_state frame"
assert "open_error" not in seen[0], seen[0]


def beat():
    while True:
        ag.post(f"/agents/{agent_id}/connection/beat", json={"connection_id": conn})
        time.sleep(2)


threading.Thread(target=beat, daemon=True).start()
print("first frame:", json.dumps(seen[0])[:160])

step("owner posts in Mattermost")
mm = httpx.Client(base_url=MM, timeout=30)
r = mm.post("/api/v4/users/login", json={"login_id": setup["MATTERMOST_USER"], "password": setup["MATTERMOST_USER_PASSWORD"]})
assert r.is_success, (r.status_code, r.text[:200])
mm.headers["Authorization"] = "Bearer " + r.headers["Token"]
team = mm.get(f"/api/v4/teams/name/{setup['MATTERMOST_TEAM_NAME']}").json()["id"]
chans = mm.get(f"/api/v4/users/me/teams/{team}/channels").json()
chan = next(c for c in chans if name in (c["name"], c["display_name"]) or name in c["name"])
token = uuid.uuid4().hex[:8]
assert mm.post("/api/v4/posts", json={"channel_id": chan["id"], "message": f"@{name} ping {token}"}).is_success
print("posted in channel", chan["name"])

step("agent receives it")
deadline = time.time() + 60
while time.time() < deadline and not any(token in json.dumps(f) for f in seen):
    time.sleep(1)
hit = next((f for f in seen if token in json.dumps(f)), None)
assert hit, "message never reached the agent: " + json.dumps(seen)[:600]
print("delivered:", json.dumps(hit)[:200])

step("agent replies, reply shows up in Mattermost")
r = ag.post(f"/agents/{agent_id}/message", json={"room_id": room_id, "content": f"pong {token}"})
assert r.is_success, (r.status_code, r.text[:300])
deadline = time.time() + 60
while time.time() < deadline:
    posts = mm.get(f"/api/v4/channels/{chan['id']}/posts").json()["posts"].values()
    reply = next((x for x in posts if x["message"].startswith("pong") and token in x["message"]), None)
    if reply:
        break
    time.sleep(2)
assert reply, "reply never reached Mattermost"
author = mm.get(f"/api/v4/users/{reply['user_id']}").json()
print("reply in Mattermost from", author.get("username"), "is_bot", author.get("is_bot"))
print("JOURNEY PASS")
