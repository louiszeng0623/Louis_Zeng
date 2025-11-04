# -*- coding: utf-8 -*-
"""
抓取【国际米兰 + 成都蓉城】赛程 -> data/schedule_2025.json
字段: date, time, opponent, venue(主/客), competition, round
策略:
- 用 r.jina.ai 读取“只读副本”绕过JS
- 懂球帝: 直接解析球队页(国际米兰ID已知: 50001042)
- 成都蓉城: 先走懂球帝球队/赛程页; 若失败, 兜底走直播吧联赛页+队名过滤
"""
import os, re, json, time
import requests
from bs4 import BeautifulSoup

OUT_PATH = "data/schedule_2025.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

def fetch(url, retry=3, sleep=1.5):
    # 用 r.jina.ai 读只读副本，稳定拿到纯文本/HTML
    if not url.startswith("https://r.jina.ai/http"):
        url = "https://r.jina.ai/http://" + url.replace("https://", "").replace("http://", "")
    last_err = None
    for _ in range(retry):
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.status_code == 200 and len(r.text) > 200:
                return r.text
        except Exception as e:
            last_err = e
        time.sleep(sleep)
    raise RuntimeError(f"fetch failed: {url} -> {last_err}")

def parse_dqd_team_html(html_text, team_cn_name):
    """从懂球帝球队页解析赛程（尽量通用，容错写法）"""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text("\n")
    # 粗暴找 “赛程/联赛/杯赛/日期样式” 的行
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    items = []
    date_pat = re.compile(r"(\d{1,2}[-/]\d{1,2}|\d{4}[-/]\d{1,2}[-/]\d{1,2})")
    time_pat = re.compile(r"(\d{1,2}:\d{2})")
    # 逐行扫描，遇到含日期+比赛双方的段落就抓
    for i, ln in enumerate(lines):
        if date_pat.search(ln):
            block = " ".join(lines[i:i+6])
            # 取出比赛双方（含 VS）
            if "VS" in block or "vs" in block or "－" in block or "-" in block:
                # 赛事
                comp = ""
                for key in ["中超", "亚冠", "足协杯", "意甲", "欧冠", "意大利杯", "意超杯", "友谊赛"]:
                    if key in block:
                        comp = key; break
                # 时间
                m_t = time_pat.search(block)
                hhmm = m_t.group(1) if m_t else ""
                # 主客与对手
                # 假设格式类似 “A VS B” ，判断哪边是本队
                who = ""
                if " VS " in block:
                    parts = block.split(" VS ")
                elif " vs " in block:
                    parts = block.split(" vs ")
                else:
                    parts = re.split(r"[－\-]", block, maxsplit=1)
                if len(parts) == 2:
                    left, right = parts[0], parts[1]
                    if team_cn_name in left and team_cn_name not in right:
                        venue, opponent = "主", re.sub(r"\W+", "", right)
                    elif team_cn_name in right and team_cn_name not in left:
                        venue, opponent = "客", re.sub(r"\W+", "", left)
                    else:
                        # 不确定时跳过
                        continue
                else:
                    continue
                # 日期
                m_d = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})|(\d{1,2}[-/]\d{1,2})", block)
                date = m_d.group(0) if m_d else ""
                if date and len(date) <= 5:
                    # 没有年份就补 2025
                    date = f"2025-{date.replace('/', '-')}"
                # 轮次
                m_r = re.search(r"(第?\d+轮|联赛阶段|1/8决赛|半决赛|决赛|第?\d+场)", block)
                round_txt = m_r.group(0) if m_r else ""
                items.append({
                    "date": date,
                    "time": hhmm,
                    "opponent": opponent,
                    "venue": venue,
                    "competition": comp,
                    "round": round_txt
                })
    # 去重
    uniq = []
    seen = set()
    for it in items:
        key = (it["date"], it["time"], it["opponent"], it["competition"])
        if key not in seen and it["date"]:
            uniq.append(it); seen.add(key)
    return uniq

