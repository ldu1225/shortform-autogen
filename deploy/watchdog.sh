#!/usr/bin/env bash
# 10/22 사고(31시간 공회전) 재발 방지: 켜진 지 150분 넘으면 NO_SHUTDOWN 파일이 없는 한 무조건 끈다. run_daily.sh 와 독립.
UP=$(awk '{print int($1/60)}' /proc/uptime)
if [ "$UP" -ge 150 ] && [ ! -f ${SHORTFORM_HOME:-/home/shortform/shortform}/NO_SHUTDOWN ]; then
  echo "[$(date '+%F %T')] watchdog: uptime ${UP}m → poweroff" >> ${SHORTFORM_HOME:-/home/shortform/shortform}/logs/server.log
  /sbin/poweroff
fi
