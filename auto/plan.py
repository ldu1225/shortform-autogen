"""채널 무인 일일 제작 — 06:00 실행. 수집 → 소재 2개 선정(Gemini+구글검색) → 공식 영상 확보 → 컷 선정(Gemini 비전)
→ 스펙·캡션 작성(Gemini) → 렌더·QA(실패 시 자동 보정 1회) → runs/날짜/outbox/ 에 릴스 2개 + 캡션.
08:00 send.py 가 outbox 를 메일로 보낸다. 사람 개입 없음.
사용: python3 -I auto/plan.py [--date YYYY-MM-DD] [--skip-collect]
ponytail: 소재 후보가 모자라면 그날은 1개만 보낸다(억지로 채우지 않음).
"""
import argparse
import base64
import datetime as dt
import json
import math
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "auto"))
import vx  # noqa: E402

PY = str(ROOT / ".venv/bin/python")
YTDLP = str(ROOT / ".venv/bin/yt-dlp")
COOKIES = ROOT / "cookies.txt"  # 10/22: GCE IP 는 유튜브 봇 차단("Sign in to confirm") → 쿠키 파일이 있으면 모든 yt-dlp 호출에 붙인다
YTDLP_OPTS = ["--cookies", str(COOKIES)] if COOKIES.exists() else []
WRITER = "gemini-3.1-pro-preview"


def _env(k, d=""):
    for l in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
        if l.startswith(k + "="):
            return l.split("=", 1)[1].strip()
    return d


CHANNEL = _env("CHANNEL_NAME", "채널")   # 채널 표시명(프롬프트·메일 제목)
HANDLE = _env("HANDLE", "@channel")      # 화면 핸들·QA 검사
VISION = "gemini-3.8-flash"  # 텍스트 감지 같은 단순 비전은 Flash(비용 절감). 컷 선정은 WRITER 유지
# 2026-10-18 사용자: 카테고리 제한 없음(옷·신발·가전·차·시계·뷰티… 신상이면 전부). 레인 로테이션 폐기, 카테고리는 색 힌트로만.
CATS = {"tech": "#FF5A36", "fashion": "#FF4F8B", "sneakers": "#FFE14D", "home": "#00C96B", "beauty": "#FF7AB6", "mobility": "#3D8BFF",
        "outdoor": "#FFB21E", "watch": "#B86BFF", "toy": "#FF5A36", "food": "#FFB21E", "pet": "#FF4F8B", "golf": "#3D8BFF", "other": "#FF5A36"}
PALETTE = ["#FF5A36", "#3D8BFF", "#FFB21E", "#FF4F8B", "#00D4FF", "#00C96B", "#B86BFF", "#FFE14D"]
THEMES = ["dark", "tint", "neon"]


def vivid(hex_, seed=""):
    """회색·어두운 accent 는 글씨가 안 보임(2026-10-18 DJI 릴스 #1C1C1C 사고, 사용자: 회색 쓰지 마) → 채도·밝기 낮으면 팔레트로 교체."""
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(hex_ or "").strip())
    if m:
        r, g, b = (int(m.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4))
        mx, mn = max(r, g, b), min(r, g, b)
        l = (mx + mn) / 2
        sat = 0 if mx == mn else (mx - mn) / (1 - abs(2 * l - 1))
        if l >= 0.42 and sat >= 0.45:
            return "#" + m.group(1).upper()
    return PALETTE[sum(map(ord, seed)) % len(PALETTE)]
VOICES = ["Leda", "Kore", "Aoede", "Zephyr", "Puck"]  # 릴스마다 돌려씀(2026-10-18 사용자: 목소리 5개 로테이션)
STYLE = "에너지 넘치는 한국어 테크 뉴스 쇼츠 내레이터. 빠르고 또렷하게, 숫자와 강조어에 힘을 주고, 진짜 놀란 듯 생생한 톤. 과장된 연기나 늘어지는 말투는 금지."


class Day:
    def __init__(self, date, slot=""):
        self.date = date
        self.name = date + slot
        self.dir = ROOT / "runs" / self.name
        self.src = ROOT / "sources" / date
        self.out = self.dir / "outbox"
        for d in (self.dir, self.src, self.out):
            d.mkdir(parents=True, exist_ok=True)
        self.report = {"date": date, "started": now(), "items": [], "errors": []}

    def log(self, msg):
        line = f"[{now()}] {msg}"
        print(line, flush=True)
        with open(self.dir / "auto.log", "a") as f:
            f.write(line + "\n")

    def save(self):
        (self.dir / "auto_report.json").write_text(json.dumps(self.report, ensure_ascii=False, indent=1))


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sh(cmd, timeout=2400, cwd=ROOT):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd))
    if r.returncode:
        raise RuntimeError(f"{Path(str(cmd[2] if len(cmd) > 2 else cmd[0])).name} 실패: {(r.stdout + r.stderr)[-600:]}")
    return r.stdout + r.stderr


def used_products(today):
    """이미 보낸 제품만(오늘 이전 auto_report). 렌더만 하고 안 보낸 건 다시 써도 된다."""
    names = ["Sony Walkman NW-ZX900/WM1AM3/WM1ZM3", "Apple iPhone Duo"]  # 2026-10-17 수동 제작분
    sent = ROOT / "track/sent.jsonl"
    if sent.exists():
        names += [json.loads(l)["product"] for l in sent.read_text().splitlines() if l.strip()]
    for rp in sorted((ROOT / "runs").glob("*/auto_report.json")):
        if rp.parent.name >= today:
            continue
        try:
            names += [i["product"] for i in json.loads(rp.read_text()).get("items", [])]
        except Exception:
            pass
    return sorted(set(names))


# ── 1. 소재 선정 ────────────────────────────────────────────────
def hot_txt(day: Day, n=45):
    """discover/hot.py 결과(유튜브 7일 인기 쇼츠·검색) → 프롬프트용 텍스트."""
    p = ROOT / "runs" / day.date / "hot.json"
    if not p.exists():
        return "(없음)"
    h = json.loads(p.read_text())
    rows = h.get("popular", []) + h.get("creators", []) + h.get("search", [])
    fresh = [r for r in rows if r.get("age_h") is not None and r["age_h"] <= 48]  # 10/19 사용자: 48시간 이내만
    unknown = [r for r in rows if r.get("age_h") is None]
    seen, out = set(), []
    for r in sorted(fresh, key=lambda r: -r.get("views", 0)) + sorted(unknown, key=lambda r: -r.get("views", 0))[:10]:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        age = f"{r['age_h']:.0f}시간 전" if r.get("age_h") is not None else "업로드 시각 미확인"
        out.append(f"- 조회 {r['views']:,} · {age} · {r.get('channel', '')} · {r['title'][:70]}")
        if len(out) >= n:
            break
    return "\n".join(out) or "(없음)"


def judge_wow(day: Day, items, kind="제품"):
    """독립 심사(Flash): 편집장 자기 점수는 후함(10/20: 타이멕스 시계·헤드폰도 7) → 보수적 기준으로 다시 매김."""
    if not items:
        return items
    lst = "\n".join(f"{i}. {it.get('brand', '')} {it.get('product', '')} — {it.get('wow_reason') or it.get('why_viral') or it.get('angle', '')}" for i, it in enumerate(items))
    prompt = f"""아래 {kind} 후보 각각에 '와우 점수'(1~10)를 매겨라. 심사 대상은 '뉴스를 안 보는 한국 일반인이 15초 영상만 보고 놀라는가'다. 점수는 짜게.
10 = 영상만 봐도 "헐" (날아가는 차, 빨래 개는 로봇, 세계 최초 투명 TV, 1억짜리 화장실, 손목 위 홀로그램)
8 = 신기해서 친구에게 보내고 싶음 (세계 최대/최소, 말도 안 되는 가격, 처음 보는 방식)
6 = 얼리어답터만 관심 (성능 좋아진 신형, 새로운 폼팩터지만 설명 필요)
4 = 후속작·스펙 업그레이드·콜라보·새 색상·한정판 (액션캠·이어폰·헤드폰·보조배터리·시계·운동화·노트북·폰 후속작은 반전이 없으면 여기)
2 = 주변기기·케이블·식품·소품
후보:
{lst}
JSON 배열로만: [{{"i": 번호, "wow": 점수, "why": "한 줄"}}, ...]"""
    try:
        text, _ = vx.gemini(prompt, model=VISION, timeout=180)
        scores = {int(s["i"]): (int(s["wow"]), s.get("why", "")) for s in vx.json_from(text)}
    except Exception as e:
        day.log(f"  와우 심사 실패(편집장 점수 사용): {str(e)[:100]}")
        return items
    for i, it in enumerate(items):
        it["wow_self"] = it.get("wow")
        it["wow"], it["wow_judge"] = scores.get(i, (int(it.get("wow") or 0), ""))
    day.log("  와우 심사: " + " / ".join(f"{it.get('brand', '')} {it.get('product', '')} {it.get('wow_self')}→{it['wow']}" for it in items))
    return items


