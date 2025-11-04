# -*- coding: utf-8 -*-
"""
make_ics.py
自动生成国际米兰 & 成都蓉城的比赛日历（含提前提醒功能）
"""

import json, os
from datetime import datetime, timedelta

def ensure_dir(p): os.makedirs(p, exist_ok=True)

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def to_ics_datetime(date_str, time_str):
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except:
        dt = datetime.strptime(f"{date_str} 20:00", "%Y-%m-%d %H:%M")
    # 北京时间 → UTC
    return (dt - timedelta(hours=8)).strftime("%Y%m%dT%H%M%SZ")

def event_block(e):
    start = to_ics_datetime(e["date"], e["time"])
    end = to_ics_datetime(e["date"], e["time"])
    summary = f"{e['team']} vs {e['opponent']}"
    desc = f"{e.get('competition','')} {e.get('round','')} {e.get('venue','')}"
    uid = f"{e['team']}-{e['date']}-{e['opponent']}".replace(" ","_")
    return f"""BEGIN:VEVENT
UID:{uid}@louis_zeng_schedule
DTSTAMP:{datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")}
DTSTART:{start}
DTEND:{end}
SUMMARY:{summary}
DESCRIPTION:{desc}
BEGIN:VALARM
TRIGGER:-PT60M
ACTION:DISPLAY
DESCRIPTION:比赛即将开始！⚽
END:VALARM
END:VEVENT
"""

def make_ics(data, year):
    events = "\n".join([event_block(e) for e in data])
    return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Louis_Zeng//MatchCalendar//CN
CALSCALE:GREGORIAN
METHOD:PUBLISH
{events}
END:VCALENDAR
"""

def main():
    ensure_dir("data/ics")
    for year in [2025, 2026]:
        path = f"data/schedule_{year}.json"
        data = load_json(path)
        if not data:
            print(f"[{year}] 无数据，跳过")
            continue
        out = make_ics(data, year)
        out_path = f"data/ics/matches_{year}.ics"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"[OK] 生成 {out_path} ({len(data)} 场)")

if __name__ == "__main__":
    main()
    
