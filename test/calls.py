#!/usr/bin/env python3
# Mattermost Calls two-browser test. On a template deploy:
#   ADMIN_USER/ADMIN_PW (setup MATTERMOST_ADMIN_*), OWNER_USER/OWNER_PW (setup MATTERMOST_USER*), TEAM=switch
#   uv run --with httpx --with playwright python test/calls.py <mattermost url> keep 0
# "keep" leaves the Calls config as the template set it. Passes when both browsers connect and send and receive audio.
"""Two-browser Mattermost Calls test against a Railway deploy.
Usage: calls_test.py <site url> <ice host> <ice port>
Creates users/team on a fresh server (first user = admin), points Calls' ICE host/port
at the Railway TCP proxy, then starts and joins a call and reads WebRTC stats."""
import json, sys, time, secrets
import httpx
from playwright.sync_api import sync_playwright

URL, ICE_HOST, ICE_PORT = sys.argv[1], sys.argv[2].rstrip("."), int(sys.argv[3])
import os
if not os.path.exists("/tmp/calls_pw"): open("/tmp/calls_pw", "w").write("Pw-" + secrets.token_hex(8))
pw = open("/tmp/calls_pw").read().strip()
api = httpx.Client(base_url=URL + "/api/v4", timeout=30)

for _ in range(60):
    try:
        if api.get("/system/ping").is_success: break
    except Exception: pass
    time.sleep(5)

def user(name, auth=None):
    r = api.post("/users", json={"username": name, "password": pw, "email": f"{name}@example.com"}, headers=auth or {})
    assert r.status_code in (201, 400, 403), r.text
    t = httpx.post(URL + "/api/v4/users/login", json={"login_id": name, "password": pw})
    return t.json()["id"], t.headers["Token"]

if os.environ.get("ADMIN_USER"):  # a template deploy: log in as its admin and owner instead of creating users
    login = lambda n, p_: httpx.post(URL + "/api/v4/users/login", json={"login_id": n, "password": p_})
    t = login(os.environ["ADMIN_USER"], os.environ["ADMIN_PW"]); A = {"Authorization": f"Bearer {t.headers['Token']}"}
    api.post("/users", headers=A, json={"username": "callee", "password": pw, "email": "callee@example.com"})
    o = login(os.environ["OWNER_USER"], os.environ["OWNER_PW"]); a_id, a_tok = o.json()["id"], o.headers["Token"]
    c = login("callee", pw); b_id, b_tok = c.json()["id"], c.headers["Token"]
    team = api.get("/teams/name/" + os.environ["TEAM"], headers=A).json()
    api.post(f"/teams/{team['id']}/members", headers=A, json={"team_id": team["id"], "user_id": b_id})
else:
    a_id, a_tok = user("calladmin")
    A = {"Authorization": f"Bearer {a_tok}"}
    b_id, b_tok = user("callee", A)
if not os.environ.get("ADMIN_USER"):
  team = api.post("/teams", headers=A, json={"name": "calls", "display_name": "Calls", "type": "O"})
  team = team.json() if team.status_code == 201 else api.get("/teams/name/calls", headers=A).json()
  api.post(f"/teams/{team['id']}/members", headers=A, json={"team_id": team["id"], "user_id": b_id})

cfg = api.get("/config", headers=A).json()
plugins = cfg["PluginSettings"].setdefault("Plugins", {})
calls = plugins.setdefault("com.mattermost.calls", {})
if ICE_HOST != "keep": calls.update({"icehostoverride": ICE_HOST, "icehostportoverride": ICE_PORT, "defaultenabled": True} if ICE_HOST != "none" else {"icehostoverride": "", "icehostportoverride": None, "defaultenabled": True})
if ICE_HOST != "keep":
    r = api.put("/config", headers=A, json=cfg); assert r.is_success, r.text[:300]
for act in (() if ICE_HOST == "keep" else ("disable", "enable")): print("plugin", act, api.post(f"/plugins/com.mattermost.calls/{act}", headers=A).status_code); time.sleep(5)
print("calls config:", {k: api.get("/config", headers=A).json()["PluginSettings"]["Plugins"]["com.mattermost.calls"].get(k) for k in ("icehostoverride", "icehostportoverride", "defaultenabled")})
st = api.get("/plugins/com.mattermost.calls/config", headers=A)
print("calls client config:", st.status_code, st.text[:200])
time.sleep(5)