def pick(day: Day, window_h=48, exclude=()):
    dd = ROOT / "runs" / day.date  # 수집 결과는 슬롯 없는 날짜 폴더에 있음(슬롯 배치가 뉴스 없이 돌던 버그 수정, 10/18)
    news = json.loads((dd / "news.json").read_text()) if (dd / "news.json").exists() else []
    cand = json.loads((dd / "candidates.json").read_text()).get("picked", []) if (dd / "candidates.json").exists() else []
    news_txt = "\n".join(f"- ({n['hours']}h, {n['source']}) {n['title']}" for n in news[:60])
    cand_txt = "\n".join(f"- {c['brand']}: {c['title']} ({c['hours']}h, 조회 {c['views']:,}{', 광고의심' if c.get('ad') else ''}{', 재탕의심' if c.get('rerun') else ''})" for c in cand)
    prompt = f"""너는 한국 인스타 릴스·유튜브 쇼츠 채널 '{CHANNEL}({HANDLE})'의 편집장이다. 채널 정체성: "세상에 갓 나온 것을 얼리어답터에게 가장 먼저".
카테고리 제한 없음 — 옷·신발·가전·IT·자동차·시계·뷰티·리빙·캠핑·골프·장난감·식음료 한정판 등 '물건'이면 전부. 오늘은 {day.date}.
오늘 올릴 릴스 소재 후보를 8개 골라 우선순위대로 JSON 배열로만 답하라. 반드시 구글 검색으로 출시일·가격·공식 영상·화제성을 확인하라.
시청자: 한국 20~40대 일반 대중. 보자마자 "뭐? 진짜?" 소리가 나와야 한다(10/20 사용자: "진짜 사람들이 와우하게, 대중을 터치하는 신기하고 새로운 것").
**와우 점수(wow, 1~10)가 선정의 핵심이다.** 10 = 처음 보는 것·불가능해 보이는 것·세계 최초/최대/최소/최고가·누구나 1초에 이해하는 물건(날아가는 차, 집안일 하는 로봇, 1억짜리 화장실, 종이처럼 접히는 TV). 7 = 신기하지만 설명이 필요. 5 이하 = 스펙 업그레이드, 시계·의류·신발 콜라보, 케이블·마우스패드·주변기기, 식품, 색상 추가. **7점 미만은 목록에서 빼라.** 와우가 없으면 차라리 후보를 적게 내라.

선정 규칙(어기면 탈락):
1. **최근 {window_h}시간** 안에 처음 발표·출시·발매·사전예약이 시작됐거나 {window_h}시간 안에 유튜브·뉴스에서 터진 '물건'만. 후보가 4개 미만일 때만 {window_h * 2}시간까지 허용하고 그 항목엔 "older": true 를 표시. 오래된 제품의 새 영상·새 기사는 탈락.
2. 지금 가장 화제인 것 우선. 근거: 아래 '유튜브 48시간 인기' 목록(경과 시간 표시됨), 뉴스에 반복 등장, 구글 검색 결과의 양·최신성. 해외든 국내든 터지고 있으면 OK.
   화제성이 비슷하면 가격이 비싼 것 > 한국에서 아는 브랜드 > 보기에 신기한 것 순.
3. 가격이 공개돼 있으면 좋다. 와우 8점 이상(로봇·탈것·세계 최초·연구 성과 등)이면 가격 미공개도 허용하고 price 에 '미공개'.
4. 그 물건을 만든 주체(브랜드·제조사·연구기관·대학·스타트업, 또는 공식 리테일·자회사) 유튜브 채널에 그 물건 영상(12초 이상)이 실제로 있어야 한다 — 검색으로 찾아 official_video_url 에 넣어라. 리뷰어·언박싱·매체 채널 영상은 안 됨. 못 찾으면 탈락. brand 에는 그 채널 이름이 들어가게 써라(예: "UCLA Engineering", "Unitree").
   와우 소재가 잘 나오는 곳: 휴머노이드·가사·배달 로봇, 플라잉카·eVTOL·초고속 탈것, 투명·롤러블 디스플레이, 스마트안경·AR, 초대형·초소형·초고가·세계 최초, 접이식·3D 프린팅 집, 우주·드론, 신기한 생활 발명품.
5. 이미 다룬 제품 제외: {', '.join(list(used_products(day.date)) + list(exclude)) or '없음'}
6. 피할 것: 연예인 자체가 주제인 것, 영화·드라마·게임 타이틀, 소프트웨어만 있는 소식, 루머·유출, 건강·효능 주장이 필요한 것(건기식·의료기기), 성인용품, 담배·주류.
7. 8개의 카테고리가 겹치지 않게(같은 카테고리 최대 2개). 중국 내수 전용·무명 브랜드·PC 부품·케이블·마우스패드·식품 같은 소품은 후순위.
8. **영상 확보 가능성**이 선정의 절반이다: 아래 '브랜드 공식 유튜브 최근 업로드' 목록에 있는 제품은 영상이 이미 있으니 최우선. 공식 유튜브가 활발한 브랜드(애플·삼성·소니·DJI·인스타360·고프로·나이키·아디다스·뉴발란스·테슬라·현대·기아·BMW·벤츠·포르쉐·LG·샤오미·구글·메타·다이슨·로보락·가민·보스·캐논·니콘·레고 등)를 우선. 공식 영상을 못 찾겠으면 그 후보는 아예 빼라.

참고 — 유튜브 48시간 인기(쇼츠 채널·검색, 조회수순, 경과 시간 포함). 여기 나온 제품·키워드는 화제성 가산점:
{hot_txt(day)}

참고 — 매체 RSS 신제품 기사(48시간):
{news_txt}

참고 — 브랜드 공식 유튜브 최근 업로드(재탕·광고가 많으니 출시일 꼭 확인):
{cand_txt}

각 항목 형식:
{{"product": "정확한 제품명(영문)", "product_ko": "한국어 표기", "brand": "브랜드",
 "category": "tech|fashion|sneakers|home|beauty|mobility|outdoor|watch|toy|food|pet|golf|other",
 "wow": 1~10, "wow_reason": "왜 사람들이 '뭐? 진짜?' 할지 한 줄",
 "hot_reason": "왜 지금 화제인지 한 줄(근거: 조회수·기사 수·검색량)",
 "announced": "YYYY-MM-DD", "announced_url": "발표일 근거 기사 URL(아래 뉴스 목록이나 검색 결과. 기억으로 쓰지 말 것 — 10/20 DJI 오즈모 액션 6 은 1년 전 제품인데 어제 발표로 적음)", "price": "대표 가격(통화 포함)", "korea": "한국 출시·가격 정보 또는 '미확인'",
 "facts": [{{"claim": "숫자가 들어간 사실 한 문장(가격·출시일·스펙·수량). 원화 환산 금지 — 원화는 한국 공식 가격일 때만", "url": "기사 원문 URL(도메인만 쓰지 말 것)"}}, ... 5~8개],
 "angle": "왜 사람들이 멈춰서 볼지 한 줄(숫자 훅)", "youtube_query": "공식 영상 검색어(영문)",
 "related_queries": ["관련 공식 영상 검색어 2~3개(영문) — 전작 모델명, 브랜드 발표 행사·키노트, 같은 라인업 다른 제품, 제조·공장 영상 등. 한 토픽을 여러 영상으로 짜깁기하기 위함"],
 "official_video_url": "https://www.youtube.com/watch?v=... (브랜드 공식 채널)"}}"""
    text, srcs = vx.gemini(prompt, model=WRITER, search=True)
    items = judge_wow(day, vx.json_from(text))
    weak = [i for i in items if int(i.get("wow") or 0) < 7]
    if weak:
        day.log("  와우 7점 미만 제외: " + " / ".join(f"{i.get('brand')} {i.get('product')}({i.get('wow')})" for i in weak))
    strong = [i for i in items if int(i.get("wow") or 0) >= 7]
    if not strong and items:  # 전부 약하면 6점만 살려서 1편은 만든다(메일에 '와우 약함' 표시)
        strong = [i for i in items if int(i.get("wow") or 0) >= 6][:2]
        for i in strong:
            i["wow_weak"] = True
        day.log(f"  와우 7+ 없음 → 6점 {len(strong)}개로 진행")
    items = strong
    (day.dir / "auto_pick.json").write_text(json.dumps({"items": items, "excluded": weak, "grounding": srcs}, ensure_ascii=False, indent=1))
    day.log(f"소재 후보 {len(items)}개: " + " / ".join(f"{i['brand']} {i['product']}({i.get('announced')})" for i in items))
    return heat_rank(day, items)


def heat_rank(day: Day, items):
    """유튜브 '오늘 · 조회수순' 검색 상위 8개 조회수 합 = 화제성(10/19 사용자: 48시간 이내). '이번 주' 합은 0.2 가중 보조. 편집장 순위와 섞어 재정렬."""
    import urllib.parse
    def views(q, sp):
        out = subprocess.run([YTDLP, *YTDLP_OPTS, "--no-warnings", "--socket-timeout", "20", "--flat-playlist", "--playlist-end", "8", "--print", "%(view_count)s",
                              f"https://www.youtube.com/results?search_query={q}&sp={sp}"], capture_output=True, text=True, timeout=120).stdout
        return sum(int(x) for x in out.split() if x.isdigit())
    for rank, it in enumerate(items):
        q = urllib.parse.quote(f"{it['brand']} {it['product']}")
        today, week = views(q, "CAMSBAgCEAE%253D"), views(q, "CAMSBAgDEAE%253D")
        it["heat_views"], it["heat_week"] = today, week
        it["heat_score"] = round(math.log10(today + 0.2 * week + 1) + (len(items) - rank) * 0.35 - (1.5 if it.get("older") else 0) + 0.6 * int(it.get("wow") or 0), 2)  # 와우가 화제성보다 무겁다(10/20)
    items.sort(key=lambda i: -i["heat_score"])
    day.log("화제성: " + " / ".join(f"{i['brand']} {i['product']} {i['heat_views']:,}({i['heat_score']})" for i in items))
    return items


