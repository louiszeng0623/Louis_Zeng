# -*- coding: utf-8 -*-
"""
防超时稳版
直接爬懂球帝网页，不再依赖 r.jina.ai。
增加网络重试机制 + 双备用源。
"""
import os, re, json, datetime as _dt, requests, urllib.parse, time
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
OUT_2025 = "data/schedule_2025.json"
OUT_2026 = "data/schedule_2026.json"
TARGET_TEAMS = ["国际米兰", "成都蓉城"]
YEARS_KEEP = {"2025","2026"}

# ------------------ 网络安全层 ------------------
def safe_get(url, retries=3, timeout=20):
    """自动重试抓网页"""
    for i in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code == 200 and len(r.text) > 1000:
                return r.text
        except Exception as e:
            print(f"[WARN] 第{i+1}次抓取 {url} 失败：{e}")
            time.sleep(3)
    return ""

def find_team_id(team_name: str) -> str | None:
    """从搜索页自动提取球队 ID"""
    q = urllib.parse.quote(team_name)
    urls = [
        f"https://www.dongqiudi.com/search?query={q}",
        f"https://dongqiudi.com/search?query={q}"
    ]
    for u in urls:
        html = safe_get(u)
        if not html:
            continue
        m = re.search(r"/team/(\d+)\.html", html)
        if m:
            return m.group(1)
    return None

# ------------------ 解析层 ------------------
def sanitize_text(s: str) -> str:
    s = re.sub(r"https?://\S+|Image\d+\S*", " ", s)
    s = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9·\-\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

TIME_HM  = re.compile(r"\b(\d{1,2}):(\d{2})\b")
DATE_YMD = re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b")
DATE_MD  = re.compile(r"\b(\d{1,2})[-/](\d{1,2})\b")
COMP_KEYS = ["中超","亚冠","足协杯","意甲","欧冠","欧联","意大利杯","意超杯","友谊赛","热身赛","世俱杯"]

def valid_date(y,m,d):
    try: _dt.date(y,m,d); return True
    except: return False

def norm_date(block, prefer_year="2025"):
    block = block.replace("/", "-")
    m = DATE_YMD.search(block)
    if m:
        y,mo,d = map(int,m.groups())
        if str(y) in YEARS_KEEP and valid_date(y,mo,d):
            return f"{y:04d}-{mo:02d}-{d:02d}"
    m = DATE_MD.search(block)
    if not m: return ""
    mo,d = map(int,m.groups())
    y = int(prefer_year)
    if not valid_date(y,mo,d):
        y = 2026 if y==2025 else 2025
        if not valid_date(y,mo,d): return ""
    return f"{y:04d}-{mo:02d}-{d:02d}"

def parse_team_page(html_text, team_name):
    soup = BeautifulSoup(html_text, "lxml")
    text = soup.get_text("\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    items = []
    for i, ln in enumerate(lines):
        if DATE_YMD.search(ln) or DATE_MD.search(ln):
            block = sanitize_text(" ".join(lines[i:i+8]))
            if team_name not in block: continue
            # 时间
            m_t = TIME_HM.search(block)
            hhmm = m_t.group(0) if m_t else "20:00"
            # 赛事
            comp = next((k for k in COMP_KEYS if k in block), "")
            # 对阵
            if " VS " in block: parts = block.split(" VS ")
            elif " vs " in block: parts = block.split(" vs ")
            else: parts = re.split(r"[－\-]", block, maxsplit=1)
            if len(parts)<2: continue
            left,right = sanitize_text(parts[0]),sanitize_text(parts[1])
            if team_name in left and team_name not in right:
                venue,opponent="主场",right
            elif team_name in right and team_name not in left:
                venue,opponent="客场",left
            else: continue
            date = norm_date(block)
            if not date: continue
            rnd = re.search(r"(第?\d+轮|1/8决赛|半决赛|决赛)",block)
            rnd = rnd.group(0) if rnd else ""
            items.append({
                "date": date, "time": hhmm,
                "competition": comp, "round": rnd,
                "opponent": opponent, "venue": venue,
                "team": team_name
            })
    # 去重
    uniq, seen = [], set()
    for x in items:
        k=(x["date"],x["time"],x["team"],x["opponent"])
        if k not in seen:
            uniq.append(x); seen.add(k)
    uniq.sort(key=lambda x:(x["date"],x["time"]))
    return uniq

# ------------------ 保存层 ------------------
def save_split(rows):
    os.makedirs("data",exist_ok=True)
    y25=[r for r in rows if r["date"].startswith("2025-")]
    y26=[r for r in rows if r["date"].startswith("2026-")]
    def write(path,data):
        with open(path,"w",encoding="utf-8") as f:
            json.dump(data,f,ensure_ascii=False,indent=2)
    write(OUT_2025,y25)
    write(OUT_2026,y26)

# ------------------ 主程序 ------------------
def main():
    all_rows=[]
    for team in TARGET_TEAMS:
        tid = find_team_id(team)
        if not tid:
            print(f"[ERROR] 找不到 {team} ID，跳过")
            continue
        print(f"[INFO] {team} ID={tid}")
        html = safe_get(f"https://www.dongqiudi.com/team/{tid}.html")
        if not html:
            print(f"[ERROR] {team} 网页抓取失败")
            continue
        rows = parse_team_page(html,team)
        print(f"[INFO] {team} 抓到 {len(rows)} 条")
        all_rows += rows
    save_split(all_rows)
    print("[DONE] 所有数据写入 data/ 文件夹")

if __name__ == "__main__":
    main()
    
