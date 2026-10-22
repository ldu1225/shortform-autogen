(function () {
const R = React;
const p01 = (T, s, d) => Math.max(0, Math.min(1, (T - s) / d));
const mix = (a, b, t) => a + (b - a) * t;
const MOTION = {
  enter: (T, s, d = 0.4) => window.Easing.easeOutCubic(p01(T, s, d)),
  draw: (T, s, d = 0.5) => window.Easing.easeInOutCubic(p01(T, s, d)),
  pop: (T, s, d = 0.35) => window.Easing.easeOutBack(p01(T, s, d)),
};
const FONT = "'Pretendard Variable', Pretendard, sans-serif";
const NUM = "Anton, 'Pretendard Variable', sans-serif";
const INK = '#0B0B0C';
const SUB_TOP = 1120;
const COL = { position: 'absolute', left: 72, right: 72, top: 236, fontFamily: FONT };
const rise = (k, d = 34) => `translateY(${mix(d, 0, k)}px)`;
const pad = i => String(i + 1).padStart(2, '0');

// "가격이 *4,900달러*였는데" → [{text,kw,sp}] ; *…* = 강조
function parseMarked(str) {
  const segs = []; let tok = ''; let kw = false; let sp = false;
  const flush = () => {
    const t = tok.trim();
    if (t) { segs.push({ text: t, kw, sp: sp && segs.length > 0 }); sp = false; }
    tok = '';
  };
  for (const ch of String(str || '')) {
    if (ch === '*') { flush(); kw = !kw; continue; }
    if (/\s/.test(ch) && !kw) { flush(); sp = true; continue; }
    tok += ch;
  }
  flush();
  return segs;
}
function groupWords(segs) {
  const out = [];
  segs.forEach((s, i) => { if (i === 0 || s.sp) out.push([]); out[out.length - 1].push(s); });
  return out;
}
function timeChunks(str, start, end) {
  const chunks = String(str || '').split('/').map(s => s.trim()).filter(Boolean).map(c => {
    const segs = parseMarked(c);
    const len = segs.reduce((n, s) => n + s.text.replace(/\s/g, '').length, 0);
    return { segs, len };
  });
  if (!chunks.length || !(end > start)) return [];
  const w = chunks.reduce((n, c) => n + c.len + 4, 0);
  let t = start;
  return chunks.map(c => {
    const d = (end - start) * (c.len + 4) / w;
    const a = t, b = t + d; t = b;
    const reveal = Math.min(d * 0.6, c.len * 0.075);
    let acc = 0;
    c.segs.forEach(s => { s.at = a + reveal * (acc / Math.max(1, c.len)); acc += s.text.replace(/\s/g, '').length; });
    return { a, b, segs: c.segs };
  });
}

function Marked({ text, accent, mode, T, start, step }) {
  const groups = groupWords(parseMarked(text));
  const stp = step || 0.12;
  let idx = 0;
  return groups.map((w, wi) => (
    <R.Fragment key={wi}>
      {wi > 0 ? ' ' : null}
      <span style={{ whiteSpace: 'nowrap' }}>
        {w.map((s, si) => {
          const i = idx++;
          let o = 1, tf = '';
          if (start != null) {
            const at = start + i * stp, k = MOTION.pop(T, at, 0.3);
            o = p01(T, at, 0.08); tf = `translateY(${mix(26, 0, k)}px) scale(${mix(0.8, 1, k)}) `;
          }
          const base = { display: 'inline-block', opacity: o, transform: tf || undefined };
          if (!s.kw) return <span key={si} style={base}>{s.text}</span>;
          if (mode === 'color') return <span key={si} style={{ ...base, color: accent }}>{s.text}</span>;
          return <span key={si} style={{ ...base, background: accent, color: INK, padding: '0 0.14em 0.04em', margin: '0 0.04em', borderRadius: '0.12em', transform: tf + 'rotate(-2deg)' }}>{s.text}</span>;
        })}
      </span>
    </R.Fragment>
  ));
}

function Media({ src, kind, fit, start, sound, T, end, blur, cuts }) {
  const c = window.useComposition();
  const fg = R.useRef(null), bg = R.useRef(null);
  R.useEffect(() => {
    if (kind !== 'video') return;
    [fg.current, bg.current].forEach((v, i) => {
      if (!v) return;
      v.muted = i === 0 ? !sound : true;
      const d = v.duration;
      let target = (+start || 0) + c.time;
      if (d && isFinite(d)) target = target % d;
      if (c.playing) {
        if (v.paused) { const pr = v.play(); if (pr) pr.catch(() => {}); }
        if (Math.abs(v.currentTime - target) > 0.35) v.currentTime = target;
      } else {
        if (!v.paused) v.pause();
        if (Math.abs(v.currentTime - target) > 0.04) v.currentTime = target;
      }
    });
  });
  const b = blur || 0;
  // 컷 전환 다이내믹: cuts(컷 시작 시각 배열)가 오면 컷마다 펀치 줌(1.14→1) + 푸시인(1→1.06) + 화이트 플래시 + 짧은 흔들림
  const cs = cuts && cuts.length ? cuts.filter(x => x <= T).pop() ?? 0 : null;
  const ce = cs != null ? (cuts.find(x => x > T) ?? end) : end;
  const punch = cs != null && cs > 0.01 ? Math.pow(1 - p01(T, cs, 0.24), 3) * 0.7 : 0;  // 10/19 사용자: 전환이 너무 빠르다 → 펀치·플래시 완화
  const ci = cs != null && cuts ? cuts.indexOf(cs) : 0;
  const prog = cs != null ? Math.min(1, (T - cs) / Math.max(0.4, ce - cs)) : 0;
  const push = cs != null ? (ci % 2 ? mix(1.08, 1.02, prog) : mix(1.0, 1.07, prog)) : 0;  // 짝수 컷 푸시인, 홀수 컷 풀아웃
  const panX = cs != null ? (ci % 3 === 1 ? 1 : ci % 3 === 2 ? -1 : 0) * mix(-14, 14, prog) : 0;
  const zoom = (cs != null ? push + 0.14 * punch : mix(1.02, 1.1, Math.min(1, T / end))) + b * 0.004;
  const flash = cs != null && cs > 0.01 ? 0.35 * Math.pow(1 - p01(T, cs, 0.1), 2) : 0;
  const jx = punch > 0.02 ? 18 * punch * Math.sin(T * 140) : 0;
  const isFit = fit === 'fit';
  const fill = { position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', display: 'block' };
  const el = (ref, style, main) => kind === 'video'
    ? <video ref={ref} src={src} muted={main ? !sound : true} playsInline preload="auto" loop
        {...(main ? { 'data-om-exportable-video-play-start': +start || 0, 'data-om-exportable-video-play-end': (+start || 0) + c.duration } : {})}
        style={style} />
    : <img src={src} alt="" style={style} />;
  return (
    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', background: '#000' }}>
      <div style={{ position: 'absolute', inset: 0, transform: `translateX(${jx + panX}px) scale(${zoom})`, filter: b > 0.5 ? `blur(${b}px)` : (punch > 0.15 ? `blur(${(punch * 6).toFixed(1)}px)` : 'none') }}>
        {isFit && el(bg, { ...fill, filter: 'blur(40px) brightness(0.5)', transform: 'scale(1.2)' }, false)}
        {el(fg, { ...fill, objectFit: isFit ? 'contain' : 'cover' }, true)}
      </div>
      {flash > 0.01 && <div style={{ position: 'absolute', inset: 0, background: '#fff', opacity: flash }} />}
    </div>
  );
}

function Scrim({ T, CUES, from, h1, h2 }) {
  const m = MOTION.draw(T, CUES['중반부'] - 0.3, 0.6);
  const out = MOTION.enter(T, CUES['마지막'] - 0.15, 0.4);
  const k = MOTION.enter(T, from || 0, 0.3) * (1 - out);
  return <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: mix(h1 || 1150, h2 || 820, m), opacity: k,
    background: 'linear-gradient(180deg, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.74) 42%, rgba(0,0,0,0) 100%)' }} />;
}

function Kicker({ T, m, accent, text }) {
  const kick = MOTION.enter(T, 0.05, 0.4), bar = MOTION.draw(T, 0.05, 0.45);
  return (
    <div style={{ height: mix(64, 0, m), opacity: kick * (1 - m), overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 18, color: '#fff', fontSize: 28, fontWeight: 700, letterSpacing: '0.18em', transform: rise(kick, 20) }}>
        <span style={{ width: 56 * bar, height: 4, background: accent, flexShrink: 0 }} />
        <span>{text}</span>
      </div>
    </div>
  );
}

// 01 숫자 훅
function HeaderNumber({ T, CUES, p, accent }) {
  const m = MOTION.draw(T, CUES['중반부'] - 0.3, 0.6);
  const out = MOTION.enter(T, CUES['마지막'] - 0.15, 0.4);
  const l1 = MOTION.enter(T, 0.2, 0.45), l2 = MOTION.enter(T, 0.4, 0.45);
  const nk = MOTION.pop(T, 0.65, 0.45), na = p01(T, 0.65, 0.1);
  const u = MOTION.enter(T, 0.95, 0.35);
  const breathe = 1 + 0.03 * MOTION.draw(T, 1.1, 2.2) * (1 - m);
  const line = mix(62, 44, m), num = mix(290, 150, m), unit = mix(88, 50, m);
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} />
      <div style={{ ...COL, opacity: 1 - out, transform: `translateY(${-50 * out}px)` }}>
        <Kicker T={T} m={m} accent={accent} text={p.kicker} />
        <div style={{ maxWidth: mix(936, 640, m), color: '#fff', fontSize: line, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.22, opacity: l1, transform: rise(l1) }}>{p.line1}</div>
        <div style={{ color: '#fff', fontSize: line, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.22, opacity: l2, transform: rise(l2) }}>{p.lead}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: mix(18, 12, m), marginTop: mix(6, 2, m) }}>
          <span style={{ fontFamily: NUM, fontSize: num, lineHeight: 1, color: accent, display: 'inline-block', transformOrigin: 'left bottom', transform: `scale(${mix(1.45, 1, nk) * breathe})`, opacity: na }}>{p.number}</span>
          <span style={{ color: '#fff', fontSize: unit, fontWeight: 900, letterSpacing: '-0.05em', opacity: u, transform: rise(u) }}>{p.unit}</span>
        </div>
      </div>
    </R.Fragment>
  );
}

