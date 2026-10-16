"""Generate dashboard.svg and stats.json from the GitHub API (aggregates only, no private names)."""
import json, os, urllib.request
from datetime import datetime, timedelta, timezone
from html import escape

USER = os.environ.get("GH_USER", "jchin14")


def get(path):
    req = urllib.request.Request("https://api.github.com/" + path)
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    return json.load(urllib.request.urlopen(req))


user = get(f"users/{USER}")
repos = get(f"users/{USER}/repos?per_page=100&sort=pushed")
events = get(f"users/{USER}/events/public?per_page=100")
now = datetime.now(timezone.utc)

# Aggregates including private repos need a PAT in PROFILE_TOKEN.
REPO = "nodes{nameWithOwner isPrivate isFork stargazerCount primaryLanguage{name} owner{login}}"
Q = """{viewer{followers{totalCount}
 repositories(ownerAffiliations:[OWNER,COLLABORATOR,ORGANIZATION_MEMBER],first:100){%s}
 organizations(first:50){nodes{repositories(first:100){%s}}}
 contributionsCollection{totalCommitContributions restrictedContributionsCount
  contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}""" % (REPO, REPO)
priv = None
tok = os.environ.get("PROFILE_TOKEN")


def gql(query):
    rq = urllib.request.Request("https://api.github.com/graphql", json.dumps({"query": query}).encode(),
                                {"Authorization": "Bearer " + tok})
    return json.load(urllib.request.urlopen(rq))["data"]


if tok:
    priv = gql(Q)["viewer"]

stars = sum(r["stargazers_count"] for r in repos)
forks = sum(r["fork"] for r in repos)
years = (now - datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))).days / 365.25
tiles = [("Repos", user["public_repos"]), ("Stars", stars), ("Followers", user["followers"]),
         ("Following", user["following"]), ("Forks", forks), ("Public", user["public_repos"])]

# Languages: commits you authored, grouped by each repo's primary language.
langs = {}
if priv:
    allr = priv["repositories"]["nodes"] + [r for o in priv["organizations"]["nodes"] for r in o["repositories"]["nodes"]]
    nodes = list({n["nameWithOwner"]: n for n in allr}.values())
    mine = [n for n in nodes if n["owner"]["login"].lower() == USER.lower()]
    cc = priv["contributionsCollection"]
    tiles = [("Repos", len(mine)), ("Private", sum(n["isPrivate"] for n in mine)),
             ("Contributed to", len(nodes) - len(mine)), ("Stars", sum(n["stargazerCount"] for n in nodes)),
             ("Followers", priv["followers"]["totalCount"]),
             ("Commits 1y", cc["totalCommitContributions"] + cc["restrictedContributionsCount"])]
    # Commits you authored per repo (default branch), in small batches to keep queries light.
    withlang = [n for n in nodes if n["primaryLanguage"]]
    for i in range(0, len(withlang), 15):
        batch = withlang[i:i + 15]
        body = " ".join(
            'r%d: repository(owner:"%s",name:"%s"){defaultBranchRef{target{... on Commit{history(author:{id:"%s"}){totalCount}}}}}'
            % (j, n["owner"]["login"], n["nameWithOwner"].split("/")[1], user["node_id"]) for j, n in enumerate(batch))
        res = gql("{" + body + "}")
        for j, n in enumerate(batch):
            h = (((res.get("r%d" % j) or {}).get("defaultBranchRef") or {}).get("target") or {}).get("history") or {}
            if h.get("totalCount"):
                name = n["primaryLanguage"]["name"]
                langs[name] = langs.get(name, 0) + h["totalCount"]
else:
    for r in repos:
        if r["language"]:
            langs[r["language"]] = langs.get(r["language"], 0) + 1
langs = sorted(langs.items(), key=lambda x: -x[1])[:5]

days = 84
cnt = [0] * days
for e in events:
    d = (now.date() - datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).date()).days
    if 0 <= d < days:
        cnt[days - 1 - d] += len(e["payload"].get("commits", [1]))
if priv:
    cal = {d["date"]: d["contributionCount"] for w in priv["contributionsCollection"]["contributionCalendar"]["weeks"]
           for d in w["contributionDays"]}
    cnt = [cal.get(str(now.date() - timedelta(days=days - 1 - i)), 0) for i in range(days)]
mx = max(cnt + [1])


def ago(s):
    sec = (now - datetime.fromisoformat(s.replace("Z", "+00:00"))).total_seconds()
    return f"{max(1, int(sec // 60))}m" if sec < 3600 else f"{int(sec // 3600)}h" if sec < 86400 else f"{int(sec // 86400)}d"


