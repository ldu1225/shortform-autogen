# 무인 숏폼 제너레이터 (shortform-autogen)

> **TL;DR (EN)** — An unattended pipeline that turns "just-launched product" news into Korean short-form vertical videos (Reels/Shorts) every morning: it discovers hot products (RSS + YouTube charts), scores them for "wow", writes a plain-language script with Gemini (search-grounded), picks clean cuts from the maker's official footage with vision checks, renders a React motion-graphics template frame-by-frame in headless Chromium, mixes Google TTS + Lyria BGM + synthesized SFX, runs QA, and emails the finished reels with captions. Built in six days (2026-10-17 → 10-22), ran on macOS launchd and then on a self-starting GCE VM. Paused when YouTube began blocking video downloads from cloud IPs. The code, the rules, and the 60+ recorded lessons are the portfolio.

매일 아침, 사람 손 없이 "세상에 갓 나온 물건" 3편을 28~36초 세로 영상으로 만들어 메일로 보내는 시스템입니다. 소재 발굴 → 선정 → 대본 → 소재 영상 확보 → 컷 선정 → 렌더 → QA → 발송까지 전부 코드이고, 돈이 드는 호출은 편당 300원 안팎입니다. 채널명·핸들·로고는 운영자 설정(`.env`, `props.logoText`)이며 저장소에는 포함하지 않습니다.

<p align="center">
  <img src="docs/images/reel_porsche.jpg" width="100%" alt="포르쉐 미션 S 편 필름스트립">
  <br><sub>포르쉐 미션 S 콘셉트 편(33초). 레이아웃 인트로 → 자막 동기화 본편 → 아웃트로. 소스는 포르쉐 공식 영상 2개를 섞음. 우상단 배지는 가림.</sub>
</p>

---

## 1. 무엇을 만들었나

| 단계 | 하는 일 | 핵심 기술 |
|---|---|---|
| **D1 발굴** | 36개 매체 RSS(테크·패션·자동차·발명) + 브랜드 공식 유튜브 RSS 55채널 + **유튜브 공식 인기 차트**(4개국 × 5카테고리, Data API) + 48시간 조회수순 검색 | `discover/news.py` `collect.py` `hot.py` |
| **D2 선정** | Gemini 3.1 Pro(구글 검색 그라운딩)가 48시간 내 발표된 '물건' 8개를 뽑고, **독립 심사(Flash)가 와우 점수**를 다시 매겨 7점 미만 탈락. 유튜브 '오늘' 조회수로 화제성 재정렬. 부족하면 14일 창으로 2차 | `auto/plan.py: pick / judge_wow / heat_rank` |
| **P2 소재** | 제작사·브랜드·연구기관 **공식 채널 영상만** 확보(메인 + 전작·행사 등 맥락 영상, 토픽당 최대 3개). 제품명 토큰·브랜드 토큰으로 채널 매칭 | `official_videos / viral_videos` |
| **P2 컷** | 9:16 타일 시트를 Gemini 비전에 보여 컷 선정 → **검은 프레임(ffmpeg 밝기)·사람 주인공·자막 글자**를 다시 검사해 ±40초 안에서 교정, 절반 이상 못 고치면 소재 폐기 | `choose_cuts / verify_cuts / burned_subtitles` |
| **P1 대본** | 14개 레이아웃 중 정보 형태에 맞는 것 선택, "중학생이 한 번 듣고 이해" 규칙, 외화는 원화 환산(일일 환율), **대본의 모든 숫자는 출처 facts 에 있어야 함**(없으면 1회 재작성) | `write_spec / unsourced_numbers` |
| **P3 렌더** | React 템플릿(claude.ai/design 산출물)을 **헤드리스 크로미움에서 프레임 단위 캡처**(1080×1920 30fps). TTS → STT 되읽기 검증 → 단어 오프셋으로 자막·컷 경계 동기화. Lyria BGM 사이드체인 덕킹, 합성 효과음 6종, 색보정, 엔드카드(선택) | `produce/render/design_reel.py` `reel-template.jsx` |
| **P4 QA** | 해상도·fps·길이(20~40초)·LUFS(-14~-11)·핸들·**세 자리 이상 숫자 전부 출처 대조** | `produce/qa.py` |
| **발송** | 편당 메일 1통(제목 + 바로 붙여넣는 캡션 + 출처 + 와우 점수 + QA 경고). 18MB 초과 시 자동 축소. 이미 보낸 파일은 재발송 안 함 | `auto/send.py` |