HOOK = """(() => { const O = window.RTCPeerConnection; window.__pcs = [];
  window.RTCPeerConnection = class extends O { constructor(...a){ super(...a); window.__pcs.push(this); } }; })();"""
STATS = """async () => { const out = [];
  const c = window.callsClient; const pcs = [c && c.peer && (c.peer.pc || c.peer)].filter(Boolean); for (const pc of pcs) { const s = await pc.getStats(); const r = {state: pc.connectionState, ice: pc.iceConnectionState, in: 0, out: 0, pair: null, remotes: []};
    const byId = {}; s.forEach(x => byId[x.id] = x);
    s.forEach(x => { if (x.type === 'remote-candidate') r.remotes.push(x.protocol + ' ' + x.address + ':' + x.port + ' ' + x.candidateType + (x.tcpType ? ' ' + x.tcpType : '')); if (x.type === 'inbound-rtp' && x.kind === 'audio') r.in += x.bytesReceived || 0;
      if (x.type === 'outbound-rtp' && x.kind === 'audio') r.out += x.bytesSent || 0;
      if (x.type === 'candidate-pair' && x.nominated && x.state === 'succeeded') { const rc = byId[x.remoteCandidateId] || {}, lc = byId[x.localCandidateId] || {};
        r.pair = {protocol: rc.protocol, remote: rc.address + ':' + rc.port, local: lc.candidateType}; } });
    out.push(r); } return out; }"""

with sync_playwright() as p:
    br = p.chromium.launch(headless=True, args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
    pages, ctxs = [], []
    for uid, tok, peer in ((a_id, a_tok, "callee"), (b_id, b_tok, os.environ.get("OWNER_USER", "calladmin"))):
        ctx = br.new_context(permissions=["microphone", "camera"]); ctxs.append(ctx)
        host = URL.split("//")[1]
        ctx.add_cookies([{"name": "MMAUTHTOKEN", "value": tok, "domain": host, "path": "/", "secure": True, "httpOnly": True},
                         {"name": "MMUSERID", "value": uid, "domain": host, "path": "/", "secure": True}])
        pg = ctx.new_page(); pg.on("crash", lambda *_: print("PAGE CRASH")); pg.on("close", lambda *_: print("PAGE CLOSED")); br.on("disconnected", lambda *_: print("BROWSER GONE")); pg.goto(f"{URL}/{os.environ.get('TEAM', 'calls')}/messages/@{peer}"); pg.wait_for_timeout(4000)
        try: pg.get_by_text("View in Browser").click(timeout=15000)
        except Exception: pass
        for dismiss in ("No thanks, I’ll figure it out myself", "No thanks, I'll figure it out myself"):
            try: pg.get_by_text(dismiss).click(timeout=4000); break
            except Exception: pass
        pg.get_by_role("button", name="Start call").or_(pg.get_by_role("button", name="Join call")).first.wait_for(timeout=30000)
        pages.append(pg)
    a, b = pages
    a.screenshot(path="/tmp/calls_a_before.png")
    a.wait_for_timeout(3000)
    btn = a.get_by_role("button", name="Start call")
    if not btn.count(): btn = a.locator("#calls-join-button, button:has-text('Start call'), button[aria-label*='call' i]")
    print("start buttons:", btn.count()); btn.first.click(); a.wait_for_timeout(6000)
    a.screenshot(path="/tmp/calls_a_started.png")
    # B answers the ringing call where it rings (Calls 1.12 rings DMs; a reload can miss the ring).
    for _ in range(20):
        jb = b.get_by_role("button", name="Join", exact=True).or_(b.get_by_role("button", name="Join call"))
        if jb.count() and jb.first.is_enabled():
            break
        b.wait_for_timeout(1500)
    print("join buttons:", jb.count()); jb.first.click(); b.wait_for_timeout(15000)
    b.screenshot(path="/tmp/calls_b_joined.png")
    a.wait_for_timeout(10000); a.screenshot(path="/tmp/calls_a_end.png"); b.screenshot(path="/tmp/calls_b_end.png")
    print("A client:", a.evaluate("() => { const c = window.callsClient; return c ? Object.keys(c).filter(k => /peer|pc|rtc/i.test(k)) : null }"))
    sa, sb = a.evaluate(STATS), b.evaluate(STATS)
    print("A:", json.dumps(sa)); print("B:", json.dumps(sb))
    ok = all(any(x["state"] == "connected" and x["in"] > 0 and x["out"] > 0 for x in s) for s in (sa, sb))
    print("CALL PASS" if ok else "CALL FAIL")
    br.close()
