"""디자인 템플릿(claude.ai/design 'Reels Template v2') 렌더 파이프라인 v0.1
- 템플릿 React 코드(animations-v3.jsx + reel-template.jsx)를 손대지 않고 headless Chrome 에서 프레임 단위 캡처 → 디자인과 픽셀 동일
  (패치 4개만: <video> 자동 seek 제거, 자막 청크 시각 외부 주입, 팩트카드 시각/취소선 옵션, autoplay off)
- 영상: 16:9 소스 여러 개를 9:16 cover 크롭(팬)으로 장면 경계에 맞춰 이어붙인 base.mp4 를 템플릿 <video> 에 물림
- 음성: Google gemini-3.1-flash-tts-preview 3구간(도입부/중반부/마지막), Speech-to-Text 단어 오프셋으로 자막 청크 시작 정렬
- BGM: Vertex Lyria 3 clip (프롬프트 해시로 캐시)
사용: ../../.venv/bin/python -I design_reel.py spec.json out.mp4
ponytail: STT 정렬은 최장일치 1회(difflib), 못 찾으면 이웃 사이 등분. 프레임은 JPEG q95 로 디스크에 떨궈 ffmpeg 가 읽음.
"""
import base64
import difflib
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from news import PROJECT, dur, gtts, run  # noqa: E402

W, H, FPS = 1080, 1920, 30
CACHE = HERE / "tts_cache"
SCENES = ["도입부", "중반부", "마지막"]
VOICE_T0 = {"훅": 0.3, "도입부": 0.25, "중반부": 0.3, "마지막": 0.3}  # 장면 시작 대비 나레이션 시작


def token():
    return subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip()