<p align="center">
  <img src="docs/images/layouts.jpg" width="100%" alt="레이아웃 예시">
  <br><sub>14개 레이아웃 중 drop · collab · colorway · stat · question. 테마 3종(dark/tint/neon) × 팔레트 8색 × 전환 3종 × 보이스 5종으로 조합을 늘림.</sub>
</p>

<p align="center">
  <img src="docs/images/reel_tesla.jpg" width="49%" alt="테슬라 로드스터 편"> <img src="docs/images/reel_amg.jpg" width="49%" alt="메르세데스 AMG 전기 SUV 편">
  <br><sub>왼쪽: 테슬라 로드스터(유튜브 7일 조회 합 4,984만, 화제성 1위로 자동 선정). 오른쪽: AMG 전기 SUV — 공식 영상 2개를 번갈아 섞은 편.</sub>
</p>

## 2. 아키텍처

```
          RSS 36개 · 브랜드 채널 RSS 55 · YouTube 인기차트/검색(API) · 환율 API
                                   │
                        discover/  news.py · collect.py · hot.py
                                   ▼
   ┌──────────── auto/plan.py (하루 러너, 제한시간 110분) ─────────────┐
   │ pick(Gemini 3.1 Pro + Google Search) ─▶ judge_wow(Flash) ─▶ heat_rank │
   │ official_videos(yt-dlp, 메인+맥락) ─▶ choose_cuts(비전) ─▶ verify_cuts │
   │ write_spec(대본·캡션·제목, 숫자 사전검사) ─▶ make_spec(accent 가드·테마) │
   │ render ─▶ qa ─▶ outbox/ (실패 시 숫자 한글화·컷 당김·속도 보정 재시도)    │
   └──────────────────────────────┬──────────────────────────────────────┘
                                  ▼
    produce/render/design_reel.py   TTS(gemini-3.1-flash-tts) → STT 되읽기 검증 → 정렬
                                    base.mp4(ffmpeg 9:16 크롭·색보정) → Chromium 프레임 캡처
                                    Lyria BGM + SFX + 덕킹 믹스 → x264 CRF14 → 엔드카드(선택)
                                  ▼
    auto/send.py  (Gmail SMTP)  ←  runs/날짜/outbox/*.mp4 + *.txt
```

실행 환경 두 가지를 거쳤습니다.
- **macOS launchd**(10/17~10/19): 06:00 제작, 08:00 발송. Desktop 아래에 두면 TCC 때문에 조용히 멈추는 것, 맥이 잠들면 DarkWake 45초 창에서만 진행되는 것을 겪음.
- **GCE 자동 기동 VM**(10/20~): 인스턴스 스케줄이 05:55에 켜고 systemd 가 `deploy/run_daily.sh`(제작 → 발송 → poweroff)를 실행, 150분 감시 타이머가 공회전을 막음. 자세한 건 [`deploy/README.md`](deploy/README.md).

## 3. 돌려보기

```bash
cp .env.example .env            # GCP_PROJECT, MAIL_TO, GMAIL_APP_PASSWORD, CHANNEL_NAME, HANDLE, (선택) YOUTUBE_API_KEY
python3 -m venv .venv && .venv/bin/pip install playwright pillow yt-dlp
.venv/bin/python -m playwright install --with-deps chromium   # macOS 는 설치된 Chrome 을 씀
gcloud auth login                # Vertex AI(Gemini·Lyria), Cloud TTS/STT 가 켜진 프로젝트

python3 -I auto/plan.py --want 3 --viral 1 --dry-pick   # 수집 + 선정만(후보·와우 점수 확인)
python3 -I auto/plan.py --want 3 --viral 1              # 제작까지 → runs/날짜/outbox/
python3 -I auto/send.py --date 2026-10-20 --wait 0      # 메일 발송
python3 -I auto/rewrite.py runs/2026-10-20 auto1        # 컷은 두고 대본만 현재 규칙으로 재작성·재렌더
```

- 비용(편당 추정): TTS+STT ≈ $0.03, Lyria $0.04, Gemini Pro 선정·대본·컷 ≈ $0.10~0.20, 단순 비전 검사는 Flash. 합계 ≈ $0.25. 렌더는 로컬 CPU(e2-standard-8 기준 5분/편).
- 비밀값은 `.env` 에만 둡니다. 코드·로그·대화에 넣지 않는 것이 규칙입니다.