function FactCard({ T, CUES, p, accent }) {
  const s = CUES['중반부'] + 4.4;
  const k = MOTION.enter(T, s, 0.45);
  if (k <= 0) return null;
  const out = MOTION.enter(T, CUES['마지막'] - 0.2, 0.3);
  const strike = MOTION.draw(T, s + 0.35, 0.4);
  const af = MOTION.pop(T, s + 0.5, 0.4);
  const b = MOTION.pop(T, s + 0.8, 0.4), ba = p01(T, s + 0.8, 0.1);
  return (
    <div style={{ position: 'absolute', left: 72, top: 548, display: 'flex', alignItems: 'center', gap: 28, padding: '26px 34px',
      background: 'rgba(14,14,16,0.84)', borderRadius: 24, border: '1px solid rgba(255,255,255,0.1)', fontFamily: FONT,
      opacity: k * (1 - out), transform: `translateX(${mix(-60, 0, k)}px)` }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span style={{ color: '#E2E2E2', fontSize: 26, fontWeight: 700 }}>{p.cardBeforeLabel}</span>
        <span style={{ position: 'relative', color: '#D2D2D2', fontSize: 60, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1 }}>
          {p.cardBefore}
          <span style={{ position: 'absolute', left: -4, top: '50%', height: 6, width: `calc(${strike * 100}% + 8px)`, background: '#fff', borderRadius: 3 }} />
        </span>
      </div>
      <span style={{ color: '#fff', fontSize: 52, fontWeight: 800 }}>→</span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span style={{ color: accent, fontSize: 26, fontWeight: 800 }}>{p.cardAfterLabel}</span>
        <span style={{ color: '#fff', fontSize: 88, fontWeight: 900, letterSpacing: '-0.045em', lineHeight: 1, display: 'inline-block', transformOrigin: 'left center', transform: `scale(${mix(0.8, 1, af)})` }}>{p.cardAfter}</span>
      </div>
      <span style={{ alignSelf: 'flex-start', background: accent, color: INK, fontSize: 38, fontWeight: 900, letterSpacing: '-0.02em', padding: '8px 16px', borderRadius: 12, opacity: ba, transform: `scale(${mix(0.4, 1, b)}) rotate(-4deg)` }}>{p.cardBadge}</span>
    </div>
  );
}

// 02 가격 비교
function HeaderVS({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.35, 0.45);
  const out = MOTION.enter(T, CUES['마지막'] - 0.15, 0.4);
  const b = MOTION.enter(T, 0.25, 0.45);
  const strike = MOTION.draw(T, 0.95, 0.35);
  const a = MOTION.pop(T, 1.35, 0.45), aa = p01(T, 1.35, 0.1);
  const st = MOTION.pop(T, 1.9, 0.4), sta = p01(T, 1.9, 0.08);
  const breathe = 1 + 0.03 * MOTION.draw(T, 2.1, 1.4);
  const c = MOTION.enter(T, M - 0.05, 0.45);
  const strikeBar = w => <span style={{ position: 'absolute', left: -6, top: '52%', height: '0.07em', width: `calc(${w * 100}% + 12px)`, background: '#fff', borderRadius: 4 }} />;
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} />
      <div style={{ ...COL, opacity: 1 - m }}>
        <Kicker T={T} m={0} accent={accent} text={p.kicker} />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 6, opacity: b, transform: rise(b) }}>
          <span style={{ color: '#E2E2E2', fontSize: 30, fontWeight: 700 }}>{p.beforeLabel}</span>
          <span style={{ position: 'relative', fontFamily: NUM, fontSize: 170, lineHeight: 1.04, color: '#C4C4C4' }}>{p.before}{strikeBar(strike)}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginTop: 34 }}>
          <span style={{ color: accent, fontSize: 32, fontWeight: 800, opacity: aa }}>{p.afterLabel}</span>
          <span style={{ background: '#fff', color: INK, fontSize: 50, fontWeight: 900, letterSpacing: '-0.03em', padding: '6px 18px', borderRadius: 12, display: 'inline-block', opacity: sta, transform: `scale(${mix(2.2, 1, st)}) rotate(-6deg)` }}>{p.badge}</span>
        </div>
        <span style={{ fontFamily: NUM, fontSize: 270, lineHeight: 1.02, color: accent, display: 'inline-block', transformOrigin: 'left bottom', transform: `scale(${mix(1.45, 1, a) * breathe})`, opacity: aa }}>{p.after}</span>
      </div>
      <div style={{ ...COL, opacity: c * (1 - out), transform: `translateY(${mix(-24, 0, c) - 50 * out}px)` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, color: '#fff', fontSize: 28, fontWeight: 700, letterSpacing: '0.18em' }}>
          <span style={{ width: 56, height: 4, background: accent }} />
          <span>{p.kicker}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginTop: 22 }}>
          <span style={{ position: 'relative', fontFamily: NUM, fontSize: 64, lineHeight: 1, color: '#CDCDCD' }}>{p.before}{strikeBar(1)}</span>
          <span style={{ color: '#fff', fontSize: 48, fontWeight: 800 }}>→</span>
          <span style={{ fontFamily: NUM, fontSize: 112, lineHeight: 1, color: accent }}>{p.after}</span>
          <span style={{ background: '#fff', color: INK, fontSize: 34, fontWeight: 900, padding: '4px 14px', borderRadius: 10, transform: 'rotate(-6deg)' }}>{p.badge}</span>
        </div>
      </div>
    </R.Fragment>
  );
}

// 03 퀴즈
function HeaderQuestion({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.35, 0.4);
  const out = MOTION.enter(T, CUES['마지막'] - 0.15, 0.4);
  const chip = MOTION.pop(T, 0.1, 0.4), chipA = p01(T, 0.1, 0.1);
  const ta = p01(T, 1.5, 0.25), timer = p01(T, 1.6, Math.max(0.5, M - 2.0));
  const q = MOTION.enter(T, M - 0.05, 0.4);
  const r = MOTION.pop(T, M + 0.2, 0.5), ra = p01(T, M + 0.2, 0.1);
  const u = MOTION.enter(T, M + 0.45, 0.35);
  const breathe = 1 + 0.03 * MOTION.draw(T, M + 0.7, 2.2);
  const plain = String(p.question || '').replace(/\*/g, '');
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} from={M - 0.2} h1={900} h2={900} />
      <div style={{ position: 'absolute', left: 90, right: 90, top: 470, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', fontFamily: FONT, opacity: 1 - m, transform: `scale(${mix(1, 0.92, m)})` }}>
        <span style={{ border: `3px solid ${accent}`, color: '#fff', fontSize: 34, fontWeight: 800, letterSpacing: '-0.01em', padding: '10px 28px', borderRadius: 999, opacity: chipA, transform: `scale(${mix(0.6, 1, chip)})` }}>{p.kicker}</span>
        <div style={{ marginTop: 48, color: '#fff', fontSize: 116, fontWeight: 900, letterSpacing: '-0.05em', lineHeight: 1.18, textWrap: 'balance' }}>
          <Marked text={p.question} accent={accent} T={T} start={0.35} step={0.16} />
        </div>
        <div style={{ marginTop: 72, width: 440, height: 10, borderRadius: 99, background: 'rgba(255,255,255,0.22)', overflow: 'hidden', opacity: ta }}>
          <div style={{ width: `${timer * 100}%`, height: '100%', background: accent }} />
        </div>
      </div>
      <div style={{ ...COL, opacity: q * (1 - out), transform: `translateY(${mix(-24, 0, q) - 50 * out}px)` }}>
        <div style={{ maxWidth: 620, color: '#E8E8E8', fontSize: 40, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.3 }}>Q. {plain}</div>
        <div style={{ display: 'flex', marginTop: 28 }}>
          <span style={{ background: accent, color: INK, fontSize: 38, fontWeight: 900, padding: '6px 18px', borderRadius: 10, display: 'inline-block', opacity: ra, transform: `scale(${mix(0.5, 1, r)}) rotate(-3deg)` }}>{p.answerLabel}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginTop: 6 }}>
          <span style={{ fontFamily: NUM, fontSize: 250, lineHeight: 1, color: accent, display: 'inline-block', transformOrigin: 'left bottom', transform: `scale(${mix(1.6, 1, r) * breathe})`, opacity: ra }}>{p.number}</span>
          <span style={{ color: '#fff', fontSize: 80, fontWeight: 900, letterSpacing: '-0.05em', opacity: u, transform: rise(u) }}>{p.unit}</span>
        </div>
      </div>
    </R.Fragment>
  );
}

