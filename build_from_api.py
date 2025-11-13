import os
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_HOST = "https://v3.football.api-sports.io"
API_KEY = os.environ["FOOTBALL_API_KEY"]

# 固定参数
TEAM_ID = 5648
CHINA_SUPER_LEAGUE_ID = 169
CHINA_FA_CUP_ID = 171
ACL_ELITE_ID = 17
SEASON = 2025

OUTPUT_ICS = Path("蓉城.ics")

# ===== 你最终确认的赛事前缀 =====
COMPETITION_STYLE = {
    "csl": ("🔥 中超", "中超联赛"),
    "cup": ("🏆 足协杯", "中国足协杯"),
    "acl": ("🏆 亚冠", "亚冠联赛"),
}

# ===== 中文队名映射 =====
TEAM_NAME_MAP = {
    "Chengdu Better City": "成都蓉城",

    # 中超队伍
    "Shanghai Port": "上海海港",
    "Shanghai Shenhua": "上海申花",
    "Beijing Guoan": "北京国安",
    "Shandong Taishan": "山东泰山",
    "Tianjin Jinmen Tiger": "天津津门虎",
    "Changchun Yatai": "长春亚泰",
    "Henan": "河南队",
    "Zhejiang Professional": "浙江队",
    "Zhejiang FC": "浙江队",
    "Wuhan Three Towns": "武汉三镇",
    "Meizhou Hakka": "梅州客家",
    "Shenzhen Peng City": "深圳新鹏城",
    "Qingdao Hainiu": "青岛海牛",
    "Qingdao West Coast": "青岛西海岸",
    "Cangzhou Mighty Lions": "沧州雄狮",
    "Nantong Zhiyun": "南通支云",

    # 亚冠常见球队
    "Yokohama F. Marinos": "横滨水手",
    "Kawasaki Frontale": "川崎前锋",
    "Ulsan HD": "蔚山现代",
    "Jeonbuk Motors": "全北现代",
    "Pohang Steelers": "浦项制铁",
    "Kitchee": "杰志",
    "Incheon United": "仁川联",
    "Buriram United": "武里南联",
    "Johor Darul Ta'zim": "柔佛新山",
}

def zh_team(name):
    return TEAM_NAME_MAP.get(name, name)

def fetch_fixtures(league_id):
    url = f"{API_HOST}/fixtures"
    headers = {"x-apisports-key": API_KEY}
    params = {"league": league_id, "season": SEASON, "team": TEAM_ID}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("response", [])

def parse_fixture_time(fix):
    dt = datetime.fromisoformat(fix["fixture"]["date"].replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc)

def build_event(uid, title, desc, start_utc, location):
    dtend_utc = start_utc + timedelta(minutes=120)
    dtstamp = datetime.utcnow().replace(tzinfo=timezone.utc)

    def fmt(dt):
        return dt.strftime("%Y%m%dT%H%M%SZ")

    return "\n".join([
        "BEGIN:VEVENT",
        f"UID:{uid}@chengdu-rongcheng",
        f"DTSTAMP:{fmt(dtstamp)}",
        f"DTSTART:{fmt(start_utc)}",
        f"DTEND:{fmt(dtend_utc)}",
        f"SUMMARY:{title}",
        f"DESCRIPTION:{desc}",
        f"LOCATION:{location}",
        "BEGIN:VALARM",
        "TRIGGER:-PT120M",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{title}（比赛前2小时提醒）",
        "END:VALARM",
        "END:VEVENT"
    ])

def fixtures_to_events(fixtures, comp_code):
    prefix, comp_cn = COMPETITION_STYLE[comp_code]
    events = []
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)

    for fix in fixtures:
        start_utc = parse_fixture_time(fix)
        if start_utc < now_utc:
            continue

        home_en = fix["teams"]["home"]["name"]
        away_en = fix["teams"]["away"]["name"]
        home = zh_team(home_en)
        away = zh_team(away_en)

        venue = fix["fixture"].get("venue", {}).get("name") or "待定球场"

        if fix["teams"]["home"]["id"] == TEAM_ID:
            home_away = "主场"
        else:
            home_away = "客场"

        title = f"{prefix} | {home} vs {away}（{home_away}）"

        round_name = fix.get("league", {}).get("round") or "待定轮次"
        desc = "\\n".join([
            f"赛事：{comp_cn}",
            f"轮次：{round_name}",
            f"比赛：{home} vs {away}",
            f"主客：{home_away}",
            f"球场：{venue}",
        ])

        uid = f"{start_utc:%Y%m%dT%H%M%S}-{home_en}-{away_en}".replace(" ", "")
        events.append(build_event(uid, title, desc, start_utc, venue))

    return events

def main():
    all_events = []
    all_events += fixtures_to_events(fetch_fixtures(CHINA_SUPER_LEAGUE_ID), "csl")
    all_events += fixtures_to_events(fetch_fixtures(CHINA_FA_CUP_ID), "cup")
    all_events += fixtures_to_events(fetch_fixtures(ACL_ELITE_ID), "acl")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"] \
            + all_events + ["END:VCALENDAR"]

    OUTPUT_ICS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已生成 {OUTPUT_ICS}，共 {len(all_events)} 场未来比赛。")

if __name__ == "__main__":
    main()
