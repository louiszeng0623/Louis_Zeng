# -*- coding: utf-8 -*-
"""
双通道稳版：
- 主通道：懂球帝 搜索 -> 球队页（直抓文本）
- 兜底通道：直播吧 联赛/总表页 过滤队名
- 调试：把原始页面保存到 data/_debug/ 供 Actions 下载查看
输出：
- data/schedule_2025.json
- data/schedule_2026.json
字段：date, time, opponent, venue, competition, round, team
"""
import os, re, json, time, urllib.parse, requests
from datetime import datetime, date, timedelta
from bs4 import BeautifulSoup

UA = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TARGET_TEAMS = ["国际米兰", "成都蓉城"]
YEARS_KEEP = {"2025","2026"}
OUT_2025 = "data/schedule_2025.json"
OUT_2026 = "data/schedule_2026.json"
DBG_DIR = "data/_debug"

# ----------------- 通用工具 -----------------
def ensure_dir(p): os.makedirs(p, exist_ok=True)
def write_text(path, text):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f: f.write(text)

def safe_get(url, retries=3, timeout=20, label=""):
    last = ""
    for i in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code == 200 and len(r.text) > 200:
                if label:
                    write_text(f"{DBG_DIR}/{label}.txt", r.text)
                return r.text
            last = f"bad status {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(2)
    print(f"[WARN] get {url} failed: {last}")
    return ""

def looks_like_team(s):
    return bool(s and 2 <= len(s) <= 28 and re.search(r"[A-Za-z\u4e00-\u9fa5]", s))

def valid_date(y,m,d):
    try: date(y,m,d); return True
    except: return False

TIME_HM  = re.compile(r"\b(\d{1,2}):(\d{2})\b")
DATE_YMD = re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b")
DATE_MD  = re.compile(r"\b(\d{1,2})[-/](\d{1,2})\b")
NON_WORD = re.compile(r"[^\u4e00-\u9fa5A-Za-z0-9·\-\s]")

def clean(s):
    s = re.sub(r"https?://\S+|Image\d+\S*", " ", s)
    s = NON_WORD.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def norm_date(block, prefer_year="2025"):
    b = block.replace("/", "-")
    m = DATE_YMD.search(b)
    if m:
        y,mo,d = map(int, m.groups())
        if str(y) in YEARS_KEEP and valid_date(y,mo,d):
            return f"{y:04d}-{mo:02d}-{d:02d}"
        return ""
    m = DATE_MD.search(b)
    if not m: return ""
    mo,d = map(int, m.groups())
    y = int(prefer_year)
    if not valid_date(y,mo,d):
        y = 2026 if y==2025 else 2025
        if not valid_date(y,mo,d): return ""
    return f"{y:04d}-{mo:02d}-{d:02d}"

def comp_guess(block):
    for k in ["中超","亚冠","足协杯","意甲","欧冠","欧联","意大利杯","意超杯","友谊赛","热身赛","世俱杯"]:
        if k in block: return k
    return ""

def add_unique(rows, item):
    key = (item["date"], item["time"], item["team"], item["opponent"], item.get("competition",""))
    if key not in {(r["date"], r["time"], r["team"], r["opponent"], r.get("competition","")) for r in rows}:
        rows.append(item)

# ----------------- 懂球帝通道 -----------------
def find_team_id(team_name):
    q = urllib.parse.quote(team_name)
    for u in [
        f"https://www.dongqiudi.com/search?query={q}",
        f"https://dongqiudi.com/search?query={q}",
    ]:
        html = safe_get(u, label=f"dqd_search_{team_name}")
        if not html: continue
        m = re.search(r"/team/(\d+)\.html", html)
        if m: return m.group(1)
    return None

def parse_team_page(html, team_name):
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = []
    for i, ln in enumerate(lines):
        if DATE_YMD.search(ln) or DATE_MD.search(ln):
            block = clean(" ".join(lines[i:i+8]))
            if team_name not in block: continue
            # 时间
            m_t = TIME_HM.search(block)
            hhmm = m_t.group(0) if m_t else "20:00"
            # 对阵
            if " VS " in block: parts = block.split(" VS ")
            elif " vs " in block: parts = block.split(" vs ")
            else: parts = re.split(r"[－\-]", block, maxsplit=1)
            if len(parts)<2: continue
            left,right = clean(parts[0]), clean(parts[1])
            if team_name in left and team_name not in right:
                venue,opponent="主场", right
            elif team_name in right and team_name not in left:
                venue,opponent="客场", left
            else:
                continue
            if not looks_like_team(opponent): continue
            d = norm_date(block, "2025")
            if not d: continue
            add_unique(out, {
                "date": d, "time": hhmm,
                "competition": comp_guess(block),
                "round": re.search(r"(第?\d+轮|1/8决赛|1/4决赛|半决赛|决赛)", block).group(0) if re.search(r"(第?\d+轮|1/8决赛|1/4决赛|半决赛|决赛)", block) else "",
                "opponent": opponent, "venue": venue, "team": team_name
            })
    out.sort(key=lambda x:(x["date"], x["time"]))
    return out