// 04 TOP 리스트
function HeaderList({ T, CUES, p, accent }) {
  const M = CUES['중반부'], Lc = CUES['마지막'];
  const m = MOTION.draw(T, M - 0.3, 0.5);
  const out = MOTION.enter(T, Lc - 0.15, 0.4);
  const pts = String(p.points || '').split('/').map(s => s.trim()).filter(Boolean);
  const n = Math.max(1, pts.length);
  const l1 = MOTION.enter(T, 0.2, 0.45);
  const nk = MOTION.pop(T, 0.55, 0.45), na = p01(T, 0.55, 0.1);
  const u = MOTION.enter(T, 0.85, 0.35);
  const s0 = M + 0.3, s1 = Lc - 0.2, seg = (s1 - s0) / n;
  const idx = Math.max(0, Math.min(n - 1, Math.floor((T - s0) / seg)));
  const ck = MOTION.pop(T, s0 + idx * seg, 0.4), ca = p01(T, s0 + idx * seg, 0.1);
  const c = MOTION.enter(T, M - 0.05, 0.4);
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} />
      <div style={{ ...COL, opacity: 1 - m }}>
        <Kicker T={T} m={0} accent={accent} text={p.kicker} />
        <div style={{ color: '#fff', fontSize: 72, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.2, opacity: l1, transform: rise(l1), textWrap: 'balance' }}>
          <Marked text={p.line1} accent={accent} />
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 20, marginTop: 4 }}>
          <span style={{ fontFamily: NUM, fontSize: 360, lineHeight: 1, color: accent, display: 'inline-block', transformOrigin: 'left bottom', transform: `scale(${mix(1.5, 1, nk)})`, opacity: na }}>{p.number}</span>
          <span style={{ color: '#fff', fontSize: 110, fontWeight: 900, letterSpacing: '-0.05em', opacity: u, transform: rise(u) }}>{p.unit}</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 20 }}>
          {pts.map((t, i) => {
            const at = 1.3 + i * 0.15, k = MOTION.pop(T, at, 0.35);
            return (
              <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, border: '2px solid rgba(255,255,255,0.55)', borderRadius: 999, padding: '10px 26px 10px 12px', background: 'rgba(0,0,0,0.35)', color: '#fff', fontSize: 34, fontWeight: 800, letterSpacing: '-0.02em', opacity: p01(T, at, 0.1), transform: `scale(${mix(0.6, 1, k)})` }}>
                <span style={{ background: accent, color: INK, fontFamily: NUM, fontSize: 28, lineHeight: 1, padding: '8px 11px', borderRadius: 999 }}>{pad(i)}</span>
                <span>{t}</span>
              </span>
            );
          })}
        </div>
      </div>
      <div style={{ ...COL, opacity: c * (1 - out), transform: `translateY(${mix(-24, 0, c) - 50 * out}px)` }}>
        <div style={{ maxWidth: 620, color: '#fff', fontSize: 44, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.25 }}>
          <Marked text={p.line1} accent={accent} mode="color" />
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 28 }}>
          {pts.map((t, i) => (
            <div key={i} style={{ flex: 1, height: 8, borderRadius: 99, background: 'rgba(255,255,255,0.25)', overflow: 'hidden' }}>
              <div style={{ width: `${p01(T, s0 + i * seg, seg) * 100}%`, height: '100%', background: accent }} />
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 28, marginTop: 30, opacity: ca, transform: `translateX(${mix(-40, 0, ck)}px)` }}>
          <span style={{ fontFamily: NUM, fontSize: 170, lineHeight: 1, color: accent }}>{pad(idx)}</span>
          <span style={{ color: '#fff', fontSize: 76, fontWeight: 900, letterSpacing: '-0.045em', lineHeight: 1.1 }}>{pts[idx] || ''}</span>
        </div>
      </div>
    </R.Fragment>
  );
}