def gpost(url, body):
    import time
    data = json.dumps(body).encode()
    for i in range(5):  # 10/19 구글 API 일시 오류(401/429/5xx) → 5회. 토큰은 시도마다 새로(401 대응)
        req = urllib.request.Request(url, data=data, headers={"Authorization": f"Bearer {token()}", "x-goog-user-project": PROJECT,
                                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode(errors="replace")
            print(f"  API {e.code} ({url.split('/')[-1][:40]}): {body[:160]}", file=sys.stderr)
            if (e.code < 500 and e.code not in (401, 429)) or i == 4:
                raise
            time.sleep(20 if e.code == 429 else (2 if e.code == 401 else 5 * (i + 1)))
        except urllib.error.URLError as e:
            print(f"  API 연결 오류: {e}", file=sys.stderr)
            if i == 4:
                raise
            time.sleep(5 * (i + 1))


def lyria(prompt):
    CACHE.mkdir(exist_ok=True)
    out = CACHE / f"lyria_{hashlib.sha1(prompt.encode()).hexdigest()[:12]}.mp3"
    if out.exists():
        return out
    d = gpost(f"https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT}/locations/global/interactions",
              {"model": "lyria-3-clip-preview", "input": [{"type": "text", "text": prompt}]})
    audio = next(o for o in d["outputs"] if o.get("type") == "audio")
    out.write_bytes(base64.b64decode(audio["data"]))
    return out


def stt_chars(mp3, model="latest_long"):
    """[(글자, 시작초)] — STT 단어 토큰을 글자 단위로 펼침(앞 '▁'는 단어 시작 표시)."""
    cache = mp3.with_suffix(".stt.json" if model == "latest_long" else f".stt_{model}.json")
    if cache.exists():
        return json.loads(cache.read_text())
    wav = mp3.with_suffix(".16k.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ar", "16000", "-ac", "1", str(wav)])
    d = gpost("https://speech.googleapis.com/v1/speech:recognize",
              {"config": {"encoding": "LINEAR16", "sampleRateHertz": 16000, "languageCode": "ko-KR",
                          "enableWordTimeOffsets": True, "model": model},
               "audio": {"content": base64.b64encode(wav.read_bytes()).decode()}})
    chars = []
    for res in d.get("results", []):
        for w in res["alternatives"][0].get("words", []):
            t = float(w["startTime"].rstrip("s"))
            for ch in w["word"].replace("▁", "").replace(" ", ""):
                chars.append((ch, t))
    cache.write_text(json.dumps(chars, ensure_ascii=False))
    return chars


def align(chunks, chars, end):
    """청크(자막 줄) 시작 시각(mp3 기준 초). 못 찾은 건 이웃 사이 등분."""
    s = "".join(c for c, _ in chars if c != ",")
    ts = [t for c, t in chars if c != ","]
    pos, out = 0, []
    for ch in chunks:
        key = re.sub(r"[\s*,.?!…'\"]", "", ch)
        m = difflib.SequenceMatcher(None, s[pos:], key, autojunk=False).find_longest_match(0, len(s) - pos, 0, len(key))
        if m.size >= max(2, len(key) // 3) and ts:
            idx = min(max(pos, pos + m.a - m.b), len(ts) - 1)
            out.append(ts[idx])
            pos = idx + max(1, int(len(key) * 0.7))
        else:
            out.append(None)
    out = [0.0 if out[0] is None else out[0]] + out[1:]
    for i in range(1, len(out)):
        if out[i] is None:
            j = next((k for k in range(i + 1, len(out)) if out[k] is not None), None)
            nxt = out[j] if j is not None else end
            out[i] = out[i - 1] + (nxt - out[i - 1]) / ((j or len(out)) - i + 1)
    return out


def lufs(path):
    err = subprocess.run(["ffmpeg", "-i", str(path), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", err.split("Integrated loudness")[-1])
    return float(m.group(1)) if m else -16.0


def speedup(mp3, speed):
    """검증·정렬은 1.0배 원본으로 하고(STT 가 1.5배속을 못 알아들음, 2026-10-18), 영상엔 atempo 로 빨라진 파일을 쓴다."""
    if speed == 1.0:
        return mp3
    out = mp3.with_name(f"{mp3.stem}_x{speed}.mp3")
    if not out.exists():
        run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-filter:a", f"atempo={speed}", "-b:a", "192k", str(out)])
    return out


def tts_checked(text, spec, tries=3):
    """TTS 결과를 STT로 되읽어 검증 — 스타일 프롬프트가 그대로 읽히거나(2026-10-17 실제 발생) 숫자가 빠지면 재합성.
    STT 는 latest_long → default 순으로 보고 더 잘 맞는 쪽 채택(latest_long 이 영어식 브랜드명 구간을 버리는 일이 있음).
    ponytail: 3회 실패면 중단하고 대본(숫자 표기·프롬프트)을 고치게 한다."""
    want = re.sub(r"[^0-9A-Za-z가-힣]", "", text).lower()
    nums = re.findall(r"(?<![a-z0-9])(?:\d{3,}|\d{1,2}(?=달러|원|%|일|월|니트|시간))", want)  # 모델명 속 숫자 제외
    for i in range(tries):
        mp3 = gtts(text, spec)
        ok_mark = mp3.with_suffix(".ok")
        if ok_mark.exists():
            return mp3  # 이미 검증 통과한 캐시
        best = None
        for model in ("latest_long", "default"):
            got = re.sub(r"[^0-9a-z가-힣]", "", "".join(c for c, _ in stt_chars(mp3, model)).lower())
            runs_ = re.findall(r"\d+", got)
            ratio = difflib.SequenceMatcher(None, want, got, autojunk=False).ratio()
            miss = [n for n in nums if n not in got and not any(r.startswith(n) for r in runs_)]  # STT가 329만→3290000 펼쳐도 통과
            if best is None or ratio > best[1]:
                best = (model, ratio, got, miss)
            d_ok = 0.05 * len(text) <= dur(mp3) <= 0.35 * len(text) + 1.5  # 하한 0.05: 1.5배속 대응  # 길이(초)가 글자 수에 비례하면 통째로 빠지거나 프롬프트가 읽힌 건 아님
            if len(got) <= 1.5 * len(want) + 6 and d_ok and ratio >= 0.35 and not miss:  # ratio 0.35: STT가 브랜드명을 심하게 틀려도 통과
                ok_mark.write_text(json.dumps({"model": model, "got": got}, ensure_ascii=False))
                return mp3
        model, ratio, got, miss = best
        print(f"  TTS 재합성({i + 1}/{tries}) [{text[:18]}…] 길이 {len(got)}/{len(want)} 유사도 {ratio:.2f}({model}) 숫자누락 {miss}\n     들린 것: {got[:140]}", file=sys.stderr)
        for q in (mp3, mp3.with_suffix(".stt.json"), mp3.with_suffix(".stt_default.json"), mp3.with_suffix(".16k.wav")):
            q.unlink(missing_ok=True)
    sys.exit(f"TTS 검증 3회 실패: '{text}' — 숫자를 한글로 풀어 쓰거나 스타일 프롬프트를 바꿔라")


def patched_template():
    s = (HERE / "reel-template.jsx").read_text()
    def rep(old, new, flags=0):
        nonlocal s
        s2 = re.sub(old, new, s, count=1, flags=flags) if flags else s.replace(old, new, 1)
        assert s2 != s, f"패치 실패: {old[:60]}"
        s = s2
    rep(r"  R\.useEffect\(\(\) => \{\n    if \(kind !== 'video'\) return;.*?\n  \}\);\n", "", re.S)
    rep('preload="auto" loop', 'preload="auto"')
    rep("function Media(", """function timeChunksAt(str, start, end, times) {
  const ch = timeChunks(str, start, end);
  if (!times || times.length !== ch.length) return ch;
  ch.forEach((c, i) => {
    c.a = times[i]; c.b = i + 1 < ch.length ? times[i + 1] : end;
    const len = c.segs.reduce((n, s) => n + s.text.replace(/\\s/g, '').length, 0);
    const reveal = Math.min((c.b - c.a) * 0.6, len * 0.075);
    let acc = 0;
    c.segs.forEach(s => { s.at = c.a + reveal * (acc / Math.max(1, len)); acc += s.text.replace(/\\s/g, '').length; });
  });
  return ch;
}

function Media(""")
    rep("...timeChunks(p.hookSubs, CUES['도입부'] + 1.2, M),", "...timeChunksAt(p.hookSubs, CUES['도입부'] + 1.2, M, p.hookTimes),")
    rep("...timeChunks(p.bodySubs, M + 0.3, CUES['마지막'] - 0.2),", "...timeChunksAt(p.bodySubs, M + 0.3, CUES['마지막'] - 0.2, p.bodyTimes),")
    # 04 리스트: 챕터 전환을 STT 정렬된 bodyTimes 에 맞춤(개수가 같을 때)
    rep("""  const s0 = M + 0.3, s1 = Lc - 0.2, seg = (s1 - s0) / n;
  const idx = Math.max(0, Math.min(n - 1, Math.floor((T - s0) / seg)));
  const ck = MOTION.pop(T, s0 + idx * seg, 0.4), ca = p01(T, s0 + idx * seg, 0.1);""",
        """  const s0 = M + 0.3, s1 = Lc - 0.2, seg = (s1 - s0) / n;
  const starts = (p.bodyTimes && p.bodyTimes.length === n) ? p.bodyTimes : Array.from({ length: n }, (_, i) => s0 + i * seg);
  const ends = starts.map((s, i) => i + 1 < n ? starts[i + 1] : s1);
  let idx = 0; for (let i = 0; i < n; i++) if (T >= starts[i]) idx = i;
  const ck = MOTION.pop(T, starts[idx], 0.4), ca = p01(T, starts[idx], 0.1);""")
    rep("<div style={{ width: `${p01(T, s0 + i * seg, seg) * 100}%`, height: '100%', background: accent }} />",
        "<div style={{ width: `${p01(T, starts[i], ends[i] - starts[i]) * 100}%`, height: '100%', background: accent }} />")
    rep("const s = CUES['중반부'] + 4.4;", "const s = p.cardAt != null ? p.cardAt : CUES['중반부'] + 4.4;")
    rep("if (k <= 0) return null;\n  const out = MOTION.enter(T, CUES['마지막'] - 0.2, 0.3);", "if (k <= 0 || !p.cardAfter) return null;\n  const out = MOTION.enter(T, CUES['마지막'] - 0.2, 0.3);")
    rep("          <span style={{ position: 'absolute', left: -4, top: '50%', height: 6, width: `calc(${strike * 100}% + 8px)`, background: '#fff', borderRadius: 3 }} />",
        "          {p.cardStrike !== false && <span style={{ position: 'absolute', left: -4, top: '50%', height: 6, width: `calc(${strike * 100}% + 8px)`, background: '#fff', borderRadius: 3 }} />}")
    rep('playback={window.OM_PLAYBACK} bg="#000">', 'playback={window.OM_PLAYBACK} bg="#000" autoplay="false">')
    return s


HARNESS = """<!doctype html><html><head><meta charset="utf-8">
<style>
@font-face{font-family:'Pretendard Variable';font-weight:700;src:url('fonts/Pretendard-Bold.otf')}
@font-face{font-family:'Pretendard Variable';font-weight:800;src:url('fonts/Pretendard-ExtraBold.otf')}
@font-face{font-family:'Pretendard Variable';font-weight:900;src:url('fonts/Pretendard-Black.otf')}
@font-face{font-family:'Anton';src:url('fonts/Anton-Regular.ttf')}
@font-face{font-family:'Unbounded';font-weight:200 900;src:url('fonts/Unbounded.ttf')}
html,body{margin:0;background:#000;overflow:hidden} #root{position:fixed;inset:0}
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone@7.26.4/babel.min.js"></script>
<script>window.OM_SCENES=__SCENES__; window.OM_PLAYBACK='{"mode":"times","count":1}'; window.PROPS=__PROPS__;</script>
</head><body><div id="root"></div>
<script type="text/babel" data-presets="react">__ENGINE__</script>
<script type="text/babel" data-presets="react">__TEMPLATE__</script>
<script type="text/babel" data-presets="react">
ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(window.ReelTemplate, window.PROPS));
window.__ready = async () => {
  await document.fonts.load("800 80px 'Pretendard Variable'"); await document.fonts.load("900 80px 'Pretendard Variable'");
  await document.fonts.load("700 30px 'Pretendard Variable'"); await document.fonts.load("200px Anton"); await document.fonts.load("900 40px Unbounded");
  const v = document.querySelector('video');
  if (v) { v.pause(); if (v.readyState < 2) await new Promise(r => v.addEventListener('loadeddata', r, {once: true})); }
  return !!document.querySelector('[data-om-exportable-video-with-duration-secs]');
};
window.__seek = async (t) => {
  const svg = document.querySelector('[data-om-exportable-video-with-duration-secs]');
  svg.dispatchEvent(new CustomEvent('data-om-seek-to-time-frame', {detail: {time: t, sync: true}}));
  const v = document.querySelector('video');
  if (v) { v.pause(); if (Math.abs(v.currentTime - t) > 0.002) {
    await new Promise(r => { v.addEventListener('seeked', r, {once: true}); setTimeout(r, 500); v.currentTime = t; }); } }
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  return true;
};
</script></body></html>"""


SFX = HERE / "sfx"  # ffmpeg 합성 효과음(whoosh/pop/ding/tick/riser/thud) — 샘플 라이브러리로 바꾸려면 같은 이름 wav 교체
POP_AT = {"number": 0.65, "vs": 1.35, "list": 0.55, "date": 0.65, "convert": 0.65, "card": 0.7, "rank": 0.6, "specs": 0.75, "breaking": 0.05,
          "drop": 0.85, "collab": 0.55, "colorway": 0.75, "stat": 0.65}


def sfx_track(events, total, work):
    """[(이름, 시각)] → 한 트랙 wav. 효과음은 -9dB 기준, whoosh 는 컷 0.15초 전에 시작."""
    events = [(n, max(0.0, t)) for n, t in events if (SFX / f"{n}.wav").exists() and t < total]
    out = work / "sfx.wav"
    if not events:
        return None
    cmd, fc, lab = ["ffmpeg", "-y", "-v", "error"], [], ""
    for i, (n, t) in enumerate(events):
        cmd += ["-i", str(SFX / f"{n}.wav")]
        fc.append(f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,adelay={int(t * 1000)}:all=1[e{i}]")
        lab += f"[e{i}]"
    fc.append(f"{lab}amix=inputs={len(events)}:normalize=0:dropout_transition=0,atrim=duration={total}[a]")
    run(cmd + ["-filter_complex", ";".join(fc), "-map", "[a]", str(out)])
    return out


def build(spec_path, out_path):
    spec = json.loads(Path(spec_path).read_text())
    base = Path(spec_path).resolve().parent
    work = HERE / "work" / Path(out_path).stem
    work.mkdir(parents=True, exist_ok=True)
    props = dict(spec["props"])

    # 1) 나레이션 → 장면 길이
    voice, sdur, cue, raw = {}, {}, {}, {}
    SPEED = float(spec.get("speed", 1.0))
    t = 0.0
    SN = (["훅"] if spec["narration"].get("훅") else []) + SCENES  # 훅 = 퀴즈형 블러 인트로(2026-10-18 사용자 지시: 모든 릴스 시작은 Reel 03 스타일)
    if "훅" in SN and not spec["cuts"].get("훅"):
        spec["cuts"]["훅"] = [{k: v for k, v in spec["cuts"]["도입부"][0].items() if k != "dur"}]
    for name in SN:
        raw[name] = tts_checked(spec["narration"][name], spec)
        mp3 = speedup(raw[name], SPEED)
        d = dur(mp3)
        tail = {"훅": 0.8, "도입부": 0.6, "중반부": 0.9, "마지막": 2.2}[name]  # 10/19 사용자: 읽을 시간 — 나레이션 끝나고도 글자가 남는 여유
        lay = props.get("layout", "number")
        mins = {"훅": 3.4, "도입부": 4.0, "중반부": 7.0 if lay == "list" else 6.0, "마지막": 4.8}
        sd = max(VOICE_T0[name] + d + tail, mins[name])
        voice[name], sdur[name], cue[name] = mp3, round(sd, 3), round(t, 3)
        t += sd
    T = round(t, 3)
    scenes = [{"name": n, "dur": sdur[n], "desc": n} for n in SN]
    print("장면:", {n: (cue[n], sdur[n]) for n in SN}, "총", T)

    # 2) 자막 청크 정렬 (STT)
    for key, name, subs in (("bodyTimes", "중반부", props.get("bodySubs")), ("hookTimes", "도입부", props.get("hookSubs"))):
        if not subs:
            continue
        chunks = [c.strip() for c in subs.split("/") if c.strip()]
        okf = raw[name].with_suffix(".ok")
        model = json.loads(okf.read_text()).get("model", "latest_long") if okf.exists() and okf.read_text().startswith("{") else "latest_long"
        rel = align(chunks, stt_chars(raw[name], model), dur(raw[name]))
        props[key] = [round(cue[name] + VOICE_T0[name] + r / SPEED, 3) for r in rel]  # 원본 시각 ÷ 배속
        print(f"{key}:", list(zip(chunks, props[key])))
    if spec.get("card_chunk") is not None and "bodyTimes" in props:
        props["cardAt"] = props["bodyTimes"][spec["card_chunk"]]

    # 3) 베이스 영상 (장면별 컷, 9:16 cover + 팬, 전부 키프레임 → Chrome seek 빠름)
    # sync_cuts: 중반부 컷 수 == 자막 청크 수면 컷 경계를 STT 정렬된 청크 시작에 맞춘다(2026-10-17 교훈: 고정 길이면 1~2초 어긋남)
    if spec.get("sync_cuts", True) and "bodyTimes" in props and len(spec["cuts"]["중반부"]) == len(props["bodyTimes"]):
        bt = [t - cue["중반부"] for t in props["bodyTimes"]]
        for i, c in enumerate(spec["cuts"]["중반부"]):
            c["dur"] = round(bt[i + 1] - bt[i], 3) if i + 1 < len(bt) else None
            if i == 0:
                c["dur"] = round(bt[1], 3)  # 첫 컷은 장면 시작부터 둘째 청크까지
        print("컷 동기화:", [c["dur"] for c in spec["cuts"]["중반부"]])
    cuts = []
    for name in SN:
        lst = spec["cuts"][name]
        fixed = sum(c["dur"] for c in lst if c.get("dur"))
        fill = round(sdur[name] - fixed, 3)
        assert fill > 0.3, f"{name}: 컷 길이가 장면보다 김"
        for c in lst:
            cuts.append({**c, "dur": c["dur"] if c.get("dur") else fill})
    props["cutTimes"], acc = [], 0.0
    for c in cuts:
        props["cutTimes"].append(round(acc, 3))
        acc += c["dur"]
    BW, BH = 1296, 2304  # 템플릿 펀치 줌(최대 1.2배)에도 원본 해상도 이하로 보이게 1.2배 크게
    clips = list(dict.fromkeys(str(base / c["clip"]) for c in cuts))
    cmd, fc, cat = ["ffmpeg", "-y", "-v", "error"], [], ""
    for cpath in clips:
        cmd += ["-i", cpath]
    for i, c in enumerate(cuts):
        k, z, d = clips.index(str(base / c["clip"])), c.get("zoom", 1.1), c["dur"]
        cx0, cx1 = (c["cx"] if isinstance(c["cx"], list) else [c["cx"]] * 2)
        assert c["in"] + d <= dur(base / c["clip"]) - 0.1, f"컷{i}: 클립 길이 초과"
        fc.append(f"[{k}:v]trim=start={c['in']}:duration={d},setpts=PTS-STARTPTS,fps={FPS},"
                  f"crop=w='min(iw\\,ih/{z}*9/16)':h='ih/{z}':x='clip(iw*({cx0}+({cx1}-{cx0})*t/{d})-ow/2,0,iw-ow)':y='{c.get('yoff', 0)}*(ih-oh)',"
                  f"scale={BW}:{BH}:flags=lanczos" + (",eq=contrast=1.05:saturation=1.14,unsharp=5:5:0.5:5:5:0,vignette=a=PI/6" if spec.get("grade", True) else "") + f",setsar=1[v{i}]")
        cat += f"[v{i}]"
    fc.append(f"{cat}concat=n={len(cuts)}:v=1:a=0[v]")
    basemp4 = work / "base.mp4"
    run(cmd + ["-filter_complex", ";".join(fc), "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "11",
               "-g", "1", "-pix_fmt", "yuv420p", str(basemp4)])

    # 4) 하네스 HTML → Chrome 프레임 캡처
    props.update({"videoSrc": basemp4.as_uri(), "videoFit": "cover", "videoStart": 0, "sound": False})
    html = (HARNESS.replace("__SCENES__", json.dumps(json.dumps(scenes, ensure_ascii=False), ensure_ascii=False))
            .replace("__PROPS__", json.dumps(props, ensure_ascii=False))
            .replace("__ENGINE__", (HERE / "animations-v3.jsx").read_text().replace("</script", "<\\/script"))
            .replace("__TEMPLATE__", patched_template().replace("</script", "<\\/script")))
    page_path = HERE / f"harness_{Path(out_path).stem}.html"
    page_path.write_text(html)
    frames = work / "frames"
    frames.mkdir(exist_ok=True)
    for f in frames.glob("*.jpg"):
        f.unlink()
    n = int(round(T * FPS))
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        import os
        chan = os.environ.get("SHORTFORM_BROWSER", "chrome" if sys.platform == "darwin" else "chromium")  # 서버는 playwright chromium(10/20)
        b = p.chromium.launch(channel=None if chan == "chromium" else chan, headless=True, args=["--allow-file-access-from-files", "--no-sandbox", "--disable-dev-shm-usage"])
        pg = b.new_page(viewport={"width": W, "height": H + 44}, device_scale_factor=1)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.goto(page_path.as_uri())
        pg.wait_for_function("() => typeof window.__ready === 'function' && document.querySelector('svg[data-om-exportable-video-with-duration-secs]')", timeout=90000)
        assert pg.evaluate("() => window.__ready()"), "스테이지 없음"
        if errs:
            print("브라우저 오류:", errs[:5], file=sys.stderr)
        box = pg.locator("svg[data-om-exportable-video-with-duration-secs]").bounding_box()
        clip = {"x": round(box["x"]), "y": round(box["y"]), "width": W, "height": H}
        for i in range(n):
            pg.evaluate("t => window.__seek(t)", i / FPS)
            pg.screenshot(path=str(frames / f"{i:05d}.jpg"), type="jpeg", quality=100, clip=clip)
            if i % 150 == 0:
                print(f"  프레임 {i}/{n}", file=sys.stderr)
        b.close()
    if errs:
        print("브라우저 오류(렌더 중):", errs[:8], file=sys.stderr)

    # 5) 오디오 믹스 + 인코딩
    bgm = lyria(spec["bgm_prompt"])
    events = []
    if spec.get("sfx", True):
        lay = props.get("layout", "number")
        if "훅" in SN:
            events += [("riser", 0.0), ("ding", cue["도입부"] - 0.05)]
        events += [("pop", cue["도입부"] + POP_AT.get(lay, 0.65)), ("thud", cue["중반부"]), ("whoosh", cue["마지막"] - 0.15), ("pop", cue["마지막"] + 1.3)]
        scene_starts = set(cue.values())
        events += [("whoosh", t - 0.15) for t in props["cutTimes"] if t > 0.2 and all(abs(t - x) > 0.3 for x in scene_starts)]
        events += [("tick", t) for t in props.get("bodyTimes", [])[1:]]
    endcard = HERE / "endcard.mp4"  # 엔드카드(선택)(1.6초) — brand/endcard.html 로 생성
    ED = dur(endcard) if (endcard.exists() and spec.get("endcard", True)) else 0.0
    TT = round(T + ED, 3)
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", str(frames / "%05d.jpg")]
    for name in SN:
        cmd += ["-i", str(voice[name])]
    cmd += ["-stream_loop", "-1", "-i", str(bgm)]
    if ED:
        cmd += ["-i", str(endcard)]
    sfx = sfx_track(events, TT, work) if events else None
    SFX_I = len(SN) + 2 + (1 if ED else 0)
    if sfx:
        cmd += ["-i", str(sfx)]
    fc, mix = [], ""
    if ED:
        fc.append(f"[0:v]setsar=1,format=yuv420p[mv];[{len(SN) + 2}:v]fps={FPS},scale={W}:{H},setsar=1,format=yuv420p[ev];[mv][ev]concat=n=2:v=1:a=0[vout]")
    for i, name in enumerate(SN):
        gain = round(max(-6, min(9, -15.0 - lufs(voice[name]))) + spec.get("voice_db", 1), 1)  # 목소리마다 -15 LUFS 로 맞춤(보이스 로테이션 대응)
        fc.append(f"[{i + 1}:a]adelay={int((cue[name] + VOICE_T0[name]) * 1000)}:all=1,volume={gain}dB,"
                  f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[s{i}]")
        mix += f"[s{i}]"
    duck = spec.get("duck", True)
    fc.append(f"[{len(SN) + 1}:a]volume={spec.get('bgm_db', -20) + (3 if duck else 0)}dB,atrim=duration={TT},afade=t=out:st={TT - 1.2:.2f}:d=1.2,"
              f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[bg]")
    fc.append(f"{mix}amix=inputs={len(SN)}:normalize=0:dropout_transition=0,apad=whole_dur={TT}[vo]")
    if duck:  # 목소리 나올 때 BGM 자동 감소(사이드체인) — 2026-10-18 청취감 개선
        fc.append("[vo]asplit[vo1][vo2];[bg][vo2]sidechaincompress=threshold=0.03:ratio=6:attack=12:release=320:makeup=1[bgd]")
        final = ["[vo1]", "[bgd]"]
    else:
        final = ["[vo]", "[bg]"]
    if sfx:
        fc.append(f"[{SFX_I}:a]volume=-9dB,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[sf]")
        final.append("[sf]")
    fc.append("".join(final) + f"amix=inputs={len(final)}:normalize=0:dropout_transition=0,alimiter=limit=0.95[a]")
    run(cmd + ["-filter_complex", ";".join(fc), "-map", "[vout]" if ED else "0:v", "-map", "[a]", "-t", f"{TT:.3f}", "-c:v", "libx264", "-preset", "slow",
               "-crf", "14", "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(out_path)])
    print(f"완료: {out_path} ({TT}s = 본편 {T}s + 엔드카드 {ED:.1f}s, {n}프레임)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
