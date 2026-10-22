#!/usr/bin/env bash
# GCE(Debian 12) 워커 1회 설정. 사용: bash deploy/setup_vm.sh  (VM 안에서, ~/shortform 에 코드 복사 후)
set -euo pipefail
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg python3-venv python3-pip fonts-noto-cjk git >/dev/null
cd ~/shortform
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q playwright pillow yt-dlp
.venv/bin/python -m playwright install --with-deps chromium >/dev/null
mkdir -p runs sources logs produce/render/work produce/render/tts_cache track
sudo timedatectl set-timezone Asia/Seoul
# 부팅 시 하루 작업 실행 → 끝나면 종료(인스턴스 스케줄이 05:55 에 켬)
sudo tee /etc/systemd/system/shortform.service >/dev/null <<UNIT
[Unit]
Description=shortform daily reels (plan -> send -> poweroff)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USER
WorkingDirectory=/home/$USER/shortform
Environment=HOME=/home/$USER
Environment=PATH=/home/$USER/shortform/.venv/bin:/usr/local/bin:/usr/bin:/bin:/snap/bin
ExecStart=/bin/bash /home/$USER/shortform/deploy/run_daily.sh
TimeoutStartSec=4h

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable shortform.service
echo "setup done: $(ffmpeg -version | head -1) / $(.venv/bin/yt-dlp --version)"
