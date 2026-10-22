"""채널 화제성 수집기 — 유튜브에서 '지금 터지는 것'을 조회수로 본다(2026-10-18 사용자: 해외·국내 가장 핫한 키워드 중심, 상위 조회수 분석).
1) 크리에이터·브랜드 쇼츠 탭 최근 30편 중 조회수 상위 (한국 테크·글로벌 테크·패션·차·시계·가전)
2) 유튜브 검색 '이번 주 · 조회수순' (sp=CAMSBAgDEAE%3D) 로 신상·발매 키워드
→ runs/날짜/hot.json, hot.md. 돈 안 듦(yt-dlp 메타만). ponytail: 채널 목록은 여기 상수 — 늘리려면 아래에 핸들 추가.
사용: python3 -I discover/hot.py [--date YYYY-MM-DD]
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YTDLP = str(ROOT / ".venv/bin/yt-dlp")
COOKIES = ROOT / "cookies.txt"
YTDLP_OPTS = ["--cookies", str(COOKIES)] if COOKIES.exists() else []
CREATORS = ["@ITSub", "@techmong", "@UNDERkg", "@Mrwhosetheboss", "@unboxtherapy", "@mkbhd", "@WhatsInsideFamily", "@SupercarBlondie",
            "@Teddybaldassarre", "@dyson", "@nike", "@adidas", "@newbalance", "@VogueKorea", "@hypebeast"]
QUERIES = ["신상", "신제품 출시", "언박싱", "발매", "신차 공개", "new gadget", "new product launch", "unboxing", "first look", "sneaker release", "just launched", "hands on"]
NOISE = re.compile(r"official (video|music|trailer|audio)|trailer|lyrics|song|teaser|episode|full movie|#shorts challenge", re.I)
FMT = "%(view_count)s\t%(duration)s\t%(channel)s\t%(id)s\t%(title)s"
# 10/19 사용자: "최근 48시간 이내 제일 핫한 영상" — 검색은 '오늘'(24h) 필터를 먼저, '이번 주'는 보조. 모든 후보는 업로드 시각으로 48h 필터.
SP_TODAY, SP_WEEK = "CAMSBAgCEAE%253D", "CAMSBAgDEAE%253D"  # 조회수순 + 오늘 / 이번 주
MAX_AGE_H = 48


def age_h(r, now=None):
    """업로드 시각(메타의 upload_date 는 일 단위) → 경과 시간. 모르면 None."""
    up = r.get("upload_date")
    if not up:
        return None
    d = dt.datetime.strptime(up, "%Y%m%d").replace(tzinfo=dt.timezone.utc)
    return round(((now or dt.datetime.now(dt.timezone.utc)) - d).total_seconds() / 3600, 1)


def enrich(rows, n):
    """'오늘' 검색 결과 전부 + 조회수 상위 n개 메타 보강(길이·라이선스·업로드일·가로세로) + age_h."""
    todays = [r for r in rows if r.get("today")]
    top = [r for r in sorted(rows, key=lambda r: -r["views"]) if not r.get("today")][:n]
    for r in todays + top:
        try:
            r.update({k: v for k, v in meta(r["id"]).items() if v is not None})
        except Exception:
            pass
        r["age_h"] = age_h(r)
    return rows
# 해외 바이럴 레인(2026-10-18 사용자: 해외에서 엄청 바이럴되는 영상도 재가공, 하루 1편) — 넓은 키워드로 '이번 주 조회수순'
VIRAL_QUERIES = ["humanoid robot", "new robot", "flying car", "world's first", "world's most expensive", "world's largest", "fastest ever", "new gadget",
                 "crazy invention", "prototype unveiled", "3D printed", "new electric", "supercar", "drone", "new machine", "insane tech", "future tech", "unboxing"]


def api_key():
    for l in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
        if l.startswith("YOUTUBE_API_KEY="):
            return l.split("=", 1)[1].strip()
    return ""


def iso_dur(s):
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else None


def api_get(path, **params):
    import urllib.request
    params["key"] = api_key()
    with urllib.request.urlopen("https://www.googleapis.com/youtube/v3/" + path + "?" + urllib.parse.urlencode(params), timeout=30) as r:
        return json.load(r)


def rows_from_videos(items, src):
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for it in items:
        sn, st, cd = it["snippet"], it.get("statistics", {}), it.get("contentDetails", {})
        pub = dt.datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
        out.append({"views": int(st.get("viewCount") or 0), "duration": iso_dur(cd.get("duration")), "channel": sn["channelTitle"], "id": it["id"],
                    "title": sn["title"], "from": src, "upload_date": pub.strftime("%Y%m%d"), "age_h": round((now - pub).total_seconds() / 3600, 1),
                    "category": sn.get("categoryId"), "lang": sn.get("defaultAudioLanguage") or sn.get("defaultLanguage")})
    return out


# 유튜브 공식 인기 차트(국가×카테고리, 1단위/호출) — 10/20 사용자: "지금 조회수 미친 듯 터진 영상"을 직접 본다
POP_REGIONS = ["KR", "US", "GB", "JP"]
POP_CATS = {None: "전체", "28": "과학기술", "2": "자동차", "26": "노하우·스타일", "24": "엔터"}
WOW_SEARCH = ["humanoid robot", "flying car", "world's first", "world's most expensive", "world's largest", "new robot", "crazy invention",
              "prototype unveiled", "new gadget", "new electric car", "insane tech", "future tech", "3D printed", "new drone"]


def popular():
    out = []
    for rg in POP_REGIONS:
        for cat, name in POP_CATS.items():
            try:
                p = {"part": "snippet,statistics,contentDetails", "chart": "mostPopular", "regionCode": rg, "maxResults": 50}
                if cat:
                    p["videoCategoryId"] = cat
                out += rows_from_videos(api_get("videos", **p).get("items", []), f"인기차트:{rg}/{name}")
            except Exception as ex:
                print(f"  인기차트 실패 {rg}/{name}: {str(ex)[:80]}", file=sys.stderr)
    seen, uniq = set(), []
    for r in sorted(out, key=lambda r: -r["views"]):
        if r["id"] not in seen:
            seen.add(r["id"]); uniq.append(r)
    return uniq


def api_search(q, hours=48, n=25):
    """search.list(조회수순, 48h 이내) + videos.list(통계). 100+1 단위."""
    after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = [i["id"]["videoId"] for i in api_get("search", part="id", q=q, type="video", order="viewCount", publishedAfter=after, maxResults=n).get("items", [])]
    if not ids:
        return []
    return rows_from_videos(api_get("videos", part="snippet,statistics,contentDetails", id=",".join(ids)).get("items", []), f"API검색:{q}")


def meta(vid):
    """길이·라이선스·업로드일·가로세로 — 영상 1개당 요청 1회."""
    out = subprocess.run([YTDLP, *YTDLP_OPTS, "--no-warnings", "--socket-timeout", "20", "--skip-download", "--print", "%(duration)s\t%(license)s\t%(upload_date)s\t%(width)s\t%(height)s\t%(channel)s",
                          f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True, timeout=90).stdout.strip().split("\t")
    if len(out) < 6:
        return {}
    d, lic, up, w, hh, ch = out
    return {"duration": float(d) if d.replace(".", "").isdigit() else None, "license": None if lic in ("NA", "None", "") else lic,
            "upload_date": up if up != "NA" else None, "width": int(w) if w.isdigit() else None, "height": int(hh) if hh.isdigit() else None, "channel": ch}


def ytp(url, n):
    out = subprocess.run([YTDLP, *YTDLP_OPTS, "--no-warnings", "--socket-timeout", "20", "--flat-playlist", "--playlist-end", str(n), "--print", FMT, url],
                         capture_output=True, text=True, timeout=180).stdout
    rows = []
    for line in out.splitlines():
        p = line.split("\t", 4)
        if len(p) < 5 or not p[0].isdigit():
            continue
        rows.append({"views": int(p[0]), "duration": float(p[1]) if p[1].replace(".", "").isdigit() else None, "channel": p[2] if p[2] != "NA" else "", "id": p[3], "title": p[4]})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    a = ap.parse_args()
    creators, search = [], []
    for ch in CREATORS:
        try:
            rows = ytp(f"https://www.youtube.com/{ch}/shorts", 12)  # 쇼츠 탭은 최신순 → 최신 12편 메타 확인 후 48h 안 것만(10/19)
            creators += [{**r, "from": ch} for r in rows]
        except Exception as ex:
            print(f"  쇼츠 실패 {ch}: {str(ex)[:80]}", file=sys.stderr)
    for q in QUERIES:
        try:
            rows = [{**r, "today": True} for r in ytp(f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&sp={SP_TODAY}", 10) if r["views"] >= 20000] + \
                   ytp(f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&sp={SP_WEEK}", 6)
            search += [{**r, "from": f"검색:{q}"} for r in rows if (r["duration"] or 0) <= 1200 and not NOISE.search(r["title"])]
        except Exception as ex:
            print(f"  검색 실패 {q}: {str(ex)[:80]}", file=sys.stderr)
    viral, seen = [], set()
    for q in VIRAL_QUERIES:
        try:
            for r in [{**r, "today": True} for r in ytp(f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&sp={SP_TODAY}", 10)] + ytp(f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&sp={SP_WEEK}", 6):
                if r["views"] >= 300_000 and (r["duration"] or 0) <= 600 and not NOISE.search(r["title"]) and r["id"] not in seen:  # 48h 기준이라 30만부터(10/19)
                    seen.add(r["id"]); viral.append({**r, "from": f"바이럴:{q}"})
        except Exception as ex:
            print(f"  바이럴 검색 실패 {q}: {str(ex)[:80]}", file=sys.stderr)
    # API 검색(48h·조회수순) 으로 바이럴 풀 보강
    if api_key():
        for q in WOW_SEARCH:
            try:
                viral += [{**r, "today": True} for r in api_search(q, 48, 25) if r["views"] >= 300_000 and (r["duration"] or 0) <= 600 and not NOISE.search(r["title"]) and r["id"] not in seen]
                seen |= {r["id"] for r in viral}
            except Exception as ex:
                print(f"  API 검색 실패 {q}: {str(ex)[:80]}", file=sys.stderr)
    viral.sort(key=lambda r: -r["views"])
    viral = viral[:60]
    pop = popular() if api_key() else []
    print(f"인기차트 {len(pop)}편 (48h 이내 {sum(1 for r in pop if r['age_h'] <= MAX_AGE_H)})")
    enrich(creators, len(creators))
    creators = [r for r in creators if r.get("age_h") is not None and r["age_h"] <= MAX_AGE_H]  # 채널은 48h 안 것만 남김
    seen_s, uniq = set(), []
    for r in sorted(search, key=lambda r: -r["views"]):
        if r["id"] not in seen_s:
            seen_s.add(r["id"]); uniq.append(r)
    search = enrich(uniq, 40)
    enrich(viral, 30)
    fresh = lambda rows: [r for r in rows if r.get("age_h") is not None and r["age_h"] <= MAX_AGE_H]
    print(f"48h 이내: 채널 {len(fresh(creators))}/{len(creators)}, 검색 {len(fresh(search))}/{len(search)}, 바이럴 {len(fresh(viral))}/{len(viral)}")
    day = ROOT / "runs" / a.date
    day.mkdir(parents=True, exist_ok=True)
    (day / "hot.json").write_text(json.dumps({"generated": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "creators": creators, "search": search, "viral": viral, "popular": pop}, ensure_ascii=False, indent=1))
    md = [f"# 유튜브 인기 — {a.date} (48시간 이내 우선)", "", "| 조회 | 경과 | 출처 | 채널 | 제목 |", "|---|---|---|---|---|"]
    allr = sorted(creators + search, key=lambda r: (not (r.get("age_h") is not None and r["age_h"] <= MAX_AGE_H), -r["views"]))
    for r in allr[:60]:
        md.append(f"| {r['views']:,} | {r['age_h'] if r.get('age_h') is not None else '?'}h | {r['from']} | {r['channel']} | [{r['title'][:70]}](https://youtu.be/{r['id']}) |")
    md += ["", "## 유튜브 인기 차트(KR·US·GB·JP × 전체·과학기술·자동차·노하우·엔터, 48h 이내 우선)", "", "| 조회 | 경과 | 차트 | 채널 | 제목 |", "|---|---|---|---|---|"]
    for r in sorted(pop, key=lambda r: (r["age_h"] > MAX_AGE_H, -r["views"]))[:80]:
        md.append(f"| {r['views']:,} | {r['age_h']}h | {r['from']} | {r['channel']} | [{r['title'][:70]}](https://youtu.be/{r['id']}) |")
    md += ["", "## 해외 바이럴(조회수순, 30만+, 48시간 이내 우선)", "", "| 조회 | 채널 | 길이 | 업로드 | 라이선스 | 제목 |", "|---|---|---|---|---|---|"]
    for r in sorted(viral, key=lambda r: (not (r.get("age_h") is not None and r["age_h"] <= MAX_AGE_H), -r["views"])):
        md.append(f"| {r['views']:,} | {r.get('channel', '')} | {int(r['duration']) if r.get('duration') else '?'}s | {r.get('upload_date') or '?'} | {('CC' if 'Creative' in str(r.get('license')) else '표준')} | [{r['title'][:70]}](https://youtu.be/{r['id']}) |")
    (day / "hot.md").write_text("\n".join(md))
    print(f"인기 {len(creators)}(채널) + {len(search)}(검색) + 바이럴 {len(viral)} + 차트 {len(pop)} → {day / 'hot.md'}")


if __name__ == "__main__":
    main()
