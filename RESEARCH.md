# Research — what pays, what top reels do, and the visual upgrade (2026-10-18)

Written 2026-10-18 after the operator asked for: "find what actually makes money, analyse the reels that perform and put it into ours, varied and good-looking visuals, many templates, top performance and quality, cost-optimised." Same-day additions: **no category limit** (clothes, shoes, appliances, cars — anything just launched), **centre on the hottest keywords at home and abroad with top-view analysis**, **no grey templates**.
All numbers are as collected on 2026-10-18. "Unverified" means not confirmed against an official source. Korean original: [`docs/ko/RESEARCH.ko.md`](docs/ko/RESEARCH.ko.md).

## 0. Conclusions
1. Broadening categories is right for revenue too: the main Korean affiliate program pays fashion, beauty and sports three times the rate of electronics (table below).
2. Top-view shorts share not "flashy editing" but a **(brand + product) + (one price or number) + (a short judgement or question)** title, an **anchor that stays on screen** (title card, price chip), and **the product in the first second**. Our format was already close, so we strengthened the title formula, the anchor, and buzz-based selection.
3. Visuals: 14 layouts × 3 themes × 8 palettes × 3 transitions × 5 voices, plus SFX, BGM ducking and colour grading. Zero added cost.

## 1. Money — commission structures

### Korean affiliate program (Coupang Partners) by category
| Category | Max rate | On a ₩150,000 sale |
|---|---|---|
| Beauty · fashion/accessories · sports/leisure · baby · books | 3% | ₩4,500 |
| Household · food/health | 2% | ₩3,000 |
| Appliances/digital | 1% | ₩1,500 |

Source: a Korean summary article (2026-07-04) citing the official partner site. No figures for Rocket-delivery vs marketplace differences or promotions. **Re-verify after joining the program (unverified).** Pets not listed.

### Direct brand programs (overseas, reference)
| Brand | Commission | Basis |
|---|---|---|
| Insta360 | 5% | Official creator-program page (third parties quote 2.4–10%) |
| DJI | 2–8% by region and category (drones 2%, handheld 5%) | Affiliate network listing |
| EcoFlow | 5–6.4% | Two networks disagree |
| eufy | 7–15% (up to 20% in some regions) | Official affiliate page |
| Anker · Garmin · Nike · Adidas · New Balance | Unverified | Check after joining Impact/Awin/CJ |

### Platform shopping tags
- YouTube Shopping affiliate: 500 subscribers + partner program (earlier note). The "2–5% for electronics" figure is unverified.
- Instagram shopping tags are limited in Korea; the realistic path is a **profile link (affiliate) + "link in bio" in the caption**. Works without a registered business.

### Cost per reel (estimate)
| Item | Cost |
|---|---|
| TTS, 3–4 segments + STT read-back | ~$0.03 |
| Lyria BGM, one clip | $0.04 |
| Gemini 3.1 Pro selection (with search), script, cut selection | ~$0.10–0.20 |
| Simple vision checks (text detection) | moved to Flash → ~$0.01 |
| Popularity collection, SFX, grading, ducking (this round) | $0 (yt-dlp metadata, ffmpeg synthesis) |

About $0.25 per reel; three a day ≈ $23 a month. Local render (Chrome frame capture) 3–5 minutes per reel.

## 2. Top-view reels analysis (collected 2026-10-18)

### Videos analysed (1 fps filmstrips + ffmpeg scene-change detection)
| Channel | Video | Views | Length | Cuts/s | Traits |
|---|---|---|---|---|---|
| ITSub (KR) | ₩200k iPhone Duo case | 1.8 M | 56 s | 0.37 | In-store hands-on; a two-line title card pinned at the top ("official accessory — worth ₩200k?"), only keywords coloured |
| ITSub (KR) | iPhone Duo in person, revealed today | 1.5 M | 44 s | 0.28 | Pinned title card, one-line bottom subtitle, product fills the frame |
| Techmong (KR) | Samsung quietly shipped this | 1.8 M | 23 s | 0.04 | Nearly single-take, big pinned title, bottom subtitle |
| UNDERkg (KR) | Apple's first innovation in four years | 3.7 M | 40 s | 0.08 | Hand + phone close-ups, two-line subtitle box |
| Mrwhosetheboss | World's most expensive keyboard | 43 M | 48 s | 0.27 | **Price chip pinned at the top, colour changes per tier ($2→$1000)**, two-shot alternating with top-down hand inserts |
| Unbox Therapy | 10,000 mAh battery phone | 12 M | 97 s | 0.34 | Presenter + product, minimal text, product close-ups |
| MKBHD | This TECH knife | 45 M | 113 s | 0.03 | Single take |
| Techmong (KR) | AI glasses in an exam | 587 K | 22 s | 0.00 | Single take |

