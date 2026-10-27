// Agent runner boot for the Agent Switch Railway template (runs as the node user).
//
// 1. Serves the admin-only connect page (connect.mjs) on $PORT.
// 2. Enrolls this machine with Switch on first boot: signs in to the dashboard as
//    the seeded admin, mints a one-time enrollment code, runs `enroll`. The
//    identity lives on the volume, so later boots skip this.
// 3. Supervises `switch-agent-controller run` with upstream's restart rules
//    (README "Running under your own supervisor"), re-enrolling when Switch has
//    revoked or forgotten this machine.
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { startConnect, claudeToken } from "./connect.mjs";

const SWITCH = (process.env.SWITCH_URL || "").replace(/\/$/, "");
const DATA = process.env.SWITCH_CONTROLLER_DATA_DIR || "/data/controller";
const NAME = process.env.MACHINE_NAME || "railway";
const log = (...a) => console.log("[agents]", ...a);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const enrolled = () => fs.existsSync(path.join(DATA, "controller.db")) && fs.existsSync(path.join(DATA, "secrets", "controller-credential"));

export async function dashboardLogin(email, password) {
  const r = await fetch(`${SWITCH}/gateway/auth/login`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }), signal: AbortSignal.timeout(15000),
  });
  const cookie = (r.headers.getSetCookie?.() || []).map((c) => c.split(";")[0]).find((c) => c.startsWith("switch_auth="));
  if (!r.ok || !cookie) return null;
  const me = await fetch(`${SWITCH}/gateway/auth/me`, { headers: { cookie }, signal: AbortSignal.timeout(15000) });
  return me.ok ? { cookie, me: await me.json() } : null;
}

function cli(args, env = process.env) {
  return new Promise((resolve) => {
    const child = spawn("switch-agent-controller", args, { stdio: "inherit", env });
    child.on("exit", (code, signal) => resolve(code ?? (signal ? 0 : 1)));
    current = child;
  });
}
let current = null;

async function enroll() {
  for (let attempt = 1; ; attempt++) {
    try {
      const s = await dashboardLogin(process.env.GATEWAY_ADMIN_EMAIL, process.env.GATEWAY_ADMIN_PASSWORD);
      if (!s) throw new Error("dashboard sign-in refused (GATEWAY_ADMIN_EMAIL / GATEWAY_ADMIN_PASSWORD no longer match the dashboard?)");
      const r = await fetch(`${SWITCH}/gateway/management/enrollment-codes`, { method: "POST", headers: { cookie: s.cookie } });
      if (r.status !== 201) throw new Error(`enrollment code: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
      const { code } = await r.json();
      const rc = await cli(["enroll", "--server", SWITCH, "--code", code, "--name", NAME,
        "--description", "Runs agents on Railway (Agent Switch template)", "--data-dir", DATA, "--secret-store", "file"]);
      if (rc === 0) return log(`enrolled as machine "${NAME}"`);
      throw new Error(`enroll exited ${rc}`);
    } catch (e) {
      const wait = Math.min(60, 5 * attempt);
      log(`enrollment not done yet: ${e.message}; retrying in ${wait}s`);
      await sleep(wait * 1000);
    }
  }
}

function forgetIdentity() {
  for (const f of fs.readdirSync(DATA)) if (f.startsWith("controller.db")) fs.rmSync(path.join(DATA, f), { force: true });
  fs.rmSync(path.join(DATA, "secrets"), { recursive: true, force: true });
}

// The connect page calls this after a sign-in changes, so providers are re-detected.
let restarting = false;
export function restartController() {
  if (current && current.exitCode === null) { restarting = true; current.kill("SIGTERM"); }
}

async function supervise() {
  let failures = 0;
  for (;;) {
    if (!enrolled()) await enroll();
    const env = { ...process.env };
    const token = claudeToken();
    if (token && !env.CLAUDE_CODE_OAUTH_TOKEN) env.CLAUDE_CODE_OAUTH_TOKEN = token;
    for (const k of ["GATEWAY_ADMIN_PASSWORD", "GATEWAY_ADMIN_EMAIL"]) delete env[k];
    log("starting controller");
    const started = Date.now();
    const rc = await cli(["run", "--data-dir", DATA], env);
    if (restarting) { restarting = false; failures = 0; continue; }
    if (stopping) return;
    if (Date.now() - started > 600000) failures = 0;
    switch (rc) {
      case 7: continue; // installed the release Switch names; start it
      case 3: case 6:
        log(`Switch ${rc === 3 ? "revoked" : "no longer knows"} this machine; enrolling it again`);
        forgetIdentity(); continue;
      case 1: case 0: {
        const wait = Math.min(60, 2 ** ++failures);
        log(`controller exited ${rc}; restarting in ${wait}s`); await sleep(wait * 1000); continue;
      }
      default: // 2 config, 4 taken over, 5 protocol: starting again unchanged would fail the same way
        log(`controller exited ${rc} (see its last line above); retrying in 5 minutes`);
        await sleep(300000);
    }
  }
}

let stopping = false;
for (const sig of ["SIGTERM", "SIGINT"]) process.on(sig, () => {
  stopping = true;
  if (current && current.exitCode === null) current.kill("SIGTERM");
  setTimeout(() => process.exit(0), 8000).unref();
  if (!current || current.exitCode !== null) process.exit(0);
});

if (!SWITCH.startsWith("https://")) { log("SWITCH_URL must be the switch service's https URL"); process.exit(1); }
fs.mkdirSync(DATA, { recursive: true, mode: 0o700 });
startConnect({ dashboardLogin, restartController });
supervise().then(() => process.exit(0));
