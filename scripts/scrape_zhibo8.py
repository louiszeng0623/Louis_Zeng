# -*- coding: utf-8 -*-
"""
抓取直播吧完赛赛程（finish_more）中包含【成都蓉城】【国际米兰】的比赛，
输出到 data/schedule_2025.json，字段固定 6 项：
date, time, opponent, venue(主/客), competition, round

注意：
- 仅抓取“完赛”页作为数据源（更稳定）；未来赛程可后续扩展别的页面/接口。
- YEAR_TARGET = 2025，可按需调整或扩展为多年份。
- 合并去重主键：(date, time, competition, opponent)
"""
import json
import re
import os
import sys
import requests
from bs4 import BeautifulSoup

# ===== 配置区 =====
TARGET_TEAMS = ["成都蓉城", "国际米兰"]
YEAR_TARGET = 2025

FOOTBALL_COMP_KEYWORDS = [
    "中超", "足协杯", "意甲", "欧冠", "欧联", "意大利杯", "超级杯", "世俱杯", "亚冠", "友谊赛", "热身赛"
]

ENDPOINTS = [
    "https://www.zhibo8.com/schedule/finish_more.htm",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}
# ==================

BASE_DIR = os.path.dirname(os.path.dirname(__file__)) if os.path.dirname(__file__) else "."
DATA_PATH = os.path.join(BASE_DIR, "data", f"schedule_{YEAR_TARGET}.json")


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


def normalize_date(month_day_str, ref_year):
    """
    将“11月04日 星期二” → YYYY-MM-DD
    """
    m = re.search(r'(\d{1,2})月(\d{1,2})日', month_day_str)
    if not m:
        return None
    month = int(m.group(1))
    day = int(m.group(2))
    return f"{ref_year:04d}-{month:02d}-{day:02d}"


def detect_competition(text):
    for key in FOOTBALL_COMP_KEYWORDS:
        if key in text:
            return key
    return ""


def parse_row_text(row_text):
    """
    从一行文本抽取：time, competition, team_a, team_b
    行例子：
    "19:35 中超 成都蓉城 2 - 1 长春亚泰"
    "18:00 足协杯 成都蓉城 vs 上海申花"
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

    # 尝试按分隔符切两队
    parts = re.split(r'\s+vs\s+|\s{2,}', rest)
    if len(parts) < 2:
        # 兜底：按照中文/字母块粗分
        tokens = rest.split()
        text_only = [t for t in tokens if re.search(r'[\u4e00-\u9fa5A-Za-z]', t)]
        if len(text_only) >= 2:
            mid = len(text_only) // 2
            parts = [' '.join(text_only[:mid]), ' '.join(text_only[mid:])]
        else:
            return time_str, comp, "", ""

    team_a = parts[0].strip("·.- ")
    team_b = parts[1].strip("·.- ") if len(parts) > 1 else ""
    return time_str, comp, team_a, team_b


def pick_record_for_targets(date_str, time_str, comp, team_a, team_b):
    """
    命中我们的目标队时，产出一条标准记录：
    date, time, competition, round, opponent, venue
    """
    if not comp:
        return None

    line = f"{comp} {team_a} vs {team_b}"
    if not any(t in line for t in TARGET_TEAMS):
        return None

    our = None
    opp = None
    venue = ""

    # 直播吧通常左主右客
    for t in TARGET_TEAMS:
        if t and t in team_a:
            our, opp, venue = t, team_b, "主场"
            break
        if t and t in team_b:
            our, opp, venue = t, team_a, "客场"
            break

    if not our or not opp:
        return None

    # 轮次
    round_info = ""
    m = re.search(r'(第?\s*\d+\s*轮|小组赛第?\s*\d+\s*轮|[1-9]\d*强)', line)
    if m:
        round_info = re.sub(r'\s+', '', m.group(1))

    return {
        "date": date_str,
        "time": time_str,
        "competition": comp,
        "round": round_info,
        "opponent": opp,
        "venue": venue
    }


def scrape():
    ref_year = YEAR_TARGET
    results = []

    for url in ENDPOINTS:
        html = fetch_html(url)
        soup = BeautifulSoup(html, "lxml")

        # 遍历文本节点，遇到“11月xx日”就更新 current_date
        current_date = None
        for node in soup.find_all(text=True):
            s = str(node).strip()
            if not s:
                continue

            # 日期标题（例如：11月04日 星期二）
            if re.search(r'\d{1,2}月\d{1,2}日', s):
                d = normalize_date(s, ref_year)
                if d:
                    current_date = d
                continue

            # 赛事行一般含有时间
            if re.search(r'\b\d{1,2}:\d{2}\b', s) and current_date:
                time_str, comp, a, b = parse_row_text(s)
                if not a or not b:
                    continue
                rec = pick_record_for_targets(current_date, time_str, comp, a, b)
                if rec:
                    # 仅保留目标年份
                    if rec["date"].startswith(f"{YEAR_TARGET}-"):
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
        # 不让CI失败；打印错误方便排查
        print("SCRAPE_ERROR:", repr(e))
        sys.exit(0)

    merged = uniq_merge(old, new_items)
    if merged != old:
        save_data(merged)
        print(f"UPDATED: {len(old)} -> {len(merged)}")
    else:
        print("NO_CHANGE")
