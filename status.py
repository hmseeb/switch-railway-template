#!/usr/bin/env python3
"""Latest deployment status per service. Usage: status.py <projectId> [--logs svc]"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402

pid = sys.argv[1]
p = rw.gql("""query($id:String!){project(id:$id){services{edges{node{id name
  deployments(first:1){edges{node{id status}}}}}}}}""", {"id": pid})["project"]
for e in p["services"]["edges"]:
    n = e["node"]
    d = n["deployments"]["edges"]
    dep = d[0]["node"] if d else {}
    print(f"{n['name']:10} {dep.get('status')} {dep.get('id')}")
    if "--logs" in sys.argv and sys.argv[sys.argv.index("--logs") + 1] == n["name"] and dep:
        logs = rw.gql("query($d:String!){deploymentLogs(deploymentId:$d,limit:60){message}}", {"d": dep["id"]})
        print("\n".join(l["message"] for l in logs["deploymentLogs"]))