# ── 1b. 해외 바이럴 레인 (2026-10-18 사용자: 해외 바이럴 영상도 재가공, 하루 1편) ─────────────
def pick_viral(day: Day):
    p = ROOT / "runs" / day.date / "hot.json"
    h = json.loads(p.read_text()) if p.exists() else {}
    rows, seen = [], set()
    for r in h.get("popular", []) + h.get("viral", []) + h.get("creators", []) + h.get("search", []):
        if r.get("age_h") is not None and r["age_h"] > 72:
            continue  # 차트는 72시간까지(10/20: 인기 차트 영상은 보통 2~3일 누적)
        if r.get("views", 0) >= 300_000 and r["id"] not in seen and not re.search(r"[가-힣]", r.get("title", "")):  # 48h 기준 30만+(10/19)
            seen.add(r["id"]); rows.append(r)
    rows.sort(key=lambda r: -r["views"])
    if not rows:
        raise RuntimeError("바이럴 후보 없음 — runs/날짜/hot.json 이 비었거나 없음(자정 넘긴 테스트는 --date 명시)")
    def shape(r):
        w, hh = r.get("width"), r.get("height")
        return ("가로" if w > hh else "세로쇼츠") if (w and hh) else ("세로쇼츠" if (r.get("duration") or 999) <= 60 else "?")
    txt = "\n".join(f"- id={r['id']} · 조회 {r['views']:,} · {r.get('channel') or r.get('from', '')} · {int(r['duration']) if r.get('duration') else '?'}초 · {shape(r)} · 업로드 {r.get('upload_date') or '?'} · "
                    f"{'CC 라이선스' if 'Creative' in str(r.get('license')) else '표준'} · {r['title'][:80]}" for r in rows[:90])
    prompt = f"""너는 한국 릴스·쇼츠 채널 '{CHANNEL}({HANDLE})'의 편집장이다. 오늘은 {day.date}. 아래는 유튜브에서 지금 터지는 해외 영상 목록(이번 주 조회수순)이다.
이 중 한국 시청자에게 "세상에 이런 게 갓 나왔다"로 소개할 만한 영상을 6개 골라 우선순위대로 JSON 배열로만 답하라. 목록 앞부분의 '인기차트'는 유튜브 공식 인기 차트(국가·카테고리별)라 지금 가장 터지는 영상들이다. 구글 검색으로 영상 속 물건·기술의 정체·가격·제작사·사실을 확인하라.
조건(어기면 탈락):
0. **와우(1~10)**: 보자마자 "뭐? 진짜?" 하는 것만(날아가는 것, 로봇이 사람 일 하는 것, 세계 최초·최대·최고가, 불가능해 보이는 장면). 7점 미만은 빼라. 출력에 "wow", "wow_reason" 포함.
1. 주인공이 '것'이어야 한다 — 물건·기술·탈것·로봇·가젯·발명·초대형/초고가 물건. 사람 얼굴 토크·프랭크·챌린지·음악·영화·스포츠·정치·사고·동물·먹방은 제외.
2. 한국어 채널·한국 소재 제외(한국 시청자가 이미 봄). 조회 30만 이상(48시간 안에 이 정도면 터지는 중), **업로드 48시간 이내**(목록이 이미 그렇게 걸러짐), 영상 길이 10분 이하.
3. '가로' 장편(1~10분, 리뷰·시승·공개 행사) 우선. '세로쇼츠'는 화면 전체에 자막·문구가 박혀 있어 재가공이 거의 불가능하니 가로 영상이 하나라도 있으면 세로는 고르지 마라. 제품이 크게 또렷이 보이는 촬영 영상 우선.
4. 이미 다룬 것 제외: {', '.join(used_products(day.date)) or '없음'}
5. **제작사·브랜드·연구기관 공식 채널 영상을 반드시 찾아 official_video_url 에 넣어라.** 세로 쇼츠는 화면에 자막이 박혀 있어 그 영상만으로는 못 만든다(10/20: 매니큐어·플라잉카·아이스해머 전부 폐기). 공식 영상이 없는 세로 쇼츠 소재는 아예 빼라. 가로 장편(리뷰·시승·공개 행사)은 그 영상만으로도 가능.

목록:
{txt}

각 항목 형식:
{{"product": "영문 주제(물건·기술명)", "product_ko": "한국어 표기", "brand": "제작사·브랜드(모르면 채널명)", "category": "tech|fashion|sneakers|home|beauty|mobility|outdoor|watch|toy|food|pet|golf|other",
 "video_id": "유튜브 id", "channel": "채널명", "views": 조회수(숫자), "why_viral": "왜 터졌는지 한 줄", "price": "가격(통화 포함) 또는 '미공개'",
 "facts": [{{"claim": "숫자가 들어간 사실 한 문장(조회수·업로드일·가격·크기·수치)", "url": "출처 URL(조회수·업로드일은 해당 유튜브 URL)"}}, ... 4~7개],
 "angle": "한국 시청자가 멈춰 볼 이유 한 줄", "youtube_query": "공식 영상 검색어(영문)", "related_queries": ["관련 공식 영상 검색어 2~3개(영문): 전작·행사·같은 라인업"], "official_video_url": "https://www.youtube.com/watch?v=... 또는 빈 문자열"}}"""
    text, srcs = vx.gemini(prompt, model=WRITER, search=True)
    items = vx.json_from(text)
    by_id = {r["id"]: r for r in rows}
    kept = []
    items = [i for i in judge_wow(day, items, "바이럴") if int(i.get("wow") or 0) >= 7]
    for it in items:
        m = re.search(r"([\w-]{11})", str(it.get("video_id", "")))
        vid = m.group(1) if m else ""
        if vid not in by_id:  # 목록 밖 id = 지어낸 것(10/19 자정 테스트에서 3개 전부 가짜 id)
            day.log(f"  바이럴 후보 제외(목록 밖 id): {it.get('product')} {vid}")
            continue
        it.update({"video_id": vid, "kind": "viral", "channel": it.get("channel") or by_id[vid].get("channel", ""), "views": by_id[vid]["views"]})
        it.setdefault("brand", it.get("channel", ""))
        kept.append(it)
    items = kept
    (day.dir / "auto_pick_viral.json").write_text(json.dumps({"items": items, "grounding": srcs}, ensure_ascii=False, indent=1))
    day.log(f"바이럴 후보 {len(items)}개: " + " / ".join(f"{i.get('channel')} {i['product']}({i.get('views')})" for i in items))
    return items


