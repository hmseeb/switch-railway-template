#!/usr/bin/env bash
# Boot-race test for the mattermost service, booted with template.json's variables.
# On a fresh deploy Railway starts every service at once, so mattermost can start
# before postgres accepts connections. It must wait, not exit: every exit is a crash
# that counts against template health (Agent Switch fell to 29%).
# Asserts:
#  1. mattermost started DELAY seconds before postgres (and with no switch boot to
#     create anything) stays up and answers /api/v4/system/ping;
#  2. a config change survives recreating the container on the same volume.
set -euo pipefail
cd "$(dirname "$0")/.."
DELAY=${DELAY:-4}
eval "$(python3 - <<'PY'
import json, shlex
s = json.load(open("template.json"))["services"]
pg, mm = s["postgres"]["variables"], s["mattermost"]["variables"]
ds = (mm["MM_SQLSETTINGS_DATASOURCE"]["defaultValue"]
      .replace("${{postgres.POSTGRES_USER}}", "postgres")
      .replace("${{postgres.POSTGRES_PASSWORD}}", "ownerpw")
      .replace("${{postgres.RAILWAY_PRIVATE_DOMAIN}}", "mm-race-pg"))
cfg = mm["MM_CONFIG"]["defaultValue"].replace("${{MM_SQLSETTINGS_DATASOURCE}}", ds)
for k, v in {"IMAGE": s["mattermost"]["source"]["image"], "VOL": s["mattermost"]["volumeMounts"]["mountPath"],
             "PGDB": pg["POSTGRES_DB"]["defaultValue"], "DS": ds, "CFG": cfg}.items():
    print(f"{k}={shlex.quote(v)}")
PY
)"
NET=mm-race-test PG=mm-race-pg APP=mm-race-app MMVOL=mm-race-data
cleanup() { docker rm -f $APP $PG >/dev/null 2>&1 || true; docker volume rm $MMVOL >/dev/null 2>&1 || true; docker network rm $NET >/dev/null 2>&1 || true; }
trap cleanup EXIT; cleanup
docker network create $NET >/dev/null
docker pull -q --platform linux/amd64 "$IMAGE" >/dev/null

mm() {
  docker rm -f $APP >/dev/null 2>&1 || true
  docker run -d --name $APP --network $NET --platform linux/amd64 -v $MMVOL:"$VOL" -p 127.0.0.1:18065:8065 \
    -e MM_SQLSETTINGS_DRIVERNAME=postgres -e MM_SQLSETTINGS_DATASOURCE="$DS" -e MM_CONFIG="$CFG" "$IMAGE" >/dev/null
}
alive() {
  [ "$(docker inspect -f '{{.State.Running}}' $APP)" = true ] && return
  docker logs $APP 2>&1 | grep -v '^\s*-\|^  [a-z]\|^Usage\|^Flags\|^Available\|^Use \|^$' | tail -3 | cut -c1-300
  echo "FAIL: mattermost exited (code $(docker inspect -f '{{.State.ExitCode}}' $APP)) $1"; exit 1
}
up() {
  for _ in $(seq 90); do
    alive "$1"
    docker run --rm --network $NET curlimages/curl -fsS http://$APP:8065/api/v4/system/ping >/dev/null 2>&1 && return
    sleep 2
  done
  echo "FAIL: mattermost never answered ping $1"; exit 1
}

mm
sleep "$DELAY"
alive "before postgres started"
docker run -d --name $PG --network $NET -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=ownerpw -e POSTGRES_DB="$PGDB" postgres:16-alpine >/dev/null
up "while postgres was starting"
echo "ok: mattermost started ${DELAY}s before postgres and came up"

# the System Console path: the first account is a system admin, PUT /config as it
api() { python3 - "$@" <<'PY'
import json, sys, urllib.request as u
op, base = sys.argv[1], "http://127.0.0.1:18065/api/v4"
def call(method, path, body=None, tok=None):
    r = u.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                  headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + tok} if tok else {})})
    with u.urlopen(r) as resp:
        return resp.headers.get("Token"), json.load(resp)
cred = {"login_id": "raceadmin", "password": "Race-test-password-1"}
if op == "set":
    call("POST", "/users", {"username": "raceadmin", "email": "race@example.com", "password": cred["password"]})
tok, _ = call("POST", "/users/login", cred)
_, cfg = call("GET", "/config", tok=tok)
if op == "set":
    cfg["TeamSettings"]["SiteName"] = "RaceTest"
    call("PUT", "/config", cfg, tok=tok)
print(cfg["TeamSettings"]["SiteName"])
PY
}
api set >/dev/null
mm
up "on restart"
got=$(api get)
[ "$got" = RaceTest ] || { echo "FAIL: config change lost on restart (SiteName=$got)"; exit 1; }
echo "ok: config change survived a restart"
echo PASS
