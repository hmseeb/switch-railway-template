#!/usr/bin/env bash
# Contract test for boot.py against the pinned switch-core image, booted the way
# Railway boots it (start command, SWITCH_BOOT variable, fresh Postgres).
# Asserts: runtime role is created and unprivileged, /health/ready answers on
# IPv4 and IPv6 from one socket, and a second boot (role already there) is clean.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=${SWITCH_VERSION:-$(python3 -c 'import json;print(json.load(open("template.json"))["services"]["switch"]["source"]["image"].split(":")[-1])')}
NET=switch-boot-test PG=switch-boot-pg APP=switch-boot-app
cleanup() { docker rm -f $APP $PG >/dev/null 2>&1 || true; docker network rm $NET >/dev/null 2>&1 || true; }
trap cleanup EXIT; cleanup
docker network create $NET >/dev/null
docker run -d --name $PG --network $NET -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=ownerpw -e POSTGRES_DB=switch postgres:16-alpine >/dev/null

boot() {
  docker rm -f $APP >/dev/null 2>&1 || true
  docker run -d --name $APP --network $NET \
    -e SWITCH_BOOT="$(cat boot.py)" -e DB_HOST=$PG -e DB_PORT=5432 -e DB_NAME=switch \
    -e DB_USER=switch_app -e DB_PASSWORD="app'pw" -e DB_OWNER_USER=postgres -e DB_OWNER_PASSWORD=ownerpw \
    -e SERVER_HOST=:: -e COLLABORATION_CALLBACK_HOST=:: -e ID_SERVER_NAME=switch.test \
    -e AGENT_REGISTRATION_TOKEN=regtoken -e SECRET_KEYS="k1:$(openssl rand -hex 32)" \
    -e GATEWAY_ADMIN_EMAIL=admin@example.com -e GATEWAY_ADMIN_PASSWORD=adminpw-adminpw \
    -e FEATURE_FLAGS_ENABLED=agent_management,agent_chats,switch_buddy,follow_the_conversation,service_connections \
    -e CONTROLLER_TOKEN_SECRET="$(openssl rand -hex 32)" \
    "ghcr.io/sandbox-quantum/switch-core:$VERSION" /bin/sh -c "printenv SWITCH_BOOT > /tmp/boot.py && exec python /tmp/boot.py" >/dev/null
  for _ in $(seq 60); do
    if docker exec $APP python -c 'import urllib.request as u;u.urlopen("http://127.0.0.1:8000/health/ready")' 2>/dev/null; then break; fi
    if [ "$(docker inspect -f '{{.State.Running}}' $APP)" != true ]; then docker logs $APP | tail -30; echo "FAIL: exited"; exit 1; fi
    sleep 2
  done
  for host in 127.0.0.1 '[::1]'; do
    docker exec $APP python -c "import urllib.request as u;print('$host', u.urlopen('http://$host:8000/health/ready').status)" \
      || { docker logs $APP | tail -30; echo "FAIL: $host"; exit 1; }
  done
}

boot
logs=$(docker logs $APP 2>&1); grep -q 'databases and runtime role ready' <<<"$logs" || { echo "FAIL: no boot line"; exit 1; }
super=$(docker exec $PG psql -U postgres -tAc "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname='switch_app'")
[ "$super" = f ] || { echo "FAIL: runtime role privileged or missing ($super)"; exit 1; }
[ "$(docker exec $PG psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='mattermost'")" = 1 ] || { echo "FAIL: no mattermost db"; exit 1; }
echo "first boot ok"
boot
echo "second boot ok"
echo PASS
