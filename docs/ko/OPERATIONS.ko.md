> 운영 당시(2026-10-17~22)의 프로세스 문서. 대시보드·승인 단계는 10/18 에 폐기되고 무인 제작 + 메일 발송으로 바뀌었으며, 10/20 부터는 GCE VM 에서 돌았다(`deploy/README.md`). 최신 요약은 루트 README 를 본다.

# 채널 (@channel) 운영 시스템

"비싼 신상 가젯 뉴스" 릴스·쇼츠를 매일 2편, 사람 손은 승인 1분. 이 문서가 프로세스의 단일 출처다. 바꿀 때는 여기부터 고친다.

## 위치와 서비스
- 실제 위치 `~/shortform` (레포의 `dropflow/shortform` 은 심볼릭 링크). **Desktop 아래 두면 launchd 에이전트가 TCC 권한 때문에 조용히 멈춘다**(2026-10-17 교훈).
- venv `~/shortform/.venv` (playwright·pillow·yt-dlp). 렌더는 `.venv/bin/python -I produce/render/design_reel.py …`
- 대시보드 **http://127.0.0.1:8787** — launchd `com.shortform.dashboard`(KeepAlive). 승인/스킵, 수집·라인업·렌더 버튼, 미리보기 재생, QA·크롭 시트, 뉴스·후보, 레슨, 지표, 실행 로그.
- 러너 `run_daily.py` — launchd `com.shortform.daily` 매일 07:00 `--step all`(수집 → 라인업 초안 → **승인된 스펙만** 소스·렌더·QA). plist: `~/Library/LaunchAgents/com.shortform.*.plist`, 로그 `logs/`.
- 돈이 드는 단계(TTS·Lyria)는 대시보드에서 승인한 스펙에만 실행된다.

## 디렉터리
```
shortform/
  run_daily.py         하루 러너(D1→D2 초안→P2~P4), runs/날짜/status.json·run.log 기록
  dashboard/           serve.py(API+정적) · index.html
  README.md            ← 이 문서(프로세스·게이트·명령)
  LESSONS.md           ← 레슨런 로그. 이상 징후 1건 = 항목 1개 + 같은 날 규칙/코드 반영
  config/              brands.json(레인별 브랜드) · channels.json(브랜드→유튜브 채널) · feeds.json(매체 RSS)
  discover/            news.py(뉴스 RSS→출시 기사) · collect.py(브랜드 유튜브 RSS→조회속도·플래그)
  produce/
    SPEC_RULES.md      대본·템플릿 선택·숫자 출처 규칙
    render/            design_reel.py(디자인 템플릿 렌더) · reel-template.jsx · animations-v3.jsx · fonts/
    sources.py         소재 다운로드 + 필름스트립 + 9:16 크롭 후보 프레임
    qa.py              길이·음량·프레임 시트·금칙어·핸들 검사
  publish/             CAPTIONS.md(캡션·고지·해시태그 템플릿) · upload_yt.py · upload_ig.py (API 승인 후)
  runs/YYYY-MM-DD/     그날의 산출물 전부: candidates.md · news.md · lineup.md · spec_*.json · preview_*.mp4 · qa_*.md · 올린 URL
  sources/YYYY-MM-DD/  다운로드한 원본(신뢰 안 함: 스크립트는 여기서 실행하지 않는다)
  track/log.csv        편별 지표
```
렌더 작업 폴더(`produce/render/work/`)와 TTS·BGM 캐시(`produce/render/tts_cache/`)는 재생성 가능.

## 하루 파이프라인 — 단계마다 게이트
| 단계 | 입력 → 출력 | 통과 조건(게이트) | 자동화 |
|---|---|---|---|
| D1 발굴 | feeds/채널 RSS → `runs/날짜/news.md`, `candidates.md` | 피드 응답 ≥ 80%, 48h 출시 기사 ≥ 1건(없으면 "오늘은 72h"로 확장하고 LESSONS에 기록) | 자동 07:00 |
| D2 선정 | news + candidates + **hot.json(유튜브 7일 인기·바이럴)** → `auto_pick.json` 8후보 + `auto_pick_viral.json` 3후보 | ① **카테고리 제한 없음**(신상 물건이면 전부, 10/18) ② 1순위 화제성(`heat_views`) ③ 10일 이내 첫 공개 ④ 가격 공개 ⑤ 브랜드 공식 유튜브 영상 ⑥ 같은 카테고리 ≤ 2 ⑦ 같은 레이아웃 연속 3편 금지 | 자동(Gemini + 구글 검색) |
| P1 스펙 | lineup → `spec_*.json` | 숫자마다 `sources`에 URL, 나레이션 ≤ 3.5/9/3초, 레이아웃 규칙(SPEC_RULES) | Claude |
| P2 소재 | spec의 소스 목록 → `sources/날짜/*.mp4` + 필름스트립 + 9:16 크롭 후보 프레임 | 모든 컷에서 피사체가 크롭 안에, 소스 자막·로고·엔드카드 없음(프레임으로 확인) | 자동 + 눈 |
| P3 렌더 | spec → `preview_*.mp4` | 렌더 성공, 길이 20~40초(목표 28~36, 엔드카드 포함). 나레이션 1.1배, 효과음·덕킹·색보정·테마 자동 | 자동 |
| P4 QA | preview → `qa_*.md` | 음량 -11~-14 LUFS, 프레임 시트 8장 이상 무결점, 핸들 @channel, 광고 고지 문구 | 자동 + 눈 |
| U1 게시 | preview + CAPTIONS → 인스타 12:00/19:00, 유튜브 동시 | 캡션에 출처·[광고] 고지·해시태그, 플랫폼별 배지 렌더 | 손(초기) → API |
| T1 추적 | 24h/7d 지표 → `track/log.csv` | 매 편 기록 | 자동 22:00 |
| W1 리뷰 | log.csv → 다음 주 비중·브랜드 목록·규칙 | 레인·템플릿별 중위 조회, 좋아요율, 링크 클릭 | 일요일 10분 |