// 05 속보
function HeaderBreaking({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.3, 0.6);
  const out = MOTION.enter(T, CUES['마지막'] - 0.15, 0.4);
  const tg = MOTION.pop(T, 0.05, 0.35), tga = p01(T, 0.05, 0.08);
  const kk = MOTION.enter(T, 0.25, 0.4);
  const tk = MOTION.draw(T, 1.4, 0.5);
  const live = 0.3 + 0.7 * (0.5 + 0.5 * Math.cos(T * 7));
  const items = String(p.ticker || '').split('/').map(s => s.trim()).filter(Boolean);
  const run = [...items, ...items, ...items];
  const shift = (T * 0.07) % 1;
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} />
      <div style={{ ...COL, opacity: 1 - out, transform: `translateY(${-50 * out}px)` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <span style={{ background: accent, color: INK, fontSize: 36, fontWeight: 900, letterSpacing: '-0.01em', padding: '6px 18px', borderRadius: 8, display: 'inline-block', transformOrigin: 'left center', opacity: tga, transform: `scale(${mix(1.6, 1, tg)})` }}>{p.tag}</span>
          <span style={{ width: 14, height: 14, borderRadius: 99, background: '#fff', opacity: live * kk }} />
          <span style={{ color: '#fff', fontSize: 30, fontWeight: 700, letterSpacing: '-0.01em', opacity: kk, transform: `translateX(${mix(-16, 0, kk)}px)` }}>{p.kicker}</span>
        </div>
        <div style={{ marginTop: mix(30, 22, m), color: '#fff', fontSize: mix(88, 60, m), fontWeight: 900, letterSpacing: '-0.045em', lineHeight: 1.18, textWrap: 'balance' }}>
          <Marked text={p.headline} accent={accent} T={T} start={0.4} step={0.12} />
        </div>
        <div style={{ marginTop: mix(40, 28, m), marginLeft: -72, width: tk * 1080, height: 76, overflow: 'hidden', background: '#fff' }}>
          <div style={{ display: 'flex', alignItems: 'center', height: '100%', whiteSpace: 'nowrap', width: 'max-content', transform: `translateX(${-shift * 33.3333}%)` }}>
            {run.map((t, i) => (
              <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 26, paddingLeft: 26, color: INK, fontSize: 34, fontWeight: 800, letterSpacing: '-0.02em' }}>
                <span style={{ width: 12, height: 12, background: accent, transform: 'rotate(45deg)' }} />
                <span>{t}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </R.Fragment>
  );
}

function Subtitles({ T, chunks, accent, band }) {
  const ch = chunks.find(c => T >= c.a && T < c.b);
  const glow = (
    <div style={{ position: 'absolute', left: -100, right: -100, top: SUB_TOP - 170, height: 560, opacity: band,
      background: 'radial-gradient(50% 50% at 50% 50%, rgba(0,0,0,0.42) 0%, rgba(0,0,0,0.22) 55%, rgba(0,0,0,0) 100%)' }} />
  );
  if (!ch) return glow;
  const ex = 1 - p01(T, ch.b - 0.1, 0.1);
  return (
    <R.Fragment>
      {glow}
      <div data-om-caption style={{ position: 'absolute', left: 100, right: 100, top: SUB_TOP, textAlign: 'center', fontFamily: FONT,
        fontSize: 80, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.32, color: '#fff', opacity: ex, textWrap: 'balance',
        WebkitTextStroke: '6px rgba(0,0,0,0.85)', paintOrder: 'stroke fill', textShadow: '0 4px 18px rgba(0,0,0,0.55)' }}>
        {groupWords(ch.segs).map((w, wi) => (
          <R.Fragment key={wi}>
            {wi > 0 ? ' ' : null}
            <span style={{ whiteSpace: 'nowrap' }}>
              {w.map((s, si) => {
                const k = MOTION.pop(T, s.at, 0.24), o = p01(T, s.at, 0.08);
                const base = { display: 'inline-block', opacity: o };
                return s.kw
                  ? <span key={si} style={{ ...base, background: accent, color: INK, WebkitTextStroke: 0, textShadow: 'none', fontWeight: 900,
                      padding: '0 0.16em 0.04em', margin: '0 0.04em', borderRadius: '0.14em', boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
                      transform: `translateY(${mix(14, 0, k)}px) scale(${mix(0.7, 1, k)}) rotate(-2deg)` }}>{s.text}</span>
                  : <span key={si} style={{ ...base, transform: `translateY(${mix(18, 0, k)}px) scale(${mix(0.85, 1, k)})` }}>{s.text}</span>;
              })}
            </span>
          </R.Fragment>
        ))}
      </div>
    </R.Fragment>
  );
}

function Outro({ T, CUES, p, accent, end }) {
  const s = CUES['마지막'];
  if (T < s) return null;
  const fade = 1 - MOTION.enter(T, end - 0.5, 0.4);
  const bar = MOTION.draw(T, s + 0.15, 0.45);
  const a = MOTION.enter(T, s + 0.25, 0.45), b = MOTION.enter(T, s + 0.5, 0.45);
  const kw = MOTION.pop(T, s + 0.8, 0.4);
  const cta = MOTION.pop(T, s + 1.3, 0.45), ctaA = p01(T, s + 1.3, 0.15);
  const h = MOTION.enter(T, s + 1.55, 0.4);
  const words = groupWords(parseMarked(p.outroLine2));
  return (
    <div style={{ position: 'absolute', left: 72, right: 72, top: 640, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', fontFamily: FONT, opacity: fade }}>
      <div style={{ width: 56 * bar, height: 4, background: accent, marginBottom: 40 }} />
      <div style={{ color: '#fff', fontSize: 68, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.2, opacity: a, transform: rise(a) }}>{p.outroLine1}</div>
      <div style={{ color: '#fff', fontSize: 96, fontWeight: 900, letterSpacing: '-0.05em', lineHeight: 1.25, marginTop: 8, opacity: b, transform: rise(b), textWrap: 'balance' }}>
        {words.map((w, wi) => (
          <R.Fragment key={wi}>
            {wi > 0 ? ' ' : null}
            <span style={{ whiteSpace: 'nowrap' }}>
              {w.map((sg, si) => sg.kw
                ? <span key={si} style={{ display: 'inline-block', background: accent, color: INK, padding: '0 0.16em 0.04em', margin: '0 0.04em', borderRadius: '0.14em', transform: `scale(${mix(0.6, 1, kw)}) rotate(-2deg)` }}>{sg.text}</span>
                : <span key={si}>{sg.text}</span>)}
            </span>
          </R.Fragment>
        ))}
      </div>
      <div style={{ marginTop: 120, display: 'flex', alignItems: 'center', gap: 18, background: '#fff', color: INK, borderRadius: 999, padding: '20px 40px 20px 20px',
        fontSize: 40, fontWeight: 800, letterSpacing: '-0.03em', opacity: ctaA, transform: `scale(${mix(0.7, 1, cta)})` }}>
        <span style={{ width: 60, height: 60, borderRadius: 999, background: accent, color: INK, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 46, fontWeight: 900, lineHeight: 1 }}>+</span>
        <span>{p.ctaText}</span>
      </div>
      <div style={{ marginTop: 24, color: '#fff', fontSize: 34, fontWeight: 700, letterSpacing: '-0.01em', opacity: h, transform: rise(h, 16) }}>{p.handle}</div>
    </div>
  );
}

// 우상단 원형 배지 — p.logoText(기본 "NEW"). 운영 채널의 로고는 저장소에 포함하지 않음.
function LogoIcon({ size, text }) {
  return (
    <div style={{ width: size, height: size, borderRadius: 999, background: '#FF4A1C', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 6px 22px rgba(0,0,0,0.35)', flexShrink: 0 }}>
      <span style={{ fontFamily: "Unbounded, 'Pretendard Variable', sans-serif", fontWeight: 900, fontSize: size * 0.26, letterSpacing: '-0.04em', color: '#fff' }}>{text || 'NEW'}</span>
    </div>
  );
}

function Badge({ T, end, p }) {
  if (p.platform === 'none') return null;
  const k = MOTION.enter(T, 0.3, 0.45) * (1 - MOTION.enter(T, end - 0.5, 0.4));
  if (p.logoIcon !== false) {
    return <div style={{ position: 'absolute', right: 64, top: 214, opacity: k, transform: `scale(${mix(0.6, 1, MOTION.pop(T, 0.3, 0.45))})`, transformOrigin: 'center' }}><LogoIcon size={104} text={p.logoText} /></div>;
  }
  if (!p.handle) return null;
  const glyph = p.platform === 'youtube'
    ? <span style={{ width: 38, height: 27, borderRadius: 8, background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <span style={{ width: 0, height: 0, borderTop: '7px solid transparent', borderBottom: '7px solid transparent', borderLeft: `11px solid ${INK}`, marginLeft: 3 }} />
      </span>
    : <span style={{ position: 'relative', width: 30, height: 30, borderRadius: 9, border: '3px solid #fff', boxSizing: 'border-box', flexShrink: 0 }}>
        <span style={{ position: 'absolute', left: '50%', top: '50%', width: 12, height: 12, margin: '-6px 0 0 -6px', borderRadius: 999, border: '3px solid #fff', boxSizing: 'border-box' }} />
        <span style={{ position: 'absolute', right: 3, top: 3, width: 4, height: 4, borderRadius: 999, background: '#fff' }} />
      </span>;
  return (
    <div style={{ position: 'absolute', right: 72, top: 232, display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px 10px 14px',
      background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(255,255,255,0.22)', borderRadius: 999, color: '#fff', fontFamily: FONT,
      fontSize: 28, fontWeight: 700, letterSpacing: '-0.01em', opacity: k, transform: `translateX(${mix(40, 0, k)}px)` }}>
      {glyph}<span>{p.handle}</span>
    </div>
  );
}

// u: -1 → 0 (cut, fully covered) → 1
const TW = 0.32;
function cutPhase(T, cuts) {
  for (const c of cuts) {
    const u = (T - c.at) / TW;
    if (u >= c.from && u <= c.to) return u;
  }
  return null;
}
function Transition({ u, kind, accent }) {
  if (u == null || kind === 'none') return null;
  if (kind === 'zoom') {
    const b = 1 - Math.abs(u);
    return <div style={{ position: 'absolute', inset: 0, background: '#fff', opacity: Math.pow(b, 4) * 0.9, pointerEvents: 'none' }} />;
  }
  const p = (u + 1) / 2;
  const e = window.Easing.easeInOutCubic;
  if (kind === 'shutter') {
    const n = 6, st = 0.025, span = 0.5 - (n - 1) * st;
    return (
      <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none' }}>
        {Array.from({ length: n }, (_, i) => {
          const dir = i % 2 ? 1 : -1;
          const a = e(Math.max(0, Math.min(1, (p - i * st) / span)));
          const b = e(Math.max(0, Math.min(1, (p - 0.5 - i * st) / span)));
          const x = dir * (1 - a) * 1120 - dir * b * 1120;
          return <div key={i} style={{ position: 'absolute', left: 0, width: 1080, top: i * 320, height: 321, background: i % 2 ? INK : accent, transform: `translateX(${x}px)` }} />;
        })}
      </div>
    );
  }
  const x1 = mix(-2100, 2100, e(p));
  const x2 = mix(-2100, 2100, e(Math.max(0, (p - 0.07) / 0.93)));
  const slab = (x, w, bg) => ({ position: 'absolute', top: -100, height: 2120, width: w, left: 540 - w / 2 + x, background: bg, transform: 'skewX(-18deg)' });
  return (
    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none' }}>
      <div style={slab(x1, 1900, accent)} />
      <div style={slab(x1 + 1010, 36, '#fff')} />
      <div style={slab(x2, 1900, INK)} />
    </div>
  );
}


// ── 06~10: 제품 정보 유형별 추가 레이아웃 (2026-10-17, 룩앤필 공유: COL/Kicker/Scrim/NUM/accent 칩) ──
const splitRows = str => String(str || '').split('/').map(s => s.trim()).filter(Boolean).map(r => r.split('|').map(x => x.trim()));
const isNum = v => /^[\d.,$%+\-~×xX\s]+[A-Za-z가-힣%]{0,6}$/.test(String(v || ''));
const numStyle = (size, color) => ({ fontFamily: NUM, fontSize: size, lineHeight: 1, color, letterSpacing: '0.01em' });
const txtStyle = (size, color, w = 900) => ({ fontFamily: FONT, fontSize: size, lineHeight: 1.05, color, fontWeight: w, letterSpacing: '-0.04em' });
const Val = ({ v, size, color }) => { const n = String(v || '').length; const f = isNum(v) ? 1 : n > 9 ? 0.5 : n > 6 ? 0.62 : 0.8; return <span style={{ ...(isNum(v) ? numStyle(size * f, color) : txtStyle(size * f, color)), whiteSpace: 'nowrap' }}>{v}</span>; };
const Compact = ({ T, CUES, children }) => {
  const c = MOTION.enter(T, CUES['중반부'] - 0.05, 0.45);
  const out = MOTION.enter(T, CUES['마지막'] - 0.15, 0.4);
  return <div style={{ ...COL, opacity: c * (1 - out), transform: `translateY(${mix(-24, 0, c) - 50 * out}px)` }}>{children}</div>;
};
const KickLine = ({ accent, text }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 18, color: '#fff', fontSize: 28, fontWeight: 700, letterSpacing: '0.18em' }}>
    <span style={{ width: 56, height: 4, background: accent }} /><span>{text}</span>
  </div>
);

// 06 스펙 비교 — 신형 vs 구형(또는 경쟁작) 항목 3~4줄, 가장 큰 변화 한 줄 강조
function HeaderSpecs({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.35, 0.45);
  const rows = splitRows(p.rows).filter(r => r.length >= 3);
  const hi = Math.max(0, Math.min(rows.length - 1, +p.highlight || 0));
  const l1 = MOTION.enter(T, 0.2, 0.45), h = MOTION.enter(T, 0.5, 0.4);
  const bk = MOTION.pop(T, 0.75 + rows.length * 0.38 + 0.2, 0.4), bka = p01(T, 0.75 + rows.length * 0.38 + 0.2, 0.08);
  const hrow = rows[hi] || ['', '', ''];
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} h1={1200} />
      <div style={{ ...COL, opacity: 1 - m }}>
        <Kicker T={T} m={0} accent={accent} text={p.kicker} />
        <div style={{ color: '#fff', fontSize: 62, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.2, opacity: l1, transform: rise(l1), textWrap: 'balance' }}><Marked text={p.line1} accent={accent} /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.15fr', gap: 12, marginTop: 34, opacity: h, transform: rise(h, 20) }}>
          <span style={{ color: '#CDCDCD', fontSize: 34, fontWeight: 800 }}>{p.leftName}</span>
          <span style={{ color: accent, fontSize: 34, fontWeight: 900 }}>{p.rightName}</span>
        </div>
        {rows.map((r, i) => {
          const at = 0.75 + i * 0.38, k = MOTION.enter(T, at, 0.4), isHi = i === hi;
          return (
            <div key={i} style={{ marginTop: 16, padding: '18px 22px', borderRadius: 20, background: isHi ? 'rgba(14,14,16,0.84)' : 'rgba(14,14,16,0.5)', border: `1px solid ${isHi ? accent : 'rgba(255,255,255,0.1)'}`, opacity: k, transform: `translateX(${mix(-40, 0, k)}px)` }}>
              <div style={{ color: '#E2E2E2', fontSize: 26, fontWeight: 700, marginBottom: 8 }}>{r[0]}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.15fr', alignItems: 'baseline', gap: 12 }}>
                <Val v={r[1]} size={52} color="#C4C4C4" />
                <span style={{ display: 'flex', alignItems: 'baseline', gap: 14 }}>
                  <span style={{ color: '#fff', fontSize: 34, fontWeight: 800 }}>→</span>
                  <Val v={r[2]} size={isHi ? 72 : 56} color={isHi ? accent : '#fff'} />
                </span>
              </div>
            </div>
          );
        })}
        {p.badge ? <span style={{ display: 'inline-block', marginTop: 18, background: accent, color: INK, fontSize: 40, fontWeight: 900, padding: '8px 18px', borderRadius: 12, opacity: bka, transform: `scale(${mix(0.4, 1, bk)}) rotate(-4deg)` }}>{p.badge}</span> : null}
      </div>
      <Compact T={T} CUES={CUES}>
        <KickLine accent={accent} text={`${p.leftName} → ${p.rightName}`} />
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginTop: 22, flexWrap: 'nowrap' }}>
          <span style={{ color: '#E2E2E2', fontSize: 30, fontWeight: 700, whiteSpace: 'nowrap' }}>{hrow[0]}</span>
          {String(hrow[0] + hrow[1] + hrow[2]).length <= 14 && <R.Fragment><Val v={hrow[1]} size={48} color="#C4C4C4" /><span style={{ color: '#fff', fontSize: 34, fontWeight: 800 }}>→</span></R.Fragment>}
          <Val v={hrow[2]} size={String(hrow[0] + hrow[1] + hrow[2]).length <= 14 ? 96 : 76} color={accent} />
          {p.badge ? <span style={{ background: accent, color: INK, fontSize: 30, fontWeight: 900, padding: '4px 12px', borderRadius: 10, transform: 'rotate(-4deg)' }}>{p.badge}</span> : null}
        </div>
      </Compact>
    </R.Fragment>
  );
}

// 07 출시일 — 날짜가 핵심 정보일 때(출시·사전예약·배송). 큰 날짜 + D-day 칩 + 타임라인
function HeaderDate({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.3, 0.6);
  const l1 = MOTION.enter(T, 0.2, 0.45);
  const nk = MOTION.pop(T, 0.65, 0.45), na = p01(T, 0.65, 0.1);
  const dd = MOTION.pop(T, 1.15, 0.4), dda = p01(T, 1.15, 0.08);
  const tl = MOTION.enter(T, 1.45, 0.4), prog = MOTION.draw(T, 1.6, 0.8) * Math.max(0, Math.min(1, +p.progress || 0));
  const ms = splitRows(p.milestones);
  const big = mix(300, 150, m), lab = mix(62, 44, m);
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} />
      <div style={{ ...COL }}>
        <Kicker T={T} m={m} accent={accent} text={p.kicker} />
        <div style={{ color: '#fff', fontSize: lab, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.22, opacity: l1, transform: rise(l1) }}>{p.label}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: mix(22, 14, m), marginTop: mix(4, 0, m) }}>
          <span style={{ ...numStyle(big, accent), display: 'inline-block', transformOrigin: 'left bottom', transform: `scale(${mix(1.45, 1, nk)})`, opacity: na }}>{p.date}</span>
          <span style={{ background: '#fff', color: INK, fontSize: mix(48, 32, m), fontWeight: 900, padding: '6px 18px', borderRadius: 12, display: 'inline-block', opacity: dda, transform: `scale(${mix(2, 1, dd)}) rotate(-6deg)` }}>{p.dday}</span>
        </div>
        <div style={{ height: mix(140, 0, m), overflow: 'hidden', opacity: tl * (1 - m) }}>
          <div style={{ position: 'relative', marginTop: 38, height: 8, borderRadius: 99, background: 'rgba(255,255,255,0.25)' }}>
            <div style={{ width: `${prog * 100}%`, height: '100%', background: accent, borderRadius: 99 }} />
            {ms.map((x, i) => {
              const pos = ms.length > 1 ? i / (ms.length - 1) : 0, done = prog >= pos - 0.01;
              return (
                <div key={i} style={{ position: 'absolute', top: -8, display: 'flex', flexDirection: 'column',
                  ...(i === 0 ? { left: 0, alignItems: 'flex-start' } : i === ms.length - 1 ? { right: 0, alignItems: 'flex-end' } : { left: `${pos * 100}%`, transform: 'translateX(-50%)', alignItems: 'center' }) }}>
                  <span style={{ width: 24, height: 24, borderRadius: 99, background: done ? accent : '#444', border: '4px solid #0B0B0C', boxSizing: 'border-box' }} />
                  <span style={{ marginTop: 10, color: done ? '#fff' : '#C4C4C4', fontSize: 26, fontWeight: 800, whiteSpace: 'nowrap' }}>{x[0]}</span>
                  <span style={{ color: '#CDCDCD', fontSize: 24, fontWeight: 700, whiteSpace: 'nowrap' }}>{x[1] || ''}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </R.Fragment>
  );
}

// 08 가격 환산 — 숫자가 와닿지 않을 때 "= 무엇 n개"로 체감시키기
function HeaderConvert({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.3, 0.6);
  const l1 = MOTION.enter(T, 0.2, 0.45);
  const nk = MOTION.pop(T, 0.65, 0.45), na = p01(T, 0.65, 0.1);
  const u = MOTION.enter(T, 0.95, 0.35);
  const eq = splitRows(p.equivalents).map(r => r[0]);
  const num = mix(250, 150, m), unit = mix(80, 50, m), line = mix(62, 44, m);
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} h1={1250} />
      <div style={{ ...COL }}>
        <Kicker T={T} m={m} accent={accent} text={p.kicker} />
        <div style={{ color: '#fff', fontSize: line, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.22, opacity: l1, transform: rise(l1) }}>{p.line1}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: mix(18, 12, m) }}>
          <span style={{ ...numStyle(num, accent), display: 'inline-block', transformOrigin: 'left bottom', transform: `scale(${mix(1.45, 1, nk)})`, opacity: na }}>{p.number}</span>
          <span style={{ color: '#fff', fontSize: unit, fontWeight: 900, letterSpacing: '-0.05em', opacity: u, transform: rise(u) }}>{p.unit}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: mix(14, 6, m), marginTop: mix(22, 8, m) }}>
          {eq.map((t, i) => {
            const at = 1.25 + i * 0.3, k = MOTION.pop(T, at, 0.4), a = p01(T, at, 0.1);
            const hide = m > 0.5 && i > 0;
            return (
              <div key={i} style={{ display: hide ? 'none' : 'flex', alignItems: 'center', gap: 18, opacity: a, transform: `translateX(${mix(-30, 0, k)}px)` }}>
                <span style={{ width: mix(64, 44, m), height: mix(64, 44, m), borderRadius: 999, background: accent, color: INK, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: NUM, fontSize: mix(40, 28, m), flexShrink: 0 }}>=</span>
                <span style={{ color: '#fff', fontSize: mix(46, 36, m), fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.15 }}><Marked text={t} accent={accent} mode="color" /></span>
              </div>
            );
          })}
        </div>
      </div>
    </R.Fragment>
  );
}

