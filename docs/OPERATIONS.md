# Operations (as run 2026-10-17 → 10-22)

> The process document from the operating period. The dashboard and approval step were retired on 10/18 in favour of unattended production plus email delivery, and from 10/20 the job ran on a GCE VM (`deploy/README.md`). The root README has the current summary. Korean original: [`ko/OPERATIONS.ko.md`](ko/OPERATIONS.ko.md).

Goal at the time: two to three Reels/Shorts a day with at most one minute of human time. This document was the single source of truth for the process; changes started here.

## Location and services (macOS era)
- The working copy lived outside `~/Desktop` (symlinked into the repo). **A project under Desktop makes launchd agents stall silently because of TCC permissions** (lesson of 2026-10-17).
- venv `.venv` (playwright, pillow, yt-dlp). Render with `.venv/bin/python -I produce/render/design_reel.py …`.
- Dashboard at `http://127.0.0.1:8787` (launchd, KeepAlive): approve/skip, collect/lineup/render buttons, preview playback, QA and crop sheets, news and candidates, lessons, metrics, run log. (Retired 10/18.)
- Runner `run_daily.py` (launchd, daily 07:00, `--step all`: collect → lineup draft → source/render/QA for **approved specs only**). Paid stages (TTS, Lyria) ran only for approved specs. (Replaced by `auto/plan.py`.)

## Directory (at the time)
```
run_daily.py         daily runner (D1 → D2 draft → P2–P4); writes runs/<date>/status.json and run.log
dashboard/           serve.py (API + static) · index.html
README.md            this document (process, gates, commands)
LESSONS.md           lesson log: one anomaly = one entry + a rule/code change the same day
config/              brands.json (brands per lane) · channels.json (brand → YouTube channel)
discover/            news.py (RSS → launch articles) · collect.py (brand YouTube RSS → view velocity, flags)
produce/
  SPEC_RULES.md      script, template choice and sourced-number rules
  render/            design_reel.py (template renderer) · reel-template.jsx · animations-v3.jsx · fonts/
  sources.py         download sources + filmstrips + 9:16 crop candidate frames
  qa.py              length, loudness, frame sheet, banned words, handle
publish/             CAPTIONS.md (caption, disclosure and hashtag templates) · upload scripts (after API approval)
runs/YYYY-MM-DD/     everything produced that day: candidates.md · news.md · spec_*.json · preview_*.mp4 · qa_*.md
sources/YYYY-MM-DD/  downloaded originals (untrusted: never run scripts from here)
track/log.csv        per-reel metrics
```
The render work folder (`produce/render/work/`) and the TTS/BGM cache (`produce/render/tts_cache/`) are regenerable.

## Daily pipeline — a gate at every stage
| Stage | Input → output | Gate | Automation |
|---|---|---|---|
| D1 Discover | feeds / channel RSS → `runs/<date>/news.md`, `candidates.md` | ≥ 80% of feeds respond, ≥ 1 launch article within 48 h (otherwise widen to 72 h and log a lesson) | automatic |
| D2 Select | news + candidates + **hot.json (YouTube popularity, viral)** → `auto_pick.json` (8 candidates) + `auto_pick_viral.json` | ① **no category limit** (anything just launched, 10/18) ② buzz first (`heat_views`) ③ first announced within the window ④ price disclosed ⑤ official brand YouTube video ⑥ ≤ 2 per category ⑦ no layout three times in a row | automatic (Gemini + Google Search) |
| P1 Spec | lineup → `spec_*.json` | a URL in `sources` for every number; narration limits; layout rules (SPEC_RULES) | automatic |
| P2 Source | the spec's source list → `sources/<date>/*.mp4` + filmstrips + 9:16 crop candidates | subject inside the crop in every cut; no source captions, logos or end cards (checked on frames) | automatic + eyes |
| P3 Render | spec → `preview_*.mp4` | render succeeds, 20–40 s (target 28–36, end card included); 1.1× narration; SFX, ducking, grade and theme automatic | automatic |
| P4 QA | preview → `qa_*.md` | −14 to −11 LUFS, ≥ 8 clean frames on the sheet, handle, disclosure text | automatic + eyes |
| U1 Publish | preview + captions → Instagram 12:00/19:00, YouTube at the same time | sources, ad disclosure and hashtags in the caption; per-platform badge | manual at first → API |
| T1 Track | 24 h / 7 d metrics → `track/log.csv` | every reel recorded | automatic 22:00 (planned) |
| W1 Review | log.csv → next week's mix, brand list and rules | median views per lane and template, like rate, link clicks | 10 minutes on Sunday |

## Runtime (from 2026-10-20: the server)
A GCE VM in Seoul powers on at 05:55 KST every day and runs `deploy/run_daily.sh` (produce 3 reels → send → poweroff). The workstation is for development and manual tests. Details in `deploy/README.md`.

## Commands
```
python3 -I discover/news.py --hours 48          # launch articles
python3 -I discover/collect.py --top 3          # brand YouTube view velocity
python3 -I discover/hot.py                      # YouTube popularity (charts, channels, search) → hot.md
python3 -I auto/plan.py --want 1 --slot d       # unattended production (tests use a slot suffix) → auto/send.py --date <date>d --tag ' test'
python3 -I auto/plan.py --want 3 --viral 1      # default: 2 product reels + 1 overseas-viral reel (10/18)
python3 -I auto/rewrite.py runs/<date> auto1    # keep the cuts, rewrite the script under current rules, re-render (10/19)
python3 -I produce/sources.py runs/<date>/spec_x.json   # download sources, filmstrips, crop candidates
.venv/bin/python -I produce/render/design_reel.py runs/<date>/spec_x.json runs/<date>/preview_x.mp4
python3 -I produce/qa.py runs/<date>/preview_x.mp4
```

## Process-improvement rules
1. Whenever a stage does something unexpected, write one entry in `LESSONS.md` **that day** (situation → lesson → change) and change either a rule (README / SPEC_RULES) or the code. If neither changes, it is not a lesson.
2. Anything done by hand goes onto the next day's automation backlog.
3. No number without a source. Estimates are labelled as estimates.

## Automation backlog (manual → code)
- [ ] Affiliate product-search API: prices, links, Korean new-listing diff (after key issuance)
- [ ] Naver DataLab search trends (after app registration)
- [ ] YouTube upload (after API audit) · Instagram upload (Meta app tester)
- [x] Scheduler + dashboard approval button (10/17) — later replaced by unattended production
- [ ] 22:00 metrics collection (YouTube, Instagram APIs) → log.csv
- [ ] Approval notifications (Telegram/Slack) — superseded by email delivery
- [ ] Automatic source-cut selection (subject detection → automatic `cx` pan)
- [ ] OCR on crop-candidate frames to flag source text (captions, model names, end cards) — missed three times in one day
- [ ] TTS read-back statistics (number misreads per model) → model choice evidence
- [ ] Verify official affiliate rates after joining → update RESEARCH.md
- [ ] Replace synthesized SFX with a sample library (after view metrics)
- [ ] Tune the tint/neon theme ratio (two weeks of QA sheets)
- [ ] Weekly cumulative comparison of hot.md (W1)