## 실행 환경 (2026-10-20부터 서버)
GCE `shortform-worker`(서울)가 매일 05:55 KST 에 켜져 `deploy/run_daily.sh`(제작 3편 → 발송 → 종료)를 돌린다. 맥은 개발·수동 테스트용. 상세 `deploy/README.md`.

## 명령
```
python3 -I run_daily.py --step all              # 07:00 자동과 동일 (collect|lineup|produce)
python3 -I discover/news.py --hours 48          # 출시 기사
python3 -I discover/collect.py --top 3          # 브랜드 유튜브 조회속도
python3 -I discover/hot.py                      # 유튜브 7일 인기(쇼츠 15채널 + 검색 11개) → hot.md (10/18)
python3 -I auto/plan.py --want 1 --slot d       # 무인 제작(테스트는 slot 으로 분리) → auto/send.py --date 날짜d --tag ' 테스트'
python3 -I auto/plan.py --want 3 --viral 1      # 기본: 제품 2편 + 해외 바이럴 재가공 1편 (10/18)
python3 -I auto/rewrite.py runs/날짜 auto1        # 컷은 두고 대본만 현재 규칙으로 다시 써 재렌더 (10/19)
python3 -I produce/sources.py runs/날짜/spec_x.json   # 소재 다운로드·스트립·크롭 후보
.venv/bin/python -I produce/render/design_reel.py runs/날짜/spec_x.json runs/날짜/preview_x.mp4
python3 -I produce/qa.py runs/날짜/preview_x.mp4
```
venv: `~/shortform/.venv`. 대시보드 버튼이 같은 명령을 백그라운드로 실행한다.

## 프로세스 개선 규칙
1. 어느 단계든 "예상과 다름"이 나오면 **그날** `LESSONS.md`에 1항목(상황→교훈→적용) 쓰고, 규칙(README/SPEC_RULES) 또는 코드 중 하나를 바꾼다. 둘 다 안 바꾸면 레슨이 아니다.
2. 사람이 손으로 한 일은 다음 날 자동화 후보에 올린다(README 끝 "자동화 대기" 목록).
3. 숫자는 출처 없으면 안 쓴다. 추정치는 "추정"이라고 쓴다.

## 자동화 대기 (손으로 하는 것 → 코드로)
- [ ] 쿠팡 파트너스 상품 검색 API: 가격·링크·국내 신상 diff (키 발급 후)
- [ ] 네이버 데이터랩 검색 추세 (앱 등록 후)
- [ ] 스펙 자동 생성(Claude API, SPEC_RULES 프롬프트)
- [ ] 유튜브 업로드(API 감사 후) · 인스타 업로드(Meta 앱 테스터)
- [x] 07:00 스케줄러(launchd) · 대시보드 승인 버튼 (10/17)
- [ ] 22:00 지표 수집(유튜브·인스타 API) → log.csv 자동
- [ ] 승인 알림(텔레그램/슬랙) — 지금은 대시보드를 열어야 보임
- [ ] 소스 컷 자동 선택(피사체 검출로 cx 팬 자동)
- [ ] 크롭 후보 프레임 OCR로 소스 텍스트(자막·모델명·엔드카드) 자동 플래그 — 10/17 하루에 세 번 놓침
- [ ] TTS 되읽기 통계(모델별 숫자 오독률) 누적 → 모델 선택 근거
- [ ] **맥 새벽 깨우기(사용자, 1회)**: `sudo pmset repeat wakeorpoweron MTWRFSU 05:58:00` — 전원 연결 상태에서 05:58 완전 기상. 실행 중 잠들기는 plan.py 의 caffeinate 가 막음(10/19 사고)
- [ ] 쿠팡 파트너스 가입 후 공식 수수료율 확인 → RESEARCH.md 표 갱신(사용자)
- [ ] 효과음 합성 → 샘플 라이브러리 교체(조회 지표 본 뒤)
- [ ] 테마 tint/neon 비율 조정(QA 시트 2주 관찰)
- [ ] hot.md 주간 누적 비교(W1)