// 09 제원 카드 — 신제품 한 대의 핵심 스탯 4개(무게·배터리·가격·출시)를 카드 타일로
function HeaderCard({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.35, 0.45);
  const stats = splitRows(p.stats).filter(r => r.length >= 2).slice(0, 4);
  const hi = Math.max(0, Math.min(stats.length - 1, +p.highlight || 0));
  const l1 = MOTION.enter(T, 0.2, 0.45), tg = MOTION.enter(T, 0.4, 0.4);
  const pr = MOTION.enter(T, 0.9 + stats.length * 0.18, 0.4);
  const hs = stats[hi] || ['', ''];
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} h1={1250} />
      <div style={{ ...COL, opacity: 1 - m }}>
        <Kicker T={T} m={0} accent={accent} text={p.kicker} />
        <div style={{ color: '#fff', fontSize: 72, fontWeight: 900, letterSpacing: '-0.05em', lineHeight: 1.1, opacity: l1, transform: rise(l1) }}>{p.name}</div>
        <div style={{ color: '#E2E2E2', fontSize: 36, fontWeight: 700, letterSpacing: '-0.02em', marginTop: 10, opacity: tg, transform: rise(tg, 20) }}>{p.tagline}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 34 }}>
          {stats.map((s, i) => {
            const at = 0.7 + i * 0.18, k = MOTION.pop(T, at, 0.4), a = p01(T, at, 0.1), isHi = i === hi;
            return (
              <div key={i} style={{ padding: '22px 26px', borderRadius: 24, background: isHi ? accent : 'rgba(14,14,16,0.84)', border: '1px solid rgba(255,255,255,0.1)', opacity: a, transform: `scale(${mix(0.7, 1, k)})` }}>
                <div style={{ color: isHi ? INK : '#E2E2E2', fontSize: 26, fontWeight: 800, marginBottom: 10 }}>{s[0]}</div>
                <Val v={s[1]} size={64} color={isHi ? INK : '#fff'} />
              </div>
            );
          })}
        </div>
        {p.price ? <div style={{ marginTop: 26, display: 'flex', alignItems: 'baseline', gap: 14, opacity: pr, transform: rise(pr, 20) }}>
          <span style={{ color: '#E2E2E2', fontSize: 30, fontWeight: 700 }}>{p.priceLabel || '가격'}</span>
          <Val v={p.price} size={84} color={accent} />
        </div> : null}
      </div>
      <Compact T={T} CUES={CUES}>
        <KickLine accent={accent} text={p.kicker} />
        <div style={{ color: '#fff', fontSize: 44, fontWeight: 900, letterSpacing: '-0.04em', marginTop: 18 }}>{p.name}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 6 }}>
          <span style={{ color: '#E2E2E2', fontSize: 28, fontWeight: 700 }}>{hs[0]}</span>
          <Val v={hs[1]} size={96} color={accent} />
          {p.price ? <span style={{ color: '#CDCDCD', fontSize: 30, fontWeight: 700 }}>· {p.price}</span> : null}
        </div>
      </Compact>
    </R.Fragment>
  );
}

