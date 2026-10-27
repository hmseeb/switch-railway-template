// Connect page for the agent runner: signs the provider CLIs on this Railway machine
// in to the deployer's own subscriptions, so nobody needs a terminal on the server.
//   Claude: paste a `claude setup-token` token; it reaches agents as CLAUDE_CODE_OAUTH_TOKEN.
//   Codex:  runs `codex login --device-auth` here and shows the link + one-time code.
// Access: Switch dashboard admins only, checked against the dashboard's own login,
// so it follows a password changed in the dashboard. Adapted from the Paperclip template.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawn } from "node:child_process";

const HOME = process.env.HOME || "/data/home";
const TOKEN_FILE = path.join(HOME, ".switch-railway", "claude-token");
const CODEX_HOME = process.env.CODEX_HOME || path.join(HOME, ".codex");
const CODEX_AUTH = path.join(CODEX_HOME, "auth.json");
const CODEX_URL = "https://auth.openai.com/codex/device";
const CODEX_TTL_MS = 15 * 60 * 1000;
const SESSION_MS = 12 * 3600 * 1000;
const log = (...a) => console.log("[connect]", ...a);

const sessions = new Map(); // cookie value -> expiry; in memory, so a restart signs you out
let codexFlow = null; // { code, status, startedAt, child }

const savedToken = () => { try { return fs.readFileSync(TOKEN_FILE, "utf8").trim(); } catch { return ""; } };
export const claudeToken = savedToken;

