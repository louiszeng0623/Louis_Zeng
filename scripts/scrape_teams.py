# -*- coding: utf-8 -*-
"""
Louis_Zeng 赛程构建器（直播吧 + 懂球帝 + 手动种子）
输出：
  data/schedule_2025.json
  data/schedule_2026.json
字段：date, time, opponent, venue, competition, round, team

策略：
- 直播吧：finish_more / all / 联赛页（结构化选择器 + 文本回退）
- 懂球帝：搜索 -> 球队页（弱解析）
- 手动种子：data/manual_seed_2025.json / 2026.json（可选）
- 调试：data/_debug/ 下保存原始页面
"""
import os, re, json, time, urllib.parse, requests
from datetime import date
from bs4 import BeautifulSoup

# ---------- 配置 ----------
UA = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TARGET_TEAMS = ["国际米兰", "成都蓉城"]
YEARS_KEEP = {"2025","2026"}

OUT_2025 = "data/schedule_2025.json"
OUT_2026 = "data/schedule_2026.json"
SEED_2025 = "data/manual_seed_2025.json"
SEED_2026 = "data/manual_seed_2026.json"

DBG_DIR = "data/_debug"

ZB_PAGES = [
    "https://www.zhibo8.com/schedule/finish_more.htm",  # 已结束汇总（历史）
    "https://www.zhibo8.com/schedule/all.htm",          # 今日/近期
    "https://www.zhibo8.com/zuqiu/zhongchao/",
    "https://www.zhibo8.com/zuqiu/yijia/",
    "https://www.zhibo8.com/zuqiu/ouguan/",
]

# ---------- 工具 ----------
def ensure_dir(p): os.makedirs(p, exist_ok=True)
def write_text(path, text):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f: f.write(text)

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def safe_get(url, retries=3, timeout=20, label=""):
    """
    稳健抓取并修正编码；始终把“正常中文”的页面保存到 data/_debug/。
    """
    last = ""
    headers = {
        **UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "close",
    }
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            raw = r.content or b""
            txt = ""
            # 1) utf-8
            try:
                txt = raw.decode("utf-8")
            except UnicodeDecodeError:
                # 2) 猜测编码
                enc = (r.apparent_encoding or "").lower()
                if enc and enc not in ("utf-8","utf8"):
                    try:
                        txt = raw.decode(enc, errors="ignore")
                    except Exception:
                        pass
                # 3) 兜底 gbk
                if not txt:
                    try:
                        txt = raw.decode("gbk", errors="ignore")
                    except Exception:
                        txt = r.text
            if r.status_code == 200 and len(txt) > 200:
                if label:
                    write_text(f"{DBG_DIR}/{label}.txt", txt)
                return txt
            last = f"bad status {r.status_code}, len={len(txt)}"
        except Exception as e:
            last = str(e)
        time.sleep(1.2)
    print(f"[WARN] get {url} failed: {last}")
    return ""

# 正则与清洗
TIME_HM  = re.compile(r"\b(\d{1,2}):(\d{2})\b")
DATE_YMD = re.compile(r"\b(2025|2026)[-/](\d{1,2})[-/](\d{1,2})\b")
DATE_MD  = re.compile(r"\b(\d{1,2})[-/](\d{1,2})\b")
NON_WORD = re.compile(r"[^\u4e00-\u9fa5A-Za-z0-9·\-\s]")

def looks_like_team(s):
    return bool(s and 1 <= len(s) <= 40 and re.search(r"[A-Za-z\u4e00-\u9fa5]", s))

def valid_date(y,m,d):
    try:
        date(y,m,d)
        return True
    except:
        return False

def clean(s):
    s = re.sub(r"https?://\S+|Image\d+\S*", " ", s or "")
    s = NON_WORD.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def norm_date_any(block, prefer_year="2025"):
    """
    支持：
      2025-05-12 / 2025/5/12
      5-12（自动补年）
    """
    b = (block or "").replace("/", "-")
    m = DATE_YMD.search(b)
    if m:
        y,mo,d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if str(y) in YEARS_KEEP and valid_date(y,mo,d):
            return f"{y:04d}-{mo:02d}-{d:02d}"
        return ""
    m = DATE_MD.search(b)
    if not m: return ""
    mo,d = int(m.group(1)), int(m.group(2))
    y = int(prefer_year)
    if not valid_date(y,mo,d):
        y = 2026 if y==2025 else 2025
        if not valid_date(y,mo,d): return ""
    return f"{y:04d}-{mo:02d}-{d:02d}"

