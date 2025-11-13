import os
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_HOST = "https://v3.football.api-sports.io"
API_KEY = os.environ["FOOTBALL_API_KEY"]

# ======= 你的实际配置 =======
TEAM_ID = 5648                 # Chengdu Better City / 成都蓉城
CHINA_SUPER_LEAGUE_ID = 169    # Chinese Super League
CHINA_FA_CUP_ID = 171          # China FA Cup
ACL_ELITE_ID = 17              # AFC Champions League
SEASON = 2025                  # 当前赛季年份
# ===========================

OUTPUT_ICS = Path("蓉城.ics")

# 赛事显示风格（emoji + 中文前缀）
COMPETITION_STYLE = {
    "csl": ("🏟 中超", "中超"),
    "cup": ("🏆 足协杯", "足协杯"),
    "acl": ("⭐ 亚冠", "亚冠"),
}


def fetch_fixtures(league_id: int):
    """
    从 API-Football 拉取指定联赛 + 赛季 + 球队的全部比赛
    文档：/fixtures endpoint
    """
    url = f"{API_HOST}/fixtures"
    headers = {
        "x-apisports-key": API_KEY,
    }
    params = {
        "league": league_id,
        "season": SEASON,
        "team": TEAM_ID,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", [])


def parse_fixture_time(fix: dict) -> datetime:
    """
    fixture.date 一般是 ISO 格式，例如：
    "2025-11-22T15:30:00+08:00"
    这里统一转成 UTC 时区的 datetime
    """
    date_str = fix["fixture"]["date"]
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc)


def build_event(uid: str, title: str, desc: str,
                start_utc: datetime, duration_minutes: int,
                location: str) -> str:
    dtend_utc = start_utc + timedelta(minutes=duration_minutes)
    dtstamp = datetime.utcnow().replace(tzinfo=timezone.utc)

    def fmt(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = []
    lines.append("BEGIN:VEVENT")
    lines.append(f"UID:{uid}@chengdu-rongcheng")
    lines.append(f"DTSTAMP:{fmt(dtstamp)}")
    lines.append(f"DTSTART:{fmt(start_utc)}")
    lines.append(f"DTEND:{fmt(dtend_utc)}")
    lines.append(f"SUMMARY:{title}")
    lines.append(f"DESCRIPTION:{desc}")
    lines.append(f"LOCATION:{location}")
    # 比赛前 2 小时提醒
    lines.append("BEGIN:VALARM")
    lines.append("TRIGGER:-PT120M")
    lines.append("ACTION:DISPLAY")
    lines.append(f"DESCRIPTION:{title}（比赛前2小时提醒）")
    lines.append("END:VALARM")
    lines.append("END:VEVENT")
    return "\n".join(lines)


def fixtures_to_events(fixtures, comp_code: str):
    emoji_title, comp_cn = COMPETITION_STYLE[comp_code]
    events = []

    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)

    for fix in fixtures:
        start_utc = parse_fixture_time(fix)
        # 只保留未来的比赛
        if start_utc < now_utc:
            continue

        home = fix["teams"]["home"]["name"]
        away = fix["teams"]["away"]["name"]
        venue = fix.get("fixture", {}).get("venue", {}) or {}
        location = venue.get("name") or "待定"

        # 这里先用英文队名，后面想要汉化可以再加映射表
        title = f"{emoji_title}：{home} vs {away}"
        desc = f"{comp_cn} - {home} vs {away}"

        uid = f"{start_utc:%Y%m%dT%H%M%S}-{home}-{away}".replace(" ", "")

        event_text = build_event(
            uid=uid,
            title=title,
            desc=desc,
            start_utc=start_utc,
            duration_minutes=120,
            location=location,
        )
        events.append(event_text)

    return events


def main():
    all_events = []

    # 中超
    if CHINA_SUPER_LEAGUE_ID:
        csl_fixtures = fetch_fixtures(CHINA_SUPER_LEAGUE_ID)
        all_events.extend(fixtures_to_events(csl_fixtures, "csl"))

    # 足协杯
    if CHINA_FA_CUP_ID:
        cup_fixtures = fetch_fixtures(CHINA_FA_CUP_ID)
        all_events.extend(fixtures_to_events(cup_fixtures, "cup"))

    # 亚冠
    if ACL_ELITE_ID:
        acl_fixtures = fetch_fixtures(ACL_ELITE_ID)
        all_events.extend(fixtures_to_events(acl_fixtures, "acl"))

    lines = []
    lines.append("BEGIN:VCALENDAR")
    lines.append("VERSION:2.0")
    lines.append("PRODID:-//LouisZeng//ChengduRongchengAPI//CN")
    lines.append("CALSCALE:GREGORIAN")
    lines.append("METHOD:PUBLISH")
    lines.extend(all_events)
    lines.append("END:VCALENDAR")

    OUTPUT_ICS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已生成 {OUTPUT_ICS}，共 {len(all_events)} 场未来比赛。")


if __name__ == "__main__":
    main()