# ----------------- 直播吧兜底通道 -----------------
ZB_PAGES = [
    "https://www.zhibo8.com/schedule/all.htm",
    "https://www.zhibo8.com/zuqiu/zhongchao/",
    "https://www.zhibo8.com/zuqiu/yaguan/",
    "https://www.zhibo8.com/zuqiu/yijia/",
    "https://www.zhibo8.com/zuqiu/ouguan/",
]

def parse_zhibo8(html, team_name):
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = []
    for i, ln in enumerate(lines):
        if team_name in ln and (DATE_YMD.search(ln) or DATE_MD.search(ln)):
            # 向前后各取几行凑一个 block
            block = clean(" ".join(lines[max(0,i-2): i+6]))
            m_t = TIME_HM.search(block)
            hhmm = m_t.group(0) if m_t else "20:00"
            d = norm_date(block, "2025")
            if not d: continue
            # 对阵
            opp = ""
            if " VS " in block:
                a,b = block.split(" VS ",1)
                opp = a if team_name in b else b
            elif " vs " in block:
                a,b = block.split(" vs ",1)
                opp = a if team_name in b else b
            else:
                # 兜底：取 team_name 左右最近的词
                segs = block.split(team_name)
                if len(segs)>=2:
                    right_tail = segs[1].split(" ",1)[0]
                    left_tail  = segs[0].split(" ")[-1] if segs[0] else ""
                    opp = clean(right_tail or left_tail)
            opp = clean(opp)
            if not looks_like_team(opp): continue
            venue = "主场" if "主" in block and "客" not in block else ("客场" if "客" in block else "")
            add_unique(out, {
                "date": d, "time": hhmm,
                "competition": comp_guess(block), "round": "",
                "opponent": opp, "venue": venue, "team": team_name
            })
    out.sort(key=lambda x:(x["date"], x["time"]))
    return out

# ----------------- 主流程 -----------------
def main():
    ensure_dir("data")
    ensure_dir(DBG_DIR)
    all_rows = []

    for team in TARGET_TEAMS:
        # 1) 懂球帝
        tid = find_team_id(team)
        team_rows = []
        if tid:
            print(f"[INFO] {team} ID={tid}")
            html = safe_get(f"https://www.dongqiudi.com/team/{tid}.html", label=f"dqd_team_{team}")
            if html:
                team_rows = parse_team_page(html, team)
                print(f"[INFO] {team} 懂球帝命中 {len(team_rows)} 条")
        else:
            print(f"[WARN] 没找到 {team} 的ID，跳过懂球帝通道")

        # 2) 兜底：直播吧
        if len(team_rows) < 3:   # 太少，用兜底补
            zb_rows = []
            for u in ZB_PAGES:
                html = safe_get(u, label=f"zb8_{team}_{u.split('/')[-2] if u.endswith('/') else 'all'}")
                if not html: continue
                rows = parse_zhibo8(html, team)
                zb_rows += rows
            # 去重后合并
            for r in zb_rows:
                add_unique(team_rows, r)
            print(f"[INFO] {team} 兜底累计 {len(team_rows)} 条")

        all_rows += team_rows

    # 按年写出
    y25 = [r for r in all_rows if r["date"].startswith("2025-")]
    y26 = [r for r in all_rows if r["date"].startswith("2026-")]

    with open(OUT_2025, "w", encoding="utf-8") as f:
        json.dump(y25, f, ensure_ascii=False, indent=2)
    with open(OUT_2026, "w", encoding="utf-8") as f:
        json.dump(y26, f, ensure_ascii=False, indent=2)

    print(f"[DONE] 2025={len(y25)} 条, 2026={len(y26)} 条；页面副本见 {DBG_DIR}/")
if __name__ == "__main__":
    main()
    