def viral_videos(day: Day, item):
    """바이럴 영상 본편 다운로드(세로도 허용) + 있으면 브랜드 공식 영상 1~2개 추가."""
    vid = str(item.get("video_id", "")).strip()
    m = re.search(r"([\w-]{11})", vid)
    if not m:
        return []
    vid = m.group(1)
    meta = subprocess.run([YTDLP, *YTDLP_OPTS, "--no-warnings", "--skip-download", "--print", "%(duration)s\t%(channel)s\t%(view_count)s\t%(title)s\t%(upload_date)s",
                           f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True, timeout=120).stdout.strip().split("\t")
    if len(meta) < 5:
        return []
    f = day.src / f"{vid}.mp4"
    if not f.exists():
        subprocess.run([YTDLP, *YTDLP_OPTS, "-q", "--no-warnings", "-f", "bv*+ba/b", "-S", "res:1080,tbr", "--merge-output-format", "mp4", "-o", str(f), f"https://www.youtube.com/watch?v={vid}"], timeout=900)
    if not f.exists():
        return []
    wh = subprocess.run([YTDLP, *YTDLP_OPTS, "--no-warnings", "--skip-download", "--print", "%(width)s|%(height)s", f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True, timeout=120).stdout.strip().split("|")
    vertical = len(wh) == 2 and wh[0].isdigit() and wh[1].isdigit() and int(wh[0]) <= int(wh[1])
    vids = [{"id": vid, "channel": meta[1], "duration": float(meta[0]), "views": int(meta[2]) if meta[2].isdigit() else 0, "title": meta[3], "upload": meta[4], "file": str(f), "credit": True, "vertical": vertical}]
    if item.get("official_video_url") or item.get("youtube_query"):
        try:
            vids += [v for v in official_videos(day, item, need=2) if v["id"] != vid]
        except Exception as e:
            day.log(f"  공식 영상 추가 실패(무시): {str(e)[:120]}")
    if vertical and len(vids) == 1:  # 세로 쇼츠 하나뿐이면 자막 때문에 거의 실패 → 5분 컷 분석 전에 건너뜀(10/20)
        day.log("  세로 쇼츠뿐이고 공식 영상 없음 → 건너뜀")
        return []
    return vids


# ── 2. 공식 영상 확보 ───────────────────────────────────────────
def official_videos(day: Day, item, need=3):
    """한 토픽에 공식 영상 여러 개(메인 = 이 제품 영상, 맥락 = 전작·행사·같은 라인업·공정) 확보. 10/19 사용자: '관련 영상 여러 개를 짜깁기하기로 했잖아'.
    메인은 45일 이내 필수, 맥락은 400일까지 허용. 전부 가로·브랜드 공식 채널."""
    known = {c["channel_id"] for c in json.loads((ROOT / "config/channels.json").read_text()).values() if c.get("channel_id")}
    fmt = "%(id)s\t%(channel_id)s\t%(channel)s\t%(duration)s\t%(view_count)s\t%(title)s"
    queries = [item["youtube_query"]] + [q for q in (item.get("related_queries") or []) if q][:3] + [f"{item['brand']} {item['product']}"]
    queries = list(dict.fromkeys(q.strip() for q in queries if q and q.strip()))
    rows = []  # (line, qi)
    url = item.get("official_video_url") or ""
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
    if m:  # 편집장이 찾아준 공식 영상을 맨 앞에
        meta = subprocess.run([YTDLP, *YTDLP_OPTS, "--no-warnings", "--skip-download", "--print", fmt, f"https://www.youtube.com/watch?v={m.group(1)}"],
                              capture_output=True, text=True, timeout=120).stdout
        rows += [(l, 0) for l in meta.splitlines()]
    for qi, q in enumerate(queries):
        out = subprocess.run([YTDLP, *YTDLP_OPTS, "--no-warnings", "--socket-timeout", "20", "--flat-playlist", "--print", fmt, f"ytsearch15:{q}"],
                             capture_output=True, text=True, timeout=180).stdout
        rows += [(l, qi) for l in out.splitlines()]
    brand = item["brand"].split()[0].lower()
    brand_keys = {k for k in (brand, brand.split("-")[0], brand.split("-")[-1]) if len(k) >= 4}  # "Mercedes-AMG" → mercedes (채널 'Mercedes-Benz' 매칭, 10/19)
    brand_keys |= {w for w in re.findall(r"[a-z0-9]+", item["brand"].lower()) if len(w) >= 4 and w not in ("the", "and", "with", "racing", "originals", "studio", "brand")}  # 10/20: "Xiaomi Redmi"→redmi, "Awake NY / The North Face"→north/face
    # 관련성: 제품명 토큰(괄호 제거, 브랜드 제외, 3자 이상)이 제목에 하나라도 있으면 OK (10/20: "Apple TV 4K (4th Generation)"·"ID. Cross" 가 전부 탈락한 버그)
    pname = re.sub(r"\(.*?\)", " ", item["product"].lower())
    toks = [w for w in re.findall(r"[a-z0-9]+", pname) if len(w) >= 3 and w not in brand_keys and w not in ("the", "and", "new", "series", "edition", "collection", "generation", "with", "pro", "max", "plus", "mini")]
    model_key = re.sub(r"[^a-z0-9]", "", pname)[-6:]
    n_off = n_rel = 0
    vids = {}
    for line, qi in rows:
        p = line.split("\t", 5)
        if len(p) < 6:
            continue
        vid, cid, ch, du, vc, title = p
        try:
            du = float(du)
        except ValueError:
            continue
        official = cid in known or any(k in ch.lower().replace(" ", "") for k in brand_keys)
        tl = re.sub(r"[^a-z0-9]", "", title.lower())
        relevant = (m and vid == m.group(1)) or any(t in tl for t in toks) or (len(model_key) >= 4 and model_key[:4] in tl)
        n_off += official; n_rel += official and relevant
        if official and 12 <= du <= 900 and vid not in vids:
            vids[vid] = {"id": vid, "channel": ch, "duration": du, "views": int(vc) if vc.isdigit() else 0, "title": title,
                         "role": "main" if relevant else "context", "pinned": bool(m and vid == m.group(1))}
    cand = sorted(vids.values(), key=lambda v: (not v["pinned"], v["role"] != "main", -v["views"]))
    day.log(f"  소스 검색: 결과 {len(rows)}줄 · 공식 {n_off} · 관련 {n_rel} · 토큰 {toks[:4]}")
    today = dt.date.fromisoformat(day.date)
    good, checked = [], 0
    for v in cand:
        if checked >= 12 or len(good) >= need:
            break
        if v["role"] == "context" and sum(1 for g in good if g["role"] == "main") == 0:
            continue  # 메인이 하나도 없으면 맥락만으로는 못 만든다
        checked += 1
        meta = subprocess.run([YTDLP, *YTDLP_OPTS, "--no-warnings", "--skip-download", "--print", "%(upload_date)s|%(width)s|%(height)s",
                               f"https://www.youtube.com/watch?v={v['id']}"], capture_output=True, text=True, timeout=120).stdout.strip().split("|")
        try:
            up = dt.datetime.strptime(meta[0], "%Y%m%d").date()
            w, h = int(meta[1]), int(meta[2])
        except Exception:
            continue
        age = (today - up).days
        if (age <= 45 if v["role"] == "main" else age <= 400):
            good.append({**v, "upload": str(up), "vertical": w <= h})
    good.sort(key=lambda v: (v["role"] != "main", v.get("vertical", False), -v["views"]))  # 가로 메인 우선, 세로는 뒤로
    if not any(g["role"] == "main" for g in good):
        return []
    for v in good:
        f = day.src / f"{v['id']}.mp4"
        if not f.exists():
            subprocess.run([YTDLP, *YTDLP_OPTS, "-q", "--no-warnings", "-f", "bv*+ba/b", "-S", "res:2160,tbr",
                            "--merge-output-format", "mp4", "-o", str(f), f"https://www.youtube.com/watch?v={v['id']}"], timeout=900)
        v["file"] = str(f) if f.exists() else None
    got = [v for v in good if v.get("file")]
    day.log(f"  소스 {len(got)}개 (메인 {sum(1 for v in got if v['role'] == 'main')}, 맥락 {sum(1 for v in got if v['role'] == 'context')}, 세로 {sum(1 for v in got if v.get('vertical'))}) — 검색어 {len(queries)}개")
    return got


def contact_sheet(video, out_jpg, step):
    """9:16 센터 크롭 타일. 타일 k = k*step 초. 10열."""
    sh(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf",
        f"fps=1/{step},crop=w='min(iw\\,ih*9/16)':h=ih:x='(iw-ow)/2':y=0,scale=108:192,tile=10x8:padding=4:color=white", "-frames:v", "1", "-q:v", "4", str(out_jpg)])


# ── 3. 컷 선정(비전) ────────────────────────────────────────────
def _pname(item):
    return f"{item['brand']} {item.get('product_ko') or item['product']} ({item.get('category', '')})" if item else "제품"


def choose_cuts(day: Day, vids, n_body, item=None):
    imgs, desc = [], []
    for i, v in enumerate(vids):
        step = max(1, int(v["duration"] // 80) + (1 if v["duration"] % 80 else 0))
        jpg = day.dir / f"auto_sheet_{v['id']}.jpg"
        contact_sheet(v["file"], jpg, step)
        imgs.append(base64.b64encode(jpg.read_bytes()).decode())
        role = "메인(이 제품 영상)" if v.get("role", "main") == "main" else "맥락(전작·행사·관련 영상 — 제품 자체가 아닐 수 있음, 자막 내용과 어긋나지 않는 장면만)"
        desc.append(f"영상{i} id={v['id']} [{role}] 길이 {v['duration']:.0f}초, 이미지{i}의 타일 k(0부터, 왼→오, 위→아래) = {step}*k 초 지점의 9:16 센터 크롭")
    prompt = f"""브랜드 공식 제품 영상의 9:16 센터 크롭 타일 시트들이다. 소개할 제품: {_pname(item)}.
영상에 다른 제품(트럭·다른 모델·주변 기기·소품)이 함께 나오면 그 장면은 제외 — 이 제품이 주인공으로 크게 보이는 타일만(10/18 테슬라 로드스터 영상에서 세미 트럭 정면을 고른 사고).
{chr(10).join(desc)}
세로 릴스용 컷을 골라라. 도입부 1컷(첫 화면 — 제품이 크고 또렷하게 보이는 가장 시선을 끄는 장면), 중반부 {n_body}컷(서로 다른 장면, 제품·사용 장면), 마지막 1컷(사람이 쓰는 장면 우선).
금지: 화면에 글자·자막·로고·모델명 텍스트가 보이는 타일, 검은 화면·페이드, 엔딩 카드, 피사체가 크롭 밖으로 잘린 타일. 마지막 8초 구간 금지.
영상이 2개 이상이면 **반드시 2개 이상 섞어라**(10/19 사용자: 한 토픽은 관련 영상 여러 개로 짜깁기): 도입부는 메인 영상, 중반부는 메인과 맥락을 번갈아(같은 영상 연속 2컷 이하), 마지막은 사람이 쓰는 장면. JSON 으로만:
{{"도입부": [{{"video": 0, "t": 초}}], "중반부": [... {n_body}개], "마지막": [{{"video": 0, "t": 초}}]}}"""
    text, _ = vx.gemini(prompt, model=WRITER, images=imgs)
    pick = vx.json_from(text)
    subbed = burned_subtitles(day, vids)
    cuts = {}
    for scene in ("훅", "도입부", "중반부", "마지막"):
        if scene not in pick:
            continue
        cuts[scene] = []
        for c in pick[scene]:
            v = vids[int(c["video"])]
            t = max(0.5, min(float(c["t"]), v["duration"] - 8.5))
            c2 = {"clip": f"../../sources/{day.date}/{v['id']}.mp4", "in": round(t, 2), "cx": 0.5, "zoom": 1.0}
            if v["id"] in subbed:
                c2.update({"zoom": 1.2, "yoff": 0})
            cuts[scene].append(c2)
    if subbed:
        day.log(f"  하단 자막 있는 영상 {sorted(subbed)} → 아래쪽 잘라냄")
    return cuts


def _cut_frames(video, times, out_jpg, zoom=1.1, yoff=0):
    """주어진 시각들의 9:16 크롭(렌더와 같은 zoom·yoff — 10/19: 하단 자막을 잘라내는 컷인데 전체 높이로 검사해 '글자 있음'으로 오판)을 가로로 이어 붙인 한 줄 이미지."""
    tmp = []
    for k, t in enumerate(times):
        f = out_jpg.with_name(f".{out_jpg.stem}_{k}.jpg")
        sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf",
            f"crop=w='min(iw\\,ih/{zoom}*9/16)':h='ih/{zoom}':x='(iw-ow)/2':y='{yoff}*(ih-oh)',scale=216:384", "-q:v", "4", str(f)])
        tmp.append(f)
    sh(["ffmpeg", "-v", "error", "-y", *sum((["-i", str(f)] for f in tmp), []), "-filter_complex", "".join(f"[{i}]" for i in range(len(tmp))) + f"hstack={len(tmp)}", str(out_jpg)])
    for f in tmp:
        f.unlink(missing_ok=True)
    return base64.b64encode(out_jpg.read_bytes()).decode()


def _luma(video, t):
    """프레임 평균 밝기(0~255). 10/20 피규로봇: 도입부 컷이 검은 화면(영상 끝 페이드)이었음."""
    try:
        err = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", "signalstats,metadata=print", "-f", "null", "-"],
                             capture_output=True, text=True, timeout=60).stderr
        m = re.search(r"lavfi\.signalstats\.YAVG=([\d.]+)", err)
        return float(m.group(1)) if m else 128.0
    except Exception:
        return 128.0


def _cut_flags(day: Day, rows):
    """rows: [(video, [t...], zoom, yoff)] → 컷마다 {"text": 글자 있음, "person": 사람이 주인공(제품이 작거나 없음)} (Flash 한 번)."""
    imgs = [_cut_frames(r[0], r[1], day.dir / f"auto_chk_{i}.jpg", *(r[2:4] if len(r) >= 4 else ())) for i, r in enumerate(rows)]
    text, _ = vx.gemini(f"이미지 {len(imgs)}장(0번부터). 각 이미지는 세로 영상의 장면 {len(rows[0][1])}컷이다. 각 이미지에 대해 두 가지를 판단하라.\n"
                        "text: 어느 컷에든 문장·단어·자막·로고·모델명 같은 글자가 화면에 보이면 true. text_pos: 그 글자가 주로 있는 위치 top|middle|bottom (없으면 none).\n"
                        "person: 사람의 얼굴·상반신이 화면의 주인공이고 소개할 제품은 작거나 안 보이면 true(제품을 손에 들고 제품이 크게 보이면 false, 제품만 있으면 false).\n"
                        'JSON 배열로만: [{"text": true, "text_pos": "bottom", "person": false}, ...]', model=VISION, images=imgs, timeout=180, retries=1)
    try:
        ans = vx.json_from(text)
        out = [{"text": bool(x.get("text")), "person": bool(x.get("person")), "pos": str(x.get("text_pos") or "none")} for x in ans][:len(rows)]
        return out + [{"text": False, "person": False, "pos": "none"}] * max(0, len(rows) - len(out))
    except Exception:
        return [{"text": False, "person": False, "pos": "none"}] * len(rows)


def _has_text(day: Day, rows):
    return [f["text"] for f in _cut_flags(day, rows)]


