#!/usr/bin/env python3
"""Imagine VR/XR bookings overview.

Reads the show times that book.filmhallen.nl itself uses, keeps the VR slots
and writes one self-contained page (index.html).

  python3 vr_overview.py                          live fetch for all festival days
  python3 vr_overview.py --from-file a.json ...   use saved copies of the XHR response
"""
import argparse, json, re, sys, time, urllib.request
from datetime import date, datetime, timedelta, timezone, time as dtime
from zoneinfo import ZoneInfo

URL = "https://book.filmhallen.nl/webservices/show_times/getShowTimes?cinema_id=2&date={d}&ts={ts}"
FIRST, LAST = date(2026, 10, 29), date(2026, 11, 8)
SEATPLAN = "https://book.filmhallen.nl/webservices/cinema_seatplans/getSeatPlanData?cinema_id=2&show_time_id={sid}&cinema_screen_id={scr}"
UA = {"User-Agent": "Mozilla/5.0 (Imagine staff overview)", "Accept": "application/json"}
AMS = ZoneInfo("Europe/Amsterdam")
COUNT_WINDOW_HOURS = 2  # only look up free places for slots starting within this many hours
PRELOAD_FROM, PRELOAD_TO = dtime(14, 0), dtime(14, 15)  # Mon-Fri: slots starting in this range are always counted and the page lists them as tasks from the start of the day
GRACE_MINUTES = 15      # a slot that started up to this long ago is still looked up (the page keeps it as a task that long)
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


def booked(r):
    """True = at least one ticket sold, False = none, None = unknown (no seat count for this slot)."""
    if r["status"] in ("sold", "low"):
        return True
    if "free" in r:
        return r["free"] < r["cap"]
    return None


GHOST = [  # X = filled cell, . = empty; the two eye rows are holes
    "....XXXX....",
    "..XXXXXXXX..",
    ".XXXXXXXXXX.",
    ".XXXXXXXXXX.",
    ".XX..XX..XX.",
    ".XX..XX..XX.",
    ".XXXXXXXXXX.",
    ".XXXXXXXXXX.",
    ".XXXXXXXXXX.",
    ".XXXXXXXXXX.",
    ".XXXXXXXXXX.",
    ".XX.XXXX.XX.",
    ".X..X..X..X.",
]
GLITCH_SHIFT = {5: 1, 9: 1}  # rows of the pink ghost pushed one cell right
ECHO_ROWS = {2, 3, 7, 8, 11}  # rows repeated in orange, one cell to the left


