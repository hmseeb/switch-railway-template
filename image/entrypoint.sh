#!/bin/sh
# Railway volumes mount root-owned. Hand /data to the node user, then drop root:
# Claude Code refuses its permission-bypass mode as root.
set -e
mkdir -p /data/home /data/controller
[ "$(stat -c %u /data/home)" = 1000 ] || chown -R 1000:1000 /data/home
[ "$(stat -c %u /data/controller)" = 1000 ] || chown -R 1000:1000 /data/controller
exec setpriv --reuid=1000 --regid=1000 --init-groups node /app/boot.mjs