def pick_hook(day: Day, vids, cuts, item=None):
    """훅 장면 전용 선정: 강한 블러 뒤에서도 제품 실루엣이 크게 보여야 한다(2026-10-18 홈뷰 훅이 회색 배경이라 뭔지 안 보임)."""
    imgs, desc, steps = [], [], []
    for i, v in enumerate(vids):
        step = max(1, int(v["duration"] // 60) + (1 if v["duration"] % 60 else 0))
        jpg = day.dir / f"auto_hook_{v['id']}.jpg"
        sh(["ffmpeg", "-v", "error", "-y", "-i", v["file"], "-vf", f"fps=1/{step},crop=w='min(iw\\,ih*9/16)':h=ih:x='(iw-ow)/2':y=0,scale=108:192,tile=10x6:padding=4:color=white", "-frames:v", "1", "-q:v", "4", str(jpg)])
        imgs.append(base64.b64encode(jpg.read_bytes()).decode())
        desc.append(f"이미지{i} = 영상{i}(id={v['id']}, {v['duration']:.0f}초) 9:16 센터 크롭 타일, 타일 k(0부터, 왼→오, 위→아래) = {step}*k 초")
        steps.append(step)
    prompt = "\n".join(desc) + f"""
소개할 제품: {_pname(item)} — 영상 속 다른 제품(트럭·다른 모델)은 제외.
릴스 첫 장면용 프레임 하나를 골라라. 이 장면은 블러 처리되고 위에 질문이 얹히므로, 블러 뒤에서도 '무슨 제품인지' 윤곽으로 알아볼 수 있어야 한다.
조건: 소개할 제품 자체가 화면 중앙에 가장 크게, 배경과 대비되어 또렷하게 보이는 타일. 제외: 사람 얼굴·손만 큰 장면, 글자·로고·UI 화면, 검은 화면·페이드, 여러 제품이 작게 흩어진 장면, 영상 마지막 8초.
후보 3개를 좋은 순서로, JSON 배열로만: [{{"video": 0, "t": 초, "why": "한 줄"}}, ...]"""
    text, _ = vx.gemini(prompt, model=WRITER, images=imgs)
    try:
        cands = vx.json_from(text)
    except Exception as e:
        day.log(f"  훅 선정 실패({e}) → 도입부 컷 사용")
        return cuts
    for r in cands[:3]:  # 실제 3프레임(0.3/1.2/2.2초 뒤)을 다시 보여 제품이 주인공인지 확인 — 타일 하나로 고르면 장면이 바뀌어 사람이 나옴(홈뷰 교훈)
        v = vids[int(r["video"])]
        t = max(0.5, min(float(r["t"]), v["duration"] - 8.5))
        img = _cut_frames(v["file"], [t + 0.3, t + 1.2, t + 2.2], day.dir / "auto_hookchk.jpg")
        ok, _ = vx.gemini("세로 영상 연속 3컷. 세 컷 모두에서 '제품(기기) 자체'가 화면의 주인공으로 크게 보이고, 사람 얼굴·몸이 주인공이 아니며, 글자·로고·UI 가 없으면 true. JSON 으로만: {\"ok\": true/false, \"why\": \"\"}", model=WRITER, images=[img])
        try:
            res = vx.json_from(ok)
        except Exception:
            res = {"ok": False}
        day.log(f"  훅 후보 영상{r['video']} {t}s → {'OK' if res.get('ok') else 'X'} {str(res.get('why', ''))[:50]}")
        if res.get("ok"):
            cuts["훅"] = [{"clip": f"../../sources/{day.date}/{v['id']}.mp4", "in": round(t, 2), "cx": 0.5, "zoom": 1.0}]
            return cuts
    # 2차: 가장 긴 공식 영상에서 12개 시점의 실제 9:16 프레임을 보여주고 제품만 나온 것을 고르게 한다(타일 기반 1차가 전부 탈락한 경우)
    v = max(vids, key=lambda x: x["duration"])
    times = [round(v["duration"] * (k + 1) / 14, 1) for k in range(12) if v["duration"] * (k + 1) / 14 <= v["duration"] - 8.5]
    img = _cut_frames(v["file"], times, day.dir / "auto_hook2.jpg")
    text, _ = vx.gemini(f"세로 영상 프레임 {len(times)}장(0번부터). 제품(기기) 자체가 화면 주인공으로 크고 또렷하며 글자·로고·UI·사람 얼굴이 없는 프레임의 번호를 좋은 순서로 최대 3개. 없으면 빈 배열. JSON 배열로만: [번호, ...]", model=WRITER, images=[img])
    try:
        for k in vx.json_from(text)[:3]:
            t = times[int(k)]
            cuts["훅"] = [{"clip": f"../../sources/{day.date}/{v['id']}.mp4", "in": round(t, 2), "cx": 0.5, "zoom": 1.0}]
            day.log(f"  훅 2차 선정: {v['id']} {t}s")
            return cuts
    except Exception as e:
        day.log(f"  훅 2차 실패({e})")
    day.log("  훅 후보 전부 탈락 → 도입부 컷 사용")
    return cuts


def verify_cuts(day: Day, cuts, strict_person=True):
    """선정된 컷에 원본 텍스트·사람 얼굴 주인공·검은 화면이 있으면 옆 시각으로 옮긴다(10/18 홈팟 문구 → 10/20 피규로봇 검은 도입부·사람 위주 컷).
    절반 이상 못 고치면 소재 거부."""
    src = lambda c: str(ROOT / "sources" / Path(c["clip"]).parent.name / Path(c["clip"]).name)
    zy = lambda c: (c.get("zoom", 1.1), c.get("yoff", 0))
    flat = [(sc, i, c) for sc, lst in cuts.items() for i, c in enumerate(lst)]
    dark = lambda v, t: min(_luma(v, t + 0.3), _luma(v, t + 1.5)) < 28
    flags = _cut_flags(day, [(src(c), [c["in"] + 0.2, c["in"] + 1.2, c["in"] + 2.2], *zy(c)) for _, _, c in flat])
    unresolved = 0
    for (sc, i, c), f in zip(flat, flags):
        d = dark(src(c), c["in"])
        person = f["person"] and strict_person  # 바이럴(크리에이터 영상)은 사람이 보여주는 장면이 본질이라 완화(10/20)
        if not (f["text"] or person or d):
            continue
        if f["text"] and not person and not d and f.get("pos") in ("top", "bottom"):  # 글자가 위/아래 띠에만 있으면 그쪽을 잘라내는 크롭으로 먼저 시도
            zz, yy = (1.45, 1) if f["pos"] == "top" else (1.45, 0)
            f2 = _cut_flags(day, [(src(c), [c["in"] + 0.2, c["in"] + 1.2, c["in"] + 2.2], zz, yy)])[0]
            if not f2["text"]:
                c.update({"zoom": zz, "yoff": yy})
                day.log(f"  컷 교정 {sc}#{i} {c['in']}s (글자 {f['pos']}) → 크롭 zoom {zz}/yoff {yy}")
                continue
        why = "+".join(k for k, on in (("글자", f["text"]), ("사람", person), ("어두움", d)) if on)
        vdur = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src(c)]).strip())
        taken = [x["in"] for _, _, x in flat if x is not c and x["clip"] == c["clip"]]
        alts = [t for t in (c["in"] + o for o in (3, -3, 6, -6, 9, -9, 12, -12, 18, -18, 24, 30, -24, 40, -40)) if 0.5 <= t <= vdur - 8.5 and all(abs(t - u) >= 2.5 for u in taken)]
        alts = [t for t in alts if not dark(src(c), t)][:8]  # 어두운 후보는 비전에 묻기 전에 제외
        if not alts:
            unresolved += 1
            day.log(f"  컷 교정 {sc}#{i} {c['in']}s ({why}) → 대안 없음")
            continue
        fl2 = _cut_flags(day, [(src(c), [t + 0.2, t + 1.2, t + 2.2], *zy(c)) for t in alts])
        new = next((t for t, f2 in zip(alts, fl2) if not (f2["text"] or (f2["person"] and strict_person))), None)
        day.log(f"  컷 교정 {sc}#{i} {c['in']}s ({why}) → {new if new is not None else '대안 없음'}")
        if new is not None:
            c["in"] = round(new, 2)
        else:
            unresolved += 1
    if flat and unresolved * 2 >= len(flat):
        raise RuntimeError(f"소스 부적합(글자·사람·어두움): 컷 {len(flat)}개 중 {unresolved}개 대안 없음")
    return cuts


def burned_subtitles(day: Day, vids):
    """원본(16:9) 프레임 4장씩 보고 화면 하단에 박힌 자막/텍스트가 계속 나오는 영상 id 집합. 2026-10-18 가민 튜토리얼 영상에서 놓친 뒤 추가."""
    imgs, desc = [], []
    for i, v in enumerate(vids):
        jpg = day.dir / f"auto_full_{v['id']}.jpg"
        step = max(1.0, v["duration"] / 5)
        sh(["ffmpeg", "-v", "error", "-y", "-i", v["file"], "-vf", f"fps=1/{step:.2f},scale=480:-1,tile=2x2:padding=4:color=white", "-frames:v", "1", "-q:v", "4", str(jpg)])
        imgs.append(base64.b64encode(jpg.read_bytes()).decode())
        desc.append(f"이미지{i} = 영상{i}(id={v['id']}) 의 4개 지점 원본 프레임")
    text, _ = vx.gemini("\n".join(desc) + "\n각 영상 화면 아래쪽에 자막·설명 문장 텍스트가 박혀 있는가(2장 이상에서)? JSON 으로만: {\"0\": true/false, ...}", model=VISION, images=imgs, timeout=180)
    try:
        ans = vx.json_from(text)
        return {vids[int(k)]["id"] for k, val in ans.items() if val}
    except Exception:
        return set()


