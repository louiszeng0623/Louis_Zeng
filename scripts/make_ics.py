#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, os, re
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))

def load_matches(paths):
    all_rows = []
    for p in paths:
        if not os.path.exists(p):
            print(f"[warn] not found: {p}")
            continue
        with open(p, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    all_rows.extend(data)
            except Exception as e:
                print(f"[warn] bad json {p}: {e}")
    def key(x):
        d = x.get("date","")
        t = x.get("time","") or "20:00"
        return f"{d} {t} {x.get('team','')}{x.get('opponent','')}{x.get('competition','')}{x.get('round','')}"
    unique = {}
    for r in all_rows:
        unique[key(r)] = r
    rows = list(unique.values())
    rows.sort(key=lambda r: (r.get("date",""), r.get("time","") or "20:00"))
    return rows

def to_dt(dt_str, tm_str):
    tm = tm_str or "20:00"
    try:
        y, m, d = [int(x) for x in dt_str.split("-")]
        hh, mm = [int(x) for x in tm.split(":")]
        return datetime(y, m, d, hh, mm, tzinfo=CST)
    except Exception:
        return None

def esc(s):
    if not s: return ""
    return re.sub(r'([,;\\])', r'\\\1', str(s)).replace("\n", "\\n")

def make_ics(rows, cal_name):
    lines = []
    lines.append("BEGIN:VCALENDAR")
    lines.append("VERSION:2.0")
    lines.append("PRODID:-//Louis_Zeng//Auto Schedules//CN")
    lines.append(f"X-WR-CALNAME:{esc(cal_name)}")
    lines.append("CALSCALE:GREGORIAN")
    lines.append("METHOD:PUBLISH")
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for r in rows:
        dt = to_dt(r.get("date",""), r.get("time",""))
        if not dt:
            continue
        dt_end = dt + timedelta(hours=2)
        dt_start_utc = dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dt_end_utc = dt_end.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        team = (r.get("team","") or "").strip()
        opp  = (r.get("opponent","") or "").strip()
        comp = (r.get("competition","") or "").strip()
        rnd  = (r.get("round","") or "").strip()
        ven  = (r.get("venue","") or "").strip()
        title = f"{team} vs {opp}" if team and opp else (team or opp or "Match")
        desc  = "；".join([x for x in [comp, rnd, ven] if x])
        uid = f"{r.get('date','')}-{esc(title)}-{esc(comp)}@louis_zeng.auto"
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}")
        lines.append(f"DTSTAMP:{now}")
        lines.append(f"DTSTART:{dt_start_utc}")
        lines.append(f"DTEND:{dt_end_utc}")
        lines.append(f"SUMMARY:{esc(title)}")
        if desc:
            lines.append(f"DESCRIPTION:{esc(desc)}")
        if ven:
            lines.append(f"LOCATION:{esc(ven)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\n".join(lines) + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", nargs="+", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--name", dest="name", default="Matches")
    args = ap.parse_args()
    rows = load_matches(args.inputs)
    ics = make_ics(rows, args.name)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(ics)
    print(f"[ok] wrote {args.out} ({len(rows)} events)")

if __name__ == "__main__":
    main()
    