// 10 비교 바 — 한 지표(가격·밝기·무게)로 제품 3~5개를 막대로. 강조 항목은 accent
function HeaderRank({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.35, 0.45);
  const items = splitRows(p.items).filter(r => r.length >= 2).slice(0, 5).map(r => ({ name: r[0], raw: r[1], v: parseFloat(String(r[1]).replace(/[^\d.]/g, '')) || 0 }));
  const max = Math.max(1, ...items.map(x => x.v));
  const hi = Math.max(0, Math.min(items.length - 1, +p.highlight || 0));
  const l1 = MOTION.enter(T, 0.2, 0.45);
  const fmt = v => (p.unitPos === 'suffix' ? `${v}${p.unit || ''}` : `${p.unit || ''}${v}`);
  const h = items[hi] || { name: '', raw: '' };
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} h1={1250} />
      <div style={{ ...COL, opacity: 1 - m }}>
        <Kicker T={T} m={0} accent={accent} text={p.kicker} />
        <div style={{ color: '#fff', fontSize: 62, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.2, opacity: l1, transform: rise(l1), textWrap: 'balance' }}><Marked text={p.line1} accent={accent} /></div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22, marginTop: 36 }}>
          {items.map((it, i) => {
            const at = 0.6 + i * 0.3, k = MOTION.draw(T, at, 0.6), a = p01(T, at, 0.1), isHi = i === hi;
            const w = Math.max(0.12, it.v / max) * k;
            return (
              <div key={i} style={{ opacity: a }}>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                  <span style={{ color: isHi ? '#fff' : '#E2E2E2', fontSize: 34, fontWeight: 800 }}>{it.name}</span>
                  <span style={numStyle(isHi ? 56 : 44, isHi ? accent : '#fff')}>{fmt(it.raw)}</span>
                </div>
                <div style={{ marginTop: 8, height: isHi ? 44 : 34, borderRadius: 99, background: 'rgba(255,255,255,0.14)', overflow: 'hidden' }}>
                  <div style={{ width: `${w * 100}%`, height: '100%', borderRadius: 99, background: isHi ? accent : 'rgba(255,255,255,0.45)' }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <Compact T={T} CUES={CUES}>
        <KickLine accent={accent} text={p.kicker} />
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 18, marginTop: 22 }}>
          <span style={{ color: '#fff', fontSize: 44, fontWeight: 900, letterSpacing: '-0.04em' }}>{h.name}</span>
          <span style={numStyle(104, accent)}>{fmt(h.raw)}</span>
        </div>
      </Compact>
    </R.Fragment>
  );
}

// ── 11~14: 카테고리 확장 레이아웃 (2026-10-18, 패션·신발·차·수치형) ──
// 11 드롭 — 발매 정보(이름·태그·날짜·가격·구매처)
function HeaderDrop({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.35, 0.45);
  const tg = MOTION.pop(T, 0.05, 0.35), tga = p01(T, 0.05, 0.08);
  const nm = MOTION.enter(T, 0.25, 0.45), l1 = MOTION.enter(T, 0.5, 0.45);
  const chips = [[p.date, '발매'], [p.price, '가격'], [p.where, '구매처'], [p.colors, '컬러']].filter(c => c[0]);
  const hs = chips[0] || ['', ''];
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} h1={1250} />
      <div style={{ ...COL, opacity: 1 - m }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ background: accent, color: INK, fontSize: 36, fontWeight: 900, padding: '6px 18px', borderRadius: 8, display: 'inline-block', transformOrigin: 'left center', opacity: tga, transform: `scale(${mix(1.6, 1, tg)})` }}>{p.tag || '드롭'}</span>
          <span style={{ color: '#fff', fontSize: 28, fontWeight: 700, letterSpacing: '0.18em', opacity: tga }}>{p.kicker}</span>
        </div>
        <div style={{ marginTop: 26, color: '#fff', fontSize: 84, fontWeight: 900, letterSpacing: '-0.05em', lineHeight: 1.05, opacity: nm, transform: rise(nm), textWrap: 'balance' }}>{p.name}</div>
        <div style={{ marginTop: 18, color: '#E2E2E2', fontSize: 50, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.2, opacity: l1, transform: rise(l1), textWrap: 'balance' }}><Marked text={p.line1} accent={accent} /></div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 34 }}>
          {chips.map((c, i) => {
            const at = 0.85 + i * 0.22, k = MOTION.pop(T, at, 0.4), a = p01(T, at, 0.1);
            return (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '18px 26px', borderRadius: 22, background: i === 0 ? accent : 'rgba(14,14,16,0.84)', border: '1px solid rgba(255,255,255,0.12)', opacity: a, transform: `scale(${mix(0.6, 1, k)})` }}>
                <span style={{ color: i === 0 ? INK : '#E2E2E2', fontSize: 24, fontWeight: 800 }}>{c[1]}</span>
                <Val v={c[0]} size={64} color={i === 0 ? INK : '#fff'} />
              </div>
            );
          })}
        </div>
      </div>
      <Compact T={T} CUES={CUES}>
        <KickLine accent={accent} text={`${p.tag || '드롭'} · ${p.kicker || ''}`} />
        <div style={{ color: '#fff', fontSize: 44, fontWeight: 900, letterSpacing: '-0.04em', marginTop: 18 }}>{p.name}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginTop: 6 }}>
          <span style={{ color: '#E2E2E2', fontSize: 28, fontWeight: 700 }}>{hs[1]}</span>
          <Val v={hs[0]} size={96} color={accent} />
          {p.price && hs[0] !== p.price ? <span style={{ color: '#E2E2E2', fontSize: 34, fontWeight: 800 }}>· {p.price}</span> : null}
        </div>
      </Compact>
    </R.Fragment>
  );
}

