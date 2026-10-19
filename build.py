#!/usr/bin/env python3
"""Rebuild index.html for Dad's 80th trip site from data.json.

Usage:
  python3 build.py            # rebuild index.html from data.json (with privacy + date checks)
  python3 build.py --publish  # rebuild, then git commit + push (GitHub Pages redeploys in ~1 min)
  python3 build.py --add-chat "Name" "message" [--date ISO] [--publish]
                              # append a chat message to data.json, rebuild (and push)

Chat timestamps are exempt from the July/August-2027 date rule (that rule covers the
calendar/schedule data); emails and phone numbers in chat names/text are stripped.

Only whitelisted, non-private fields are published. Guests: name, status, party,
dates/flights/lodging checkboxes, optional role. Never emails, phones, or notes.
Only dates in July or August 2027 are allowed on the page.
"""
import argparse, json, re, subprocess, sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RSVP = "chief_hamish+edinburgh80@mail.grokbot.com"
STATUSES = {"Committed", "Considering", "Not coming", "No reply"}
WINDOW = re.compile(r"^2027-0[78]-\d\d$")

def b(v):
    return v is True or str(v).strip().lower() in {"true", "yes", "__yes__", "1", "✓", "x"}

EMAIL_RE = re.compile(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\w#/-])\+?\(?\d[\d ()./-]{6,}\d(?![\w/-])")

def scrub(text):
    """Remove emails and phone-like numbers (7+ digits, not ISO dates) from free text."""
    text = EMAIL_RE.sub("[email removed]", str(text or ""))
    def ph(m):
        v = m.group(0)
        if re.fullmatch(r"\d{4}-\d\d-\d\d", v.strip()) or len(re.sub(r"\D", "", v)) < 7:
            return v
        return "[number removed]"
    return PHONE_RE.sub(ph, text)

def norm_date(d):
    d = str(d or "").strip()
    if not d:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
    except ValueError:
        sys.exit(f"Bad --date {d!r}; use ISO like 2026-10-20T14:05 or 2026-10-20")
    if dt.tzinfo is None:
        dt = dt.astimezone()          # assume box-local (America/New_York)
    return dt.isoformat(timespec="seconds")

def clean_chat(chat):
    out = []
    for m in chat or []:
        text = scrub(m.get("text", "")).strip()[:2000]
        if not text:
            continue
        out.append({"name": scrub(m.get("name", "")).strip()[:60] or "Someone",
                    "date": norm_date(m.get("date")), "text": text})
    out.sort(key=lambda m: m["date"])
    return out

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
            "flights": flights, "lodging": lodging,
            "resources": clean_resources(data.get("resources") or {})}, clean_chat(data.get("chat"))

def clean_resources(r):
    """Links + housing cards. https URLs only; text scrubbed of emails/phones;
    any listing date outside Jul/Aug 2027 is dropped."""
    def url(u):
        u = str(u or "").strip()
        return u if u.startswith("https://") and not EMAIL_RE.search(u) else ""
    def dates_ok(v):
        found = re.findall(r"20\d\d-\d\d-\d\d", str(v or ""))
        return all(in_window(d) for d in found)
    flights = []
    for f in r.get("flights", []):
        u = url(f.get("url"))
        if u and dates_ok(u):
            flights.append({"title": scrub(f.get("title", "")), "url": u, "note": scrub(f.get("note", ""))})
    housing = []
    for h in r.get("housing", []):
        item = {k: scrub(h.get(k, "")).strip() for k in ("name", "area", "sleeps", "price", "dates", "comment", "shared_by")}
        if not dates_ok(item["dates"]):
            item["dates"] = ""                           # omit out-of-window listing dates
        item["url"] = url(h.get("url"))
        if item["name"]:
            housing.append({k: v for k, v in item.items() if v})
    return {"flights": flights, "housing": housing,
            "housing_intro": scrub(r.get("housing_intro", "")), "housing_tip": scrub(r.get("housing_tip", ""))}

CHAT_BLOCK = re.compile(r'<script type="application/json" id="chat-data">.*?</script>', re.S)

def privacy_check(html):
    from urllib.parse import unquote
    html = unquote(html)                         # catch encoded emails/dates inside links too
    emails = set(re.findall(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}", html)) - {RSVP}
    phones = re.findall(r"(?<![\w#-])\+?\d[\d ()./-]{8,}\d(?![\w-])", html)
    phones = [p for p in phones if len(re.sub(r"\D", "", p)) >= 10 and not re.match(r"^20\d\d-\d\d-\d\d", p)]
    no_chat = CHAT_BLOCK.sub("", html)             # chat timestamps are exempt from the date rule
    bad_dates = [d for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", no_chat) if not in_window(d)]
    problems = []
    if emails: problems.append(f"emails found: {sorted(emails)}")
    if phones: problems.append(f"phone-like numbers found: {phones}")
    if bad_dates: problems.append(f"dates outside Jul/Aug 2027: {sorted(set(bad_dates))}")
    return problems

def build():
    raw = json.loads((HERE / "data.json").read_text())
    data, chat = clean(raw)
    blob = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    cblob = json.dumps(chat, ensure_ascii=False, indent=1).replace("</", "<\\/")
    html = (HERE / "template.html").read_text().replace("__TRIP_DATA__", blob).replace("__CHAT_DATA__", cblob)
    problems = privacy_check(html)
    if problems:
        sys.exit("REFUSING TO BUILD:\n  " + "\n  ".join(problems))
    (HERE / "index.html").write_text(html)
    c = {}
    for g in data["guests"]: c[g["status"]] = c.get(g["status"], 0) + g["party"]
    print(f"Built index.html · {len(data['guests'])} guests {c} · {len(data['activities'])} activities · "
          f"{len(data['todos'])} to-dos · {len(chat)} chat messages")

def add_chat(name, text, date):
    path = HERE / "data.json"
    raw = json.loads(path.read_text())
    msg = {"name": scrub(name).strip()[:60] or "Someone", "date": norm_date(date), "text": scrub(text).strip()[:2000]}
    if not msg["text"]:
        sys.exit("Empty message; nothing added.")
    raw.setdefault("chat", []).append(msg)
    raw["chat"].sort(key=lambda m: str(m.get("date", "")))
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n")
    print(f"Added chat from {msg['name']} at {msg['date']}: {msg['text'][:70]}")

def publish(msg):
    git = lambda *a: subprocess.run(["git", "-C", str(HERE), *a], check=False)
    git("add", "index.html", "data.json", "template.html", "build.py", "README.md")
    git("commit", "-m", msg)
    r = subprocess.run(["git", "-C", str(HERE), "push", "origin", "main"])
    if r.returncode: sys.exit("push failed")
    print("Pushed. GitHub Pages redeploys in about a minute.")

def main():
    ap = argparse.ArgumentParser(description="Build Dad's 80th trip page")
    ap.add_argument("--publish", action="store_true", help="git commit + push after building")
    ap.add_argument("--add-chat", nargs=2, metavar=("NAME", "MESSAGE"), help="append a chat message")
    ap.add_argument("--date", help="ISO timestamp for --add-chat (default: now)")
    a = ap.parse_args()
    if a.add_chat:
        add_chat(a.add_chat[0], a.add_chat[1], a.date)
    build()
    if a.publish:
        publish(f"Chat: {a.add_chat[0]}" if a.add_chat else "Update trip page")

if __name__ == "__main__":
    main()
