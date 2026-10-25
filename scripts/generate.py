"""Generate dashboard.svg and stats.json from the GitHub API (aggregates only, no private names)."""
import json, os, urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

USER = os.environ.get("GH_USER", "jchin14")

NAME = "Jono"
# Profile text shown in the dashboard. SVG text does not wrap, so lines are pre-broken.
ABOUT = ["Hey, I'm Jono, a final-year engineering student in Melbourne",
         "who's into embedded hardware, RF/comms and networks, and a",
         "little obsessed with 5G deployments, spectrum and RAN. I've",
         "designed 18 PCBs for Monash Nova Rover, led its 15-person",
         "electrical team and helped bring home 5 international podiums.",
         "I've shrunk a neonatal research sensor's PCB by 58%, built a",
         "PoE sensor for 94% less than off-the-shelf, designed Wi-Fi for",
         "50+ clients and taught 1,800+ students. And when a gadget",
         "won't tell me how it works, I open it up and find out."]
HIRE = ("Open to embedded, RF & comms roles",
        ["Graduating 2026 · Melbourne · open to relocation",
         "PCB design · firmware · CAN · RF",
         "5G deployments · spectrum · RAN",
         "Wi-Fi & networks · UniFi · VLANs",
         "Altium Accredited PCB Design (Advanced)"],
        "github@jchin.au")
PROJECTS = [("Monash Nova Rover", ["Led a 15-person team through 13 modular PCBs, a",
                                   "CAN-FD migration and a Jetson Orin integration."]),
            ("Neonatal sensor probe", ["Summer research upgrading an ESP32 sensor probe:",
                                       "58% smaller PCB and 2× the telemetry rate."]),
            ("Making a dumb house smart", ["Reverse-engineered my Brivis air con's wall panel and",
                                           "built an ESP32 bridge into Home Assistant and HomeKit."]),
            ("Reverse-engineering UniFi", ["Decoding the UniFi protocol so SNMP and EasyMesh",
                                           "gear can join and be managed in my UniFi ecosystem."]),
            ("binarypb.jchin.au", ["Browser editor for the band combos a Pixel or Samsung",
                                   "modem advertises. Exports a Magisk module, no backend."]),
            ("cellular.jchin.au", ["My reference site for AU & NZ mobile networks:",
                                   "spectrum holdings, RAN vendors and 5G rollouts."]),
            ("JC Wireless", ["Designing and deploying UniFi Wi-Fi for homes and small",
                             "businesses around Melbourne. 2,000+ devices connected."]),
            ("MetroBae", ["Open the app, see the next tram from your closest stop.",
                          "React Native + PTV API, in development."])]
SUPPORT = ["Most of what I make is open source. Found a bug or want a feature? Open an issue or send a PR, I'm happy",
           "to help. If something here saved you time, a star means a lot, or you can buy me a coffee at",
           "buymeacoffee.com/jchin14. And if you're hiring for embedded, RF or comms, let's chat!"]

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


THEMES = {
    "light": dict(paper="#f7f6f1", ink="#151819", line="#cbcfc8", muted="#626765", blue="#0d5bd7", green="#237351", track="#e9e8e0",
                          heat=["#cfe6d2", "#9fcfa8", "#52a07a", "#237351"], blob1="#aecbff", o1=".55", blob2="#ffd9b8", o2=".55"),
    "dark": dict(paper="#0f1211", ink="#e8eae6", line="#2a2f2d", muted="#8d9390", blue="#6ea2ff", green="#39d353", track="#1d2220",
                               heat=["#0e4429", "#006d32", "#26a641", "#39d353"], blob1="#1d3a78", o1=".55", blob2="#5a3a1f", o2=".4"),
}


