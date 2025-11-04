#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from datetime import datetime, timedelta
from uuid import uuid4
import re

# 将 "2025-05-24" + "21:00" 解析为 UTC 时间（假定输入为本地北京时间）
# 如只给日期没给时间，则用 08:00，北京时间早上八点（避免全日事件被折叠）
DEFAULT_LOCAL_TIME = "08:00"

def parse_local(dt_str: str, tm_str: str | None):
    if not tm_str or not tm_str.strip():
        tm_str = DEFAULT_LOCAL_TIME
    # 允许 21:00 或 21：00（中文冒号）
    tm_str = tm_str.replace("：", ":").strip()
    # 容错：只给“21”也能过
    if re.fullmatch(r"^\d{1,2}$", tm_str):
        tm_str = f"{tm_str}:00"
    local_dt = datetime.strptime(f"{dt_str.strip()} {tm_str}", "%Y-%m-%d %H:%M")
    # 北京时间转 UTC（减去 8 小时）
    return local_dt - timedelta(hours=8)

def load_items(paths):
    items = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    items.extend(data)
            except json.JSONDecodeError:
                # 空文件 [] 也允许
                pass
    return items

def esc(s: str) -> str:
    # ics 基本转义
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")

def make_ics(items, title: str):
    # 排序：时间、队伍优先
    def keyfn(it):
        dt = parse_local(it.get("date","1970-01-01"), it.get("time","08:00"))
        return (dt, it.get("team",""))
    items_sorted = sorted(items, key=keyfn)

    lines = []
    lines.append("BEGIN:VCALENDAR")
    lines.append("VERSION:2.0")
    lines.append("PRODID:-//Louis_Zeng//Matches//CN")
    lines.append("CALSCALE:GREGORIAN")
    lines.append("METHOD:PUBLISH")
    lines.append(f"X-WR-CALNAME:{esc(title)}")
    lines.append("X-WR-TIMEZONE:Asia/Shanghai")

    for it in items_sorted:
        date = it.get("date","")
        time = it.get("time","")
        team = it.get("team","")
        opp  = it.get("opponent","")
        venue = it.get("venue","")
        comp = it.get("competition","")
        rnd  = it.get("round","")

        start_utc = parse_local(date, time)  # naive UTC
        dtstart = start_utc.strftime("%Y%m%dT%H%M%SZ")
        # 默认给 2 小时时长（如果没有时间就用全天 2 小时占位）
        dtend = (start_utc + timedelta(hours=2)).strftime("%Y%m%dT%H%M%SZ")

        summary_parts = [team]
        if opp:
            summary_parts.append(f"vs {opp}")
        if comp:
            summary_parts.append(f"({comp})")
        summary = " ".join(summary_parts)

        desc_lines = []
        if rnd:   desc_lines.append(f"轮次: {rnd}")
        if venue: desc_lines.append(f"场地: {venue}")
        description = "\\n".join([esc(x) for x in desc_lines]) if desc_lines else ""

        uid = f"{uuid4()}@louis_zeng_matches"
        dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}")
        lines.append(f"DTSTAMP:{dtstamp}")
        lines.append(f"DTSTART:{dtstart}")
        lines.append(f"DTEND:{dtend}")
        lines.append(f"SUMMARY:{esc(summary)}")
        if description:
            lines.append(f"DESCRIPTION:{description}")
        if venue:
            lines.append(f"LOCATION:{esc(venue)}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

def main():
    ap = argparse.ArgumentParser(description="Merge schedules (JSON) into ICS.")
    ap.add_argument("--inputs", nargs="+", required=True, help="JSON files like data/schedule_2025.json ...")
    ap.add_argument("--out", required=True, help="Output ICS path, e.g., data/ics/matches_all.ics")
    ap.add_argument("--title", default="Louis_Zeng 合并赛程", help="Calendar display name")
    args = ap.parse_args()

    items = load_items(args.inputs)
    ics = make_ics(items, args.title)

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(ics)
    print(f"Wrote ICS: {args.out} (events={len(items)})")

if __name__ == "__main__":
    main()
    