// 12 협업 — A × B
function HeaderCollab({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.35, 0.45);
  const a = MOTION.enter(T, 0.15, 0.45), x = MOTION.pop(T, 0.55, 0.45), xa = p01(T, 0.55, 0.08), b = MOTION.enter(T, 0.8, 0.45);
  const l1 = MOTION.enter(T, 1.2, 0.45), pr = MOTION.pop(T, 1.5, 0.4), pra = p01(T, 1.5, 0.1);
  const big = { color: '#fff', fontSize: 96, fontWeight: 900, letterSpacing: '-0.05em', lineHeight: 1.0 };
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} h1={1250} />
      <div style={{ ...COL, opacity: 1 - m }}>
        <Kicker T={T} m={0} accent={accent} text={p.kicker} />
        <div style={{ ...big, opacity: a, transform: `translateX(${mix(-60, 0, a)}px)` }}>{p.left}</div>
        <div style={{ ...numStyle(150, accent), margin: '6px 0', display: 'inline-block', transformOrigin: 'left center', opacity: xa, transform: `scale(${mix(2.2, 1, x)}) rotate(${mix(-90, 0, x)}deg)` }}>×</div>
        <div style={{ ...big, opacity: b, transform: `translateX(${mix(60, 0, b)}px)` }}>{p.right}</div>
        <div style={{ marginTop: 30, color: '#E2E2E2', fontSize: 50, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.2, opacity: l1, transform: rise(l1), textWrap: 'balance' }}><Marked text={p.line1} accent={accent} /></div>
        <div style={{ display: 'flex', gap: 14, marginTop: 26, opacity: pra, transform: `scale(${mix(0.6, 1, pr)})`, transformOrigin: 'left center' }}>
          {p.price ? <span style={{ background: accent, color: INK, fontSize: 40, fontWeight: 900, padding: '8px 18px', borderRadius: 12, transform: 'rotate(-3deg)' }}>{p.price}</span> : null}
          {p.date ? <span style={{ border: '3px solid #fff', color: '#fff', fontSize: 36, fontWeight: 800, padding: '8px 18px', borderRadius: 12 }}>{p.date}</span> : null}
        </div>
      </div>
      <Compact T={T} CUES={CUES}>
        <KickLine accent={accent} text={p.kicker} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 18, color: '#fff', fontSize: 48, fontWeight: 900, letterSpacing: '-0.04em' }}>
          <span>{p.left}</span><span style={numStyle(64, accent)}>×</span><span>{p.right}</span>
        </div>
        {p.price ? <div style={{ marginTop: 6 }}><Val v={p.price} size={96} color={accent} /></div> : null}
      </Compact>
    </R.Fragment>
  );
}

// 13 컬러웨이 — 색 칩(실제 hex) 나열
function HeaderColorway({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.35, 0.45);
  const sw = splitRows(p.swatches).filter(r => r.length >= 2).slice(0, 6);
  const nm = MOTION.enter(T, 0.2, 0.45), l1 = MOTION.enter(T, 0.45, 0.45);
  const cnt = MOTION.pop(T, 0.75, 0.45), cnta = p01(T, 0.75, 0.1);
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} h1={1250} />
      <div style={{ ...COL, opacity: 1 - m }}>
        <Kicker T={T} m={0} accent={accent} text={p.kicker} />
        <div style={{ color: '#fff', fontSize: 72, fontWeight: 900, letterSpacing: '-0.05em', lineHeight: 1.1, opacity: nm, transform: rise(nm) }}>{p.name}</div>
        <div style={{ marginTop: 12, color: '#E2E2E2', fontSize: 48, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.2, opacity: l1, transform: rise(l1), textWrap: 'balance' }}><Marked text={p.line1} accent={accent} /></div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginTop: 10 }}>
          <span style={{ ...numStyle(220, accent), display: 'inline-block', transformOrigin: 'left bottom', transform: `scale(${mix(1.5, 1, cnt)})`, opacity: cnta }}>{sw.length}</span>
          <span style={{ color: '#fff', fontSize: 70, fontWeight: 900, letterSpacing: '-0.05em', opacity: cnta }}>가지 색</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 24 }}>
          {sw.map((r, i) => {
            const at = 1.0 + i * 0.16, k = MOTION.pop(T, at, 0.4), a = p01(T, at, 0.1);
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 22px 10px 10px', borderRadius: 999, background: 'rgba(14,14,16,0.84)', border: '1px solid rgba(255,255,255,0.14)', opacity: a, transform: `scale(${mix(0.5, 1, k)})` }}>
                <span style={{ width: 54, height: 54, borderRadius: 999, background: r[1], border: '3px solid rgba(255,255,255,0.7)', flexShrink: 0 }} />
                <span style={{ color: '#fff', fontSize: 32, fontWeight: 800 }}>{r[0]}</span>
              </div>
            );
          })}
        </div>
      </div>
      <Compact T={T} CUES={CUES}>
        <KickLine accent={accent} text={p.kicker} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginTop: 18 }}>
          <span style={{ color: '#fff', fontSize: 44, fontWeight: 900, letterSpacing: '-0.04em' }}>{p.name}</span>
          <span style={{ display: 'flex', gap: 8 }}>{sw.map((r, i) => <span key={i} style={{ width: 34, height: 34, borderRadius: 999, background: r[1], border: '2px solid rgba(255,255,255,0.7)' }} />)}</span>
        </div>
        {p.price ? <div style={{ marginTop: 6 }}><Val v={p.price} size={96} color={accent} /></div> : null}
      </Compact>
    </R.Fragment>
  );
}

// 14 스탯 — 수치 하나 + 링 게이지
function HeaderStat({ T, CUES, p, accent }) {
  const M = CUES['중반부'];
  const m = MOTION.draw(T, M - 0.3, 0.6);
  const lb = MOTION.enter(T, 0.2, 0.45), nk = MOTION.pop(T, 0.65, 0.45), na = p01(T, 0.65, 0.1), u = MOTION.enter(T, 0.95, 0.35);
  const ring = MOTION.draw(T, 0.8, 1.1) * Math.max(0.04, Math.min(1, +p.ring || 0.8));
  const sb = MOTION.enter(T, 1.5, 0.4);
  const R0 = 150, C = 2 * Math.PI * R0, size = mix(360, 0, m);
  return (
    <R.Fragment>
      <Scrim T={T} CUES={CUES} h1={1250} />
      <div style={{ ...COL }}>
        <Kicker T={T} m={m} accent={accent} text={p.kicker} />
        <div style={{ color: '#fff', fontSize: mix(60, 44, m), fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.22, opacity: lb, transform: rise(lb) }}>{p.label}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 28, marginTop: mix(10, 2, m) }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: mix(16, 10, m) }}>
            <span style={{ ...numStyle(mix(250, 150, m), accent), display: 'inline-block', transformOrigin: 'left bottom', transform: `scale(${mix(1.45, 1, nk)})`, opacity: na }}>{p.number}</span>
            <span style={{ color: '#fff', fontSize: mix(80, 50, m), fontWeight: 900, letterSpacing: '-0.05em', opacity: u, transform: rise(u) }}>{p.unit}</span>
          </div>
          <svg width={size} height={size} viewBox="0 0 360 360" style={{ opacity: na * (1 - m), flexShrink: 0 }}>
            <circle cx="180" cy="180" r={R0} fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth="26" />
            <circle cx="180" cy="180" r={R0} fill="none" stroke={accent} strokeWidth="26" strokeLinecap="round" strokeDasharray={`${C * ring} ${C}`} transform="rotate(-90 180 180)" />
          </svg>
        </div>
        <div style={{ marginTop: mix(18, 6, m), color: '#E2E2E2', fontSize: mix(40, 32, m), fontWeight: 700, letterSpacing: '-0.02em', opacity: sb, transform: rise(sb, 16) }}>{p.sub}</div>
      </div>
    </R.Fragment>
  );
}