def parse_zhibo8_league_filter(html_text, team_keywords):
    """从直播吧联赛页抓所有比赛，按队名关键词过滤"""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text("\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = []
    for i, ln in enumerate(lines):
        if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", ln) or re.search(r"\d{1,2}[-/]\d{1,2}", ln):
            block = " ".join(lines[i:i+5])
            if any(k in block for k in team_keywords) and ("VS" in block or "vs" in block or "-" in block):
                # 抽取
                m_d = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})|(\d{1,2}[-/]\d{1,2})", block)
                date = m_d.group(0).replace("/", "-") if m_d else ""
                if date and len(date) <= 5:
                    date = f"2025-{date}"
                m_t = re.search(r"\d{1,2}:\d{2}", block)
                hhmm = m_t.group(0) if m_t else ""
                # 对手&主客
                parts = re.split(r"\s+VS\s+|\s+vs\s+|－|\-", block)
                if len(parts) >= 2:
                    left, right = parts[0], parts[1]
                    if any(k in left for k in team_keywords):
                        venue, opponent = "主", re.sub(r"\W+", "", right)
                    elif any(k in right for k in team_keywords):
                        venue, opponent = "客", re.sub(r"\W+", "", left)
                    else:
                        continue
                else:
                    continue
                # 赛事/轮次（从邻近行扒一点提示）
                comp = ""
                for key in ["中超", "亚冠", "足协杯", "意甲", "欧冠", "意大利杯", "意超杯"]:
                    if key in block:
                        comp = key; break
                m_r = re.search(r"(第?\d+轮|联赛阶段|1/8决赛|半决赛|决赛|第?\d+场)", block)
                out.append({
                    "date": date, "time": hhmm,
                    "opponent": opponent, "venue": venue,
                    "competition": comp, "round": m_r.group(0) if m_r else ""
                })
    # 去重
    uniq, seen = [], set()
    for it in out:
        key = (it["date"], it["time"], it["opponent"], it["competition"])
        if key not in seen and it["date"]:
            uniq.append(it); seen.add(key)
    return uniq

def main():
    all_rows = []

    # 1) 国际米兰（懂球帝球队页，ID已知）
    inter_html = fetch("https://www.dongqiudi.com/team/50001042.html")
    inter_rows = parse_dqd_team_html(inter_html, "国际米兰")
    for r in inter_rows:
        all_rows.append({**r, "team": "国际米兰"})

    # 2) 成都蓉城（优先懂球帝球队/赛程页，如果你找到固定ID可直接替换；否则走联赛页过滤）
    try:
        # 尝试用懂球帝“成都蓉城”球队页（如果你知道ID，替换下面URL）
        # 示例：team/5xxxxxxx.html
        chengdu_html = fetch("https://www.dongqiudi.com/search?query=%E6%88%90%E9%83%BD%E8%93%89%E5%9F%8E")
        cd_rows = parse_dqd_team_html(chengdu_html, "成都蓉城")
    except Exception:
        cd_rows = []

    if len(cd_rows) < 5:
        # 兜底：直播吧联赛页，按“成都蓉城”关键字过滤
        # 这里给两个常见入口，你任选其一更新：
        # 中超赛程页（示例）：https://www.zhibo8.com/zuqiu/zhongchao/ （或具体赛季页）
        # 亚冠赛程页（示例）：https://www.zhibo8.com/zuqiu/yaguan/
        for league_url in [
            "https://www.zhibo8.com/zuqiu/zhongchao/",
            "https://www.zhibo8.com/zuqiu/yaguan/",
            "https://www.zhibo8.com/schedule/finish_more.htm"
        ]:
            try:
                html = fetch(league_url)
                cd_rows += parse_zhibo8_league_filter(html, ["成都蓉城", "成都"])
            except Exception:
                pass
    for r in cd_rows:
        all_rows.append({**r, "team": "成都蓉城"})

    # 3) 只保留 2025 年
    all_rows = [x for x in all_rows if x["date"].startswith("2025-")]

    # 4) 排序并输出
    all_rows.sort(key=lambda x: (x["date"], x["time"], x["team"]))
    os.makedirs("data", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)

    # Debug: 在 Actions 日志里打印前10条
    print("[OK] total:", len(all_rows))
    for it in all_rows[:10]:
        print(it)

if __name__ == "__main__":
    main()
    
