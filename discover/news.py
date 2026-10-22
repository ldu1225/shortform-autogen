"""채널 신제품 뉴스 수집기 v0 — 매체 RSS에서 '출시/공개' 기사만 골라 브랜드·레인에 매핑.
교훈(2026-10-17): 브랜드 유튜브의 '새 업로드'는 대부분 캠페인 재탕이라 신제품 신호가 아니다. 신제품은 뉴스가 먼저, 유튜브는 소재(공식 영상) 확보용.
사용: python3 -I news.py [--hours 48]
"""
import argparse
import datetime as dt
import email.utils
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG, RUNS = ROOT / "config", ROOT / "runs"
FEEDS = {
    # 테크
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Engadget": "https://www.engadget.com/rss.xml",
    "Gizmodo": "https://gizmodo.com/feed",
    "9to5Google": "https://9to5google.com/feed/",
    "9to5Mac": "https://9to5mac.com/feed/",
    "GSMArena": "https://www.gsmarena.com/rss-news-reviews.php3",
    "PetaPixel": "https://petapixel.com/feed/",
    "Notebookcheck": "https://www.notebookcheck.net/News.152.100.html",
    "TechCrunch Gadgets": "https://techcrunch.com/category/gadgets/feed/",
    "Apple Newsroom": "https://www.apple.com/newsroom/rss-feed.rss",
    "삼성 뉴스룸": "https://news.samsung.com/kr/feed",
    "지디넷코리아": "https://zdnet.co.kr/rss/",
    "전자신문": "https://rss.etnews.com/Section902.xml",
    "IT동아": "https://it.donga.com/rss/",
    # 패션·스니커즈 (2026-10-18 카테고리 확장)
    "Hypebeast": "https://hypebeast.com/feed",
    "Hypebeast KR": "https://hypebeast.kr/feed",
    "Highsnobiety": "https://www.highsnobiety.com/feed/",
    "Sneaker News": "https://sneakernews.com/feed/",
    "Nice Kicks": "https://www.nicekicks.com/feed/",
    "Hypebae": "https://hypebae.com/feed",
    # 디자인·리빙·가젯 라이프스타일
    "Yanko Design": "https://www.yankodesign.com/feed/",
    "Design Milk": "https://design-milk.com/feed/",
    "Wallpaper": "https://www.wallpaper.com/feeds/all",
    "Gear Patrol": "https://www.gearpatrol.com/feed/",
    "HiConsumption": "https://hiconsumption.com/feed/",
    "Cool Material": "https://coolmaterial.com/feed/",
    "GearJunkie": "https://gearjunkie.com/feed",
    # 자동차·모빌리티
    "Car and Driver": "https://www.caranddriver.com/rss/all.xml/",
    "Electrek": "https://electrek.co/feed/",
    "The Drive": "https://www.thedrive.com/feed",
    # 골프
    "MyGolfSpy": "https://mygolfspy.com/feed/",
    "GolfWRX": "https://www.golfwrx.com/feed/",
    "Golf Monthly": "https://www.golfmonthly.com/feeds/all",
    # 뷰티
    "Allure": "https://www.allure.com/feed/rss",
    # 신기한 것·발명·로봇 (10/20 사용자: 와우한 소재)
    "New Atlas": "https://newatlas.com/index.rss",
    "Interesting Engineering": "https://interestingengineering.com/feed",
    "Core77": "https://www.core77.com/feed",
    "designboom": "https://www.designboom.com/feed/",
    "The Robot Report": "https://www.therobotreport.com/feed/",
    "IEEE Spectrum": "https://spectrum.ieee.org/feeds/feed.rss",
    "Hypebeast Tech": "https://hypebeast.com/tech/feed",
}
LAUNCH = re.compile(r"launch|announc|unveil|introduc|debut|reveal|goes on sale|now available|pre-?order|releas|drop|collab|collection|edition|first look|hands-on|unbox|world'?s|first-ever|flying|robot|humanoid|prototype|concept|record|출시|공개|선보|발표|사전 ?예약|발매|한정|컬래버|협업|신상|신제품|신차|최초|로봇", re.I)
NOISE = re.compile(r"review|deal|discount|sale:|best .* (deals|prices)|rumor|leak|vs\.|how to|where to buy|restock", re.I)


def parse_date(s):
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s)
    except Exception:
        try:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (shortform feed reader)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        def g(*names):
            for n in names:
                for ch in it:
                    if ch.tag.split("}")[-1] == n:
                        return (ch.text or ch.get("href") or "").strip()
            return ""
        link = g("link")
        if not link:
            for ch in it:
                if ch.tag.split("}")[-1] == "link" and ch.get("href"):
                    link = ch.get("href")
        items.append({"title": re.sub(r"\s+", " ", g("title")), "link": link, "date": parse_date(g("pubDate", "published", "updated"))})
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=48)
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    brands = json.loads((CONFIG / "brands.json").read_text())
    brand_lane = {b.lower(): lane for lane, bs in brands.items() for b in bs}
    rows, ok = [], []
    for name, url in FEEDS.items():
        try:
            items = fetch(url)
            ok.append(name)
        except Exception as ex:
            print(f"  피드 실패 {name}: {str(ex)[:80]}", file=sys.stderr)
            continue
        for it in items:
            if not it["date"]:
                continue
            hrs = (now - it["date"].astimezone(dt.timezone.utc)).total_seconds() / 3600
            if hrs > a.hours or not LAUNCH.search(it["title"]) or NOISE.search(it["title"]):
                continue
            t = it["title"].lower()
            # 브랜드 매칭: 여러 단어 브랜드는 전체, 한 단어는 단어 경계. 너무 흔한 첫 단어(full·goal·snow·shot·voice·1x)는 전체명만.
            def hit_of(b):
                key = b.lower()
                if " " in key and key.split()[0] in ("full", "goal", "snow", "shot", "voice", "ray-ban", "anker", "garmin", "bushnell", "callaway", "taylormade", "ping", "litter-robot", "unitree", "boston", "figure", "agility"):
                    return re.search(r"\b" + re.escape(key.split()[0]) + r"\b", t) is not None and (key.split()[0] not in ("full", "goal", "snow", "shot", "voice") or key in t)
                return re.search(r"\b" + re.escape(key.split()[0]) + r"\b", t) is not None
            hit = next((b for b in brand_lane if hit_of(b)), None)
            rows.append({**it, "date": it["date"].isoformat(), "source": name, "hours": round(hrs, 1),
                         "brand": hit, "lane": brand_lane.get(hit) if hit else None})
    rows.sort(key=lambda r: r["hours"])  # 2026-10-18: 카테고리 제한 없음 → 최신순
    day = RUNS / now.astimezone().strftime("%Y-%m-%d")
    day.mkdir(exist_ok=True)
    (day / "news.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    md = [f"# 신제품 뉴스 — {day.name} ({a.hours:.0f}h 이내, 피드 {len(ok)}/{len(FEEDS)} 응답)", "",
          "| 경과 | 매체 | 브랜드/레인 | 제목 |", "|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['hours']:.0f}h | {r['source']} | {(r['brand'] or '') + (' · ' + r['lane'] if r['lane'] else '')} | [{r['title'][:90]}]({r['link']}) |")
    md += ["", f"브랜드 매칭 {sum(1 for r in rows if r['lane'])}건 / 전체 {len(rows)}건. 매칭 안 된 기사도 신제품이면 brands.json 에 브랜드 추가."]
    (day / "news.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
