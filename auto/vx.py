"""Vertex AI 호출 헬퍼 — Claude(rawPredict) · Gemini(generateContent, Google 검색 그라운딩). gcloud 토큰 사용, 키 없음."""
import json
import subprocess
import urllib.error
import urllib.request

import os
PROJECT = os.environ.get("GCP_PROJECT") or next((l.split("=", 1)[1].strip() for l in (__import__("pathlib").Path(__file__).resolve().parents[1] / ".env").read_text().splitlines() if l.startswith("GCP_PROJECT=")), "")  # .env 의 GCP_PROJECT
import time

_tok = {"v": None, "at": 0.0}


def token(force=False):
    """gcloud 액세스 토큰. 10/19 사고: 프로세스 내내 캐시해 1시간 뒤 전부 401 → 40분마다 갱신, 401 이면 강제 재발급."""
    if force or not _tok["v"] or time.time() - _tok["at"] > 2400:
        _tok["v"] = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip()
        _tok["at"] = time.time()
    return _tok["v"]


def post(url, body, timeout=300):
    data = json.dumps(body).encode()
    for i in range(4):  # 401 → 토큰 재발급, 429/5xx → 대기 후 재시도
        req = urllib.request.Request(url, data=data, headers={
            "Authorization": f"Bearer {token(force=i > 0)}", "x-goog-user-project": PROJECT, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            if i < 3 and (e.code == 401 or e.code == 429 or e.code >= 500):
                time.sleep(2 if e.code == 401 else (20 if e.code == 429 else 5 * (i + 1)))
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg}")


def claude(prompt, model="claude-opus-5-5", system=None, max_tokens=4000, images=(), location="global"):
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}} for b in images]
    content.append({"type": "text", "text": prompt})
    body = {"anthropic_version": "vertex-2023-10-16", "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]}
    if system:
        body["system"] = system
    host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    d = post(f"https://{host}/v1/projects/{PROJECT}/locations/{location}/publishers/anthropic/models/{model}:rawPredict", body)
    return "".join(c.get("text", "") for c in d["content"])


def gemini(prompt, model="gemini-3.8-flash", search=False, images=(), timeout=900, fallback="gemini-3.8-flash", retries=3):
    """타임아웃·5xx 면 한 번 더, 그래도 안 되면 fallback 모델로(2026-10-18: 3.1 Pro + 검색이 300초 넘김). retries=1 이면 한 번만(비전 검사용, 10/20)."""
    parts = [{"inlineData": {"mimeType": "image/jpeg", "data": b}} for b in images] + [{"text": prompt}]
    body = {"contents": [{"role": "user", "parts": parts}]}
    if search:
        body["tools"] = [{"googleSearch": {}}]
    d, last = None, None
    for m in (model, model, fallback)[:max(1, retries)]:
        try:
            d = post(f"https://aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/global/publishers/google/models/{m}:generateContent", body, timeout=timeout)
            break
        except (TimeoutError, OSError, RuntimeError) as e:
            last = e
            if isinstance(e, RuntimeError) and not any(c in str(e) for c in ("HTTP 5", "HTTP 429")):
                raise
    if d is None:
        raise RuntimeError(f"Gemini 호출 실패: {last}")
    c = d["candidates"][0]
    text = "".join(p.get("text", "") for p in c["content"]["parts"])
    srcs = [{"title": g.get("web", {}).get("title"), "url": g.get("web", {}).get("uri")} for g in c.get("groundingMetadata", {}).get("groundingChunks", [])]
    return text, srcs


def json_from(text):
    """모델 응답에서 첫 JSON 객체/배열 추출."""
    t = text.strip()
    if "```" in t:
        t = t.split("```")[1]
        t = t[4:] if t.startswith("json") else t
    i = min([x for x in (t.find("{"), t.find("[")) if x >= 0])
    return json.loads(t[i:t.rfind("}" if t[i] == "{" else "]") + 1])