## 4. 규칙 문서 (프로세스가 곧 제품)

- [`LESSONS.md`](LESSONS.md) — 날짜별 레슨 60여 건. "이상 징후 1건 = 레슨 1건 + 같은 날 코드나 규칙 변경"이 원칙.
- [`RESEARCH.md`](RESEARCH.md) — 돈 되는 소재(제휴 카테고리 수수료율, 브랜드 제휴율), 상위 조회 쇼츠 8편 분석(필름스트립·컷 검출), 영상미 업그레이드 설계.
- [`produce/SPEC_RULES.md`](produce/SPEC_RULES.md) — 14개 레이아웃 선택 순서, 대본 길이·눈높이·숫자 출처 규칙.
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — 운영 당시 단계별 게이트·명령·자동화 대기 목록(대시보드 시절 내용 일부 포함).

## 5. 배운 것 (요약)

1. **검증은 기계가 잘 듣는 조건에서.** 1.5배속 TTS 를 STT 로 되읽으면 멀쩡한 음성을 버린다 → 검증·정렬은 1.0배, 재생만 atempo.
2. **시간축을 밀면 그 축을 보는 값도 전부 민다.** 훅 장면을 앞에 붙이자 진행바가 깨졌다(bodyTimes/cardAt 미보정).
3. **모델이 고른 것은 코드가 검증한다.** 빈 목록을 주면 영상 id 를 지어내고, 자기 와우 점수는 후하며(시계 7점), 발표일은 기억으로 쓴다(1년 전 제품을 '어제 발표') → 목록 대조·독립 심사·공식 영상 45일 규칙.
4. **컷 검사는 '글자 없음'이 아니라 '제품이 크고 밝게 보이는가'.** 도입부 6초 검은 화면, 사람 상반신만 나오는 로봇 편을 겪고 밝기·사람·글자 3중 검사로.
5. **조회수와 재가공 가능성은 별개.** 740만 뷰 쇼츠도 자막이 가운데 박히면 못 쓴다 → 바이럴은 '무엇이 터졌나'의 신호, 영상은 제작사 채널에서.
6. **무인 자동화의 전제는 꺼지지 않는 실행 환경.** 노트북 DarkWake, 토큰 1시간 만료, `grep -q 1` 이 404 본문의 "v1"에 걸려 매일 작업을 건너뛰고 31시간 공회전한 사고까지 — 전부 레슨에 있음.
7. **"짧고 빠르게"는 내 가정이었다.** 시청자 기준은 "읽히고 이해되는가" → 나레이션 1.1배, 장면 최소 길이, 한글 단어 중간 줄바꿈 금지(keep-all), 외화는 반드시 원화 환산.

## 6. 현재 상태와 다음 단계

- **2026-10-22 중단.** 유튜브가 클라우드 IP 의 개별 영상 조회·다운로드를 봇으로 차단("Sign in to confirm you're not a bot")하면서 서버에서 공식 영상을 받을 수 없게 됨. 선정은 정상(휴머노이드 로봇, 플라잉카 등을 뽑음)이었으나 소스 확보 단계에서 전부 탈락. 클라우드 자원은 전부 삭제.
- 다시 돌리려면: `cookies.txt`(유튜브 로그인 쿠키, 버리는 계정 권장)를 저장소 루트에 두면 모든 yt-dlp 호출이 자동으로 사용. 또는 주거용 프록시.
- 남은 과제: 패션·신발처럼 공식 영상이 드문 카테고리의 소스 확보, 편수 vs 와우 기준의 트레이드오프, 업로드 API 연동(유튜브·인스타), 성과 지표 수집.

## 7. 저장소 구성

```
auto/        plan.py(하루 러너) · send.py(메일) · rewrite.py(대본 재작성) · vx.py(Vertex 호출·토큰 갱신·재시도)
discover/    news.py(RSS) · collect.py(브랜드 유튜브 RSS) · hot.py(인기 차트·검색·메타)
produce/     render/(design_reel.py · reel-template.jsx · animations-v3.jsx · fonts · sfx) · qa.py · sources.py · SPEC_RULES.md
config/      brands.json · channels.json
deploy/      GCE 설정·동기화·부팅 실행·감시 타이머 스크립트
docs/        OPERATIONS.md · images/
```

템플릿의 폰트(Pretendard, Anton, Unbounded)는 SIL OFL 1.1. 코드는 MIT.
