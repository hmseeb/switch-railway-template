#!/usr/bin/env python3
"""Rename (slug comes from the stored name), set icon, then publish in Auromations."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402

HERE = pathlib.Path(__file__).parent
WS = "fc4796db-2c6c-4354-a564-d4a1d900af53"
TID = (HERE / "template-id").read_text().strip()
NAME = json.loads((HERE / "template.json").read_text())["name"]
DESC = "Team server for AI coding agents in Slack, Teams, Discord or Mattermost"
ICON = "https://cdn.prod.website-files.com/6a26f9dd113918ff685f6913/6ac805606fcbcbc3e2ac7d8a_switch-webclip.png"
assert len(DESC) <= 75 and "\u2014" not in DESC

rw.gql("mutation($id:String!,$i:TemplateUpsertSettingsInput!){templateUpsertSettings(id:$id,input:$i){id}}",
       {"id": TID, "i": {"workspaceId": WS, "name": NAME, "image": ICON, "description": DESC}}, internal=True)
got = rw.gql("query($id:String!){template(id:$id){name}}", {"id": TID})["template"]["name"]
assert got == NAME, got
r = rw.gql("mutation($id:String!,$i:TemplatePublishInput!){templatePublish(id:$id,input:$i){id code status}}",
           {"id": TID, "i": {"workspaceId": WS, "category": "AI/ML", "description": DESC, "image": ICON,
                             "readme": (HERE / "TEMPLATE_OVERVIEW.md").read_text()}})
print(r)