export function startConnect({ dashboardLogin, restartController }) {
  function startCodex() {
    if (codexFlow && codexFlow.child && codexFlow.child.exitCode === null) return;
    fs.mkdirSync(CODEX_HOME, { recursive: true, mode: 0o700 });
    const s = (codexFlow = { code: null, status: "starting", startedAt: Date.now(), child: null });
    // `script` gives codex a pseudo-terminal; it prints the device code only when it has one.
    const cmd = `codex -c 'cli_auth_credentials_store="file"' login --device-auth`;
    const child = spawn("script", ["-qfec", cmd, "/dev/null"], { env: { ...process.env, CODEX_HOME } });
    s.child = child;
    let out = "";
    const onData = (buf) => {
      out = (out + buf.toString()).replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "").slice(-4000);
      const m = out.match(/\b([A-Z0-9]{4}-[A-Z0-9]{5})\b/);
      if (m && !s.code) { s.code = m[1]; s.status = "waiting"; log("Codex sign-in: code issued"); }
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
    const timer = setTimeout(() => child.kill("SIGTERM"), CODEX_TTL_MS);
    child.on("exit", (code) => {
      clearTimeout(timer);
      s.status = code === 0 && fs.existsSync(CODEX_AUTH) ? "connected" : "failed";
      log(`Codex sign-in: ${s.status}`);
      if (s.status === "connected") restartController();
    });
  }

  async function saveClaude(token) {
    token = token.trim();
    if (!token) { fs.rmSync(TOKEN_FILE, { force: true }); restartController(); return { ok: true }; }
    if (!/^sk-ant-oat\d*-/.test(token)) return { ok: false, error: "That does not look like a setup token. Run claude setup-token and paste the sk-ant-oat... value." };
    const r = await fetch("https://api.anthropic.com/api/oauth/usage", {
      headers: { authorization: `Bearer ${token}`, "anthropic-beta": "oauth-2025-04-20" },
      signal: AbortSignal.timeout(15000),
    }).catch(() => null);
    // Only 401 means a bad token: setup tokens are inference-only, so 403 (no profile scope) and 429 are normal.
    if (r && r.status === 401) return { ok: false, error: "Anthropic rejected the token. Run claude setup-token again and paste the new one." };
    fs.mkdirSync(path.dirname(TOKEN_FILE), { recursive: true, mode: 0o700 });
    fs.writeFileSync(TOKEN_FILE, token, { mode: 0o600 });
    restartController();
    return { ok: true };
  }

  const state = () => ({
    claude: process.env.CLAUDE_CODE_OAUTH_TOKEN ? "variable" : savedToken() ? "saved" : process.env.ANTHROPIC_API_KEY ? "api_key" : null,
    codex: fs.existsSync(CODEX_AUTH) ? "signed_in" : process.env.OPENAI_API_KEY ? "api_key" : null,
    codexFlow: codexFlow && { url: CODEX_URL, code: codexFlow.code, status: codexFlow.status, expiresAt: codexFlow.startedAt + CODEX_TTL_MS },
  });

  const body = (req) => new Promise((ok) => { let b = ""; req.on("data", (c) => { b += c; if (b.length > 1e5) req.destroy(); }); req.on("end", () => ok(b)); });
  const send = (res, code, type, data, headers = {}) => { res.writeHead(code, { "content-type": type, "cache-control": "no-store", ...headers }); res.end(data); };
  const json = (res, code, data, headers) => send(res, code, "application/json", JSON.stringify(data), headers);
  const cookieOf = (req) => (/(?:^|;\s*)sw_connect=([a-f0-9]{64})/.exec(req.headers.cookie || "") || [])[1];
  const signedIn = (req) => { const c = cookieOf(req); return c && sessions.get(c) > Date.now(); };

  async function handle(req, res) {
    const url = req.url.split("?")[0];
    if (url === "/health") return send(res, 200, "text/plain", "ok");
    if (url === "/" ) { res.writeHead(302, { location: "/connect" }); return res.end(); }
    if (req.method === "POST") {
      const origin = req.headers.origin || "";
      if (!origin || new URL(origin).host !== req.headers.host) return json(res, 403, { ok: false, error: "Bad origin" });
      const input = JSON.parse((await body(req)) || "{}");
      if (url === "/connect/login") {
        const s = await dashboardLogin(String(input.email || ""), String(input.password || "")).catch(() => null);
        if (!s) return json(res, 401, { ok: false, error: "Wrong email or password for the Switch dashboard." });
        if (s.me.role !== "admin") return json(res, 403, { ok: false, error: "Only a Switch dashboard admin can connect providers." });
        const c = crypto.randomBytes(32).toString("hex");
        sessions.set(c, Date.now() + SESSION_MS);
        return json(res, 200, { ok: true }, { "set-cookie": `sw_connect=${c}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${SESSION_MS / 1000}` });
      }
      if (!signedIn(req)) return json(res, 401, { ok: false, error: "Sign in first." });
      if (url === "/connect/claude") return json(res, 200, await saveClaude(String(input.token || "")));
      if (url === "/connect/codex/start") { startCodex(); return json(res, 200, { ok: true }); }
      if (url === "/connect/codex/signout") { fs.rmSync(CODEX_AUTH, { force: true }); restartController(); return json(res, 200, { ok: true }); }
      return json(res, 404, { ok: false });
    }
    if (url === "/connect") return send(res, 200, "text/html; charset=utf-8", signedIn(req) ? PAGE : LOGIN);
    if (url === "/connect/state") return signedIn(req) ? json(res, 200, state()) : json(res, 401, {});
    send(res, 404, "text/plain", "Not found");
  }

  http.createServer((req, res) => handle(req, res).catch((e) => { log(e); send(res, 500, "text/plain", "error"); }))
    .listen(Number(process.env.PORT || 8080), "::", () => log(`connect page on :${process.env.PORT || 8080}`));
}

const STYLE = `<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:15px/1.5 ui-sans-serif,-apple-system,sans-serif;background:#111;color:#f5f5f5;max-width:620px;margin:48px auto;padding:0 20px}
h1{font-size:26px;margin:0 0 4px}p.sub{color:#9a9a9a;margin:0 0 28px}section{border:1px solid #2c2c2c;border-radius:14px;padding:20px;margin:0 0 18px;background:#1a1a1a}
h2{font-size:17px;margin:0 0 10px}ol{padding-left:20px;margin:8px 0}code,.code{font-family:ui-monospace,Menlo,monospace}
.code{font-size:30px;letter-spacing:3px;margin:10px 0;display:block}input{width:100%;box-sizing:border-box;background:#111;color:#fff;border:1px solid #3a3a3a;border-radius:8px;padding:10px;font:14px ui-monospace,monospace;margin:4px 0}
button{margin-top:10px;background:#fff;color:#111;border:0;border-radius:999px;padding:8px 18px;font-weight:600;cursor:pointer}button.link{background:none;color:#93c5fd;padding:0;margin:0 0 0 8px;font-weight:400}
.muted{color:#9a9a9a}.ok{color:#22c55e}.err{color:#f87171}a{color:#93c5fd}</style>`;

