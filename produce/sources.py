"""소재 준비 — 스펙의 컷마다 (1) 소스 다운로드(없을 때) (2) 9:16 크롭 후보 프레임 시트.
사용: python3 -I produce/sources.py runs/날짜/spec_x.json [--fetch] [--height 1440]
- 소스 파일은 스펙의 clip 경로(스펙 파일 기준 상대경로). 파일명이 유튜브 ID(11자)면 --fetch 로 받는다.
- 크롭 후보: 컷 시작·중간·끝 시각에서 cx 팬을 적용한 9:16 센터 크롭 → runs/날짜/crop_<spec>.jpg (한 줄 = 컷 하나)
ponytail: 피사체 자동 검출 없음. 사람이 시트를 보고 cx/in 을 고친다.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

YTDLP = str(Path(__file__).resolve().parents[1] / ".venv/bin/yt-dlp")
_CK = Path(__file__).resolve().parents[1] / "cookies.txt"
YTDLP_OPTS = ["--cookies", str(_CK)] if _CK.exists() else []
SCENES = ["도입부", "중반부", "마지막"]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"실패: {' '.join(map(str, cmd))[:300]}\n{r.stderr[-800:]}")
    return r.stdout


def fetch(clip: Path, height):
    vid = clip.stem
    if clip.exists() or not re.fullmatch(r"[\w-]{11}", vid):
        return
    clip.parent.mkdir(parents=True, exist_ok=True)
    run([YTDLP, *YTDLP_OPTS, "-q", "--no-warnings", "-f", "bv*+ba/b", "-S", f"res:{height},tbr",
         "--merge-output-format", "mp4", "-o", str(clip), f"https://www.youtube.com/watch?v={vid}"])
    print(f"  받음 {clip.name}")


def crop_sheet(spec_path: Path, spec):
    base = spec_path.parent
    tiles, labels = [], []
    tmp = base / f".crop_{spec_path.stem}"
    tmp.mkdir(exist_ok=True)
    for name in SCENES:
        for ci, c in enumerate(spec["cuts"][name]):
            clip = (base / c["clip"]).resolve()
            z = c.get("zoom", 1.1)
            cx0, cx1 = (c["cx"] if isinstance(c["cx"], list) else [c["cx"]] * 2)
            d = c.get("dur") or 3.0
            row = []
            for k, frac in enumerate((0.0, 0.25, 0.5, 0.75, 1.0)):
                t, cx = c["in"] + d * frac, cx0 + (cx1 - cx0) * frac
                out = tmp / f"{name}_{ci}_{k}.jpg"
                vf = (f"crop=w='ih/{z}*9/16':h='ih/{z}':x='clip(iw*{cx}-ow/2,0,iw-ow)':y='{c.get('yoff', 0)}*(ih-oh)',"
                      f"scale=180:-1,drawbox=0:0:iw:36:black@0.6:t=fill")
                run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(clip), "-frames:v", "1", "-vf", vf, "-q:v", "3", str(out)])
                row.append(out)
            tiles.append(row)
            labels.append(f"{name}#{ci} {clip.name} in={c['in']} d={d}")
    # 각 줄 hstack → 전체 vstack
    rows = []
    for i, row in enumerate(tiles):
        o = tmp / f"row_{i}.jpg"
        run(["ffmpeg", "-v", "error", "-y", *sum((["-i", str(p)] for p in row), []), "-filter_complex", "[0][1][2][3][4]hstack=5", str(o)])
        rows.append(o)
    sheet = base / f"crop_{spec_path.stem}.jpg"
    run(["ffmpeg", "-v", "error", "-y", *sum((["-i", str(p)] for p in rows), []), "-filter_complex",
         "".join(f"[{i}]" for i in range(len(rows))) + f"vstack={len(rows)}", str(sheet)])
    (base / f"crop_{spec_path.stem}.txt").write_text("\n".join(f"{i}: {l}" for i, l in enumerate(labels)))
    print(f"크롭 후보 시트: {sheet}  (줄 순서는 crop_{spec_path.stem}.txt)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--height", type=int, default=2160)
    a = ap.parse_args()
    sp = Path(a.spec).resolve()
    spec = json.loads(sp.read_text())
    if a.fetch:
        for name in SCENES:
            for c in spec["cuts"][name]:
                fetch((sp.parent / c["clip"]).resolve(), a.height)
    crop_sheet(sp, spec)


if __name__ == "__main__":
    main()
