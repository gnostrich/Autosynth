"""Railway deploy helper for the ets-companion service. Self-contained: reads the
project-access token from /root/.railway_token, DISCOVERS the service + environment
ids from the API (no hardcoded/scraped ids), and can trigger a redeploy of a commit.

Usage:
  python3 deploy.py discover              # print project/services/environments (ids)
  python3 deploy.py deploy <commitSha>    # redeploy that commit on ets-companion

The token is read from disk and never printed. Save this file so the deploy path is
reproducible across sessions (the operator asked for the whole path saved, not just
the secret)."""
import json, sys, os, requests

GQL = "https://backboard.railway.app/graphql/v2"
TOKEN = open("/root/.railway_token").read().strip()   # project-access token

def q(query, variables=None):
    r = requests.post(GQL, json={"query": query, "variables": variables or {}},
                      headers={"Project-Access-Token": TOKEN}, timeout=45)
    r.raise_for_status()
    out = r.json()
    if out.get("errors"):
        raise SystemExit("GQL errors: " + json.dumps(out["errors"])[:500])
    return out["data"]

# A project-access token is scoped to ONE project; this returns that project.
PROJECT_Q = """
query {
  projectToken {
    projectId
    environmentId
    project {
      name
      services { edges { node { id name } } }
      environments { edges { node { id name } } }
    }
  }
}"""

def discover():
    d = q(PROJECT_Q)["projectToken"]
    proj = d["project"]
    svcs = [(e["node"]["name"], e["node"]["id"]) for e in proj["services"]["edges"]]
    envs = [(e["node"]["name"], e["node"]["id"]) for e in proj["environments"]["edges"]]
    print("project:", proj["name"])
    print("token-default environmentId:", d.get("environmentId"))
    print("services:")
    for n, i in svcs: print("   ", n, i)
    print("environments:")
    for n, i in envs: print("   ", n, i)
    return d, svcs, envs

def pick_companion(svcs):
    # the live companion (www.autosynth.fun) is the 'ets-web' service.
    for n, i in svcs:
        if n.lower() == "ets-web":
            return n, i
    for n, i in svcs:
        if "web" in n.lower() or "compan" in n.lower():
            return n, i
    return svcs[0] if svcs else (None, None)

DEPLOY_M = """
mutation($serviceId: String!, $environmentId: String!, $commitSha: String) {
  serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId, commitSha: $commitSha)
}"""

def deploy(commit):
    d, svcs, envs = discover()
    envid = d.get("environmentId") or (envs[0][1] if envs else None)
    name, svcid = pick_companion(svcs)
    print(f"\ndeploying commit {commit} on service '{name}' ({svcid}) env {envid}")
    res = q(DEPLOY_M, {"serviceId": svcid, "environmentId": envid, "commitSha": commit})
    print("deploy result:", json.dumps(res)[:300])

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "discover"
    if cmd == "discover":
        discover()
    elif cmd == "deploy":
        deploy(sys.argv[2])
    else:
        raise SystemExit("usage: deploy.py [discover|deploy <commitSha>]")