def level(c):
    if not c:
        return "#161b22"
    r = c / mx
    return "#0e4429" if r <= .25 else "#006d32" if r <= .5 else "#26a641" if r <= .75 else "#39d353"


W, H = 860, 492
M = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
LBL = f'fill="#8b949e" font-size="11" letter-spacing="1.2" font-family="{M}"'
o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{M}">',
     f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="6" fill="#0d1117" stroke="#30363d"/>',
     f'<text x="24" y="46" font-size="24" font-weight="600" fill="#e6edf3">{escape(user.get("name") or USER)}'
     f'<tspan fill="#8b949e" font-size="16" font-weight="400"> @{USER}</tspan></text>',
     f'<text x="{W-24}" y="46" font-size="24" font-weight="600" fill="#58a6ff" text-anchor="end">{years:.1f} yrs'
     f'<tspan fill="#8b949e" font-size="13" font-weight="400"> on GitHub</tspan></text>',
     f'<path d="M0 68H{W}" stroke="#30363d"/>']
colw = (W - 48) / 6
for i, (k, v) in enumerate(tiles):
    x = 24 + i * colw
    if i:
        o.append(f'<path d="M{x-12:.0f} 84V138" stroke="#21262d"/>')
    o.append(f'<text x="{x:.0f}" y="116" font-size="26" font-weight="600" fill="#e6edf3">{v}</text>'
             f'<text x="{x:.0f}" y="134" {LBL.replace('font-size="11"', 'font-size="10"')}>{k.upper()}</text>')
o.append(f'<path d="M0 156H{W}" stroke="#30363d"/>')
o.append(f'<text x="24" y="184" {LBL}>LANGUAGES · BY COMMITS</text>')
tot = sum(v for _, v in langs) or 1
for i, (k, v) in enumerate(langs):
    y = 204 + i * 26
    o.append(f'<text x="24" y="{y+9}" font-size="12" fill="#c9d1d9">{escape(k)}</text>'
             f'<rect x="130" y="{y+2}" width="230" height="6" rx="1" fill="#21262d"/>'
             f'<rect x="130" y="{y+2}" width="{max(2, 230*v/tot):.0f}" height="6" rx="1" fill="#58a6ff"/>'
             f'<text x="400" y="{y+9}" font-size="12" fill="#8b949e" text-anchor="end">{v}</text>')
o.append(f'<text x="470" y="184" {LBL}>ACTIVITY · 12 WEEKS</text>')
for i, c in enumerate(cnt):
    x, y = 470 + (i // 7) * 25, 198 + (i % 7) * 20
    o.append(f'<rect x="{x}" y="{y}" width="21" height="16" rx="2" fill="{level(c)}"/>')
o.append(f'<path d="M0 352H{W}" stroke="#30363d"/>')
o.append(f'<text x="24" y="378" {LBL}>RECENTLY PUSHED</text><text x="470" y="378" {LBL}>RECENT EVENTS</text>')
for i, r in enumerate(repos[:4]):
    y = 402 + i * 20
    o.append(f'<text x="24" y="{y}" font-size="13" fill="#58a6ff">{escape(r["name"])[:26]}</text>'
             f'<text x="420" y="{y}" font-size="12" fill="#8b949e" text-anchor="end">'
             f'★ {r["stargazers_count"]} · {escape(r["language"] + " · " if r["language"] else "")}{ago(r["pushed_at"])}</text>')
for i, e in enumerate(events[:4]):
    y = 402 + i * 20
    o.append(f'<text x="470" y="{y}" font-size="13" fill="#c9d1d9">{escape(e["type"].replace("Event", ""))}'
             f'<tspan fill="#8b949e"> {escape(e["repo"]["name"].split("/")[1])[:22]}</tspan></text>'
             f'<text x="{W-24}" y="{y}" font-size="12" fill="#8b949e" text-anchor="end">{ago(e["created_at"])}</text>')
o.append(f'<text x="{W-24}" y="{H-14}" font-size="10" fill="#484f58" text-anchor="end">updated {now:%Y-%m-%d %H:%M} UTC</text></svg>')
open("dashboard.svg", "w").write("\n".join(o))

json.dump({"updated": now.isoformat(), "includes_private": bool(priv),
           "tiles": [{"label": k, "value": v} for k, v in tiles],
           "languages": [{"name": k, "count": v} for k, v in langs],
           "activity": cnt}, open("stats.json", "w"))
