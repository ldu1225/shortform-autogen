# SPEC_RULES — how a spec (script + template) is written

Korean original: [`../docs/ko/SPEC_RULES.ko.md`](../docs/ko/SPEC_RULES.ko.md).

## 1. Choosing the template (`props.layout`)
| Situation | layout | Notes |
|---|---|---|
| Breaking: launch day, price reveal, pre-orders | `breaking` (05) | 4 ticker items = 4 key numbers |
| Price cut, old vs new, list vs discount | `vs` (02) | Links directly to shopping tags |
| N reasons/features of one product, or N products | `list` (04) | number of points = number of body chunks |
| Engagement, guess-the-price | `question` (03) | intro ≥ 4 s (timer) |
| Otherwise, one striking number | `number` (01) | fact card before → after |
| New vs old (or rival) specs, 2–4 rows | `specs` (06) | rows "item\|old\|new / …", highlight (largest change), badge "+71%" |
| A date is the key fact (launch, pre-order, delivery) | `date` (07) | date "10.23", dday "D-6", milestones "announced\|9.9 / pre-order\|10.16 / launch\|10.23", progress 0–1 |
| A price too large to feel | `convert` (08) | number/unit + equivalents "iPhone Duo *×3* / …" |
| 3–4 core stats of one product | `card` (09) | name, tagline, stats "price\|$1,899 / screen\|5 in / …", highlight, price |
| 3–5 products on one metric | `rank` (10) | items "name\|value / …", unit, unitPos, highlight |
| Release info is the point (fashion, sneakers, limited drops) | `drop` (11) | tag "drop/release/limited", name, line1, date, price, where, colors |
| Two brands or IPs collaborating | `collab` (12) | left, right, line1, price, date |
| Colours or options are the spectacle (shoes, phones, cars) | `colorway` (13) | swatches "name\|#hex / …" 2–6 real colours, name, line1, price |
| One overwhelming number (horsepower, battery, weight, count) | `stat` (14) | label, number, unit, ring 0–1, sub |

No layout three reels in a row. No category limit (10/18): fashion and footwear prefer 11 and 13, collaborations 12, extreme numbers 14. Theme (`props.theme` dark/tint/neon) and accent are set by `make_spec` — **grey or dark accents are forbidden (`vivid` guard)**. **The blurred quiz hook intro was retired on 10/19** — every template starts with its own designed intro, with no intro blur.

**Decision order by shape of information**: Is a date the key? → 07 / A comparison target with 2+ spec rows? → 06 / Only a price, with a predecessor price? → 02 / A big price that converts amusingly? → 08 / Several products on one metric? → 10 / 3–4 stats to list? → 09 / N reasons or features? → 04 / Same-day breaking news? → 05 / Engagement? → 03 / Otherwise → 01.

## 2. Script structure and length
Hook (a number) → identity (brand, product) → comparison (predecessor, rival, people) → verdict (worth buying?) → a question.
- **Top rule: a middle-schooler understands on first listen** (10/19). First sentence says "what this is"; no jargon, model names or English abbreviations; one idea per sentence, about 20 characters; analogies for numbers; foreign prices must be converted ("about ₩N00 million").
- Hook ≤ 2.5 s, intro ≤ 4 s (what it is + the answer number), body 14–18 s (5 chunks = why it is trending / key 1 / key 2 / converted price / when and where), ending ≤ 3.5 s (one question). Played at 1.1×; 28–36 s total plus end card. On-screen text is plain language, 8–12 characters, no mid-word Korean line breaks (`keep-all`).
- Body subtitle chunks use **the same words as the narration** (for STT alignment). ≤ 14 characters per chunk, one `*keyword*`.
- Numbers only with a source: the spec's `sources` array holds `{"claim": "...", "url": "..."}`. Currency conversions say "about" and carry the rate date.
- Forbidden: celebrity names, disparaging other companies, unsourced "best/first" claims, health or efficacy claims.

## 3. Three-source rule
Main news clip (official) + comparison/context clip (predecessor, rival, official) + a clip with people. Brand official channels first; media and creator footage is not used.
Cuts align to scene boundaries (intro / body / ending). Each cut 2–3 s; the last cut omits `dur` (fills the remaining scene).

## 4. Audio
- TTS: the latest Google model (currently `gemini-3.1-flash-tts-preview`), one fixed style prompt, `rate` 1.08.
- BGM: Lyria 3 clip; the prompt carries the mood, "Instrumental only, no vocals" and a BPM. `bgm_db` −20.
- Source audio is never used.

## 5. Common props
`handle` from `.env` (`HANDLE`), `platform` instagram (a second youtube variant if needed), accent from the category palette (tech `#FF5A36`, mobility `#3D8BFF`, outdoor `#FFB21E`, pet `#FF4F8B`, …).

## 6. TTS read-back validation (automatic)
Every narration segment is synthesized, read back with STT and checked for length, similarity and numbers (`tts_checked`). If a number is missed three times (e.g. "2,999 dollars" heard as "299"), **the narration alone switches to Korean number words**; subtitles keep Arabic digits.
