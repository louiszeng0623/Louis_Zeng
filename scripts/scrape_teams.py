# -*- coding: utf-8 -*-
"""
抓取【国际米兰、成都蓉城】在懂球帝的球队页赛程，输出：
- data/schedule_2025.json
- data/schedule_2026.json
字段：date, time, opponent, venue(主/客), competition, round, team
策略：
1) 先用懂球帝搜索页自动发现球队ID（/team/<id>.html）
2) 通过 r.jina.ai 只读镜像抓HTML（稳定绕过JS）
3) 文本解析 + 清洗 + 严格日期校验
4) 仅保留 2025/2026 两年
"""
import os, re, json, datetime as _dt, requests, urllib.parse
from bs4 import BeautifulSoup

UA = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
OUT_2025 = "data/schedule_2025.json"
OUT_2026 = "data/schedule_2026.json"
TARGET_TEAMS = ["国际米兰", "成都蓉城"]
YEARS_KEEP = {"2025","2026"}

# 清洗正则
URL_JUNK_RE = re.compile(r"https?://\S+|Image\d+\S*", re.I)
NON_WORD_RE = re.compile(r"[^\u4e00-\u9fa5A-Za-z0-9·\-\s]")
TIME_HM  = re.compile(r"\b(\d{1,2}):(\d{2})\b")
DATE_YMD = re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b")
DATE_MD  = re.compile(r"\b(\d{1,2})[-/](\d{1,2})\b")

COMP_KEYS = ["中超","亚冠","足协杯","意甲","欧冠","欧联","意大利杯","意超杯","友谊赛","热身赛","世俱杯"]

def _mirror(url: str) -> str:
    return "https://r.jina.ai/http://" + url.replace("https://","").replace("http://","")

def fetch(url: str) -> str:
    r = requests.get(_mirror(url), headers=UA, timeout=25)
    r.raise_for_status()
    return r.text

def sanitize_text(s: str) -> str:
    s = URL_JUNK_RE.sub(" ", s)
    s = NON_WORD_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def looks_like_team(s: str) -> bool:
    return bool(s and 2 <= len(s) <= 28 and re.search(r"[A-Za-z\u4e00-\u9fa5]", s))

def valid_date(y:int,m:int,d:int)->bool:
    try: _dt.date(y,m,d); return True
    except ValueError: return False

def norm_date_in_block(block: str, prefer_year: str) -> str:
    block = block.replace("/", "-")
    m = DATE_YMD.search(block)
    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}" if str(y) in YEARS_KEEP and valid_date(y,mo,d) else ""
    m = DATE_MD.search(block)
    if not m: return ""
    mo, d = map(int, m.groups())
    y = int(prefer_year)
    if not valid_date(y, mo, d):
        alt = 2026 if y == 2025 else 2025
        if valid_date(alt, mo, d): y = alt
        else: return ""
    return f"{y:04d}-{mo:02d}-{d:02d}"

def find_team_id(team_name: str) -> str | None:
    url = "https://www.dongqiudi.com/search?query=" + urllib.parse.quote(team_name)
    html = fetch(url)
    m = re.search(r"/team/(\d+)\.html", html)
    return m.group(1) if m else None

def parse_team_page(html_text: str, team_name: str):
    soup = BeautifulSoup(html_text, "lxml")
    text = soup.get_text("\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    items = []
    for i, ln in enumerate(lines):
        # 找到含日期的起始行，向后取 6～8 行作为一个 block
        if DATE_YMD.search(ln) or DATE_MD.search(ln):
            block = sanitize_text(" ".join(lines[i:i+8]))
            if team_name not in block: 
                continue
            # 时间
            m_t = TIME_HM.search(block)
            hhmm = m_t.group(0) if m_t else "20:00"
            # 赛事
            comp = ""
            for k in COMP_KEYS:
                if k in block: comp = k; break
            # 对阵 split
            if " VS " in block: parts = block.split(" VS ")
            elif " vs " in block: parts = block.split(" vs ")
            else: parts = re.split(r"[－\-]", block, maxsplit=1)
            if len(parts) < 2: 
                continue
            left, right = sanitize_text(parts[0]), sanitize_text(parts[1])
            # 主客判断
            if team_name in left and team_name not in right:
                venue, opponent = "主场", right
            elif team_name in right and team_name not in left:
                venue, opponent = "客场", left
            else:
                continue
            if not looks_like_team(opponent): 
                continue
            # 日期（智能落在 2025/2026）
            date = norm_date_in_block(block, "2025")
            if not date or date[:4] not in YEARS_KEEP: 
                continue
            # 轮次
            m_r = re.search(r"(第?\d+轮|小组赛第?\d+轮|1/8决赛|1/4决赛|半决赛|决赛|第?\d+场)", block)
            rnd = m_r.group(0) if m_r else ""
            items.append({
                "date": date, "time": hhmm,
                "competition": comp, "round": rnd,
                "opponent": opponent, "venue": venue
            })
    # 去重排序
    seen, out = set(), []
    for it in items:
        key = (it["date"], it["time"], it["opponent"], it["competition"])
        if key not in seen:
            seen.add(key); out.append(it)
    out.sort(key=lambda x: (x["date"], x["time"], x["opponent"]))
    return out

def save_year_split(rows, team):
    os.makedirs("data", exist_ok=True)
    y2025 = [dict(r, team=team) for r in rows if r["date"].startswith("2025-")]
    y2026 = [dict(r, team=team) for r in rows if r["date"].startswith("2026-")]
    def _write(path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    # 先读已有，合并去重
    def _merge(path, new):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                try: old = json.load(f)
                except Exception: old = []
        else:
            old = []
        idx = {(o["date"], o["time"], o["team"], o["opponent"], o.get("competition","")): i for i,o in enumerate(old)}
        for r in new:
            key = (r["date"], r["time"], r["team"], r["opponent"], r.get("competition",""))
            if key in idx:
                old[idx[key]] = r
            else:
                old.append(r)
        old.sort(key=lambda r: (r["date"], r["time"], r["team"]))
        return old

    json_2025 = _merge(OUT_2025, y2025)
    json_2026 = _merge(OUT_2026, y2026)
    _write(OUT_2025, json_2025)
    _write(OUT_2026, json_2026)

def main():
    for team in TARGET_TEAMS:
        # 1) 找ID
        tid = find_team_id(team)
        if not tid:
            print(f"[WARN] 未找到 {team} 的ID，跳过")
            continue
        print(f"[INFO] {team} ID = {tid}")
        # 2) 抓球队页
        html = fetch(f"https://www.dongqiudi.com/team/{tid}.html")
        rows = parse_team_page(html, team)
        print(f"[INFO] {team} 抓到 {len(rows)} 条")
        # 3) 写两个年份
        save_year_split(rows, team)

if __name__ == "__main__":
    main()
