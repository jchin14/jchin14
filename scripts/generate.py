"""Generate dashboard.svg from the public GitHub API."""
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

# Aggregate stats including private repos/commits (needs a PAT in PROFILE_TOKEN; only counts are published).
Q = """{viewer{followers{totalCount} following{totalCount}
 repositories(ownerAffiliations:OWNER,first:100){totalCount nodes{isPrivate isFork stargazerCount primaryLanguage{name}}}
 contributionsCollection{totalCommitContributions restrictedContributionsCount
  contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
priv = None
tok = os.environ.get("PROFILE_TOKEN")
if tok:
    rq = urllib.request.Request("https://api.github.com/graphql", json.dumps({"query": Q}).encode(),
                                {"Authorization": "Bearer " + tok})
    priv = json.load(urllib.request.urlopen(rq))["data"]["viewer"]

stars = sum(r["stargazers_count"] for r in repos)
forks = sum(r["fork"] for r in repos)
years = (now - datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))).days / 365.25
tiles = [("Repos", user["public_repos"]), ("Stars", stars), ("Followers", user["followers"]),
         ("Following", user["following"]), ("Forks", forks), ("Years", f"{years:.1f}")]
if priv:
    nodes = priv["repositories"]["nodes"]
    cc = priv["contributionsCollection"]
    tiles = [("Repos", priv["repositories"]["totalCount"]), ("Private", sum(n["isPrivate"] for n in nodes)),
             ("Stars", sum(n["stargazerCount"] for n in nodes)), ("Followers", priv["followers"]["totalCount"]),
             ("Commits 1y", cc["totalCommitContributions"] + cc["restrictedContributionsCount"]),
             ("Years", f"{years:.1f}")]

langs = {}
for r in (priv["repositories"]["nodes"] if priv else repos):
    name = (r["primaryLanguage"] or {}).get("name") if priv else r["language"]
    if name:
        langs[name] = langs.get(name, 0) + 1
langs = sorted(langs.items(), key=lambda x: -x[1])[:5]

days = 84
cnt = [0] * days
for e in events:
    d = (now.date() - datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).date()).days
    if 0 <= d < days:
        cnt[days - 1 - d] += len(e["payload"].get("commits", [1]))
if priv:
    cal = {d["date"]: d["contributionCount"] for w in priv["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]}
    cnt = [cal.get(str(now.date() - timedelta(days=days - 1 - i)), 0) for i in range(days)]
mx = max(cnt + [1])

def ago(s):
    sec = (now - datetime.fromisoformat(s.replace("Z", "+00:00"))).total_seconds()
    return f"{max(1, int(sec // 60))}m" if sec < 3600 else f"{int(sec // 3600)}h" if sec < 86400 else f"{int(sec // 86400)}d"

o = ['<svg xmlns="http://www.w3.org/2000/svg" width="860" height="500" viewBox="0 0 860 500" font-family="Segoe UI,Helvetica,Arial,sans-serif">',
     '<defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#7c5cff"/><stop offset="1" stop-color="#22d3ee"/></linearGradient></defs>',
     '<rect width="860" height="500" rx="18" fill="#0b0f17"/>',
     f'<text x="30" y="46" fill="#e6edf3" font-size="26" font-weight="700">{escape(user.get("name") or USER)} · @{USER}</text>',
     '<rect x="30" y="58" width="120" height="3" rx="1.5" fill="url(#g)"/>']
for i, (k, v) in enumerate(tiles):
    x = 30 + i * 133
    o.append(f'<rect x="{x}" y="80" width="121" height="70" rx="12" fill="#121826" stroke="#1f2937"/>'
             f'<text x="{x+14}" y="118" fill="url(#g)" font-size="28" font-weight="700">{v}</text>'
             f'<text x="{x+14}" y="138" fill="#8b98a9" font-size="11" letter-spacing="1">{k.upper()}</text>')
o.append('<text x="30" y="188" fill="#8b98a9" font-size="12" letter-spacing="1">LANGUAGES</text>')
tot = sum(v for _, v in langs) or 1
for i, (k, v) in enumerate(langs):
    y = 204 + i * 28
    o.append(f'<text x="30" y="{y+10}" fill="#e6edf3" font-size="13">{escape(k)}</text>'
             f'<rect x="110" y="{y}" width="260" height="10" rx="5" fill="#1a2233"/>'
             f'<rect x="110" y="{y}" width="{260*v/tot:.0f}" height="10" rx="5" fill="url(#g)"/>'
             f'<text x="380" y="{y+10}" fill="#8b98a9" font-size="12">{v}</text>')
o.append('<text x="450" y="188" fill="#8b98a9" font-size="12" letter-spacing="1">ACTIVITY · 12 WEEKS</text>')
for i, c in enumerate(cnt):
    x, y = 450 + (i // 7) * 29, 202 + (i % 7) * 20
    fill = f'rgba(52,211,153,{.25+.75*c/mx:.2f})' if c else '#1a2233'
    o.append(f'<rect x="{x}" y="{y}" width="25" height="16" rx="3" fill="{fill}"/>')
o.append('<text x="30" y="372" fill="#8b98a9" font-size="12" letter-spacing="1">RECENTLY PUSHED</text>')
for i, r in enumerate(repos[:4]):
    y = 396 + i * 22
    o.append(f'<text x="30" y="{y}" fill="#e6edf3" font-size="14" font-weight="600">{escape(r["name"])}</text>'
             f'<text x="330" y="{y}" fill="#8b98a9" font-size="12">★ {r["stargazers_count"]} · {escape(r["language"] + " · " if r["language"] else "")}{ago(r["pushed_at"])} ago</text>')
o.append('<text x="560" y="372" fill="#8b98a9" font-size="12" letter-spacing="1">RECENT EVENTS</text>')
for i, e in enumerate(events[:4]):
    y = 396 + i * 22
    o.append(f'<text x="560" y="{y}" fill="#e6edf3" font-size="13">{escape(e["type"].replace("Event",""))} · {escape(e["repo"]["name"].split("/")[1])[:18]}</text>'
             f'<text x="810" y="{y}" fill="#8b98a9" font-size="12" text-anchor="end">{ago(e["created_at"])}</text>')
o.append(f'<text x="830" y="488" fill="#4b5563" font-size="10" text-anchor="end">updated {now:%Y-%m-%d %H:%M} UTC</text></svg>')
open("dashboard.svg", "w").write("\n".join(o))

json.dump({"updated": now.isoformat(), "includes_private": bool(priv),
           "tiles": [{"label": k, "value": v} for k, v in tiles],
           "languages": [{"name": k, "count": v} for k, v in langs],
           "activity": cnt}, open("stats.json", "w"))
