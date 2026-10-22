"""AI 뉴스형 쇼츠 생성기 v0.1 (벤치마크: Unitree 공식 쇼츠 + 노컷뉴스 재가공)
- 16:9 원본 → 4:5 창(1080x1350) 크롭, 세그먼트별 x-팬(cx 시작→끝), 위아래 검은 바
- 상단 2줄 제목(슬라이드 인), 하단 신뢰 줄(실제 영상·배속 없음·출처)
- 자막 = 칩(pill) 카드: 문장 하나가 한 카드, 칩이 말하는 순서대로 오버슈트 팝 + 슬라이드업.
  '*…*' 전체 강조 칩은 노랑 반전, 부분 강조는 노랑 글자, size 로 숫자 칩 확대.
- TTS: Google Cloud gemini-2.5-pro-tts (스타일 프롬프트), 응답은 tts_cache/ 에 캐시
- 칩 타이밍: 문장 TTS 의 발화 구간(앞뒤 무음 제외)을 음절 수 비례로 분배, 구두점 뒤는 쉼 가중치.
  ponytail: STT 정렬 없음. 어긋나면 Speech-to-Text 단어 오프셋으로 교체.
사용: ../.venv/bin/python -I news.py spec.json out.mp4   (spec.json --check 로 타이밍/레이아웃만 검사)
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import time
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
VW, VH = 1080, 1350
TY = (H - VH) // 2  # 285
CY = 1430  # 칩 카드 세로 중심 (영상 창 하단 1/3, 쇼츠 UI 피함)
MAXW, GAP = 840, 18
HERE = Path(__file__).resolve().parent
FONTS = {"heavy": HERE / "fonts/Pretendard-Black.otf", "bold": HERE / "fonts/Pretendard-ExtraBold.otf",
         "regular": HERE / "fonts/Pretendard-Bold.otf"}
YELLOW, WHITE, BLACK, GRAY = (255, 226, 0), (255, 255, 255), (0, 0, 0), (200, 200, 200)
PROJECT = os.environ.get("GCP_PROJECT") or next((l.split("=", 1)[1].strip() for l in (Path(__file__).resolve().parents[2] / ".env").read_text().splitlines() if l.startswith("GCP_PROJECT=")), "")  # .env 의 GCP_PROJECT
CACHE = HERE / "tts_cache"
POP = 0.26  # 칩 팝 길이(초)


def font(size, w="heavy"):
    return ImageFont.truetype(str(FONTS[w]), int(size))


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"ffmpeg 실패:\n{' '.join(map(str, cmd))[:600]}\n{r.stderr[-2000:]}")
    return r


def dur(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).stdout)


def speech_bounds(p):
    """앞뒤 무음을 뺀 (발화 시작, 끝)."""
    d = dur(p)
    r = subprocess.run(["ffmpeg", "-i", str(p), "-af", "silencedetect=noise=-38dB:d=0.12", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    s = ends[0] if starts and starts[0] < 0.05 and ends else 0.0
    e = starts[-1] if starts and len(starts) > len(ends) else d  # 마지막 무음이 끝까지 이어짐
    return s, max(e, s + 0.3), d


def gtts(text, spec):
    CACHE.mkdir(exist_ok=True)
    key = hashlib.sha1("|".join([spec["model"], spec["voice"], spec["style"], str(spec["rate"]), text]).encode()).hexdigest()[:12]
    out = CACHE / f"{key}.mp3"
    if out.exists():
        return out
    token = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip()
    body = {"input": {"text": text, "prompt": spec["style"]},
            "voice": {"languageCode": "ko-KR", "name": spec["voice"], "modelName": spec["model"]},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": spec["rate"]}}
    req = urllib.request.Request("https://texttospeech.googleapis.com/v1/text:synthesize", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT,
                                          "Content-Type": "application/json"})
    d = None
    for i in range(5):  # 구글 API 일시 오류 재시도(10/19): 429 는 20초, 5xx 는 5·10·15초
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
            break
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode(errors="replace")
            print(f"  TTS API {e.code}: {body[:160]}", file=sys.stderr)
            if (e.code < 500 and e.code not in (401, 429)) or i == 4:
                raise
            time.sleep(20 if e.code == 429 else (2 if e.code == 401 else 5 * (i + 1)))
            if e.code == 401:  # 토큰 새로
                req.remove_header("Authorization")
                req.add_header("Authorization", "Bearer " + subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip())
        except urllib.error.URLError as e:
            print(f"  TTS 연결 오류: {e}", file=sys.stderr)
            if i == 4:
                raise
            time.sleep(5 * (i + 1))
    out.write_bytes(base64.b64decode(d["audioContent"]))
    return out


def parse_marks(text):
    toks, cur, inside = [], "", False
    for ch in text:
        if ch == "*":
            if cur:
                toks.append((cur, inside))
            cur, inside = "", not inside
        else:
            cur += ch
    if cur:
        toks.append((cur, inside))
    return toks


def chip_img(chip):
    text, size = (chip, 1.0) if isinstance(chip, str) else (chip["t"], chip.get("size", 1.0))
    toks = parse_marks(text)
    key = all(m for _, m in toks)  # 전체 강조 → 노랑 반전 칩
    f = font(64 * size)
    padx, pady, r, m = int(30 * size), int(14 * size), int(30 * size), 14
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    widths = [d0.textlength(t, font=f) for t, _ in toks]
    asc, desc = f.getmetrics()
    tw, th = int(sum(widths)), asc + desc
    bw, bh = tw + 2 * padx, th + 2 * pady
    im = Image.new("RGBA", (bw + 2 * m, bh + 2 * m), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([m, m + 6, m + bw, m + bh + 6], radius=r, fill=(0, 0, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([m, m, m + bw, m + bh], radius=r, fill=(*YELLOW, 255) if key else (0, 0, 0, 190))
    x = m + padx
    for (t, mk), w in zip(toks, widths):
        d.text((x, m + pady), t, font=f, fill=BLACK if key else (YELLOW if mk else WHITE))
        x += w
    return im


def layout(chips):
    """칩 이미지를 줄바꿈해 가운데 정렬. 위치는 처음부터 고정(나중 칩이 떠도 앞 칩이 안 움직임)."""
    imgs = [chip_img(c) for c in chips]
    lines, cur, cw = [], [], 0
    for im in imgs:
        if cur and cw + GAP + im.width > MAXW:
            lines.append(cur)
            cur, cw = [], 0
        cur.append(im)
        cw += (GAP if cw else 0) + im.width
    lines.append(cur)
    lh = max(im.height for im in imgs) - 10
    y0 = CY - lh * len(lines) // 2
    pos = []
    for li, line in enumerate(lines):
        lw = sum(im.width for im in line) + GAP * (len(line) - 1)
        x = (W - lw) // 2
        for im in line:
            pos.append((im, x, y0 + li * lh + (lh - im.height) // 2))
            x += im.width + GAP
    return pos


def chip_times(seg, start, ss, se):
    """칩 시작 시각: 발화 구간을 음절 수(+구두점 쉼) 비례로."""
    narr = re.sub(r"\s", "", seg["text"])
    ws, pos = [], 0
    for c in seg["chips"]:
        plain = re.sub(r"[\s*]", "", c if isinstance(c, str) else c["t"])
        i = narr.find(plain, pos)
        w = len(plain)
        if i >= 0:
            pos = i + len(plain)
            after = narr[pos:pos + 1]
            w += 1.3 if after in ".?!" else 0.8 if after in ",…" else 0
        else:
            print(f"  경고: 칩 '{plain}' 이 대본에 없음", file=sys.stderr)
        ws.append(w)
    total, acc, ts = sum(ws), 0.0, []
    for w in ws:
        ts.append(start + ss + (se - ss) * acc / total)
        acc += w
    return ts


def ease_out_back(x, s=2.4):
    x -= 1
    return 1 + x * x * ((s + 1) * x + s)


def anim(dt):
    if dt < 0:
        return None
    p = min(dt / POP, 1.0)
    return 0.5 + 0.5 * ease_out_back(p), min(dt / 0.08, 1.0), int(28 * (1 - p) ** 2)


def paste(dst, im, x, y, scale=1.0, alpha=1.0):
    if scale != 1.0:
        w, h = max(1, int(im.width * scale)), max(1, int(im.height * scale))
        x, y = x + (im.width - w) // 2, y + (im.height - h) // 2
        im = im.resize((w, h), Image.LANCZOS)
    if alpha < 1.0:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    dst.alpha_composite(im, (x, y))


def title_img(spec, slide=1.0):
    im = Image.new("RGBA", (W, TY), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font(72)
    y = (TY - (2 * 86 - 10)) // 2
    for i, line in enumerate(spec["title"]):
        col = YELLOW if line.get("color") == "yellow" else WHITE
        ox = int(-90 * (1 - slide) ** 2)
        d.text((72 + ox, y + i * 86), line["text"], font=f, fill=(*col, int(255 * slide)))
    return im


def build(spec_path, out_path, check=False):
    spec = json.loads(Path(spec_path).read_text())
    base = Path(spec_path).resolve().parent
    work = HERE / "work_news"
    work.mkdir(exist_ok=True)

    # 1) TTS + 타임라인
    t = 0.0
    for i, seg in enumerate(spec["segments"]):
        seg["mp3"] = gtts(seg["text"], spec)
        ss, se, d = speech_bounds(seg["mp3"])
        seg["start"], seg["dur"] = t, d + seg.get("pad", 0.25)
        seg["times"] = chip_times(seg, t, ss, se)
        seg["pos"] = layout(seg["chips"])
        clip = base / seg["clip"]
        assert seg["in"] + seg["dur"] <= dur(clip) - 0.1, f"seg{i}: 클립 길이 초과 {clip.name}"
        print(f"seg{i} {t:5.2f}s +{seg['dur']:.2f} 발화 {ss:.2f}-{se:.2f}  칩 {[round(x - t, 2) for x in seg['times']]}")
        t += seg["dur"]
    T = t
    print(f"총 {T:.1f}s")
    if check:
        return

    # 2) 베이스 영상 (크롭/팬 + 패드 + 현장음)
    clips = list(dict.fromkeys(str(base / s["clip"]) for s in spec["segments"]))
    cmd, fc, cat = ["ffmpeg", "-y"], [], ""
    for c in clips:
        cmd += ["-i", c]
    for i, seg in enumerate(spec["segments"]):
        k, z, d = clips.index(str(base / seg["clip"])), seg.get("zoom", 1.1), seg["dur"]
        cx0, cx1 = (seg["cx"] if isinstance(seg["cx"], list) else [seg["cx"]] * 2)
        fc.append(f"[{k}:v]trim=start={seg['in']}:duration={d},setpts=PTS-STARTPTS,fps={FPS},"
                  f"crop=w='ih/{z}*4/5':h='ih/{z}':x='clip(iw*({cx0}+({cx1}-{cx0})*t/{d})-ow/2,0,iw-ow)':y='{seg.get('yoff', 0)}*(ih-oh)',"
                  f"scale={VW}:{VH}:flags=lanczos,setsar=1,pad={W}:{H}:0:{TY}:black[v{i}]")
        fc.append(f"[{k}:a]atrim=start={seg['in']}:duration={d},asetpts=PTS-STARTPTS,aresample=48000,"
                  f"aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        cat += f"[v{i}][a{i}]"
    fc.append(f"{cat}concat=n={len(spec['segments'])}:v=1:a=1[v][a]")
    basemp4 = work / "base.mp4"
    run(cmd + ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast",
               "-crf", "16", "-c:a", "aac", "-b:a", "192k", str(basemp4)])

    # 3) 오버레이 프레임 파이프 + 오디오 믹스 → 최종
    n = len(spec["segments"])
    cmd = ["ffmpeg", "-y", "-i", str(basemp4), "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "pipe:0"]
    for seg in spec["segments"]:
        cmd += ["-i", str(seg["mp3"])]
    cmd += ["-stream_loop", "-1", "-i", str(HERE / spec["bgm"])]
    fc = ["[0:v][1:v]overlay=format=auto:shortest=1[v]",
          f"[0:a]volume={spec.get('amb_db', -20)}dB[amb]",
          f"[{n + 2}:a]volume={spec.get('bgm_db', -26)}dB,atrim=duration={T},aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[bg]"]
    mix = "[amb]"
    for i, seg in enumerate(spec["segments"]):
        fc.append(f"[{i + 2}:a]adelay={int(seg['start'] * 1000)}:all=1,volume={spec.get('voice_db', 1)}dB,"
                  f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[t{i}]")
        mix += f"[t{i}]"
    fc.append(f"{mix}[bg]amix=inputs={n + 2}:normalize=0:dropout_transition=0,alimiter=limit=0.95[a]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-t", f"{T:.3f}", "-c:v", "libx264", "-preset", "medium",
            "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]
    log = open(work / "final.log", "w")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=log)

    static = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    static.alpha_composite(title_img(spec), (0, 0))
    d = ImageDraw.Draw(static)
    size = 30
    while (tw := d.textlength(spec["trust"], font=(ft := font(size, "regular")))) > W - 120:
        size -= 1
    d.text(((W - tw) / 2, TY + VH + 22), spec["trust"], font=ft, fill=(*GRAY, 255))
    frames = int(T * FPS)
    for fi in range(frames):
        tt = fi / FPS
        if tt < 0.4:
            im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            im.alpha_composite(title_img(spec, slide=min(tt / 0.4, 1.0)), (0, 0))
            im.alpha_composite(static.crop((0, TY, W, H)), (0, TY))
        else:
            im = static.copy()
        seg = next((s for s in reversed(spec["segments"]) if s["start"] <= tt), spec["segments"][0])
        for (cimg, x, y), ts in zip(seg["pos"], seg["times"]):
            a = anim(tt - ts)
            if a:
                sc, al, dy = a
                paste(im, cimg, x, y + dy, sc, al)
        proc.stdin.write(im.tobytes())
        if fi % 150 == 0:
            print(f"  프레임 {fi}/{frames}", file=sys.stderr)
    proc.stdin.close()
    if proc.wait():
        sys.exit(f"최종 인코딩 실패: {(work / 'final.log').read_text()[-1500:]}")
    print(f"완료: {out_path} ({T:.1f}s)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, check="--check" in sys.argv)
