"""QA — 렌더 결과 자동 검사 + 눈검수용 프레임 시트.
사용: python3 -I produce/qa.py runs/날짜/preview_x.mp4 [runs/날짜/spec_x.json]
검사: 길이 20~40초 · 음량 -11~-14 LUFS · 1080x1920 30fps · 스펙 핸들 핸들 · 숫자 출처(sources) 존재
출력: 같은 폴더 qa_<이름>.md + qa_<이름>.jpg (8프레임)
"""
import json
import re
import subprocess
import sys
from pathlib import Path


def probe(v):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate:format=duration",
                          "-of", "csv=p=0", str(v)], capture_output=True, text=True).stdout.split()
    w, h, fps = out[0].split(",")[:3]
    return int(w), int(h), fps, float(out[1])


def loudness(v):
    err = subprocess.run(["ffmpeg", "-i", str(v), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", err.split("Integrated loudness")[-1])
    return float(m.group(1)) if m else None


def main():
    v = Path(sys.argv[1]).resolve()
    if not v.exists():
        sys.exit(f"# QA {v.name} — FAIL (파일 없음: 렌더 실패)")
    spec = json.loads(Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 else None
    w, h, fps, dur = probe(v)
    lufs = loudness(v)
    checks = [
        ("해상도 1080x1920", (w, h) == (1080, 1920), f"{w}x{h}"),
        ("30fps", fps.startswith("30/1"), fps),
        ("길이 20~40초", 20 <= dur <= 40, f"{dur:.1f}s"),
        ("음량 -14~-11 LUFS", lufs is not None and -14 <= lufs <= -11, f"{lufs} LUFS"),
    ]
    if spec:
        HANDLE = next((l.split("=", 1)[1].strip() for l in (Path(__file__).resolve().parents[1] / ".env").read_text().splitlines() if l.startswith("HANDLE=")), "@channel") if (Path(__file__).resolve().parents[1] / ".env").exists() else "@channel"
        checks.append((f"핸들 {HANDLE}", spec["props"].get("handle") == HANDLE, spec["props"].get("handle")))
        checks.append(("숫자 출처(sources)", bool(spec.get("sources")), f"{len(spec.get('sources', []))}건"))
        blob = json.dumps(spec["props"], ensure_ascii=False) + json.dumps(spec["narration"], ensure_ascii=False)
        blob = re.sub(r"[\d,.]+\s*(?:만|억|천)\s*원", " ", blob)  # 원화 환산("약 5억 원", "120만 원")은 출처 검사 제외(10/19: 환산 허용. 한국 공식가는 claim 에 보통 있음)
        nums = re.findall(r"(?<![A-Za-z0-9])\d[\d,]*\d(?![A-Za-z0-9])", blob)  # 모델명(ZX900) 제외, 끝 콤마 제외
        claims = " ".join(s.get("claim", "") for s in spec.get("sources", []))
        # 숫자 비교는 자릿수 콤마·한글 단위(16만 7,999 → 167999)를 풀어 digits 로 (2026-10-18: "2,000니트" vs "2000니트" 오탐)
        expand = lambda t: re.sub(r"(\d+)\s*만\s*(\d[\d,]*)", lambda m: str(int(m.group(1)) * 10000 + int(m.group(2).replace(",", ""))), t)
        cd = expand(claims).replace(",", "")
        missing = sorted({n for n in nums if len(n.replace(",", "")) >= 3 and not re.fullmatch(r"20[2-3]\d", n) and n.replace(",", "") not in cd})  # 연도(kicker) 제외
        checks.append(("세 자리 이상 숫자 모두 출처 claim 에 등장", not missing, f"누락 {missing}" if missing else "ok"))
    # 프레임 시트 8장
    sheet = v.with_name(f"qa_{v.stem}.jpg")
    tmp = []
    for i in range(8):
        t = dur * (0.03 + 0.94 * i / 7)
        p = v.with_name(f".qa_{v.stem}_{i}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(v), "-frames:v", "1", "-vf", "scale=300:-1", "-q:v", "3", str(p)])
        tmp.append(p)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *sum((["-i", str(p)] for p in tmp), []), "-filter_complex", "".join(f"[{i}]" for i in range(8)) + "hstack=8", str(sheet)])
    for p in tmp:
        p.unlink(missing_ok=True)
    ok = all(c[1] for c in checks)
    md = [f"# QA {v.name} — {'PASS' if ok else 'FAIL'}", "", "| 검사 | 결과 | 값 |", "|---|---|---|"]
    md += [f"| {n} | {'✅' if r else '❌'} | {val} |" for n, r, val in checks]
    md += ["", f"프레임 시트: {sheet.name} — 눈으로: 피사체 잘림 / 소스 자막·로고 / 자막 오타 / 숫자 일치", ""]
    v.with_name(f"qa_{v.stem}.md").write_text("\n".join(md))
    print("\n".join(md))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