def comp_guess(block):
    for k in ["中超","亚冠","足协杯","意甲","欧冠","欧联","意大利杯","意超杯","友谊赛","热身赛","世俱杯"]:
        if k in (block or ""): return k
    return ""

def add_unique(rows, item):
    key = (item["date"], item["time"], item["team"], item["opponent"], item.get("competition",""))
    if key not in {(r["date"], r["time"], r["team"], r["opponent"], r.get("competition","")) for r in rows}:
        rows.append(item)

# ---------- 懂球帝 ----------
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

def parse_dqd_team(html, team_name):
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = []
    for i, ln in enumerate(lines):
        if (DATE_YMD.search(ln) or DATE_MD.search(ln)) and team_name in " ".join(lines[i:i+5]):
            block = clean(" ".join(lines[i:i+8]))
            m_t = TIME_HM.search(block)
            hhmm = m_t.group(0) if m_t else "20:00"
            # 对手&主客
            opponent, venue = "", ""
            if " VS " in block:
                a,b = block.split(" VS ",1)
                opponent = clean(a if team_name in b else b)
            elif " vs " in block:
                a,b = block.split(" vs ",1)
                opponent = clean(a if team_name in b else b)
            else:
                segs = block.split(team_name)
                if len(segs)>=2:
                    right_tail = clean(segs[1].split(" ",1)[0])
                    left_tail  = clean(segs[0].split(" ")[-1] if segs[0] else "")
                    opponent   = right_tail or left_tail
            if not looks_like_team(opponent): continue
            d = norm_date_any(block, "2025")
            if not d: continue
            venue = "主场" if "主" in block and "客" not in block else ("客场" if "客" in block else "")
            add_unique(out, {
                "date": d, "time": hhmm,
                "competition": comp_guess(block),
                "round": re.search(r"(第?\d+轮|1/8决赛|1/4决赛|半决赛|决赛)", block).group(0) if re.search(r"(第?\d+轮|1/8决赛|1/4决赛|半决赛|决赛)", block) else "",
                "opponent": opponent, "venue": venue, "team": team_name
            })
    out.sort(key=lambda x:(x["date"], x["time"]))
    return out