def render(fname, T):
    # Palette and type taken from jchin.au / portfolio.jchin.au
    PAPER, INK, LINE, MUTED, BLUE, GREEN, LIME, TRACK = T["paper"], T["ink"], T["line"], T["muted"], T["blue"], T["green"], "#c3f144", T["track"]
    SANS = "'DM Sans','Helvetica Neue',Helvetica,Arial,sans-serif"
    SERIF = "'Fraunces',Georgia,'Times New Roman',serif"
    MONO = "'DM Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


    def level(c):
        if not c:
            return TRACK
        r = c / mx
        return T["heat"][0] if r <= .25 else T["heat"][1] if r <= .5 else T["heat"][2] if r <= .75 else T["heat"][3]


    about_end = 120 + 20 * (len(ABOUT) - 1)
    top = about_end + 26  # divider under About
    grid = top + 50  # first project row
    rows_end = grid + 64 * ((len(PROJECTS) + 1) // 2)
    off = rows_end - 122  # shift for the stats block below
    foot = 504 + off + 22  # divider above Support
    W, H = 860, foot + 64 + 18 * len(SUPPORT)
    LBL = f'fill="{MUTED}" font-size="10" letter-spacing="1.4" font-family="{MONO}"'
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{SANS}">',
         f'<defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#7c5cff"/><stop offset="1" stop-color="#22d3ee"/></linearGradient><radialGradient id="b" cx=".85" cy=".05" r=".5"><stop offset="0" stop-color="{T["blob1"]}" stop-opacity="{T["o1"]}"/><stop offset="1" stop-color="{T["blob1"]}" stop-opacity="0"/></radialGradient>'
         f'<radialGradient id="p" cx=".05" cy=".98" r=".4"><stop offset="0" stop-color="{T["blob2"]}" stop-opacity="{T["o2"]}"/><stop offset="1" stop-color="{T["blob2"]}" stop-opacity="0"/></radialGradient></defs>',
         f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="2" fill="{PAPER}" stroke="{LINE}"/>',
         f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="2" fill="url(#b)"/><rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="2" fill="url(#p)"/>',
         f'<text x="24" y="46" font-size="26" font-weight="700" fill="{INK}">{escape(NAME)} · @{USER}</text>',
         '<rect x="24" y="58" width="120" height="3" rx="1.5" fill="url(#g)"/>',
         f'<text x="{W-24}" y="46" font-size="26" font-weight="700" fill="url(#g)" text-anchor="end">{years:.1f} years'
         f'<tspan fill="{MUTED}" font-size="14" font-weight="400"> on GitHub</tspan></text>',
         f'<text x="24" y="96" {LBL}>ABOUT</text><text x="490" y="96" {LBL}>WORK WITH ME</text>']
    for i, line in enumerate(ABOUT):
        o.append(f'<text x="24" y="{120 + i*20}" font-size="14" fill="{INK}">{escape(line)}</text>')
    title, lines, email = HIRE
    o.append(f'<rect x="490" y="108" width="{W-514}" height="{about_end - 96}" rx="4" fill="{PAPER}" fill-opacity=".6" stroke="url(#g)"/>'
             f'<text x="506" y="136" font-size="15" font-weight="700" fill="{INK}">{escape(title)}</text>')
    for i, line in enumerate(lines):
        o.append(f'<text x="506" y="{162 + i*20}" font-size="13" fill="{MUTED}">{escape(line)}</text>')
    o.append(f'<text x="506" y="{about_end - 2}" font-family="{MONO}" font-size="13" fill="{BLUE}">{escape(email)} →</text>')
    o.append(f'<path d="M24 {top}H{W-24}" stroke="{LINE}"/><text x="24" y="{top + 26}" {LBL}>WHAT I\'M BUILDING</text>')
    for i, (name, desc) in enumerate(PROJECTS):
        x, y = 24 + (i % 2) * 422, grid + (i // 2) * 64
        o.append(f'<rect x="{x}" y="{y-9}" width="6" height="6" rx="1" fill="url(#g)"/>'
                 f'<text x="{x+14}" y="{y}" font-size="14" font-weight="600" fill="{BLUE}">{escape(name)}</text>')
        for j, line in enumerate(desc):
            o.append(f'<text x="{x+14}" y="{y + 20 + j*17}" font-size="12.5" fill="{MUTED}">{escape(line)}</text>')
    o.append(f'<path d="M24 {rows_end}H{W-24}" stroke="{LINE}"/><g transform="translate(0,{off})">')
    colw = (W - 48) / 6
    for i, (k, v) in enumerate(tiles):
        x = 24 + i * colw
        if i:
            o.append(f'<path d="M{x-10:.0f} 134V184" stroke="{LINE}"/>')
        o.append(f'<text x="{x:.0f}" y="165" font-size="30" font-weight="700" letter-spacing="-1" fill="url(#g)">{v}</text>'
                 f'<text x="{x:.0f}" y="180" {LBL.replace('font-size="10"', 'font-size="9"')}>{k.upper()}</text>')
    o.append(f'<path d="M24 204H{W-24}" stroke="{LINE}"/>')
    o.append(f'<text x="24" y="230" {LBL}>LANGUAGES · BY COMMITS</text>')
    tot = sum(v for _, v in langs) or 1
    for i, (k, v) in enumerate(langs):
        y = 248 + i * 26
        o.append(f'<text x="24" y="{y+10}" font-size="13" font-weight="500" fill="{INK}">{escape(k)}</text>'
                 f'<rect x="130" y="{y+3}" width="230" height="6" rx="3" fill="{TRACK}"/>'
                 f'<rect x="130" y="{y+3}" width="{max(2, 230*v/tot):.0f}" height="6" rx="3" fill="url(#g)"/>'
                 f'<text x="400" y="{y+10}" font-family="{MONO}" font-size="11" fill="{MUTED}" text-anchor="end">{v}</text>')
    o.append(f'<text x="470" y="230" {LBL}>ACTIVITY · LAST 12 WEEKS</text>')
    for i, c in enumerate(cnt):
        x, y = 470 + (i // 7) * 32, 242 + (i % 7) * 17
        o.append(f'<rect x="{x}" y="{y}" width="28" height="13" fill="{level(c)}"/>')
    o.append(f'<text x="470" y="378" {LBL.replace('font-size="10"', 'font-size="9"')}>12 WEEKS AGO</text>'
             f'<text x="{470 + 11*32 + 28}" y="378" {LBL.replace('font-size="10"', 'font-size="9"')} text-anchor="end">LAST WEEK</text>')
    o.append(f'<path d="M24 396H{W-24}" stroke="{LINE}"/>')
    o.append(f'<text x="24" y="420" {LBL}>RECENTLY PUSHED</text><text x="470" y="420" {LBL}>RECENT EVENTS</text>')
    for i, r in enumerate(repos[:4]):
        y = 444 + i * 20
        o.append(f'<text x="24" y="{y}" font-size="14" font-weight="500" fill="{BLUE}">{escape(r["name"])[:26]}</text>'
                 f'<text x="420" y="{y}" font-family="{MONO}" font-size="11" fill="{MUTED}" text-anchor="end">'
                 f'★ {r["stargazers_count"]}{" · " + escape(r["language"]) if r["language"] else ""}</text>')
    for i, e in enumerate(events[:4]):
        y = 444 + i * 20
        o.append(f'<text x="470" y="{y}" font-size="14" font-weight="500" fill="{INK}">{escape(e["type"].replace("Event", ""))}'
                 f'<tspan font-weight="400" fill="{MUTED}"> {escape(e["repo"]["name"].split("/")[1])[:22]}</tspan></text>')
    o.append('</g>')
    o.append(f'<path d="M24 {foot}H{W-24}" stroke="{LINE}"/><text x="24" y="{foot + 26}" {LBL}>CONTRIBUTING &amp; SUPPORT</text>')
    for i, line in enumerate(SUPPORT):
        o.append(f'<text x="24" y="{foot + 50 + i*18}" font-size="13" fill="{INK}">{escape(line)}</text>')
    o.append(f'<text x="{W-24}" y="{H-8}" font-family="{MONO}" font-size="9" fill="#9da2a0" text-anchor="end">UPDATED {now.astimezone(ZoneInfo("Australia/Melbourne")):%Y-%m-%d %H:%M %Z}</text></svg>')
    open(fname, "w").write("\n".join(o))


# Light and dark variants; the README <picture> picks one from the viewer's own colour-scheme setting.
render("dashboard.svg", THEMES["light"])
render("dashboard-dark.svg", THEMES["dark"])


json.dump({"updated": now.isoformat(), "includes_private": bool(priv),
           "tiles": [{"label": k, "value": v} for k, v in tiles],
           "languages": [{"name": k, "count": v} for k, v in langs],
           "activity": cnt}, open("stats.json", "w"))
