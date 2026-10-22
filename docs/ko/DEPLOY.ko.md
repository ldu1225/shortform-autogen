# 서버 배포 (GCE, 2026-10-20)
- VM: `shortform-worker` (asia-northeast3-a, e2-standard-8, Debian 12, 50GB). 인스턴스 스케줄 `shortform-0555` 가 매일 05:55 KST 에 켜고, 작업이 끝나면 VM 이 스스로 꺼진다(`deploy/run_daily.sh`).
- 부팅 → systemd `shortform.service` → `plan.py --want 3 --viral 1` → `send.py --wait 0` → poweroff. 로그 `logs/server.log`.
- 코드 동기화(맥에서): `bash deploy/sync.sh` (runs/sources/work/캐시 제외, .env 포함).
- 수동 실행: `gcloud compute ssh shortform-worker --zone asia-northeast3-a -- 'touch ~/shortform/NO_SHUTDOWN; cd ~/shortform && .venv/bin/python -I auto/plan.py --want 1 --viral 0'`
- 인증: VM 기본 서비스 계정(cloud-platform 스코프) → gcloud 토큰. 키 파일 없음. 지메일 앱 비밀번호는 `.env` 만.
- 유튜브 다운로드가 데이터센터 IP 에서 막히면(`Sign in to confirm you're not a bot`) `--cookies`(브라우저 쿠키 파일) 또는 프록시 필요 — 배포 직후 반드시 테스트.

## 검증 (2026-10-20)
- 서버 IP 에서 yt-dlp 메타·검색·480p 다운로드 정상(차단 없음).
- 리터로봇 스펙 렌더: 4분 57초(e2-standard-8, 665프레임), QA PASS, 메일 발송 OK(TTS·STT·Lyria·Gemini 전부 VM 서비스 계정 토큰).
- 맥 launchd(daily·send)는 내림 → `~/Library/LaunchAgents/disabled/`. 맥은 개발·수동 테스트 전용.
- 운영: 05:55 자동 시작 → 완성 즉시 발송(대개 07:00 전후) → VM 자동 종료. 로그는 `logs/server.log`(VM), 확인: `gcloud compute ssh shortform-worker --zone asia-northeast3-a -- tail -50 ~/shortform/logs/server.log`
- VM 이 꺼져 있으면 ssh 전에 `gcloud compute instances start shortform-worker --zone asia-northeast3-a` (부팅 시 shortform.service 가 바로 하루 작업을 돌림 — 수동 작업만 하려면 `sudo systemctl stop shortform` 먼저).
- 수동 작업: `gcloud compute instances add-metadata shortform-worker --zone asia-northeast3-a --metadata shortform-skip=1` → start → 작업 → `remove-metadata --keys shortform-skip` → stop. (부팅 시 서비스가 skip 플래그를 보고 하루 작업을 건너뜀)

## 종료 (2026-10-22)
- 유튜브가 클라우드 IP 의 영상 다운로드를 차단해 중단. VM·인스턴스 스케줄·API 키·예산 알림 전부 삭제. 재가동 시 `cookies.txt` 필요.