# ---------- 直播吧 ----------
def parse_zhibo8(html, team_name):
    """
    结构化优先 + 文本回退
    """
    out = []
    soup = BeautifulSoup(html, "lxml")

    def push(date_str, time_str, comp, round_str, opp, venue):
        d = norm_date_any(date_str, "2025")
        if not d: return
        hhmm = time_str if TIME_HM.search(time_str or "") else "20:00"
        opp = clean(opp)
        if not looks_like_team(opp): return
        add_unique(out, {
            "date": d, "time": hhmm,
            "competition": comp_guess(comp or "") or comp_guess(round_str or ""),
            "round": round_str or "",
            "opponent": opp, "venue": venue or "",
            "team": team_name
        })

    def infer_venue(text):
        t = text or ""
        if "主" in t and "客" not in t: return "主场"
        if "客" in t: return "客场"
        return ""

    # 结构化容器
    containers = []
    containers += soup.select(".record-list, .record_list, .recordlist")
    containers += soup.select(".box, .list_box, .match-box, .module, .list")
    containers = containers or [soup]  # 至少跑一次

    for box in containers:
        # 日期来源：box标题/日期节点 或 每个 li 自带
        date_in_box = ""
        for dtag in box.select("h3,h4,.date,.title,.time-title"):
            txt = clean(dtag.get_text(" "))
            if DATE_YMD.search(txt) or DATE_MD.search(txt):
                date_in_box = txt
                break

        lis = box.select("li") or []
        for li in lis:
            text = clean(li.get_text(" "))
            if team_name not in text: 
                continue

            date_str = ""
            if DATE_YMD.search(text) or DATE_MD.search(text):
                date_str = text
            else:
                date_str = date_in_box

            m_t = TIME_HM.search(text)
            hhmm = m_t.group(0) if m_t else "20:00"

            comp = ""
            for k in ["中超","亚冠","足协杯","意甲","欧冠","欧联","意大利杯","意超杯","友谊赛","热身赛","世俱杯"]:
                if k in text:
                    comp = k
                    break
            m_round = re.search(r"(第?\d+轮|1/8决赛|1/4决赛|半决赛|决赛)", text)
            round_str = m_round.group(0) if m_round else ""

            # 对手
            opp = ""
            if " VS " in text:
                a,b = text.split(" VS ",1)
                opp = a if team_name in b else b
            elif " vs " in text:
                a,b = text.split(" vs ",1)
                opp = a if team_name in b else b
            else:
                segs = text.split(team_name)
                if len(segs)>=2:
                    right_tail = clean(segs[1].split(" ",1)[0])
                    left_tail  = clean(segs[0].split(" ")[-1] if segs[0] else "")
                    opp = right_tail or left_tail
            venue = infer_venue(text)

            push(date_str, hhmm, comp, round_str, opp, venue)

    # 文本回退
    if not out:
        text = soup.get_text("\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for i, ln in enumerate(lines):
            if team_name in ln and (DATE_YMD.search(ln) or DATE_MD.search(ln)):
                block = clean(" ".join(lines[max(0,i-2): i+6]))
                m_t = TIME_HM.search(block)
                hhmm = m_t.group(0) if m_t else "20:00"
                d = norm_date_any(block, "2025")
                if not d: continue
                opp = ""
                if " VS " in block:
                    a,b = block.split(" VS ",1)
                    opp = a if team_name in b else b
                elif " vs " in block:
                    a,b = block.split(" vs ",1)
                    opp = a if team_name in b else b
                else:
                    segs = block.split(team_name)
                    if len(segs)>=2:
                        right_tail = clean(segs[1].split(" ",1)[0])
                        left_tail  = clean(segs[0].split(" ")[-1] if segs[0] else "")
                        opp = right_tail or left_tail
                venue = "主场" if "主" in block and "客" not in block else ("客场" if "客" in block else "")
                add_unique(out, {
                    "date": d, "time": hhmm,
                    "competition": comp_guess(block), "round": "",
                    "opponent": opp, "venue": venue, "team": team_name
                })

    out.sort(key=lambda x:(x["date"], x["time"]))
    return out

# ---------- 主流程 ----------
def main():
    ensure_dir("data")
    ensure_dir(DBG_DIR)

    all_rows = []

    # 1) 直播吧兜底
    for team in TARGET_TEAMS:
        zb_rows = []
        for u in ZB_PAGES:
            lab = f"zb8_{team}_{u.split('/')[-2] if u.endswith('/') else u.split('/')[-1].split('.')[0]}"
            html = safe_get(u, label=lab)
            if not html: continue
            rows = parse_zhibo8(html, team)
            zb_rows += rows
        for r in zb_rows:
            add_unique(all_rows, r)
        print(f"[ZB] {team} 抓到 {len(zb_rows)} 条（去重前）")

    # 2) 懂球帝补充
    for team in TARGET_TEAMS:
        tid = find_team_id(team)
        if not tid:
            print(f"[DQD] 未找到 {team} 的ID，跳过")
            continue
        html = safe_get(f"https://www.dongqiudi.com/team/{tid}.html", label=f"dqd_team_{team}")
        if not html: 
            continue
        rows = parse_dqd_team(html, team)
        for r in rows:
            add_unique(all_rows, r)
        print(f"[DQD] {team} 补充 {len(rows)} 条")

    # 3) 手动种子合并（解决未来赛季页面未发布导致空表）
    seed25 = load_json(SEED_2025)
    seed26 = load_json(SEED_2026)
    for r in seed25 + seed26:
        # 基本字段清理与校验
        if not r or "date" not in r or "team" not in r or "opponent" not in r:
            continue
        r["date"] = norm_date_any(r["date"], "2025")
        r["time"] = r.get("time") or "20:00"
        r["competition"] = r.get("competition") or ""
        r["round"] = r.get("round") or ""
        r["venue"] = r.get("venue") or ""
        if r["date"] and looks_like_team(r["opponent"]):
            add_unique(all_rows, r)
    if seed25 or seed26:
        print(f"[SEED] 合并手动种子：2025={len(seed25)}，2026={len(seed26)}")

    # 4) 只保留 2025/2026
    y25 = [r for r in all_rows if r["date"].startswith("2025-")]
    y26 = [r for r in all_rows if r["date"].startswith("2026-")]

    with open(OUT_2025, "w", encoding="utf-8") as f:
        json.dump(sorted(y25, key=lambda x:(x["date"], x["time"], x["team"])), f, ensure_ascii=False, indent=2)
    with open(OUT_2026, "w", encoding="utf-8") as f:
        json.dump(sorted(y26, key=lambda x:(x["date"], x["time"], x["team"])), f, ensure_ascii=False, indent=2)

    print(f"[DONE] 最终输出：2025={len(y25)} 条，2026={len(y26)} 条；原始页面见 {DBG_DIR}/")

if __name__ == "__main__":
    main()
    
