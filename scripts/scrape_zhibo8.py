# -*- coding: utf-8 -*-
"""
鲁棒版：抓取直播吧 all.htm（全部赛程），命中【成都蓉城】【国际米兰】即收。
- 采用“日期区块 + 行内正则”两层策略，尽量避免因结构细节变化而漏抓
- 输出 data/schedule_2025.json（包含 2024/2025）
- 字段：date,time,opponent,venue,competition,round
"""
import os, re, sys, json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

TARGET_TEAMS = ["成都蓉城", "国际米兰"]
YEARS_ALLOWED = {"2024", "2025"}
URL = "https://www.zhibo8.com/schedule/all.htm"
HEADERS = {"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"}

BASE_DIR = os.path.dirname(os.path.dirname(__file__)) if os.path.dirname(__file__) else "."
DATA_PATH = os.path.join(BASE_DIR, "data", "schedule_2025.json")

COMP_KEYS = ["中超","足协杯","意甲","欧冠","欧联","意大利杯","超级杯","世俱杯","亚冠","友谊赛","热身赛"]
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
DATE_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")
ROUND_RE = re.compile(r"(第?\s*\d+\s*轮|小组赛第?\s*\d+\s*轮|[1-9]\d*强)")

def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text

def infer_year(month:int)->int:
    now = datetime.utcnow()
    cy, cm = now.year, now.month
    if str(cy) in YEARS_ALLOWED:
        if cm >= 10 and month <= 3 and str(cy+1) in YEARS_ALLOWED:
            return cy+1
        return cy
    # 选离当前年最近的允许年
    ys = sorted(int(y) for y in YEARS_ALLOWED)
    return min(ys, key=lambda y: abs(y-cy))

def norm_date(s:str)->str|None:
    m = DATE_RE.search(s)
    if not m: return None
    y = infer_year(int(m.group(1)))
    return f"{y:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

def detect_comp(s:str)->str:
    for k in COMP_KEYS:
        if k in s: return k
    return ""

def parse_line(raw:str):
    """从一行原始文本尽力抽 time/comp/两队"""
    s = re.sub(r"\s+", " ", raw).strip()
    tm_m = TIME_RE.search(s)
    time_str = tm_m.group(1) if tm_m else "00:00"
    comp = detect_comp(s)

    # 去比分
    s_wo_score = re.sub(r"\b\d+\s*[-:]\s*\d+\b", " ", s)
    # 统一 vs
    s_wo_score = s_wo_score.replace("VS","vs").replace("Vs","vs")
    # 去掉时间和赛事名的前缀
    if tm_m:
        s_tmp = s_wo_score.split(time_str,1)[1].strip()
    else:
        s_tmp = s_wo_score
    if comp:
        idx = s_tmp.find(comp)
        if idx != -1:
            s_tmp = s_tmp[idx+len(comp):].strip()

    parts = re.split(r"\s+vs\s+|\s{2,}", s_tmp)
    if len(parts)<2:
        toks = [t for t in s_tmp.split() if re.search(r"[\u4e00-\u9fa5A-Za-z]", t)]
        if len(toks)>=2:
            mid = len(toks)//2
            parts = [" ".join(toks[:mid]), " ".join(toks[mid:])]
        else:
            return time_str, comp, "", ""

    a = parts[0].strip("·.- ")
    b = parts[1].strip("·.- ")
    return time_str, comp, a, b

def pick_record(date_str:str, time_str:str, comp:str, a:str, b:str):
    if date_str[:4] not in YEARS_ALLOWED: return None
    line = f"{comp} {a} vs {b}"
    if not any(t in line for t in TARGET_TEAMS): return None
    # 左主右客（大多数页面如此）
    venue, opp = "", ""
    for t in TARGET_TEAMS:
        if t in a: opp, venue = b, "主场"; break
        if t in b: opp, venue = a, "客场"; break
    if not opp: return None
    rnd = ""
    m = ROUND_RE.search(line)
    if m: rnd = re.sub(r"\s+","", m.group(1))
    return {
        "date": date_str, "time": time_str,
        "competition": comp, "round": rnd,
        "opponent": opp, "venue": venue
    }

def scrape():
    html = fetch_html(URL)
    soup = BeautifulSoup(html, "lxml")

    results = []
    current_date = None

    # 先把页面按“日期标题所在的块”切段：凡是含有“X月Y日”的节点都视作一个分隔点
    texts = [t.strip() for t in soup.find_all(string=True) if t and t.strip()]
    for s in texts:
        # 遇到日期更新 current_date
        if DATE_RE.search(s):
            d = norm_date(s)
            if d: current_date = d
            continue
        # 行里既要有时间，又至少包含一个目标队名，才尝试解析
        if current_date and TIME_RE.search(s) and any(t in s for t in TARGET_TEAMS):
            tstr, comp, a, b = parse_line(s)
            if a and b:
                rec = pick_record(current_date, tstr, comp, a, b)
                if rec: results.append(rec)

    return results

def load_existing():
    if not os.path.exists(DATA_PATH): return []
    try:
        with open(DATA_PATH,"r",encoding="utf-8") as f: return json.load(f)
    except Exception: return []

def save(items):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH,"w",encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

def uniq_merge(old, new):
    key = lambda r: (r["date"], r["time"], r["competition"], r["opponent"])
    seen = {key(r): r for r in old}
    for r in new: seen[key(r)] = r
    merged = list(seen.values())
    merged.sort(key=lambda r: (r["date"], r["time"], r["competition"], r["opponent"]))
    return merged

if __name__ == "__main__":
    print("=== SCRAPER RUN (robust) ===")
    old = load_existing()
    try:
        items = scrape()
        print(f"抓到 {len(items)} 条候选")
        if items[:5]:
            for it in items[:5]:
                print("SAMPLE:", it)
    except Exception as e:
        print("SCRAPE_ERROR:", repr(e))
        sys.exit(0)

    merged = uniq_merge(old, items)
    if merged != old:
        save(merged)
        print(f"UPDATED: {len(old)} -> {len(merged)}")
    else:
        print("NO_CHANGE")