const LOGIN = `<!doctype html><html><head>${STYLE}<title>Connect agents · Switch</title></head><body>
<h1>Connect agents</h1><p class="sub">Sign in with your Switch dashboard admin account.</p>
<section><input id="em" type="email" placeholder="Email" autocomplete="username"><input id="pw" type="password" placeholder="Password" autocomplete="current-password">
<button id="go">Sign in</button><p id="msg" class="err"></p></section>
<script>document.getElementById('go').onclick=async()=>{const r=await fetch('/connect/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({email:em.value,password:pw.value})});const j=await r.json();if(j.ok)location.reload();else msg.textContent=j.error};
pw.onkeydown=e=>{if(e.key==='Enter')go.click()}</script></body></html>`;

const PAGE = `<!doctype html><html><head>${STYLE}<title>Connect agents · Switch</title></head><body>
<h1>Connect agents</h1><p class="sub">Sign this Railway machine in to your own subscriptions. Agents you place on the <b>railway</b> machine use them.</p>
<section><h2>Claude subscription</h2><p id="cst" class="muted"></p>
<ol><li>On your own computer run <code>claude setup-token</code> and copy the <code>sk-ant-oat…</code> token.</li><li>Paste it here and save. It stays on this service's volume.</li></ol>
<input id="tok" type="password" placeholder="sk-ant-oat01-..." autocomplete="off"><button id="save">Save token</button><button class="link" id="clear">Remove</button><p id="cmsg"></p></section>
<section><h2>Codex (ChatGPT subscription)</h2><p id="xst0" class="muted"></p><button id="xgo">Sign in with ChatGPT</button><button class="link" id="xout">Sign out</button>
<div id="xbox" hidden><ol><li>Open <a id="xurl" target="_blank" rel="noopener"></a> and sign in to ChatGPT.</li><li>Enter this code:</li></ol><span class="code" id="xcode"></span><p id="xst" class="muted"></p></div></section>
<script>
const $=id=>document.getElementById(id);const post=(u,b)=>fetch(u,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(b||{})}).then(r=>r.json());
async function refresh(){const r=await fetch('/connect/state');if(r.status===401)return location.reload();const s=await r.json();
$('cst').className=s.claude?'ok':'muted';$('cst').textContent={variable:'Connected through the CLAUDE_CODE_OAUTH_TOKEN variable.',saved:'Connected with your saved token.',api_key:'Using the ANTHROPIC_API_KEY variable (pay per use). Save a token to use your subscription instead.'}[s.claude]||'Not connected.';
$('xst0').className=s.codex==='signed_in'?'ok':'muted';$('xst0').textContent={signed_in:'Signed in with ChatGPT.',api_key:'Using the OPENAI_API_KEY variable (pay per use).'}[s.codex]||'Not connected.';
const x=s.codexFlow;$('xbox').hidden=!x||!x.code||x.status==='connected';if(x){$('xurl').href=$('xurl').textContent=x.url;$('xcode').textContent=x.code||'';
const left=Math.max(0,Math.round((x.expiresAt-Date.now())/1000));
$('xst').textContent={starting:'Starting…',waiting:'Waiting for you to approve ('+Math.floor(left/60)+':'+String(left%60).padStart(2,'0')+' left).',failed:'Sign-in failed or expired. Click Sign in with ChatGPT again.'}[x.status]||'';}}
$('save').onclick=async()=>{$('cmsg').className='muted';$('cmsg').textContent='Checking the token with Anthropic…';const r=await post('/connect/claude',{token:$('tok').value});
$('cmsg').className=r.ok?'ok':'err';$('cmsg').textContent=r.ok?'Saved. Agents pick it up within a few seconds.':r.error;if(r.ok)$('tok').value='';refresh()};
$('clear').onclick=async()=>{await post('/connect/claude',{token:''});refresh()};
$('xgo').onclick=async()=>{await post('/connect/codex/start');refresh()};$('xout').onclick=async()=>{await post('/connect/codex/signout');refresh()};
refresh();setInterval(refresh,2000);
</script></body></html>`;