// 퀴즈 훅 인트로 — 어떤 레이아웃이든 맨 앞에 Reel 03 스타일(블러 + 칩 + 큰 질문 + 타이머)을 붙인다. p.hook = {kicker, question}
function QuizHook({ T, off, p, accent }) {
  const m = MOTION.draw(T, off - 0.28, 0.28);
  if (m >= 1) return null;
  const chip = MOTION.pop(T, 0.05, 0.35), chipA = p01(T, 0.05, 0.1);
  const ta = p01(T, 0.5, 0.2), timer = p01(T, 0.6, Math.max(0.5, off - 0.9));
  const plain = String(p.hook.question || '').replace(/\*/g, '');
  const fs = plain.length <= 13 ? 156 : plain.length <= 19 ? 138 : plain.length <= 26 ? 120 : 104;  // 10/18 사용자: 첫 장면 글자 키움
  return (
    <div style={{ position: 'absolute', left: 56, right: 56, top: 400, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', fontFamily: FONT, opacity: 1 - m, transform: `scale(${mix(1, 1.08, m)})` }}>
      <span style={{ border: `4px solid ${accent}`, color: '#fff', fontSize: 42, fontWeight: 800, letterSpacing: '-0.01em', padding: '12px 34px', borderRadius: 999, opacity: chipA, transform: `scale(${mix(0.6, 1, chip)})` }}>{p.hook.kicker}</span>
      <div style={{ marginTop: 52, color: '#fff', fontSize: fs, fontWeight: 900, letterSpacing: '-0.05em', lineHeight: 1.16, textWrap: 'balance', textShadow: '0 6px 30px rgba(0,0,0,0.6)' }}>
        <Marked text={p.hook.question} accent={accent} T={T} start={0.18} step={0.09} />
      </div>
      <div style={{ marginTop: 76, width: 560, height: 12, borderRadius: 99, background: 'rgba(255,255,255,0.22)', overflow: 'hidden', opacity: ta }}>
        <div style={{ width: `${timer * 100}%`, height: '100%', background: accent }} />
      </div>
    </div>
  );
}

const HEADERS = { number: HeaderNumber, vs: HeaderVS, question: HeaderQuestion, list: HeaderList, breaking: HeaderBreaking, specs: HeaderSpecs, date: HeaderDate, convert: HeaderConvert, card: HeaderCard, rank: HeaderRank, drop: HeaderDrop, collab: HeaderCollab, colorway: HeaderColorway, stat: HeaderStat };

function ReelPiece(p) {
  const c = window.useComposition();
  const T = c.T, CUES = c.CUES, end = c.authoredTotal;
  const accent = p.accent || '#FF5A36';
  const L = HEADERS[p.layout] ? p.layout : 'number';
  const M = CUES['중반부'];
  const [drop, setDrop] = R.useState(null);
  R.useEffect(() => {
    const over = e => e.preventDefault();
    const onDrop = e => {
      e.preventDefault();
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (!f) return;
      const k = f.type.startsWith('video') ? 'video' : f.type.startsWith('image') ? 'image' : null;
      if (k) setDrop({ url: URL.createObjectURL(f), kind: k });
    };
    window.addEventListener('dragover', over);
    window.addEventListener('drop', onDrop);
    return () => { window.removeEventListener('dragover', over); window.removeEventListener('drop', onDrop); };
  }, []);
  const src = drop ? drop.url : (p.videoSrc || '');
  const kind = drop ? drop.kind : (src && !/\.(png|jpe?g|webp|gif|avif)$/i.test(src) ? 'video' : 'image');
  const chunks = [
    ...timeChunks(p.hookSubs, CUES['도입부'] + 1.2, M),
    ...timeChunks(p.bodySubs, M + 0.3, CUES['마지막'] - 0.2),
  ];
  const band = MOTION.enter(T, M - 0.2, 0.4) * (1 - MOTION.enter(T, CUES['마지막'] - 0.3, 0.3));
  const dim = MOTION.draw(T, CUES['마지막'] - 0.1, 0.5) * (1 - MOTION.draw(T, end - 0.5, 0.45));
  const qIntro = L === 'question' ? 1 - MOTION.draw(T, M - 0.35, 0.4) : 0;
  const hasHook = !!(p.hook && p.hook.question) && L !== 'question';
  const off = hasHook ? CUES['도입부'] : 0;  // 훅 장면이 있으면 레이아웃은 off 초 뒤에 자기 인트로를 시작
  const T2 = T - off;
  const C2 = hasHook ? { '도입부': CUES['도입부'] - off, '중반부': CUES['중반부'] - off, '마지막': CUES['마지막'] - off } : CUES;
  const hookBlur = hasHook ? 1 - MOTION.draw(T, off - 0.3, 0.32) : 0;
  const pH = hasHook ? { ...p, bodyTimes: (p.bodyTimes || []).map(x => x - off), hookTimes: (p.hookTimes || []).map(x => x - off), cardAt: p.cardAt != null ? p.cardAt - off : p.cardAt } : p;
  const tr = p.transition || 'slash';
  const u = tr === 'none' ? null : cutPhase(T, [
    { at: 0, from: 0, to: 1 }, ...(hasHook ? [{ at: off, from: -1, to: 1 }] : []), { at: M, from: -1, to: 1 },
    { at: CUES['마지막'], from: -1, to: 1 }, { at: end, from: -1, to: 0 },
  ]);
  const pb = tr === 'zoom' && u != null ? Math.pow(1 - Math.abs(u), 2) : 0;
  const shakeAt = { number: 0.65, vs: 1.35, question: M + 0.2, list: 0.55, date: 0.65, convert: 0.65, card: 0.7, rank: 0.6, drop: 0.85, collab: 0.55, colorway: 0.75, stat: 0.65 }[L];
  const shk0 = shakeAt != null && L !== 'question' ? shakeAt + off : shakeAt;
  const shk = shk0 != null && T > shk0 && T < shk0 + 0.35 ? (1 - p01(T, shk0, 0.35)) * 16 : 0;
  const sx = shk * Math.sin(T * 95), sy = shk * 0.6 * Math.cos(T * 120);
  const H = HEADERS[L];
  return (
    <div data-screen-label={'t=' + Math.floor(c.time) + 's'} style={{ position: 'absolute', inset: 0, overflow: 'hidden', fontFamily: FONT, wordBreak: 'keep-all', overflowWrap: 'break-word', lineBreak: 'strict' }}>
      <div style={{ position: 'absolute', inset: 0, transform: `translate(${sx}px, ${sy}px) scale(${1 + 0.28 * pb})`, filter: pb > 0.01 ? `blur(${18 * pb}px)` : 'none' }}>
        <Media src={src || 'assets/sample-frame.png'} kind={kind} fit={p.videoFit} start={p.videoStart} sound={p.sound} T={T} end={end} blur={0} cuts={p.cutTimes} />  {/* 10/19 사용자: 인트로 블러 제거 */}
        <div style={{ position: 'absolute', inset: 0, background: '#000', opacity: Math.max(0.42 * qIntro, 0.3 * hookBlur, 0.62 * dim) }} />
        {p.theme === 'tint' && <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(180deg, ${accent}55 0%, rgba(0,0,0,0) 42%, ${accent}33 100%)`, mixBlendMode: 'screen', pointerEvents: 'none' }} />}
        {p.theme === 'neon' && <div style={{ position: 'absolute', inset: 0, boxShadow: `inset 0 0 260px ${accent}66, inset 0 0 60px ${accent}33`, pointerEvents: 'none' }} />}
        {hasHook && <QuizHook T={T} off={off} p={p} accent={accent} />}
        <H T={T2} CUES={C2} p={pH} accent={accent} />
        {L === 'number' && <FactCard T={T} CUES={CUES} p={p} accent={accent} />}
        <Subtitles T={T} chunks={chunks} accent={accent} band={band} />
        <Outro T={T} CUES={CUES} p={p} accent={accent} end={end} />
        <Badge T={T} end={end} p={p} />
      </div>
      <Transition u={u} kind={tr} accent={accent} />
    </div>
  );
}

function ReelTemplate(props) {
  return (
    <window.CompositionStage width={1080} height={1920} scenes={window.OM_SCENES} playback={window.OM_PLAYBACK} bg="#000">
      <ReelPiece {...props} />
    </window.CompositionStage>
  );
}
window.ReelTemplate = ReelTemplate;
})();
