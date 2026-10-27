#!/usr/bin/env python3
"""Deploy the template into a brand-new project, exactly what the button does.
Prompted variables (no default) are answered from same-named env vars.

Usage: deploy_as_stranger.py [templateId] [workspaceId]
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402

WORKSPACE = sys.argv[2] if len(sys.argv) > 2 else "fc4796db-2c6c-4354-a564-d4a1d900af53"  # default Auromations
tid = sys.argv[1] if len(sys.argv) > 1 else (pathlib.Path(__file__).parent / "template-id").read_text().strip()
t = rw.gql("query($id: String!) { template(code: $id) { id serializedConfig } }", {"id": tid})["template"]
# answer the deploy form's prompts (variables with no default) from the environment, as a deployer types them
for svc in t["serializedConfig"]["services"].values():
    for k, v in svc.get("variables", {}).items():
        if not v.get("defaultValue") and not v.get("isOptional"):
            v["defaultValue"] = os.environ[k]
r = rw.gql("""mutation($input: TemplateDeployV2Input!) { templateDeployV2(input: $input) { projectId workflowId } }""",
           {"input": {"templateId": t["id"], "workspaceId": WORKSPACE, "serializedConfig": t["serializedConfig"]}},
           internal=True)["templateDeployV2"]
print(json.dumps(r, indent=2))
