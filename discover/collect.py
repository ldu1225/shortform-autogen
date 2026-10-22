"""채널 소재 수집기 v0 — 공급 신호(브랜드 공식 유튜브 RSS) + 조회 속도.
- channels.json 의 채널마다 RSS(쿼터 0)로 최근 업로드 15개 → 7일 이내만 남김, 48시간 이내는 신선도 1.0
- RSS 에 조회수가 있어서 yt-dlp 는 길이 확인용으로 신선한 것에만 호출
- 점수 = 신선도 × log(조회속도) ; 레인별 상위 N 을 candidates.md / candidates.json 으로
- 수요 신호(네이버 데이터랩)·판매 신호(쿠팡 파트너스 API)는 키 발급 후 붙임(ponytail: 지금은 빈 칸)
사용: python3 -I collect.py [--hours 48] [--top 3]
"""
import argparse
import datetime as dt
import json
import math
import re
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG, RUNS = ROOT / "config", ROOT / "runs"
YTDLP = str(ROOT / ".venv/bin/yt-dlp")
COOKIES = ROOT / "cookies.txt"
YTDLP_OPTS = ["--cookies", str(COOKIES)] if COOKIES.exists() else []
NS = {"a": "http://www.w3.org/2005/Atom", "m": "http://search.yahoo.com/mrss/", "yt": "http://www.youtube.com/xml/schemas/2015"}
LANE_KO = {"ai_gadget": "AI·IT 가젯", "golf_tech": "골프 테크", "power_camp": "파워·캠핑", "pet_tech": "펫 테크", "ai_robot": "AI 로봇(도달용)"}
TEMPLATE_HINT = [
    (r"introduc|launch|unveil|announc|new |all-new|meet |공개|출시", "05 속보"),
    (r"\$|price|가격|off|deal|sale|discount", "02 가격 비교"),
    (r"top \d|\d+ (reasons|ways|things|features)|best", "04 TOP 리스트"),
    (r"\?|guess|quiz", "03 퀴즈"),
]


def rss(channel_id):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    with urllib.request.urlopen(url, timeout=30) as r:
        root = ET.fromstring(r.read())
    out = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        pub = dt.datetime.fromisoformat(e.findtext("a:published", namespaces=NS))
        stats = e.find("m:group/m:community/m:statistics", NS)
        views = int(stats.get("views", "0")) if stats is not None else 0
        star = e.find("m:group/m:community/m:starRating", NS)
        likes = int(star.get("count", "0")) if star is not None else 0
        out.append({"id": vid, "title": e.findtext("a:title", namespaces=NS), "published": pub, "views": views, "likes": likes,
                    "url": f"https://www.youtube.com/watch?v={vid}"})
    return out


def duration(vid):
    r = subprocess.run([YTDLP, *YTDLP_OPTS, "--no-warnings", "--skip-download", "--print", "%(duration)s|%(width)s|%(height)s", f"https://www.youtube.com/watch?v={vid}"],
                       capture_output=True, text=True)
    try:
        d, w, h = r.stdout.strip().split("|")
        return int(float(d)), int(w) >= int(h)
    except Exception:
        return None, None


def product_key(title, brand):
    """제목에서 제품명 추정: 브랜드명 뒤 '모델 + 숫자' 패턴 (예: 'Litter-Robot 5', 'X6', 'Osmo Nano')."""
    m = re.search(r"([A-Za-z][A-Za-z\-]+ ?\d+[A-Za-z]*|[A-Z][a-z]+ [A-Z][a-z]+)", title.replace(brand, ""))
    return m.group(1).lower().strip() if m else ""


def hint(title):
    t = title.lower()
    for pat, name in TEMPLATE_HINT:
        if re.search(pat, t):
            return name
    return "01 숫자 훅"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=48)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--days", type=float, default=7)
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    chans = json.loads((CONFIG / "channels.json").read_text())
    rows = []
    for brand, c in chans.items():
        if not c.get("channel_id"):
            continue
        try:
            items = rss(c["channel_id"])
        except Exception as ex:
            print(f"  RSS 실패 {brand}: {ex}", file=sys.stderr)
            continue
        for it in items:
            hrs = (now - it["published"]).total_seconds() / 3600
            if hrs > a.days * 24:
                continue
            fresh = 1.0 if hrs <= a.hours else 0.5
            vel = it["views"] / max(hrs, 1.0)
            ad = it["views"] > 50000 and it["likes"] / max(it["views"], 1) < 0.001  # 좋아요율 0.1% 미만 = 광고 집행
            key = product_key(it["title"], brand)
            older = [o for o in items if o["published"] < it["published"] - dt.timedelta(hours=a.hours)]
            rerun = bool(key) and any(key in o["title"].lower() for o in older)  # 48h 전 업로드에 같은 제품명 → 캠페인 재탕
            score = fresh * math.log10(vel + 1) * (0.4 if ad else 1.0) * (0.5 if rerun else 1.0)
            rows.append({**it, "published": it["published"].isoformat(), "brand": brand, "lane": c["lane"], "hours": round(hrs, 1),
                         "velocity": round(vel, 1), "ad": ad, "rerun": rerun, "score": round(score, 3), "template": hint(it["title"])})
    rows.sort(key=lambda r: -r["score"])
    picked = []
    for lane in LANE_KO:
        lane_rows = [r for r in rows if r["lane"] == lane][: a.top]
        for r in lane_rows:
            r["duration"], r["landscape"] = duration(r["id"])
        picked += lane_rows
    day = RUNS / now.astimezone().strftime("%Y-%m-%d")
    day.mkdir(exist_ok=True)
    (day / "candidates.json").write_text(json.dumps({"generated": now.isoformat(), "all": rows, "picked": picked}, ensure_ascii=False, indent=1))
    md = [f"# 채널 소재 후보 — {day.name} (수집 {now.astimezone().strftime('%H:%M')})", "",
          f"채널 {sum(1 for c in chans.values() if c.get('channel_id'))}개 RSS, 7일 이내 {len(rows)}건, 48h 이내 {sum(1 for r in rows if r['hours'] <= a.hours)}건. 점수 = 신선도 × log10(조회/시간).", ""]
    for lane, ko in LANE_KO.items():
        md += [f"## {ko}", "", "| 점수 | 브랜드 | 제목 | 경과 | 조회 | 좋아요율 | 플래그 | 길이 | 추천 템플릿 | 쿠팡 가격 | 예상 수수료 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in [p for p in picked if p["lane"] == lane]:
            dur = f"{r['duration'] // 60}:{r['duration'] % 60:02d}" if r.get("duration") else "?"
            flag = " ".join(f for f, on in (("광고", r["ad"]), ("재탕", r["rerun"])) if on)
            md.append(f"| {r['score']:.2f} | {r['brand']} | [{r['title'][:60]}]({r['url']}) | {r['hours']:.0f}h | {r['views']:,} | {100 * r['likes'] / max(r['views'], 1):.2f}% | {flag} | {dur}{'' if r.get('landscape') in (None, True) else ' 세로'} | {r['template']} | | |")
        md.append("")
    md += ["---", "쿠팡 가격·수수료는 파트너스 API 키 발급 후 자동. 그 전엔 승인 시 손으로 채움."]
    (day / "candidates.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
