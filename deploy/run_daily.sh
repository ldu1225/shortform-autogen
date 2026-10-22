#!/usr/bin/env bash
# 부팅 때 systemd 가 실행. 제작 → 발송 → (수동 세션이 없으면) 전원 끄기.
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:$PATH" TZ=Asia/Seoul
# 수동 작업용으로 켠 경우(메타데이터 shortform-skip=1)는 하루 작업을 돌리지 않는다
# 10/21 사고: 플래그가 없을 때 404 HTML 의 "v1" 을 grep 1 이 잡아 매일 작업을 건너뜀 → -f(404 면 빈 출력) + 정확 비교
SKIP=$(curl -sf -m 3 -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/shortform-skip 2>/dev/null || true)
if [ "$SKIP" = "1" ]; then
  echo "[$(date '+%F %T')] shortform-skip=1 → 수동 세션, 작업 생략 (3시간 뒤 자동 종료 예약)" >> logs/server.log
  sudo /sbin/shutdown -h +180 >/dev/null 2>&1 || true
  exit 0
fi
D=$(date +%F)
echo "[$(date '+%F %T')] run_daily start" >> logs/server.log
if [ -f NO_SHUTDOWN ]; then echo "NO_SHUTDOWN 파일 있음 → 작업 후 켜둠" >> logs/server.log; fi
# 08:00 이전에 끝나면 send.py 가 보낼 때까지 기다리지 않고 바로 보낸다(서버는 완성 즉시 발송 — 10/20 사용자: 아침에 와야 함)
python3 -I auto/plan.py --date "$D" --want 3 --viral 1 >> logs/server.log 2>&1 || echo "plan exit $?" >> logs/server.log
python3 -I auto/send.py --date "$D" --wait 0 >> logs/server.log 2>&1 || echo "send exit $?" >> logs/server.log
echo "[$(date '+%F %T')] run_daily end" >> logs/server.log
if [ ! -f NO_SHUTDOWN ]; then sudo /sbin/poweroff; fi
