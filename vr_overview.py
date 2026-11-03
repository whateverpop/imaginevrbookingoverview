#!/usr/bin/env python3
"""Imagine VR/XR bookings overview.

Reads the show times that book.filmhallen.nl itself uses, keeps the VR slots
and writes one self-contained page (index.html).

  python3 vr_overview.py                          live fetch for all festival days
  python3 vr_overview.py --from-file a.json ...   use saved copies of the XHR response
"""
import argparse, json, sys, time, urllib.request
from datetime import date, datetime, timedelta, timezone

URL = "https://book.filmhallen.nl/webservices/show_times/getShowTimes?cinema_id=2&date={d}&ts={ts}"
FIRST, LAST = date(2026, 10, 29), date(2026, 11, 8)
SEATPLAN = "https://book.filmhallen.nl/webservices/cinema_seatplans/getSeatPlanData?cinema_id=2&show_time_id={sid}&cinema_screen_id={scr}"
UA = {"User-Agent": "Mozilla/5.0 (Imagine staff overview)", "Accept": "application/json"}
COUNT_WINDOW_HOURS = 2  # only look up free places for slots starting within this many hours
MAX_PLAN_CALLS = 40     # safety cap per run


def fetch_day(d):
    req = urllib.request.Request(
        URL.format(d=d.isoformat(), ts=int(time.time())),
        headers=UA,
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("data", [])


def fetch_seats(s):
    """Returns (free, capacity). Only counts are kept, never the customer fields in the response."""
    req = urllib.request.Request(SEATPLAN.format(sid=s["show_time_id"], scr=s["cinema_screen_id"]), headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        plan = json.load(r).get("data", [])
    bookable = [p for p in plan if p.get("seat_selectable")]
    taken = sum(1 for p in bookable if p.get("seat_status"))
    cap = min(s.get("maximum_capacity") or len(bookable), len(bookable))
    return max(cap - taken, 0), cap


def is_vr(s):
    return s.get("title", "").startswith("VR:") or s.get("screen_name", "").startswith("VR")


def status(s):
    if s.get("sold_out"):
        return "sold"
    if not s.get("bookable"):
        return "closed"  # not on sale (locked, ended, ...), not the same as sold out
    return "low" if s.get("seats_low") else "open"


def row(s):
    return {
        "id": s["show_time_id"],
        "title": s["title"].replace("VR:", "").strip(),
        "room": s["screen_name"],
        "start": s["show_time"],
        "end": s["show_time_end"],
        "status": status(s),
    }


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="120">
<title>Imagine VR/XR bookings live feed</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mute:#666;--line:#ddd;--open:#d8f0d8;--low:#ffe9b3;--sold:#f4c7c7;--closed:#e6e6e6}
@media(prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--mute:#aaa;--line:#333;--open:#1f4a28;--low:#5a4510;--sold:#5c2222;--closed:#2c2c2c}}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:16px/1.4 system-ui,sans-serif;max-width:900px;margin-inline:auto}
h1{font-size:1.25rem;margin:0}.mute{color:var(--mute);font-size:.85rem}
.tabs{display:flex;gap:6px;overflow-x:auto;margin:12px 0}
.tabs button{flex:none;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:none;color:inherit;font:inherit}
.tabs button[aria-pressed=true]{background:var(--fg);color:var(--bg)}
.piece{border-top:1px solid var(--line);padding:10px 0}
.piece h2{font-size:1rem;margin:0}.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.chip{padding:4px 8px;border-radius:6px;font-size:.9rem;font-variant-numeric:tabular-nums}
.open{background:var(--open)}.low{background:var(--low)}.sold{background:var(--sold);text-decoration:line-through}.closed{background:var(--closed)}
.past{opacity:.45}
</style></head><body>
<h1>Imagine VR/XR bookings</h1>
<div class="mute">Data from https://book.filmhallen.nl/#, last updated __UPDATED__.</div>
<div class="mute">Green = available, yellow/few left = 1/2 booked, red = sold out; grey = past.</div>
<div class="tabs" id="tabs"></div><div id="out"></div>
<script>
const D=__DATA__,tz="Europe/Amsterdam";
const fT=new Intl.DateTimeFormat("nl-NL",{timeZone:tz,hour:"2-digit",minute:"2-digit"});
const fD=new Intl.DateTimeFormat("en-CA",{timeZone:tz});
const fL=new Intl.DateTimeFormat("en-GB",{timeZone:tz,weekday:"short",day:"numeric",month:"short"});
D.forEach(r=>{const t=new Date(r.start);r.day=fD.format(t);r.t=fT.format(t);r.label=fL.format(t);r.past=t<new Date();});
const days=[...new Set(D.map(r=>r.day))].sort();
const today=fD.format(new Date());
let cur=days.includes(today)?today:days[0];
const TXT={open:"",low:" few left",sold:" full",closed:" closed"};
function h(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function render(){
  const tabs=document.getElementById("tabs"),out=document.getElementById("out");
  tabs.replaceChildren();out.replaceChildren();
  if(!D.length){out.append(h("p","","No VR slots found."));return}
  days.forEach(d=>{const b=h("button","",D.find(r=>r.day===d).label);b.setAttribute("aria-pressed",d===cur);b.onclick=()=>{cur=d;render()};tabs.append(b)});
  const rows=D.filter(r=>r.day===cur).sort((a,b)=>a.start.localeCompare(b.start));
  const groups=new Map();rows.forEach(r=>{if(!groups.has(r.title))groups.set(r.title,[]);groups.get(r.title).push(r)});
  groups.forEach((list,title)=>{
    const sold=list.filter(r=>r.status==="sold").length,low=list.filter(r=>r.status==="low").length;
    const p=h("div","piece");
    p.append(h("h2","",title));
    p.append(h("div","mute",list[0].room+" · "+list.length+" slots · "+sold+" full"+(low?" · "+low+" few left":"")));
    const c=h("div","chips");
    list.forEach(r=>c.append(h("span","chip "+r.status+(r.past?" past":""),r.t+(r.free!==undefined?" · "+r.free+"/"+r.cap+" free":TXT[r.status]))));
    p.append(c);out.append(p);
  });
}
render();
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file", nargs="+", help="saved XHR responses instead of a live fetch")
    ap.add_argument("--out", default="index.html")
    ap.add_argument("--no-counts", action="store_true", help="skip the per-slot free-places lookup")
    a = ap.parse_args()

    shows, failed = [], 0
    if a.from_file:
        for f in a.from_file:
            with open(f, encoding="utf-8") as fh:
                shows += json.load(fh).get("data", [])
    else:
        d = FIRST
        while d <= LAST:
            try:
                shows += fetch_day(d)
            except Exception as e:
                failed += 1
                print(f"{d}: could not fetch ({e})", file=sys.stderr)
            d += timedelta(days=1)
        if failed == (LAST - FIRST).days + 1:
            sys.exit("Nothing could be fetched. Save the XHR response from the browser and use --from-file.")

    rows = {s["show_time_id"]: row(s) for s in shows if is_vr(s)}
    if not a.from_file and not a.no_counts:
        now, calls = datetime.now(timezone.utc), 0
        for s in sorted(shows, key=lambda s: s["show_time"]):
            r = rows.get(s["show_time_id"]) if is_vr(s) else None
            start = datetime.fromisoformat(s["show_time"].replace("Z", "+00:00"))
            if not r or r["status"] in ("sold", "closed") or not now <= start <= now + timedelta(hours=COUNT_WINDOW_HOURS):
                continue
            if calls >= MAX_PLAN_CALLS:
                break
            try:
                r["free"], r["cap"] = fetch_seats(s)
                r["status"] = "sold" if r["free"] == 0 else ("low" if r["free"] < r["cap"] else "open")
            except Exception as e:
                print(f"{r['title']} {s['show_time']}: no seat count ({e})", file=sys.stderr)
            calls += 1
            time.sleep(0.3)
    data = sorted(rows.values(), key=lambda r: r["start"])
    stamp = datetime.now(timezone.utc).astimezone().strftime("%a %d %b %H:%M")
    html = PAGE.replace("__DATA__", json.dumps(data).replace("</", "<\\/")).replace("__UPDATED__", stamp)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"{len(data)} VR slots written to {a.out}")


if __name__ == "__main__":
    main()
