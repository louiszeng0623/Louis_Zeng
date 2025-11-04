# scripts/make_ics.py
import os
import json
from datetime import datetime

def load_matches(json_path):
    """读入 JSON 赛程文件，返回 list[dict]；不存在则返回空列表"""
    if not os.path.exists(json_path):
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []

def normalize_date(date_str):
    """把 'YYYY-MM-DD' 转成 (YYYY,MM,DD)、DTSTART 字符串；失败返回 None"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt, dt.strftime("%Y%m%d")
    except Exception:
        return None, None

def uniq_key(match):
    """用于去重的键：日期 + team + opponent + competition"""
    return (
        match.get("date", ""),
        match.get("team", ""),
        match.get("opponent", ""),
        match.get("competition", ""),
    )

def jsons_to_single_ics(json_paths, ics_path, calendar_name="Louis_Zeng 赛程（2025–2026）"):
    # 汇总
    all_matches = []
    for p in json_paths:
        all_matches.extend(load_matches(p))

    # 清洗、去重
    seen = set()
    cleaned = []
    for m in all_matches:
        k = uniq_key(m)
        if not m.get("date"):
            continue
        if k in seen:
            continue
        seen.add(k)
        cleaned.append(m)

    # 按日期排序
    def sort_key(m):
        dt, _ = normalize_date(m.get("date", ""))
        # 排序兜底：解析失败放最后
        return dt or datetime(9999, 12, 31)
    cleaned.sort(key=sort_key)

    # 生成 ICS
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LouisZeng//Football Schedule//CN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{calendar_name}",
        "X-WR-TIMEZONE:Asia/Shanghai",
    ]

    for m in cleaned:
        date_str = m.get("date", "")
        dt, dtstart = normalize_date(date_str)
        if not dtstart:
            continue
        team = m.get("team", "").strip() or "球队"
        opponent = m.get("opponent", "").strip() or "待定"
        venue = m.get("venue", "").strip() or "待定"
        comp = m.get("competition", "").strip() or ""
        round_info = m.get("round", "").strip()
        note = " | ".join([x for x in [comp, round_info] if x])

        summary = f"{team} vs {opponent}"
        desc = f"{note} | 地点：{venue}" if note else f"地点：{venue}"
        uid = f"{team}-{opponent}-{dtstart}@LouisZeng"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    os.makedirs(os.path.dirname(ics_path), exist_ok=True)
    with open(ics_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ 已生成 {ics_path}，共 {len(cleaned)} 场")

def main():
    # 把两个赛程 JSON 合并到一个 ICS
    json_paths = ["data/schedule_2025.json", "data/schedule_2026.json"]
    jsons_to_single_ics(json_paths, "data/ics/matches_all.ics", "Louis_Zeng：成都蓉城 + 国际米兰（2025–2026）")

if __name__ == "__main__":
    main()
    