# ── 4. 스펙·캡션 작성 ───────────────────────────────────────────
LAYOUTS = """레이아웃(props.layout)과 전용 props — 제품 정보 형태로 고른다:
- date(07): 출시일·사전예약일이 핵심일 때. label, date("10.23"), dday("D-5" 또는 "출시"), milestones("발표|9.9 / 사전예약|10.16 / 출시|10.23"), progress(0~1)
- specs(06): 구형 vs 신형(또는 경쟁작) 스펙 2~4줄. line1(*강조*), leftName, rightName, rows("항목|구형값|신형값 / ..."), highlight(가장 큰 변화 행 index), badge("+71%")
- vs(02): 전작 가격 → 신작 가격. kicker, beforeLabel, before("$16,000"), afterLabel, after("$4,900"), badge("−69%")
- convert(08): 가격이 커서 체감 환산이 재밌을 때. line1, number("5,899"), unit("달러"), equivalents("아이폰 *3대* / ...")
- rank(10): 같은 라인업 3~5개를 한 지표로. line1, items("이름|값 / ..."), unit("$"), unitPos("prefix"|"suffix"), highlight
- card(09): 신제품 한 대의 핵심 스탯 3~4개. name, tagline, stats("가격|$899 / 측정|15개 지표 / ..."), highlight, price(""), priceLabel
- list(04): 이유·기능 N가지. kicker, line1(*강조*), number("3"), unit("가지"), points("a / b / c") — points 개수 = bodySubs 청크 수
- breaking(05): 오늘·어제 막 발표된 속보. tag("속보"), kicker, headline(*강조*), ticker("a / b / c / d")
- drop(11): 발매 정보가 핵심(패션·스니커즈·한정판·굿즈). name, tag("드롭"|"발매"|"한정"), line1(*강조*), date("10.24"), price("$150"), where("SNKRS"·"무신사" 등 구매처), colors(선택, "3색")
- collab(12): 두 브랜드·IP 협업. left("Nike"), right("Jacquemus"), line1(*강조*), price, date
- colorway(13): 컬러·옵션이 볼거리일 때(신발·폰·차). name, line1(*강조*), swatches("블랙|#111111 / 세이지|#9CAF88 / ..." 2~6개, 실제 색 hex), price
- stat(14): 수치 하나가 압도적일 때(마력·배터리·무게·두께·수량). label, number, unit, ring(0~1, 예: 전작 대비 비율), sub("전작 870마력")
- question(03): 도입부가 퀴즈일 때(가격·수치 맞히기). kicker(칩 2~5자, 예 "가격 실화?"), question(14~20자, *강조* 1개, 물음표로 끝), answerLabel("정답"), number, unit. 도입부 나레이션은 질문 1문장.
- number(01): 그 외 숫자 하나가 훅. kicker, line1, lead, number, unit, cardBeforeLabel, cardBefore, cardAfterLabel, cardAfter, cardBadge, cardStrike(false면 취소선 없음). 팩트카드는 **같은 항목의 전→후**만(예: 전작 가격 → 신작 가격, 원래 자리엔 큰 모니터 → 이 차는 내 폰 끼우기). 전·후 짝이 없으면 cardAfter 를 비워라(카드 생략).
공통: kicker("브랜드 · 분류"), bodySubs("청크1 / 청크2 / 청크3 [/ 청크4]", 4~5개, 각 청크 14자 이내, *키워드* 1개), outroLine1, outroLine2(*강조* 포함 질문), ctaText("팔로우하고 다음 소식 받기")."""


def viral_rules(item):
    if item.get("kind") != "viral":
        return ""
    ch, v = item.get("channel", ""), int(item.get("views") or 0)
    vk = f"{v // 10000:,}만 뷰" if v >= 10000 else f"{v:,}뷰"
    return f"""※ 이 소재는 해외 바이럴 영상 재가공이다 — 채널 @{ch}, 조회 {v:,}. 규칙:
- 제목에 조회수를 써도 좋다(예: "4,800만 명이 본 1만 달러 고압세척기, 정체는?"). 핵심은 '저게 뭐냐 + 얼마냐 + 왜 터졌냐'.
- kicker 는 정확히 "@{ch} · {vk}" (화면 출처 표기). 캡션 마지막 줄 바로 위는 "영상: @{ch} (유튜브)".
- 영상 속 주장은 facts 에 있는 것만. 채널·출연자 비방 금지, 사람 이름 언급 금지(채널명만). 영상 길이·컷 규칙은 동일."""


RATES_FALLBACK = {"USD": 1335, "GBP": 1778, "EUR": 1500, "JPY": 8.45, "CNY": 199}  # 2026-10-18 open.er-api.com


def rates():
    """원화 환산용 환율(open.er-api.com 무료, 하루 캐시). 실패하면 상수."""
    cache = ROOT / "runs" / "rates.json"
    try:
        if cache.exists() and (dt.datetime.now().timestamp() - cache.stat().st_mtime) < 86400:
            return json.loads(cache.read_text())
        import urllib.request
        with urllib.request.urlopen("https://open.er-api.com/v6/latest/USD", timeout=15) as r:
            j = json.load(r)["rates"]
        out = {"USD": round(j["KRW"]), "GBP": round(j["KRW"] / j["GBP"]), "EUR": round(j["KRW"] / j["EUR"]), "JPY": round(j["KRW"] / j["JPY"], 2), "CNY": round(j["KRW"] / j["CNY"])}
        cache.write_text(json.dumps(out))
        return out
    except Exception:
        return RATES_FALLBACK


def unsourced_numbers(w, item):
    """props+narration 의 세 자리 이상 숫자 중 facts claim 에 없는 것(qa.py 와 같은 규칙, 원화 환산·연도 제외)."""
    blob = json.dumps(w.get("props", {}), ensure_ascii=False) + json.dumps(w.get("narration", {}), ensure_ascii=False)
    blob = re.sub(r"[\d,.]+\s*(?:만|억|천)\s*원", " ", blob)
    nums = re.findall(r"(?<![A-Za-z0-9])\d[\d,]*\d(?![A-Za-z0-9])", blob)
    claims = " ".join(f.get("claim", "") for f in item.get("facts", []))
    expand = lambda t: re.sub(r"(\d+)\s*만\s*(\d[\d,]*)", lambda m: str(int(m.group(1)) * 10000 + int(m.group(2).replace(",", ""))), t)
    cd = expand(claims).replace(",", "")
    return sorted({n for n in nums if len(n.replace(",", "")) >= 3 and not re.fullmatch(r"20[2-3]\d", n) and n.replace(",", "") not in cd})


def write_spec(day: Day, item, recent_layouts, feedback=""):
    examples = []
    for n in ("spec_sony.json", "spec_duo.json", "spec_t06_specs.json", "spec_t09_card.json"):
        p = ROOT / "runs/2026-10-17" / n
        if p.exists():
            j = json.loads(p.read_text())
            examples.append(json.dumps({"props": j["props"], "narration": j["narration"]}, ensure_ascii=False))
    prompt = f"""한국 인스타 릴스·유튜브 쇼츠 '{CHANNEL}({HANDLE})' 28~36초 영상의 대본과 캡션을 써라. 채널: 세상에 갓 나온 물건을 얼리어답터에게 가장 먼저(카테고리 제한 없음).
시청자는 그 분야를 전혀 모르는 일반인이다. **중학생이 한 번 듣고 이해해야 한다.** 이것이 다른 모든 규칙보다 우선한다. 제품 정보(출처 포함):
{json.dumps(item, ensure_ascii=False)}

{LAYOUTS}
최근 사용한 레이아웃(연속 3번 금지): {recent_layouts}
{viral_rules(item)}
{feedback}

규칙:
- 쉬운 말 규칙(10/19 사용자: "무슨 말인지 전혀 이해가 안 돼"): ① 전문용어·영어 약어·모델명 금지(브랜드명과 이 제품 이름만 허용. "918 스파이더 후속", "GT3 RS", "다운포스", "mAh", "니트" 같은 건 쓰지 말거나 바로 풀어 쓴다: "다운포스" → "차를 땅에 눌러주는 힘"). ② 첫 문장은 '이게 뭔지'를 한 줄로("포르쉐가 만든 새 스포츠카", "고양이 화장실을 알아서 치우는 기계"). ③ 한 문장에 한 가지 뜻, 20자 안팎, 구어체. ④ 숫자는 비유나 비교를 붙인다("아이폰 3대 값", "서울~부산 두 번 갈 거리"). ⑤ 왜 화제인지 한 문장을 꼭 넣는다.
- 숫자는 facts 에 있는 것만. 없는 숫자 만들지 말 것. heat_views(유튜브 조회수)는 "유튜브 조회 1억 뷰"처럼 조회수로만 쓰고 기간("3일 만에")을 지어내지 말 것. 외화 가격은 반드시 원화 환산을 붙인다: "30만 파운드, 우리 돈 약 5억 원". 환율(오늘): {json.dumps(rates())} — '약' + 만/억 단위로 반올림(예: 5,999달러 → 약 800만 원). 한국 공식 가격이 facts 에 있으면 그것을 쓴다.
- 화면 글자(line1·points·rows·stats·label 등)도 같은 눈높이: 쉬운 말, 8~12자, 모델명·영어 약어 금지.
- title 과 도입부 첫 문장은 '와우 포인트'로 시작한다(10/20 사용자: 후킹을 세게, 와우하게). 와우 포인트 = 이 제품에서 가장 믿기 힘든 사실 하나(item.wow_reason 참고). 공식: [믿기 힘든 사실] + [숫자 하나]. 예: "이 차, 진짜 날아갑니다. 가격은 25만 달러", "로봇이 빨래를 개서 서랍에 넣었습니다", "1억 2천만 원짜리 화장실이 팔렸습니다", "종이처럼 말리는 TV, 두께 2mm". 금지: "~출시", "~공개", "~컬렉션", "신형 ~" 같은 뉴스체, 와우 없는 가격 나열.
- title 은 이 영상의 성패를 가른다. '사실만 쓰되 클릭을 안 하면 못 배기게' 쓴다. 공식: [반전·대비] + [구체 숫자 하나] + [궁금증을 남기는 끝맺음]. 뉴스 헤드라인("~공개", "~출시")은 0점.
  좋은 예: "애플이 6년 동안 안 내던 스피커, 왜 지금 149달러로 돌아왔나" / "버튼이 하나도 없는 애플 신제품, 실물 보면 소름" / "닌텐도가 안 만들어서 중국이 만든 3DS, 285달러" / "센서 없이 스윙을 읽는 시계, 가격이 799달러인 이유" / "금도금 워크맨 5,899달러, 누가 사나 했더니" / "이 안경 밝기만 2배 됐는데 가격은 그대로".
  한국 상위 조회 쇼츠 공식(2026-10-18 분석): [브랜드+제품] + [가격·수치 하나] + [짧은 질문·판단]. 예: "20만 원짜리 아이폰 듀오 케이스, 돈값 할까", "세상에서 가장 비싼 키보드의 정체", "오늘 공개된 아이폰 듀오 실물". '실물', '정체', '돈값', '가장 ~한', '처음' 같은 단어가 잘 먹힌다. 12~26자.
  나쁜 예: "애플 최초 스마트홈 허브 홈뷰 공개" / "가민 어프로치 S72 출시". 금지: 허위·과장(혁명, 역대급, 미쳤다 같은 근거 없는 평가), 건강·효능 주장, 타사 비방. 허용: 반전, 궁금증, 가격 대비, "왜", "정체", "실화", "소름"(사실에 근거할 때).
  title 은 30자 이내, 이모지 없음. caption 첫 줄은 title 을 그대로 쓴다(이모지 1개 앞에).
- 훅 장면은 없다(10/19 사용자: 블러 인트로 폐지). 도입부 첫 문장이 곧 훅이다 — 숫자나 반전으로 시작.
- 레이아웃은 14종 모두 쓸 수 있다. 원래 10종(01~10)을 우선하고, 정보 형태에 맞는 걸 고른다. question(03)은 도입부가 퀴즈(question + answerLabel + number)인 레이아웃이다.
- narration(1.0배 기준 길이): 도입부 = 숫자·반전으로 시작하는 '이게 뭔지' 한두 문장(4.5초 이내; question 레이아웃이면 질문 1문장), 중반부 = bodySubs 청크를 같은 단어로 이어 읽기(14~18초, 5청크 = 왜 화제인지 / 핵심 1 / 핵심 2 / 가격(원화 환산) / 언제·어디서), 마지막 = 질문 1개(3.5초 이내). 천천히 또박또박 읽어도 되는 짧은 문장들로.
- 카테고리별: 패션·신발 = 발매일·가격·구매처·컬러 수·한정 수량이 핵심(사이즈 얘기 금지). 자동차 = 마력·가격·출시 시기·전작 대비. 뷰티 = 효능 주장 금지, 가격·용량·출시만. 가전·IT = 전작 대비 바뀐 수치. 영어 제품명은 한국어 발음으로(예: XREAL → 엑스리얼).
- bodySubs 청크 5개, 각 8~14자, 한 청크 = 한 뜻. 청크 글자는 narration 에 그대로 나와야 함(자막 정렬용).
- 말투: 친구한테 신기한 거 알려주듯. 과장·광고 문구 금지.
- caption(인스타): 첫 줄 맨 앞에만 이모지 1개. 그 외 어디에도 이모지 금지. 진짜 사람이 쓴 것처럼 2~4문장, 구어체, 핵심 숫자 포함. 마지막 줄 바로 위에 "영상: <브랜드> 공식 유튜브". 마지막 줄 해시태그 정확히 5개 이하.
- bgm_prompt: 영어, 제품 분위기에 맞는 20초 배경음악, 반드시 "Instrumental only, no vocals." 와 BPM 포함.

예시(형식 참고, 내용 베끼지 말 것):
{chr(10).join(examples)}

JSON 으로만 답:
{{"layout": "...", "title": "후킹 제목(릴스·유튜브 제목용, 30자 이내, 이모지 없이)", "props": {{...레이아웃 props + 공통 props...}}, "narration": {{"도입부": "...", "중반부": "...", "마지막": "..."}}, "bgm_prompt": "...", "caption": "...", "card_chunk": (number 레이아웃일 때 팩트카드가 뜰 bodySubs 청크 index, 아니면 null)}}"""
    text, _ = vx.gemini(prompt, model=WRITER)
    w = vx.json_from(text)
    missing = unsourced_numbers(w, item)
    if missing and not feedback:  # 출처 없는 숫자 → 한 번 다시 쓰게(그래도 남으면 QA 경고로 메일에 표시)
        day.log(f"  대본 숫자 출처 없음 {missing} → 재작성")
        return write_spec(day, item, recent_layouts, feedback=f"※ 이전 대본에 facts 에 없는 숫자 {missing} 가 있었다. 이 숫자들은 빼거나 facts 에 있는 숫자로만 바꿔라. 새 숫자를 만들지 마라.")
    return w


EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍‼⁉™ℹ↔-↪⌚-⏿Ⓜ▪-◾]")


def clean_caption(c):
    lines = [l.rstrip() for l in c.strip().splitlines()]
    tags = []
    body = []
    for l in lines:
        found = re.findall(r"#[^\s#]+", l)
        if found and len(l.replace(" ", "")) <= sum(len(t) for t in found) + 2:
            tags += found
        else:
            body.append(l)
    first_emoji = EMOJI.findall(body[0])[:1] if body else []
    body = [EMOJI.sub("", l).strip() for l in body]
    if body and first_emoji:
        body[0] = first_emoji[0] + " " + body[0]
    out = "\n".join(body).strip()
    seen = []
    for t in tags:
        if t not in seen:
            seen.append(t)
    return out + ("\n\n" + " ".join(seen[:5]) if seen else "")


KO_DIG = "영일이삼사오육칠팔구"


def num2ko(n):
    if n == 0:
        return "영"
    out = ""
    for unit, val in (("억", 10**8), ("만", 10**4), ("", 1)):
        q, n = divmod(n, val) if val > 1 else (n, 0)
        if not q:
            continue
        part = ""
        for u, v in (("천", 1000), ("백", 100), ("십", 10), ("", 1)):
            d, q = divmod(q, v)
            if d:
                part += ("" if d == 1 and u else KO_DIG[d]) + u
        out += part + unit
    return out


def spell_numbers(text):
    return re.sub(r"\d{1,3}(?:,\d{3})+|\d{3,}", lambda m: num2ko(int(m.group().replace(",", ""))), text)


BAD_KICKERS = {"가격 맞히기", "가격맞히기", "이게 신상?", "퀴즈", "신제품", "속보"}


def fix_kicker(hook, title=""):
    """칩은 1~2단어·5자 이내·질문과 단어 중복 금지. 어기면 질문 내용에 맞는 기본값으로 교체(2026-10-18 사용자: '6년 만에'·'가격 맞히기' 금지)."""
    if not hook:
        return hook
    k = str(hook.get("kicker", "")).strip()
    q = str(hook.get("question", ""))
    words = set(re.findall(r"[가-힣A-Za-z0-9]+", q))
    bad = (not k or len(k.replace(" ", "")) > 5 or k in BAD_KICKERS or any(w in k for w in words if len(w) >= 2))
    if bad:
        pool = ["가격 실화?", "얼마게?", "맞혀봐", "충격 가격", "1초 퀴즈"] if ("얼마" in q or "가격" in q or "달러" in q) else ["정체는?", "이게 뭐지?", "맞혀봐", "신상 등장"]
        hook["kicker"] = pool[sum(map(ord, q)) % len(pool)]  # 질문마다 다른 칩
    return hook


def spec_theme(spec_p):
    try:
        return json.loads(spec_p.read_text())["props"].get("theme")
    except Exception:
        return None


def fix_credit(caption, vids, cuts, item):
    """캡션 '영상: …' 줄을 실제로 쓴 컷의 채널로 교체(10/19 포르쉐: 바이럴은 carwow 인데 컷은 전부 포르쉐 공식 → 출처가 틀림)."""
    used = {Path(c["clip"]).stem for lst in cuts.values() for c in lst}
    chans = []
    for v in vids:
        if v["id"] in used and v["channel"] not in chans:
            chans.append(v["channel"])
    if not chans:
        return caption
    parts = [f"@{c} (유튜브)" if any(v.get("credit") and v["channel"] == c for v in vids) else f"{c} 공식 유튜브" for c in chans]
    line = "영상: " + ", ".join(parts)
    if item.get("kind") == "viral" and not any(v.get("credit") and v["id"] in used for v in vids):
        line += f" · 화제: @{item.get('channel')} {int(item.get('views') or 0) // 10000}만 뷰"
    lines = caption.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.strip().startswith("영상:")), None)
    if idx is None:
        tag_i = next((i for i, l in enumerate(lines) if l.strip().startswith("#")), len(lines))
        lines.insert(tag_i, line); lines.insert(tag_i, "")
    else:
        lines[idx] = line
    return "\n".join(lines)


def make_spec(day: Day, item, w, cuts, idx):
    w["hook"] = None  # 10/19 사용자: 블러 훅 인트로 폐지 — 원래 템플릿 인트로 그대로
    w["narration"].pop("훅", None)
    cuts.pop("훅", None)
    sent_n = sum(1 for _ in open(ROOT / "track/sent.jsonl")) if (ROOT / "track/sent.jsonl").exists() else 0
    props = {**w["props"], "layout": w["layout"], "platform": "instagram", "handle": HANDLE,
             "accent": vivid(w["props"].get("accent") or CATS.get(item.get("category"), ""), item.get("brand", "")), "hookSubs": "",
             "theme": THEMES[(sent_n + idx) % len(THEMES)]}
    props.setdefault("transition", {"breaking": "shutter", "vs": "shutter", "specs": "shutter", "rank": "shutter", "question": "zoom", "drop": "shutter", "colorway": "zoom"}.get(w["layout"], "slash"))
    spec = {"product": f"{item['brand']} {item['product']}", "model": "gemini-3.1-flash-tts-preview", "voice": VOICES[(sent_n + idx) % len(VOICES)], "rate": 1.08, "speed": 1.1,  # 10/19 사용자: 너무 빨라 못 읽음 → 1.3→1.1
            "style": STYLE, "bgm_prompt": w["bgm_prompt"], "bgm_db": -20, "voice_db": 2, "sync_cuts": True,  # 덕킹 후 전체 음량이 -14 LUFS 경계라 목소리 +1dB(10/18)
            "sources": item["facts"], "props": props, "narration": w["narration"], "cuts": cuts, "sfx": True, "duck": True, "grade": True}
    if w.get("card_chunk") is not None:
        spec["card_chunk"] = int(w["card_chunk"])
    p = day.dir / f"spec_auto{idx}.json"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=1))
    return p


