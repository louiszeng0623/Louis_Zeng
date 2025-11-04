# -*- coding: utf-8 -*-
"""
抓取直播吧“全部赛程” all.htm，筛选【成都蓉城】【国际米兰】的比赛，
输出到 data/schedule_2025.json，字段固定 6 项：
date, time, opponent, venue(主/客), competition, round

说明：
- 来源改为 all.htm（包含未开赛+已完赛，命中率更高）
- 仅写入 2024/2025 年的数据（可在 YEARS_ALLOWED 中调整）
- 主客判断：默认“左主右客”
- 去重主键：(date, time, competition, opponent)
"""
import os
import re
import sys
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ===== 配置区 =====
TARGET_TEAMS = ["成都蓉城", "国际米兰"]
YEARS_ALLOWED = {"2024", "2025"}

ENDPOINTS = [
    "https://www.zhibo8.com/schedule/all.htm",   # 全部赛程（含未来+完赛）
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}
# ==================

BASE_DIR = os.path.dirname(os.path.dirname(__file__)) if os.path.dirname(__file__) else "."
DATA_PATH = os.path.join(BASE_DIR, "data", "schedule_2025.json")


def load_existing():
    if not os.path.exists(DATA_PATH):
        return []
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_data(items):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def fetch_html(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def infer_year(month: int) -> int:
    """
    页面日期多为 “MM月DD日”，无年份。
    这里根据“当前月份”和允许年的范围，粗略推断最近的合法年份。
    规则：优先取“当前年份”；若不在 YEARS_ALLOWED，则取 YEARS_ALLOWED 中的最大年；
    若当前为跨年（例如当前 11 月而页面是 1~2 月），优先选下一年（若在允许集合）。
    """
    now = datetime.utcnow()  # 不用本地时区，足够稳
    cur_y, cur_m = now.year, now.month

    # 优先用当前年（若允许）
    if str(cur_y) in YEARS_ALLOWED:
        # 粗跨年纠偏：若当前在下半年而遇到 1~3 月，猜测是下一年
        if cur_m >= 10 and month <= 3 and str(cur_y + 1) in YEARS_ALLOWED:
            return cur_y + 1
        return cur_y

    # 其次用允许集合里最接近当前年的那个
    years = sorted(int(y) for y in YEARS_ALLOWED)
    # 取与当前年差值最小的
    best = min(years, key=lambda y: abs(y - cur_y))
    return best


def normalize_date(month_day_str: str) -> str | None:
    """
    将“11月04日 星期二” → YYYY-MM-DD（推断年份）
    """
    m = re.search(r'(\d{1,2})月(\d{1,2})日', month_day_str)
    if not m:
        return None
    month = int(m.group(1))
    day = int(m.group(2))
    year = infer_year(month)
    return f"{year:04d}-{month:02d}-{day:02d}"


FOOTBALL_COMP_KEYWORDS = [
    "中超", "足协杯", "意甲", "欧冠", "欧联", "意大利杯", "超级杯",
    "世俱杯", "亚冠", "友谊赛", "热身赛"
]


def detect_competition(text: str) -> str:
    for key in FOOTBALL_COMP_KEYWORDS:
        if key in text:
            return key
    return ""


def parse_row_text(row_text: str):
    """
    解析一条行文本：
    返回 (time_str, competition, team_a, team_b)
    """
    s = re.sub(r'\s+', ' ', row_text).strip()
    # 时间
    tm = re.search(r'\b(\d{1,2}:\d{2})\b', s)
    time_str = tm.group(1) if tm else "00:00"

    # 赛事
    comp = detect_competition(s)

    # 去掉时间与赛事前缀
    rest = s
    if tm:
        rest = rest.split(time_str, 1)[1].strip()
    if comp:
        idx = rest.find(comp)
        if idx != -1:
            rest = rest[idx + len(comp):].strip()

    # 去掉比分
    rest = re.sub(r'\b\d+\s*[-:]\s*\d+\b', ' ', rest)

    # 标准化 VS
    rest = rest.replace("VS", "vs").replace("Vs", "vs")

    # 以 vs 或多个空格切分
    parts = re.split(r'\s+vs\s+|\s{2,}', rest)
    if len(parts) < 2:
        tokens = rest.split()
        text_only = [t for t in tokens if re.search(r'[\u4e00-\u9fa5A-Za-z]', t)]
        if len(text_only) >= 2:
            mid = len(text_only) // 2
            parts = [' '.join(text_only[:mid]), ' '.join(text_only[mid:])]
        else:
            return time_str, comp, "", ""

    team_a = parts[0].strip("·.- ")
    team_b = parts[1].strip("·.- ")
    return time_str, comp, team_a, team_b


def pick_record_for_targets(date_str: str, time_str: str, comp: str, team_a: str, team_b: str):
    """
    若该行命中我们的目标队，则返回一条记录 dict，否则返回 None
    """
    if not comp:
        return None

    line = f"{comp} {team_a} vs {team_b}"
    if not any(t in line for t in TARGET_TEAMS):
        return None

    our = None
    opp = None
    venue = ""  # 主/客
    for t in TARGET_TEAMS:
        if t in team_a:
            our, opp, venue = t, team_b, "主场"
            break
        if t in team_b:
            our, opp, venue = t, team_a, "客场"
            break
    if not our or not opp:
        return None

    # 轮次匹配（第X轮/小组赛第X轮/XX强等）
    round_info = ""
    m = re.search(r'(第?\s*\d+\s*轮|小组赛第?\s*\d+\s*轮|[1-9]\d*强)', line)
    if m:
        round_info = re.sub(r'\s+', '', m.group(1))

    # 年份过滤（只保留允许的年份）
    if date_str[:4] not in YEARS_ALLOWED:
        return None

    return {
        "date": date_str,
        "time": time_str,
        "competition": comp,
        "round": round_info,
        "opponent": opp,
        "venue": venue
    }


def scrape():
    results = []
    for url in ENDPOINTS:
        html = fetch_html(url)
        soup = BeautifulSoup(html, "lxml")

        current_date = None
        # 遍历所有文本节点，靠“11月04日”这类标题更新 current_date
        for node in soup.find_all(text=True):
            s = str(node).strip()
            if not s:
                continue

            # 日期标题
            if re.search(r'\d{1,2}月\d{1,2}日', s):
                d = normalize_date(s)
                if d:
                    current_date = d
                continue

            # 赛事行（含时间）
            if current_date and re.search(r'\b\d{1,2}:\d{2}\b', s):
                time_str, comp, a, b = parse_row_text(s)
                if not a or not b:
                    continue
                rec = pick_record_for_targets(current_date, time_str, comp, a, b)
                if rec:
                    results.append(rec)

    return results


def uniq_merge(old, new):
    key = lambda r: (r["date"], r["time"], r["competition"], r["opponent"])
    seen = {key(r): r for r in old}
    for r in new:
        seen[key(r)] = r
    merged = list(seen.values())
    merged.sort(key=lambda r: (r["date"], r["time"], r["competition"], r["opponent"]))
    return merged


if __name__ == "__main__":
    old = load_existing()
    try:
        new_items = scrape()
    except Exception as e:
        print("SCRAPE_ERROR:", repr(e))
        sys.exit(0)  # 不让 CI 失败

    merged = uniq_merge(old, new_items)
    if merged != old:
        save_data(merged)
        print(f"UPDATED: {len(old)} -> {len(merged)}")
    else:
        print("NO_CHANGE")
