"""08:00 발송 — runs/날짜/outbox 의 릴스를 한 편당 메일 한 통으로 보낸다(본문 = 그대로 붙여넣을 캡션).
비밀번호는 ~/shortform/.env 의 GMAIL_APP_PASSWORD (구글 계정 > 보안 > 앱 비밀번호). 코드·대화에 넣지 않는다.
첨부가 18MB 넘으면 ffmpeg 로 줄인다(지메일 25MB 제한, base64 로 33% 커짐). 완성본이 없으면 실패 사유 메일.
사용: python3 -I auto/send.py [--date YYYY-MM-DD] [--dry]
"""
import argparse
import datetime as dt
import json
import re
import smtplib
import ssl
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TO = None  # .env 의 MAIL_TO (main 에서 읽음)
CHANNEL = "채널"  # .env 의 CHANNEL_NAME (main 에서 읽음)
MAX = 18 * 1024 * 1024


def env():
    e = {}
    p = ROOT / ".env"
    if p.exists():
        for l in p.read_text().splitlines():
            if "=" in l and not l.strip().startswith("#"):
                k, v = l.split("=", 1)
                e[k.strip()] = v.strip().strip('"').strip("'")
    return e


def shrink(mp4: Path):
    if mp4.stat().st_size <= MAX:
        return mp4
    small = mp4.with_name(mp4.stem + "_mail.mp4")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)], capture_output=True, text=True).stdout)
    kbps = int((MAX * 8 / 1024) / dur * 0.9) - 160
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-c:v", "libx264", "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{2 * kbps}k",
                    "-preset", "medium", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(small)], check=True)
    return small


def send(msgs, dry):
    if dry:
        for m in msgs:
            print("DRY:", m["Subject"], [p.get_filename() for p in m.iter_attachments()])
        return
    pw = env().get("GMAIL_APP_PASSWORD")
    if not pw:
        raise SystemExit("~/shortform/.env 에 GMAIL_APP_PASSWORD 가 없음")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(TO, pw.replace(" ", ""))
        for m in msgs:
            s.send_message(m)


def mail(subject, body, attach=None):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = f"{CHANNEL} <{TO}>", TO, subject
    m.set_content(body)
    if attach:
        m.add_attachment(attach.read_bytes(), maintype="video", subtype="mp4", filename=attach.name.replace("_mail", ""))
    return m


