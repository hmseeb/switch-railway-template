"""switch-core boot shim for Railway, run as `printenv SWITCH_BOOT > /tmp/boot.py && exec python /tmp/boot.py`.

Does the two things compose does outside the image, then hands over to switch-core:
1. init-db: create the `switch` and `mattermost` databases and the unprivileged
   DB_USER runtime role (switch-core refuses to serve as the schema owner).
   Idempotent; ALTER ROLE re-applies a changed DB_PASSWORD.
2. Dual-stack listen: Railway's private network is IPv6, its healthchecker IPv4.
   asyncio forces IPV6_V6ONLY=1 on a `::` socket, so coerce it to 0 and one
   socket serves both.
"""
import asyncio
import os
import runpy
import socket

import asyncpg

_setsockopt = socket.socket.setsockopt


def _dual_stack(self, level, opt, value, *rest):
    if level == socket.IPPROTO_IPV6 and opt == socket.IPV6_V6ONLY:
        value = 0
    return _setsockopt(self, level, opt, value, *rest)


socket.socket.setsockopt = _dual_stack


async def init_db():
    e = os.environ
    for _ in range(90):
        try:
            conn = await asyncpg.connect(host=e["DB_HOST"], port=int(e["DB_PORT"]), user=e["DB_OWNER_USER"],
                                         password=e["DB_OWNER_PASSWORD"], database="postgres")
            break
        except (OSError, asyncpg.PostgresError) as err:
            print(f"switch-boot: waiting for postgres: {err}", flush=True)
            await asyncio.sleep(2)
    else:
        raise SystemExit("switch-boot: postgres never answered")
    try:
        for db in (e["DB_NAME"], "mattermost"):
            if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db):
                await conn.execute(f'CREATE DATABASE "{db}"')
        role = e["DB_USER"]
        password = e["DB_PASSWORD"].replace("'", "''")
        if not await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role):
            await conn.execute(f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{password}' "
                               "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS")
        await conn.execute(f"ALTER ROLE \"{role}\" PASSWORD '{password}'")
    finally:
        await conn.close()
    print("switch-boot: databases and runtime role ready", flush=True)


asyncio.run(init_db())
runpy.run_module("switch_core.main", run_name="__main__")
