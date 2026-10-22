# Server deployment (GCE, 2026-10-20)

Korean original: [`../docs/ko/DEPLOY.ko.md`](../docs/ko/DEPLOY.ko.md).

- VM: `shortform-worker` (asia-northeast3-a, e2-standard-8, Debian 12, 50 GB). An instance schedule `shortform-0555` starts it at 05:55 KST every day; the VM powers itself off when the job ends (`deploy/run_daily.sh`).
- Boot → systemd `shortform.service` → `plan.py --want 3 --viral 1` → `send.py --wait 0` → poweroff. Log: `logs/server.log`.
- Code sync from the workstation: `bash deploy/sync.sh` (excludes runs, sources, work and caches; includes `.env`).
- Manual run: `gcloud compute ssh shortform-worker --zone asia-northeast3-a -- 'touch ~/shortform/NO_SHUTDOWN; cd ~/shortform && .venv/bin/python -I auto/plan.py --want 1 --viral 0'`
- Auth: the VM's default service account (cloud-platform scope) → gcloud token. No key files. The Gmail app password lives only in `.env`.
- If YouTube downloads are blocked from the datacenter IP (`Sign in to confirm you're not a bot`), a `--cookies` file or a proxy is required — test immediately after deploying.

## Validation (2026-10-20)
- From the server IP: yt-dlp metadata, search and a 480p download all worked (no block that day).
- A full render of a saved spec: 4 min 57 s (e2-standard-8, 665 frames), QA PASS, email sent (TTS, STT, Lyria and Gemini all via the VM service-account token).
- The macOS launchd jobs were removed; the workstation is for development and manual tests only.
- Operation: 05:55 auto start → send as soon as reels are finished (usually around 07:00) → VM shuts down. Check with `gcloud compute ssh shortform-worker --zone asia-northeast3-a -- tail -50 ~/shortform/logs/server.log`.
- If the VM is off, start it first (`gcloud compute instances start shortform-worker --zone asia-northeast3-a`). The boot service runs the daily job immediately — for manual work, stop it first (`sudo systemctl stop shortform`).
- Manual sessions: `gcloud compute instances add-metadata shortform-worker --zone asia-northeast3-a --metadata shortform-skip=1` → start → work → `remove-metadata --keys shortform-skip` → stop. The boot service sees the flag and skips the daily job (and schedules a shutdown three hours later).
- Safety: `shortform-watchdog.timer` runs every 10 minutes and powers the VM off after 150 minutes of uptime unless a `NO_SHUTDOWN` file exists. Added after the VM idled for 31 hours because of a flag-check bug (`grep -q 1` matched "v1" in a 404 body).

## Shutdown (2026-10-22)
- Stopped because YouTube blocked video downloads from cloud IPs. The VM, instance schedule, API key and budget alert were all deleted. Restarting requires `cookies.txt`.