def main():
    global TO
    global CHANNEL
    CHANNEL = env().get("CHANNEL_NAME") or "채널"
    TO = env().get("MAIL_TO") or ""
    if not TO:
        raise SystemExit(".env 에 MAIL_TO 가 없음")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--wait", type=int, default=90, help="제작이 진행 중이면 최대 N분 대기")
    ap.add_argument("--resend", action="store_true", help="이미 보낸 파일도 다시 보냄")
    a = ap.parse_args()
    d = ROOT / "runs" / a.date
    # 제작(plan.py)이 아직 돌고 있으면 최대 --wait 분 기다린다(10/19: 맥 수면으로 늦어진 제작을 두고 '없음' 메일을 보낸 사고)
    import os, time
    pid_f = d / "running.pid"
    waited = 0
    import subprocess as _sp
    if sys.platform == "darwin":
        _sp.Popen(["/usr/bin/caffeinate", "-u", "-i", "-s", "-w", str(os.getpid())], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)  # 대기 중 잠들기 금지(10/20)
    while pid_f.exists() and waited < a.wait * 60:
        try:
            os.kill(int(pid_f.read_text().strip()), 0)
        except (ValueError, ProcessLookupError, PermissionError):
            break
        if waited == 0:
            print("제작 진행 중 → 대기")
        time.sleep(60); waited += 60
    out = d / "outbox"
    reels = sorted(p for p in out.glob("*.mp4") if not p.stem.endswith("_mail")) if out.exists() else []
    sent_p = d / "sent.json"
    prev = json.loads(sent_p.read_text()) if sent_p.exists() else {}
    if not a.resend:  # 이미 보낸 파일은 다시 안 보냄(10/19: 늦게 복구한 편만 추가 발송)
        reels = [r for r in reels if r.name not in prev.get("files", [])]
    rep = json.loads((d / "auto_report.json").read_text()) if (d / "auto_report.json").exists() else {}
    msgs = []
    for i, r in enumerate(reels, 1):
        cap = r.with_suffix(".txt").read_text() if r.with_suffix(".txt").exists() else ""
        info = next((x for x in rep.get("items", []) if x.get("file") == r.name), {})
        note = ""
        if info:
            note = "\n\n---\n(아래는 참고용, 캡션에 넣지 마세요)\n" + f"와우 점수 {info.get('wow', '-')}/10 — {info.get('wow_judge') or ''}{' (오늘 7점 이상 소재 없어 6점으로 진행)' if info.get('wow_weak') else ''}\n" + (f"★ 해외 바이럴 재가공 — 출처 채널 @{info.get('credit')} (캡션·화면에 출처 표기됨)\n" if info.get('kind') == 'viral' else "") + f"제품: {info.get('product')}\n카테고리: {info.get('category') or '-'} · 레이아웃 {info.get('layout')} · 테마 {info.get('theme') or 'dark'}\n" + \
                   f"왜 지금: {info.get('hot_reason') or '-'} (유튜브 7일 조회 {info.get('heat_views') or 0:,})\n한국 출시: {info.get('korea') or '미확인'}\n" + \
                   "출처:\n" + "\n".join(f"- {f.get('claim')} {f.get('url')}" for f in info.get("facts", [])[:6])
        title = info.get("title") or info.get("product", r.stem)
        qa = str(info.get("qa", ""))
        warn = ""
        if "FAIL" in qa:  # QA 경고는 메일 맨 위에(숫자 출처 미확인 등 → 올리기 전 확인)
            warn = "⚠ QA 경고: " + (qa.split("—", 1)[-1].strip() or "검사 실패") + " — 올리기 전에 확인하세요.\n\n"
        body = f"{warn}제목\n{title}\n\n캡션 (아래 그대로 복사)\n{cap}"
        msgs.append(mail(f"[{CHANNEL}]{a.tag} {i}/{len(reels)} {title}", body + note, shrink(r)))
    if not reels and re.search(r"\d{4}-\d{2}-\d{2}\w+$", a.date):  # 슬롯(테스트) 런은 '없음' 메일을 보내지 않는다(10/20)
        print("릴스 없음(슬롯 런) → 메일 생략"); return
    if not reels and not prev.get("files"):
        errs = "\n".join(f"- {e}" for e in rep.get("errors", [])) or ("- 제작이 아직 진행 중(맥이 잠들어 늦어짐). 끝나면 '지연' 메일로 보냄" if pid_f.exists() else "- 실행 기록 없음(06:00 작업이 안 돌았거나 맥이 잠자고 있었음)")
        msgs.append(mail(f"[{CHANNEL}] {a.date} 오늘 릴스 없음", f"오늘은 보낼 릴스를 못 만들었어요.\n\n사유:\n{errs}"))
    send(msgs, a.dry)
    if not a.dry:  # 보낸 제품 기록 → 다음 선정에서 중복 제외
        with open(ROOT / "track/sent.jsonl", "a") as f:
            for x in rep.get("items", []):
                f.write(json.dumps({"date": a.date, "product": x.get("product"), "title": x.get("title")}, ensure_ascii=False) + "\n")
    if not a.dry:
        files = prev.get("files", []) + [r.name for r in reels]
        sent_p.write_text(json.dumps({"at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "count": len(files), "files": files, "dry": a.dry}, ensure_ascii=False))
    print(f"보냄 {len(msgs)}통 (릴스 {len(reels)}개){' [dry]' if a.dry else ''}")


if __name__ == "__main__":
    main()
