#!/usr/bin/env python3
"""Generate self-hosted GitHub stats cards (stats.svg, langs.svg) for a profile README.

Runs inside GitHub Actions with the default GITHUB_TOKEN, so it does not depend on
any third-party stats server. Output goes to ./dist (or the path in argv[1]).
Set MOCK=1 to render sample data without touching the network.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

OUT = sys.argv[1] if len(sys.argv) > 1 else "dist"
USER = os.environ.get("GITHUB_REPOSITORY_OWNER", "not-xygen")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
MOCK = os.environ.get("MOCK") == "1"

BG, BORDER = "#000000", "#2a1214"
RED, TEXT, MUTED, TRACK = "#ef4444", "#e6edf3", "#8b949e", "#1c1c1f"
RAMP = ["#ef4444", "#dc2626", "#f87171", "#b91c1c", "#fca5a5", "#7f1d1d"]
FONT = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"


def api(path, params=None):
    url = "https://api.github.com" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-stats",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def safe(fn, default):
    try:
        return fn()
    except Exception as exc:  # keep going: one failed call must not break the workflow
        print(f"warn: {exc}", file=sys.stderr)
        return default


def collect():
    if MOCK:
        return {
            "name": "Dhaffa Agus", "repos": 28, "stars": 14, "followers": 35,
            "forks": 3, "commits": 812, "prs": 41, "issues": 9,
            "langs": {"TypeScript": 520000, "JavaScript": 210000, "Rust": 90000,
                      "Vue": 60000, "Go": 30000, "Dart": 25000, "HTML": 20000},
        }
    user = api(f"/users/{USER}")
    repos, page = [], 1
    while True:
        chunk = api(f"/users/{USER}/repos", {"per_page": 100, "page": page, "type": "owner"})
        repos += chunk
        if len(chunk) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"]]
    langs = {}
    for r in own:
        for lang, n in safe(lambda r=r: api(f"/repos/{USER}/{r['name']}/languages"), {}).items():
            langs[lang] = langs.get(lang, 0) + n
    count = lambda path, q: safe(lambda: api(path, {"q": q, "per_page": 1})["total_count"], 0)
    return {
        "name": user.get("name") or USER,
        "repos": user.get("public_repos", len(repos)),
        "stars": sum(r["stargazers_count"] for r in own),
        "followers": user.get("followers", 0),
        "forks": sum(r["forks_count"] for r in own),
        "commits": count("/search/commits", f"author:{USER}"),
        "prs": count("/search/issues", f"author:{USER} type:pr"),
        "issues": count("/search/issues", f"author:{USER} type:issue"),
        "langs": langs,
    }


def card(title, body, w=495, h=195):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{escape(title)}">'
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" fill="{BG}" stroke="{BORDER}"/>'
        f'<text x="28" y="38" font-family="{FONT}" font-size="18" font-weight="600" fill="{RED}">{escape(title)}</text>'
        f'{body}</svg>'
    )


def stats_svg(d):
    rows = [("Public repos", d["repos"]), ("Stars earned", d["stars"]), ("Commits", d["commits"]),
            ("Pull requests", d["prs"]), ("Issues", d["issues"]), ("Followers", d["followers"])]
    parts = []
    for i, (label, val) in enumerate(rows):
        col, row = i % 2, i // 2
        x, y = 28 + col * 225, 76 + row * 42
        parts.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="12" fill="{MUTED}">{escape(label)}</text>'
            f'<text x="{x}" y="{y+20}" font-family="{FONT}" font-size="20" font-weight="600" fill="{TEXT}">{val:,}</text>'
        )
    return card(f"{d['name']}'s GitHub Stats", "".join(parts))


def langs_svg(d):
    total = sum(d["langs"].values()) or 1
    top = sorted(d["langs"].items(), key=lambda kv: -kv[1])[:6]
    shown = sum(n for _, n in top)
    items = [(k, n / total * 100) for k, n in top]
    if total - shown > 0:
        items.append(("Other", (total - shown) / total * 100))
    bar_x, bar_w, bar_y = 28, 439, 58
    color = lambda i, name: "#52525b" if name == "Other" else RAMP[i % len(RAMP)]
    parts = [f'<clipPath id="c"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="10" rx="5"/></clipPath>'
             f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="10" rx="5" fill="{TRACK}"/><g clip-path="url(#c)">']
    x = bar_x
    for i, (name, pct) in enumerate(items):
        w = bar_w * pct / 100
        parts.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{w:.2f}" height="10" fill="{color(i, name)}"/>')
        x += w
    parts.append("</g>")
    for i, (lang, pct) in enumerate(items):
        col, row = i % 2, i // 2
        cx, cy = 28 + col * 225, 98 + row * 24
        parts.append(
            f'<circle cx="{cx+5}" cy="{cy-4}" r="5" fill="{color(i, lang)}"/>'
            f'<text x="{cx+18}" y="{cy}" font-family="{FONT}" font-size="12.5" fill="{TEXT}">{escape(lang)}'
            f' <tspan fill="{MUTED}">{pct:.1f}%</tspan></text>'
        )
    return card("Top Languages", "".join(parts))


def main():
    data = collect()
    os.makedirs(OUT, exist_ok=True)
    for name, svg in (("stats.svg", stats_svg(data)), ("langs.svg", langs_svg(data))):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(svg)
    print("wrote", os.listdir(OUT))


if __name__ == "__main__":
    main()
