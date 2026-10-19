#!/usr/bin/env python3
"""Rebuild index.html for Dad's 80th trip site from data.json.

Usage:
  python3 build.py            # rebuild index.html from data.json (with privacy + date checks)
  python3 build.py --publish  # rebuild, then git commit + push (GitHub Pages redeploys in ~1 min)

Only whitelisted, non-private fields are published. Guests: name, status, party,
dates/flights/lodging checkboxes, optional role. Never emails, phones, or notes.
Only dates in July or August 2027 are allowed on the page.
"""
import json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RSVP = "chief_hamish+edinburgh80@mail.grokbot.com"
STATUSES = {"Committed", "Considering", "Not coming", "No reply"}
WINDOW = re.compile(r"^2027-0[78]-\d\d$")

def b(v):
    return v is True or str(v).strip().lower() in {"true", "yes", "__yes__", "1", "✓", "x"}

def in_window(d):
    return bool(d) and bool(WINDOW.match(str(d)[:10]))

def clean(data):
    t = data.get("trip", {})
    trip = {
        "title": t.get("title", "Dad's 80th in Scotland"),
        "place": t.get("place", "Edinburgh, Scotland"),
        "window": t.get("window", "July – August 2027"),
        "birthday": "2027-08-05",                       # hard rule
        "birthday_tz_offset": t.get("birthday_tz_offset", "+01:00"),
        "rsvp_email": RSVP,
        "tagline": t.get("tagline", ""),
    }
    guests = []
    for g in data.get("guests", []):
        st = g.get("status") or "No reply"
        guests.append({
            "name": str(g["name"]).strip(),
            "status": st if st in STATUSES else "No reply",
            "party": int(g.get("party") or 1),
            "dates": b(g.get("dates")), "flights": b(g.get("flights")), "lodging": b(g.get("lodging")),
            **({"role": g["role"]} if g.get("role") else {}),
        })
    acts = []
    for a in data.get("activities", []):
        s, e = a.get("start"), a.get("end")
        if s and not in_window(s):
            continue                                     # drop anything outside Jul/Aug 2027
        if e and not in_window(e):
            e = None
        item = {k: a.get(k) for k in ("name", "status", "who", "notes", "time", "link", "highlight") if a.get(k)}
        item.update({"start": s or None, "end": e or None})
        acts.append(item)
    todos = [{k: t.get(k) for k in ("name", "status", "owner", "notes") if t.get(k)}
             for t in data.get("todos", [])]
    # flights/lodging: only non-sensitive summary fields (no confirmation #s, costs, notes)
    flights = [{"traveler": f.get("traveler", ""), "direction": f.get("direction", ""), "status": f.get("status", "")}
               for f in data.get("flights", [])]
    lodging = [{"name": l.get("name", ""), "type": l.get("type", ""), "status": l.get("status", "")}
               for l in data.get("lodging", [])]
    return {"trip": trip, "guests": guests, "activities": acts, "todos": todos,
            "flights": flights, "lodging": lodging}

def privacy_check(html):
    emails = set(re.findall(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}", html)) - {RSVP}
    phones = re.findall(r"(?<![\w#-])\+?\d[\d ()./-]{8,}\d(?![\w-])", html)
    phones = [p for p in phones if len(re.sub(r"\D", "", p)) >= 10 and not re.match(r"^20\d\d-\d\d-\d\d", p)]
    bad_dates = [d for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", html) if not in_window(d)]
    problems = []
    if emails: problems.append(f"emails found: {sorted(emails)}")
    if phones: problems.append(f"phone-like numbers found: {phones}")
    if bad_dates: problems.append(f"dates outside Jul/Aug 2027: {sorted(set(bad_dates))}")
    return problems

def main():
    data = clean(json.loads((HERE / "data.json").read_text()))
    blob = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    html = (HERE / "template.html").read_text().replace("__TRIP_DATA__", blob)
    problems = privacy_check(html)
    if problems:
        sys.exit("REFUSING TO BUILD:\n  " + "\n  ".join(problems))
    (HERE / "index.html").write_text(html)
    c = {}
    for g in data["guests"]: c[g["status"]] = c.get(g["status"], 0) + g["party"]
    print(f"Built index.html · {len(data['guests'])} guests {c} · {len(data['activities'])} activities · {len(data['todos'])} to-dos")
    if "--publish" in sys.argv:
        git = lambda *a: subprocess.run(["git", "-C", str(HERE), *a], check=False)
        git("add", "index.html", "data.json", "template.html", "build.py", "README.md")
        git("commit", "-m", "Update trip page")
        r = subprocess.run(["git", "-C", str(HERE), "push", "origin", "main"])
        if r.returncode: sys.exit("push failed")
        print("Pushed. GitHub Pages redeploys in about a minute.")

if __name__ == "__main__":
    main()