def ghost_svg():
    def layer(rows, cls):
        d = ""
        for y, shift in rows:
            x = 0
            for run in re.findall(r"X+|\.+", GHOST[y]):
                if run[0] == "X":
                    d += f"M{x + shift} {y}h{len(run)}v1h-{len(run)}z"
                x += len(run)
        return f'<path class="{cls}" d="{d}"/>'
    echo = layer([(y, -1) for y in sorted(ECHO_ROWS)], "g-echo")
    body = layer([(y, GLITCH_SHIFT.get(y, 0)) for y in range(len(GHOST))], "g-body")
    return (f'<svg class="ghost" viewBox="-1 0 15 {len(GHOST)}" aria-hidden="true">'
            f'<style>.g-echo{{fill:var(--orange)}}.g-body{{fill:var(--pink)}}</style>{echo}{body}</svg>')


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="120">
<title>Imagine VR/XR bookings live feed</title>
<style>
:root{--bg:#f7f7f5;--card:#eceef1;--card-line:#a9aeb7;--ink:#232325;--mute:#5f6168;--line:rgba(35,35,37,.2);--pink:#e24cb4;--orange:#f0653a;--late:#e8502a;--on-fill:#232325;--open:#c5e8d0;--low:#ffe28f;--sold:#f4a58a;--closed:#dcdde1;--on-chip:#232325}
@media(prefers-color-scheme:dark){:root{--bg:#1c1c1e;--card:#2a2a2d;--card-line:#5a5c64;--ink:#f1f1ee;--mute:#a3a5ad;--line:rgba(241,241,238,.22);--pink:#ee62c2;--orange:#f26a40;--late:#f26a40;--open:#24503a;--low:#6b5a12;--sold:#7d3322;--closed:#34353a;--on-chip:#f1f1ee}}
*{box-sizing:border-box}
body{margin:0;padding:20px 16px 48px;background:var(--bg);color:var(--ink);font:16px/1.45 "Helvetica Neue",Arial,system-ui,sans-serif;max-width:900px;margin-inline:auto}
:focus-visible{outline:3px solid var(--pink);outline-offset:2px}
.disp{font-family:Haettenschweiler,Impact,"Arial Narrow","Roboto Condensed",sans-serif;font-weight:700;font-synthesis:none;letter-spacing:-.01em}
.card-label{font-family:Georgia,"Times New Roman",serif;font-variant-caps:all-small-caps;letter-spacing:.06em}
.top{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 16px}
h1{font-size:clamp(2.6rem,10vw,4.4rem);line-height:.9;margin:0}
.clock{font-size:1.15rem;font-weight:700;font-variant-numeric:tabular-nums}
.ghost{display:block;width:75px;height:65px;margin:10px 0 12px;shape-rendering:crispEdges}
.mute{color:var(--mute);font-size:.85rem}
.tasks{margin:24px 0 10px}
.tasks h2{font-size:2rem;line-height:1;margin:0 0 4px}
.stale{color:var(--ink);font-weight:700}
.task-list{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));margin-top:14px}
.task{position:relative;background:var(--card);border-radius:2px;padding:16px 20px 14px;display:grid;grid-template-columns:auto 1fr;gap:0 16px;align-items:center}
.task::after{content:"";position:absolute;inset:6px;border:1px solid var(--card-line);pointer-events:none}
.task.soon::after{border:2px solid var(--pink)}
.task.late::after{border:2px solid var(--late)}
.task .time{grid-row:span 2;font-size:3.2rem;line-height:.95;font-variant-numeric:tabular-nums}
.task .what{font-weight:700;line-height:1.2}
.task .meta{color:var(--mute);font-size:1rem}
.task .when{grid-column:1/-1;display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;margin-top:10px;font-size:.9rem;font-weight:600}
.task .when .state{padding:1px 8px;border-radius:3px;background:var(--closed);color:var(--on-chip)}
.task.soon .state{background:var(--pink);color:var(--on-fill)}
.task.late .state{background:var(--orange);color:var(--on-fill)}
.task.soon .state::before{content:"";display:inline-block;width:.5em;height:.5em;margin-right:.5em;border-radius:50%;background:currentColor}
@media(prefers-reduced-motion:no-preference){.task.soon .state::before{animation:blink 1.4s ease-in-out infinite}}
@keyframes blink{50%{opacity:.25}}
.empty{margin:14px 0 0;padding:16px 20px;background:var(--card);border-radius:2px}
.warn{margin:10px 0 0;font-size:.85rem;color:var(--mute)}
.tabs{display:flex;gap:6px;overflow-x:auto;margin:26px 0 12px;padding-bottom:2px}
.tabs button{flex:none;padding:6px 14px;border:2px solid var(--ink);border-radius:3px;background:none;color:inherit;font:inherit;font-weight:700;cursor:pointer}
.tabs button[aria-pressed=true]{background:var(--pink);border-color:var(--pink);color:var(--on-fill)}
.piece{border-top:2px solid var(--line);padding:12px 0}
.piece h2{font-size:1.6rem;line-height:1;margin:0}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{padding:4px 10px;border-radius:3px;font-size:.9rem;font-weight:600;font-variant-numeric:tabular-nums;color:var(--on-chip)}
.open{background:var(--open)}.low{background:var(--low)}.sold{background:var(--sold);text-decoration:line-through}.closed{background:var(--closed)}
.past{opacity:.45}
</style></head><body>
<header class="top"><h1 class="disp">Imagine VR/XR bookings</h1><div class="clock card-label" id="clock"></div></header>
__GHOST__
<div class="mute">Data from https://book.filmhallen.nl/#, last updated <span id="updated">__UPDATED__</span>.</div>
<div class="mute">Green = available, yellow/few left = 1/2 booked, red = sold out; grey = past.</div>
<section class="tasks" id="tasks" aria-labelledby="tasks-h"></section>
<div class="tabs" id="tabs"></div><div id="out"></div>
<script>
const D=__DATA__,META=__META__,tz="Europe/Amsterdam";
const PRE_FROM=14*60,PRE_TO=14*60+15; // Mon-Fri: slots starting 14:00-14:15 are listed from the start of the day
const APPEAR=15,GRACE=15,ARRIVE=10,STALE=30; // minutes: task appears this long before the start / stays this long after it / guests may show up this early / data older than this gets a warning
const fT=new Intl.DateTimeFormat("nl-NL",{timeZone:tz,hour:"2-digit",minute:"2-digit"});
const fD=new Intl.DateTimeFormat("en-CA",{timeZone:tz});
const fL=new Intl.DateTimeFormat("en-GB",{timeZone:tz,weekday:"short",day:"numeric",month:"short"});
D.forEach(r=>{const t=new Date(r.start);r.ms=+t;r.day=fD.format(t);r.t=fT.format(t);r.label=fL.format(t);r.past=t<new Date();
  const [Y,M,Dy]=r.day.split("-").map(Number),dow=new Date(Date.UTC(Y,M-1,Dy)).getUTCDay(),[hh,mm]=r.t.split(":").map(Number),mod=hh*60+mm;
  r.pre=dow>=1&&dow<=5&&mod>=PRE_FROM&&mod<=PRE_TO;});
const isPre=(r,now)=>r.pre&&r.day===fD.format(now);
const days=[...new Set(D.map(r=>r.day))].sort();
const today=fD.format(new Date());
let cur=days.includes(today)?today:days[0];
const TXT={open:"",low:" few left",sold:" full",closed:" closed"};
function h(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function dur(m){const h=Math.floor(m/60),n=m%60;return h?(n?h+" h "+n+" min":h+" h"):n+" min"}
function bookedText(r){return r.free!==undefined&&r.cap?(r.cap-r.free)+" of "+r.cap+" booked":(r.status==="sold"?"fully booked":"booked")}
function renderTasks(){
  const now=Date.now(),box=document.getElementById("tasks");
  box.replaceChildren();
  document.getElementById("clock").textContent="Amsterdam "+fT.format(now);
  const live=D.filter(r=>now<r.ms+GRACE*60000);
  const shown=live.filter(r=>now>=r.ms-APPEAR*60000||isPre(r,now));
  const tasks=shown.filter(r=>r.booked===true).sort((a,b)=>a.ms-b.ms);
  const head=h("div","tasks-head");
  const title=h("h2","disp","To set up");title.id="tasks-h";head.append(title);
  head.append(h("div","mute","Booked slots show up "+APPEAR+" min before the start and stay until "+GRACE+" min after it."+(D.some(r=>isPre(r,now))?" Mon-Fri the slots at 14:00-14:15 are listed from the start of the day.":"")));
  if(META.built){
    const age=Math.max(0,Math.round((now-Date.parse(META.built))/60000));
    const old=age>STALE;
    head.append(h("div","mute"+(old?" stale":""),"Booking data from "+fT.format(Date.parse(META.built))+" ("+age+" min ago)"+(old?". A recent booking may be missing.":".")));
  }
  box.append(head);
  if(tasks.length){
    const list=h("div","task-list");
    tasks.forEach(r=>{
      const diff=(r.ms-now)/60000;
      const c=h("div","task "+(diff>ARRIVE?"later":diff>0?"soon":"late"));
      c.append(h("div","time disp",r.t),h("div","what",r.title),h("div","meta card-label",r.room));
      const w=h("div","when");
      const st=diff>ARRIVE?"in "+dur(Math.ceil(diff)):diff>0?"in "+dur(Math.ceil(diff))+", guests may arrive":Math.floor(-diff)<1?"starting now":"started "+dur(Math.floor(-diff))+" ago";
      w.append(h("span","state",st),h("span","",bookedText(r)));
      c.append(w);list.append(c);
    });
    box.append(list);
  }else{
    const next=live.filter(r=>r.booked===true&&r.ms>now).sort((a,b)=>a.ms-b.ms)[0];
    box.append(h("p","empty","Nothing to set up right now."+(next?" Next booked slot: "+(next.day===fD.format(now)?"":next.label+" ")+next.t+", "+next.title+".":"")));
  }
  const unk=META.windowEnd?shown.filter(r=>r.booked===null&&(r.ms<=Date.parse(META.windowEnd)||isPre(r,now))):[];
  if(unk.length)box.append(h("p","warn","No booking count for "+unk.length+" slot"+(unk.length>1?"s":"")+" (first: "+unk[0].t+" "+unk[0].title+"). Check those in the overview below."));
}
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
    p.append(h("h2","disp",title));
    p.append(h("div","mute",list[0].room+" · "+list.length+" slots · "+sold+" full"+(low?" · "+low+" few left":"")));
    const c=h("div","chips");
    list.forEach(r=>c.append(h("span","chip "+r.status+(r.past?" past":""),r.t+(r.free!==undefined?" · "+r.free+"/"+r.cap+" free":TXT[r.status]))));
    p.append(c);out.append(p);
  });
}
renderTasks();render();
setInterval(renderTasks,10000);
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
    now = datetime.now(timezone.utc)
    counting = not a.from_file and not a.no_counts
    if counting:
        calls = 0
        for s in sorted(shows, key=lambda s: s["show_time"]):
            r = rows.get(s["show_time_id"]) if is_vr(s) else None
            start = datetime.fromisoformat(s["show_time"].replace("Z", "+00:00"))
            # sold slots already count as booked; closed slots are looked up too, because sales
            # can close shortly before the start while the slot still has guests coming
            local = start.astimezone(AMS)
            preload = local.weekday() < 5 and local.date() == now.astimezone(AMS).date() and PRELOAD_FROM <= local.time() <= PRELOAD_TO
            if not r or r["status"] == "sold" or not (now - timedelta(minutes=GRACE_MINUTES) <= start and (start <= now + timedelta(hours=COUNT_WINDOW_HOURS) or preload)):
                continue
            if calls >= MAX_PLAN_CALLS:
                break
            try:
                r["free"], r["cap"] = fetch_seats(s)
                if r["status"] != "closed":
                    r["status"] = "sold" if r["free"] == 0 else ("low" if r["free"] < r["cap"] else "open")
            except Exception as e:
                print(f"{r['title']} {s['show_time']}: no seat count ({e})", file=sys.stderr)
            calls += 1
            time.sleep(0.3)
    for r in rows.values():
        r["booked"] = booked(r)
    data = sorted(rows.values(), key=lambda r: r["start"])
    meta = {
        "built": now.isoformat(),
        "windowEnd": (now + timedelta(hours=COUNT_WINDOW_HOURS)).isoformat() if counting else None,
    }
    stamp = datetime.now(AMS).strftime("%a %d %b %H:%M")
    esc = lambda o: json.dumps(o).replace("</", "<\\/")
    html = PAGE.replace("__DATA__", esc(data)).replace("__META__", esc(meta)).replace("__UPDATED__", stamp).replace("__GHOST__", ghost_svg())
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"{len(data)} VR slots written to {a.out}")


if __name__ == "__main__":
    main()