def render(day: Day, spec_p, tries=3):
    preview = day.dir / f"preview_{spec_p.stem[5:]}.mp4"
    for attempt in range(tries):
        spec = json.loads(spec_p.read_text())
        try:
            sh([PY, "-I", "produce/render/design_reel.py", str(spec_p), str(preview)], timeout=2400)
        except RuntimeError as e:
            msg = str(e)
            if "TTS 검증" in msg:  # 숫자 오독 → 나레이션 숫자를 한글로
                spec["narration"] = {k: spell_numbers(v) for k, v in spec["narration"].items()}
                spec_p.write_text(json.dumps(spec, ensure_ascii=False, indent=1))
                day.log(f"  보정: 나레이션 숫자 한글화 후 재시도 ({attempt + 1})")
                continue
            if "클립 길이 초과" in msg or "장면보다 김" in msg:
                for sc in spec["cuts"].values():
                    for c in sc:
                        c["in"] = max(0.5, c["in"] - 4)
                spec_p.write_text(json.dumps(spec, ensure_ascii=False, indent=1))
                day.log(f"  보정: 컷 시작 당김 후 재시도 ({attempt + 1})")
                continue
            raise
        qa = subprocess.run(["python3", "-I", "produce/qa.py", str(preview), str(spec_p)], capture_output=True, text=True, cwd=str(ROOT))
        head = qa.stdout.splitlines()[0] if qa.stdout else ""
        fails = re.findall(r"\| (.+?) \| ❌ \| (.+?) \|", qa.stdout)
        if fails:
            head += " — " + "; ".join(f"{k}: {v}" for k, v in fails)
        if qa.returncode == 0:
            return preview, head
        mlen = re.search(r"\| 길이[^|]*\| ❌ \| ([\d.]+)s \|", qa.stdout)
        if mlen:
            d = float(mlen.group(1))
            spec["speed"] = round(min(1.25, max(1.0, float(spec.get("speed", 1.1)) * (1.08 if d > 40 else 0.92))), 2)  # 10/19: 기본 1.1, 1.0~1.25
            spec_p.write_text(json.dumps(spec, ensure_ascii=False, indent=1))
            day.log(f"  보정: 길이 {d}s → speed {spec['speed']} 재렌더")
            continue
        return preview, head  # 그 외 QA 실패는 결과와 함께 보고
    raise RuntimeError("렌더 보정 3회 실패")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--skip-collect", action="store_true")
    ap.add_argument("--want", type=int, default=3)
    ap.add_argument("--slot", default="", help="같은 날 추가 배치면 'b' 등")
    ap.add_argument("--viral", type=int, default=1, help="하루 편수 중 해외 바이럴 재가공 편수")
    ap.add_argument("--deadline", type=int, default=110, help="시작 후 N분이 지나면 새 편 제작을 멈춘다(발송 시각 보호)")
    ap.add_argument("--dry-pick", action="store_true", help="선정(제품·바이럴)까지만 하고 제작은 안 함 — 후보 확인용")
    a = ap.parse_args()
    day = Day(a.date, a.slot)
    day.log("=== 무인 제작 시작")
    import os, time
    started = time.time()
    (day.dir / "running.pid").write_text(str(os.getpid()))  # send.py 가 이 파일로 '아직 제작 중'을 안다
    # 10/19 새벽 사고: 맥이 잠들었다 깼다 해서 수집 56분·선정 2시간+ → 실행 중엔 유휴 잠들기 금지(배터리에서도 동작, 뚜껑 닫힘은 못 막음)
    # 10/20 재발: DarkWake(유지보수 깨움) 중 시작되면 caffeinate -i 로는 2초 뒤 다시 잠듦("Sleep Service Back to Sleep").
    # → -u 로 '사용자 활동' 선언해 완전 기상시키고, -s(전원 연결 시 시스템 잠들기 금지) + -i 로 유지. 뚜껑 닫힘은 못 막음.
    if sys.platform == "darwin":  # 서버(리눅스)에선 불필요(10/20 GCE 이전)
        subprocess.run(["/usr/bin/caffeinate", "-u", "-t", "5"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["/usr/bin/caffeinate", "-u", "-i", "-s", "-w", str(os.getpid())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not a.skip_collect:
            sh(["python3", "-I", "discover/news.py", "--hours", "48"])
            sh(["python3", "-I", "discover/collect.py", "--top", "3"])
            try:
                sh(["python3", "-I", "discover/hot.py"], timeout=1500)
            except Exception as e:  # 인기 수집은 보조 신호 — 실패해도 진행
                day.log(f"hot.py 실패(무시): {str(e)[:200]}")
            day.log("수집 완료")
        items = pick(day) if a.viral < a.want else []  # 바이럴만 만들 땐 제품 선정 생략(실패 시 아래서 지연 선정)
    except Exception as e:
        day.report["errors"].append(f"선정 실패: {e}")
        day.log(traceback.format_exc())
        day.save()
        return
    recent = []
    for sp in sorted((ROOT / "runs").glob("*/spec_*.json"))[-6:]:
        try:
            recent.append(json.loads(sp.read_text())["props"].get("layout"))
        except Exception:
            pass
    virals = []
    if a.viral > 0:
        try:
            virals = pick_viral(day)
        except Exception as e:
            day.report["errors"].append(f"바이럴 선정 실패: {e}")
            day.log(traceback.format_exc())
    # 순서: 제품(want-viral) → 바이럴(viral) → 모자라면 남은 제품으로 채움
    if a.dry_pick:
        day.log("dry-pick: 선정만 하고 종료")
        for it in items:
            day.log(f"  [제품] {it['brand']} {it['product']} · 발표 {it.get('announced')} · 화제 {it.get('heat_views', 0):,}(오늘)/{it.get('heat_week', 0):,}(주) · {'OLDER ' if it.get('older') else ''}{it.get('hot_reason', '')[:60]}")
        for it in virals:
            day.log(f"  [바이럴] {it.get('channel')} {it['product']} · 조회 {it.get('views', 0):,} · {it.get('why_viral', '')[:60]}")
        (day.dir / "running.pid").unlink(missing_ok=True)
        return
    n_prod = max(0, a.want - a.viral)
    queue = items[:n_prod] + virals + items[n_prod:]
    made = 0
    qi = 0
    widened = False
    while qi < len(queue) or (made < a.want and not widened):
        if made >= a.want:
            break
        if (time.time() - started) / 60 > a.deadline:
            day.report["errors"].append(f"제한시간 {a.deadline}분 초과 — {made}편에서 중단")
            day.log(f"제한시간 초과({a.deadline}분) → 중단")
            break
        if qi >= len(queue):  # 큐 소진: 제품 선정을 아직 안 했으면 지금, 했으면 7일 창으로 2차 선정(10/20: 월요일 48h 풀 0편)
            if widened:
                break
            try:
                tried = [f"{i.get('brand', '')} {i.get('product', '')}" for i in queue if i.get("product")]
                items = pick(day, window_h=48 if not items else 336, exclude=tried) or [{}]  # 2차는 14일(한국 시청자에겐 아직 '갓 나온' 것)
                widened = bool(items) and items != [{}] and len(tried) > 0
                if widened:
                    day.log(f"  2차 선정(14일 창): {len([i for i in items if i])}개")
            except Exception as e:
                day.report["errors"].append(f"선정 실패: {e}")
                break
            queue += [i for i in items if i]
            if qi >= len(queue):
                break
        item = queue[qi]
        qi += 1
        tag = f"{item['brand']} {item['product']}"
        try:
            day.log(f"▶ {tag}" + (" [바이럴]" if item.get("kind") == "viral" else ""))
            vids = viral_videos(day, item) if item.get("kind") == "viral" else official_videos(day, item)
            if not vids:
                raise RuntimeError("영상 없음(바이럴 다운로드 실패)" if item.get("kind") == "viral" else "최근 45일 공식 유튜브 영상 없음")
            day.log(f"  공식 영상 {len(vids)}개: " + ", ".join(f"{v['id']}({v['duration']:.0f}s)" for v in vids))
            w = write_spec(day, item, recent[-3:])
            n_body = len([c for c in str(w["props"].get("bodySubs", "")).split("/") if c.strip()]) or 3
            cuts = choose_cuts(day, vids, n_body, item)
            cuts.pop("훅", None)  # 훅 장면 없음(10/19)
            cuts = verify_cuts(day, cuts, strict_person=item.get("kind") != "viral")
            spec_p = make_spec(day, item, w, cuts, made + 1)
            preview, qa = render(day, spec_p)
            caption = fix_credit(clean_caption(w["caption"]), vids, cuts, item)
            made += 1
            dst = day.out / f"{made}_{re.sub(r'[^A-Za-z0-9]+', '_', tag).strip('_')}.mp4"
            shutil.copy(preview, dst)
            dst.with_suffix(".txt").write_text(caption)
            recent.append(w["layout"])
            title = (w.get("title") or "").strip()
            day.report["items"].append({"product": tag, "layout": w["layout"], "file": dst.name, "qa": qa, "caption": caption, "title": title,
                                        "hook": w.get("hook"), "category": item.get("category"), "hot_reason": item.get("hot_reason") or item.get("why_viral"), "heat_views": item.get("heat_views") or item.get("views"),
                                        "kind": item.get("kind", "product"), "credit": item.get("channel") if item.get("kind") == "viral" else None,
                                        "wow": item.get("wow"), "wow_judge": item.get("wow_judge"), "wow_weak": item.get("wow_weak", False),
                                        "theme": spec_theme(spec_p),
                                        "facts": item["facts"], "korea": item.get("korea"), "videos": [v["id"] for v in vids]})
            day.log(f"  완료 {dst.name} · {qa}")
        except Exception as e:
            day.report["errors"].append(f"{tag}: {str(e)[-500:]}")  # 끝부분(실제 예외 줄)을 남긴다(10/19: 앞 300자만 남겨 원인을 못 봄)
            day.log(f"  건너뜀 {tag}: {str(e)[-500:]}")
        day.save()
    day.report["finished"] = now()
    day.save()
    (day.dir / "running.pid").unlink(missing_ok=True)
    day.log(f"=== 끝: {made}개 완성")
    # 08:00 이 지나서 끝났고 아직 릴스를 못 보냈으면(없음 메일만 갔으면) 지금 보낸다 — 10/19 사고 재발 방지
    sent_p = day.dir / "sent.json"
    already = json.loads(sent_p.read_text()).get("count", 0) if sent_p.exists() else 0
    if not a.slot and made and dt.datetime.now().hour >= 8 and not already:
        r = subprocess.run([sys.executable, "-I", str(ROOT / "auto/send.py"), "--date", a.date, "--tag", " 지연"], capture_output=True, text=True)
        day.log(f"지연 발송: {(r.stdout + r.stderr).strip()[-200:]}")


if __name__ == "__main__":
    main()
