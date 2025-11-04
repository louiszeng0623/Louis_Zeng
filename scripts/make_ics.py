# -*- coding: utf-8 -*-
"""
把 data/schedule_2025.json 和 data/schedule_2026.json 转成 ICS：
- data/ics/inter_2025.ics / inter_2026.ics
- data/ics/chengdu_2025.ics / chengdu_2026.ics
- data/ics/all_2025.ics / all_2026.ics
"""
import os, json
from datetime import datetime, timedelta

SRC = ["data/schedule_2025.json", "data/schedule_2026.json"]
OUT_DIR = "data/ics"
DURATION_HOURS = 2  # 比赛默认时长

def read_json(path):
    if not os.path.exists(path): return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []

def to_ics_datetime(datestr, timestr):
    try:
        if not timestr:
            timestr = "20:00"
        dt = datetime.strptime(datestr + " " + timestr, "%Y-%m-%d %H:%M")
    except Exception:
        dt = datetime.strptime(datestr + " 20:00", "%Y-%m-%d %H:%M")
    return dt.strftime("%Y%m%dT%H%M%S")

def build_ics(events, cal_name):
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Louis_Zeng//Match Calendar//CN",
        f"X-WR-CALNAME:{cal_name}"
    ]
    for ev in events:
        dtstart = to_ics_datetime(ev["date"], ev.get("time",""))
        start_dt = datetime.strptime(dtstart, "%Y%m%dT%H%M%S")
        dtend = (start_dt + timedelta(hours=DURATION_HOURS)).strftime("%Y%m%dT%H%M%S")
        uid = f"{ev['team']}-{ev['date']}-{ev.get('time','')}-{ev['opponent']}"
        title = f"{ev['team']} vs {ev['opponent']}（{ev.get('competition','')}）"
        location = ev.get("venue","")
        desc = f"{ev.get('competition','')} {ev.get('round','')}".strip()
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{title}",
            f"LOCATION:{location}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT"
        ]
    lines.append("END:VCALENDAR")
    return "\n".join(lines)

def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def main():
    by_year_team = {}  # {(year, team): [events]}
    for src in SRC:
        data = read_json(src)
        for ev in data:
            y = ev["date"][:4]
            key = (y, ev["team"])
            by_year_team.setdefault(key, []).append(ev)

    years = ["2025","2026"]
    teams = set(k[1] for k in by_year_team.keys())

    for y in years:
        all_events = []
        for t in teams:
            evs = sorted(by_year_team.get((y,t), []), key=lambda e:(e["date"], e.get("time","")))
            if not evs: continue
            all_events += evs
            ics = build_ics(evs, f"{t} {y}")
            safe_team = "inter" if "国际米兰" in t else ("chengdu" if "成都" in t else "team")
            write_file(f"{OUT_DIR}/{safe_team}_{y}.ics", ics)

        all_events = sorted(all_events, key=lambda e:(e["date"], e.get('time','')))
        if all_events:
            ics_all = build_ics(all_events, f"All Teams {y}")
            write_file(f"{OUT_DIR}/all_{y}.ics", ics_all)

if __name__ == "__main__":
    main()
