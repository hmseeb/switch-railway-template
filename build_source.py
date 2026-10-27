#!/usr/bin/env python3
"""Materialize template.json into an existing empty live project, mirroring a template
deploy: services empty first, then bucket/volume/domain, then variables, then images
and deploys, so every ${{...}} reference resolves on first boot.

projectCreate via API is "Not Authorized" in My Projects (billing state) but
`railway init -w <ws>` works, so create the project with the CLI and pass its id.

Usage: build_source.py <projectId>
"""
import json
import os
import pathlib
import re
import secrets
import string
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402
from upsert import load_sheet  # noqa: E402

HERE = pathlib.Path(__file__).parent
SECRET = re.compile(r'\$\{\{\s*secret\((\d+)(?:,\s*"([^"]+)")?\)\s*\}\}')


def live_value(v):
    """A live project cannot evaluate ${{secret()}}; generate the literal here."""
    def gen(m):
        alphabet = m.group(2) or string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(int(m.group(1))))
    return SECRET.sub(gen, v)


def main():
    sheet = load_sheet()
    pid = sys.argv[1]
    p = rw.gql("query($id:String!){project(id:$id){environments{edges{node{id name}}}}}", {"id": pid})["project"]
    env = next(e["node"]["id"] for e in p["environments"]["edges"] if e["node"]["name"] == "production")
    out = {"projectId": pid, "environmentId": env, "services": {}, "domains": {}}

    for name in sheet["services"]:
        out["services"][name] = rw.gql("mutation($i:ServiceCreateInput!){serviceCreate(input:$i){id}}",
                                       {"i": {"projectId": pid, "environmentId": env, "name": name}})["serviceCreate"]["id"]
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["railway", "link", "-p", pid, "-e", env], cwd=d, check=True, capture_output=True)
        for b in sheet.get("buckets", []):
            subprocess.run(["railway", "bucket", "create", b, "-r", "iad", "--json"], cwd=d, check=True, capture_output=True)

    for name, s in sheet["services"].items():
        sid = out["services"][name]
        if "volumeMounts" in s:
            rw.gql("mutation($i:VolumeCreateInput!){volumeCreate(input:$i){id}}",
                   {"i": {"projectId": pid, "environmentId": env, "serviceId": sid, "mountPath": s["volumeMounts"]["mountPath"]}})
        if "networking" in s:
            dom = rw.gql("mutation($i:ServiceDomainCreateInput!){serviceDomainCreate(input:$i){domain}}",
                         {"i": {"environmentId": env, "serviceId": sid, "targetPort": s["networking"]["port"]}})
            out["domains"][name] = "https://" + dom["serviceDomainCreate"]["domain"]

    for name, s in sheet["services"].items():
        rw.gql("mutation($i:VariableCollectionUpsertInput!){variableCollectionUpsert(input:$i)}",
               {"i": {"projectId": pid, "environmentId": env, "serviceId": out["services"][name], "replace": True,
                      "skipDeploys": True, "variables": {k: live_value(v.get("defaultValue") or os.environ.get(k, "")) for k, v in s["variables"].items()}}})

    for name, s in sheet["services"].items():
        sid = out["services"][name]
        update = {"source": {"image": s["source"]["image"]}, **{k: v for k, v in s["deploy"].items() if v is not None}}
        if "healthcheckPath" in update:
            update["healthcheckTimeout"] = 300  # what published templates get
        rw.gql("mutation($s:String!,$e:String!,$i:ServiceInstanceUpdateInput!){serviceInstanceUpdate(serviceId:$s,environmentId:$e,input:$i)}",
               {"s": sid, "e": env, "i": update})
        rw.gql("mutation($s:String!,$e:String!){serviceInstanceDeployV2(serviceId:$s,environmentId:$e)}", {"s": sid, "e": env})

    (HERE / "source-project.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
