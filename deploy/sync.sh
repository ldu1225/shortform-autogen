#!/usr/bin/env bash
# 맥 → VM 코드 동기화. 사용: bash deploy/sync.sh [zone]
set -euo pipefail
ZONE=${1:-asia-northeast3-a}
cd ~/shortform
tar czf /tmp/shortform_sync.tgz --exclude=.venv --exclude=runs --exclude=sources --exclude='produce/render/work' --exclude='produce/render/tts_cache' --exclude=logs --exclude='*.pyc' --exclude=__pycache__ --exclude=dashboard .
gcloud compute scp /tmp/shortform_sync.tgz shortform-worker:/tmp/shortform_sync.tgz --zone "$ZONE"
gcloud compute ssh shortform-worker --zone "$ZONE" -- 'mkdir -p ~/shortform && tar xzf /tmp/shortform_sync.tgz -C ~/shortform && rm /tmp/shortform_sync.tgz && echo synced'