Top of channel Shorts tabs (last 30 uploads): Nike 8.6 M (athlete campaign), Adidas 2.8 M, New Balance 1.4 M, Dyson 182 K (product intro), Supercar Blondie 9.6 M, WhatsInside 3.1 M (Chinese EV), Vogue Korea 230 K, Hypebeast 50 K. Sneaker-news channels sit at 15–30 K — **fashion and footwear short-form lives on Instagram, not YouTube** (consistent with our Instagram-first strategy).

### Common traits → applied
| Finding | Applied (code) |
|---|---|
| Title = brand + product + price/number + short judgement | Korean-style formula and examples added to the script prompt (`auto/plan.py` write_spec) |
| An anchor stays on screen (title card, price chip) | Layout compact header (existing); price-chip colour progression handled by the `rank` and `vs` layouts |
| Product large in the first second | Product-dominant intro frame checks |
| 0.27–0.37 cuts/s (hands-on) and single takes both work | 2.5–3 s cuts (0.33/s) kept; cut motion alternates push-in / pull-out / pan |
| Korean top titles use immediacy words ("in person", "revealed today", "worth it") | Keyword list extended ("in person", "the truth about", "worth it", "the most ~", "first") |
| Global top titles use extremes (most expensive, heaviest, 10,000 mAh) | Selection rule "when buzz ties, prefer expensive and strange" + the `stat` layout |

### Buzz signals — what worked and what didn't
| Signal | Result |
|---|---|
| Google Trends RSS (KR, US) | News, sports and celebrities only; no product signal → not used |
| Reddit hot.json | Blocked without login → not used |
| YouTube search "this week, by views" (`sp=CAMSBAgDEAE%3D`) | Works. Product-name search → view sum of top 8 = `heat_views` |
| Creator and brand Shorts-tab view counts (yt-dlp flat) | Works. 15 channels, top 5 each → `hot.json` |
| Media RSS (fashion, sneakers, design, cars, beauty added) | 31 of 36 responded. All four Korean fashion-press feeds are dead → replaced by Hypebeast KR |

## 3. Visual upgrade (applied 2026-10-18)
- **Layouts 10 → 14**: `drop` (release info: tag, name, date, price, retailer, colours), `collab` (A × B), `colorway` (real hex swatches), `stat` (one number + ring gauge). The original ten kept.
- **Three themes** `props.theme`: `dark` (default) / `tint` (accent gradient, screen blend) / `neon` (edge glow). Rotated per reel.
- **Accent guard** `vivid()`: lightness < 0.42 or saturation < 0.45 (greys, blacks, brand darks) → replaced from an 8-colour palette. Secondary text greys raised to ≥ #C4C4C4.
- **Alternating cut motion**: even cuts push in (1.00 → 1.07), odd cuts pull out (1.08 → 1.02), a ±14 px pan every third cut. Punch zoom, flash and shake kept.
- **Colour grade** per cut: contrast 1.05, saturation 1.14, unsharp 0.5, vignette π/6. `spec.grade=false` disables.
- **Six SFX** (`produce/render/sfx/*.wav`, synthesized with ffmpeg): riser, ding, pop, whoosh (0.15 s before each cut), thud (body start), tick (chunk change). Mixed at −9 dB. `spec.sfx=false` disables. Replace the wav files to use a sample library (direct downloads from a free library returned 403).
- **BGM sidechain ducking**: the voice track compresses the BGM (threshold 0.03, ratio 6, attack 12 ms, release 320 ms); BGM bed +3 dB. `spec.duck=false` disables.
- Combinations: 14 layouts × 3 themes × 8 palettes × 3 transitions × 5 voices = 5,040.

## 4. Selection changes (operator, 2026-10-18)
- Identity line: "the first to show early adopters what just came out". No category limit; lane rotation removed; `category` (tech / fashion / sneakers / home / beauty / mobility / outdoor / watch / toy / food / pet / golf / other) is a colour hint and a record only.
- Priority 1 = buzz (YouTube 7-day popularity list + search volume), priority 2 = recency (within 10 days); ties go to the more expensive, then Korea-known brands, then the stranger thing. 8 candidates, at most 2 per category.
- Excluded: celebrities as the subject, films/series/games, software-only news, rumours and leaks, health or efficacy claims (supplements, medical devices), adult products, tobacco and alcohol. (Cars, beauty and kids became allowed.)
- Constraint kept: **an official brand YouTube video is mandatory** (copyright and footage quality). Fashion works only when the brand posts product videos on YouTube (Nike, Adidas, New Balance, Uniqlo, Dyson do; Instagram-only campaigns cannot be used), so fashion will produce fewer reels than tech.

## 5. Remaining risks and next steps
- Verify official affiliate rates after joining (operator action); brand programs (Impact, Awin) likewise.
- Fashion lacks official footage; using brand Instagram video is unverified for both copyright and download reliability. Not done.
- Synthesized SFX are simple; consider a sample library once view metrics exist.
- `neon` and `tint` themes can overpower some footage; observe QA frame sheets for two weeks and adjust the ratio.
- The top-reel analysis is a single snapshot; `discover/hot.py` leaves a daily `runs/<date>/hot.md` for cumulative weekly comparison.
