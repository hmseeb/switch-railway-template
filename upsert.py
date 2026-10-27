#!/usr/bin/env python3
"""template.json -> Railway template via templateUpsertConfig (internal endpoint), then
read it back and assert every field. No source project: the sheet IS the config.

Usage: upsert.py [templateId]   (omit to mint a new template; id saved to template-id)
"""
import json
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402

HERE = pathlib.Path(__file__).parent
import os
# Test copies go to My Projects: TEMPLATE_WS=d10da65a-... TEMPLATE_IDFILE=template-id.test
WORKSPACE = os.environ.get("TEMPLATE_WS", "fc4796db-2c6c-4354-a564-d4a1d900af53")  # default Auromations


def strip_notes(x):
    if isinstance(x, dict):
        return {k: strip_notes(v) for k, v in x.items() if not k.startswith("$")}
    return x


def load_sheet():
    """template.json minus $notes, with "@<file>" values replaced by that file's contents."""
    sheet = strip_notes(json.loads((HERE / "template.json").read_text()))
    for svc in sheet["services"].values():
        for v in svc["variables"].values():
            if v.get("defaultValue", "").startswith("@"):
                v["defaultValue"] = (HERE / v["defaultValue"][1:]).read_text()
    return sheet


def build(sheet):
    services = {}
    for name, s in sheet["services"].items():
        svc = {"name": name, "icon": s["icon"], "source": dict(s["source"]), "deploy": dict(s.get("deploy", {})),
               "variables": {k: {"isOptional": False, **v} for k, v in s["variables"].items()}}
        if "volumeMounts" in s:
            svc["volumeMounts"] = {str(uuid.uuid4()): s["volumeMounts"]}
        if "networking" in s:
            p = s["networking"]["port"]
            svc["networking"] = {"serviceDomains": {f"<hasDomain>:{p}": {"port": p}}}
        services[str(uuid.uuid4())] = svc
    return {"buckets": {str(uuid.uuid4()): {"name": b} for b in sheet.get("buckets", [])}, "services": services}


def main():
    sheet = load_sheet()
    idfile = HERE / os.environ.get("TEMPLATE_IDFILE", "template-id")
    tid = sys.argv[1] if len(sys.argv) > 1 else (idfile.read_text().strip() if idfile.exists() else str(uuid.uuid4()))
    want = build(sheet)
    if idfile.exists():  # keep existing service/volume/bucket ids on an update
        cur = rw.gql("query($id:String!){template(id:$id){serializedConfig}}", {"id": tid})["template"]["serializedConfig"]
        by = {s["name"]: k for k, s in cur["services"].items()}
        want["services"] = {by.get(s["name"], k): s for k, s in want["services"].items()}
        for k, s in want["services"].items():
            if "volumeMounts" in s and k in cur["services"]:
                s["volumeMounts"] = cur["services"][k].get("volumeMounts") or s["volumeMounts"]
        want["buckets"] = cur.get("buckets") or want["buckets"]
    saved = rw.gql("""mutation($id:String!,$input:TemplateUpsertConfigInput!){
                        templateUpsertConfig(id:$id,input:$input){id code}}""",
                   {"id": tid, "input": {"name": sheet["name"], "workspaceId": WORKSPACE,
                                         "serializedConfig": want, "canvasConfig": {}}}, internal=True)["templateUpsertConfig"]
    idfile.write_text(saved["id"] + "\n")
    print("saved", saved)

    back = rw.gql("query($c:String!){template(code:$c){serializedConfig}}", {"c": saved["code"]})["template"]["serializedConfig"]
    problems = []
    got = {s["name"]: s for s in back["services"].values()}
    for s in want["services"].values():
        g = got.get(s["name"])
        if not g:
            problems.append(f"{s['name']} missing")
            continue
        for k, v in s["variables"].items():
            gv = g.get("variables", {}).get(k, {})
            if (gv.get("defaultValue") or None) != v.get("defaultValue"):  # prompted vars have none
                problems.append(f"{s['name']}.{k} = {gv.get('defaultValue')!r}")
        for f in ("startCommand", "healthcheckPath", "restartPolicyType"):
            if s["deploy"].get(f) != (g.get("deploy") or {}).get(f):
                problems.append(f"{s['name']}.{f} = {(g.get('deploy') or {}).get(f)!r}")
        if s["source"]["image"] != g["source"].get("image"):
            problems.append(f"{s['name']}.image")
        if s.get("networking") != g.get("networking"):
            problems.append(f"{s['name']}.networking = {g.get('networking')}")
        if bool(s.get("volumeMounts")) != bool(g.get("volumeMounts")):
            problems.append(f"{s['name']} volume")
    if re.findall(r"\$\{\{\s*[0-9a-f]{8}-[0-9a-f]{4}-", json.dumps(back)):
        problems.append("UUID-keyed reference")
    if [b["name"] for b in (back.get("buckets") or {}).values()] != sheet.get("buckets", []):
        problems.append(f"buckets {back.get('buckets')}")
    print("\n".join(problems) or "read-back verified")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
