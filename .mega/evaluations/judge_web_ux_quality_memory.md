# Web UX Quality Judge — Cumulative Memory

Target file: `src/personalens/webapp.py` (1098 lines, ~46 KB, single-file inline HTML/CSS/JS)

## Structural Map of `webapp.py`

### Module-level constants
- **L17** `APP_TITLE = "PersonaLens"`
- **L18-66** `AUTO_RECONNECT_SCRIPT` — inline `<script>` string. Health poller at `/health` every 1.5s, builds a fixed bottom-right banner with inline `style="..."` properties (11 of them). `window.location.reload()` on recovery. No `visibilitychange` / `document.hidden` awareness. English-only banner text.

### HTTP handler `AppHandler` (L69-170)
- **L70-83** `do_GET` — routes `/` → `render_form`, `/health` → `ok`, `/skeleton?name=…` → `render_skeleton`, else 404.
- **L85-97** `do_POST` — routes `/persona` → `_handle_persona`, `/review` → `_handle_review`.
- **L99-108** `_handle_persona` — calls `generate_persona_from_form`, renders persona card on success, re-renders form with error on failure.
- **L110-151** `_handle_review` — pops `persona_json` from form, calls `run_review_for_brief`, writes artifacts under `build/web/`, renders result.
- **L156-162** `_send_html`, **L164-170** `_send_text` — plain `BaseHTTPRequestHandler` responses.
- **L173-176** `serve(host, port)` — `ThreadingHTTPServer`.

### `render_form(error, values)` (L179-479)
- Field order: service_name (L366) → service_url (L369, type=url) → service_type (L372) → core_journey (L375, textarea) → persona_description (L379, textarea) → business_goal (L383, textarea) → problems (L387, textarea, optional) → competitors (L391, textarea, optional) → model (L394-398, select).
- Every input has a proper `<label for="...">` and matching `id=` — no placeholder-as-label violations.
- `required` on service_name, service_url, service_type, core_journey, persona_description.
- User values escaped via `v()` helper at L182-183 using `html.escape`.
- Error block at L185 — styled `<div class="error">`, no `role="alert"`.
- CSS variables at L193-202 (palette: --bg #f4efe6, --panel #fffaf2, --ink #1f1b16, --muted #6b6258, --accent #0e6b58, --accent-2 #d97a2b, --line #d8cec0, --error #a83131).
- Breakpoint: `@media (max-width: 860px)` at L342 collapses grid + un-sticks tips.
- Lang-switch at L354-357: two `<button>`s with inline `onclick="setLang(...)"`, labels 'English' / '한국어' each in own script.
- Lang toggle JS at L418-430: swaps `textContent` for `[data-ko]` elements, placeholders for `[data-placeholder-ko]`, sets `.active` class on matched button, updates `document.documentElement.lang`, saves to `localStorage['qra-lang']`.
- On-load at L431-434: reads `qra-lang` from localStorage, calls `setLang(saved)` if non-en. No `navigator.language` fallback.
- `showPersonaLoading()` at L437-452: replaces `document.body.innerHTML` with a centered spinner + bilingual message. Uses inline style="…" extensively. Spin keyframe at L450, NO `prefers-reduced-motion` fallback.
- Form submit handler at L454-475: prevents default, calls `showPersonaLoading()`, then `fetch('/persona')`, uses `document.open/write/close` to replace document with response HTML.
- `AUTO_RECONNECT_SCRIPT` appended after `</body>` at L478 — technically malformed HTML (script outside body).

### `render_result(form, brief, result)` (L482-716)
- `<html lang="en">` hardcoded at L593 — **not toggled**.
- CSS variables duplicated at L599 (--bg #f7f3ec, --panel #fffdf9, --ink #1e1a16, --muted #6d645a, --line #d8cec0, --accent #0e6b58).
- Base `body { font-size:14px; }` at L601 — px not rem.
- `score_labels` dict at L494-503, English only.
- `priority_colors` dict at L506-511 — Blocker/High/Medium/Nit each with text label in HTML (passes WCAG 1.4.1).
- `score_color(val)` at L513-516 — green ≥4 / yellow ≥3 / red otherwise.
- Score chip markup at L527-529 includes `{s}/5` text beside the color bar (passes 1.4.1).
- Inline `style="color:{color}"` for dynamic per-score color at L528 and .sc-fill at L529.
- Confidence pill at L669: `style="color:{conf_color};background:{conf_color}18"` — 8-digit hex alpha giving ~10% tint, likely <3:1 non-text contrast.
- Result page breakpoint: `@media (max-width:768px)` at L656.
- Section headers include emoji (📊 ✅ ❓ 🔍 🚀) — not wrapped in `<span aria-hidden="true">`.
- 'Run another review' button L671 — English only.
- `AUTO_RECONNECT_SCRIPT` appended after `</body>` at L715.

### `render_persona_card(form, persona)` (L719-866)
- `<html lang="en">` hardcoded at L739 — not toggled.
- CSS variables duplicated at L746.
- Step indicator badge 'Step 2 of 3 — Persona Check' at L778 — English only.
- Persona displayed as read-only `<div>`/`<ul>` at L783-822 — **not editable**, despite judge-def expectation of editable persona.
- Hidden form carries original form fields + `persona_json` (L824-833).
- Three action buttons at L828-830:
  - 'Looks good, run review' (primary submit)
  - 'Regenerate' (type=button, `onclick="location.reload()"` — NO-OP: reloads same page, does not re-POST /persona)
  - 'Back to form' (anchor to `/`)
- Persona breakpoint: `@media (max-width:720px)` at L772.
- Form submit handler at L836-863: prevents default, fetches `/skeleton?name=<service_name>`, writes skeleton HTML, then fetches `/review`, writes result HTML. Uses `document.open/write/close`.
- Entire template is English-only: no `data-en/data-ko` attributes anywhere.

### `render_skeleton(service_name)` (L869-1098)
- Strategy: build a fake `ReviewBrief` + fake `result` dict, call `render_result()`, then inject skeleton CSS into `<head>`. This achieves pixel-perfect layout parity with the real result page — no CLS on content swap.
- `ph(length)` helper at L875-878 emits block characters in 4-char chunks so text wraps.
- Fake data at L880-952 covers summary, 8 scores, 3 strengths, 4 findings, 2 quick-wins + 2 structural-fixes + 1 experiment, 3 open questions.
- Skeleton CSS at L958-1080:
  - `@keyframes skel-shimmer` (L960-963) 1.6s cycle, soft gradient `#ebe5d8 → #f6f1e7 → #ebe5d8`
  - `@keyframes skel-fade-in` (L964-967) 0.25s
  - `@keyframes skel-dot-anim` (L1076-1079)
  - Applies color:transparent + shimmer gradient to all dynamic text selectors (L990-1010)
  - `.fi-item::after` pseudo-element provides a dedicated shimmer block (L1016-1025)
  - `.skel-progress` message at L1059-1065 with animated dots at L1066-1079
  - **NO `@media (prefers-reduced-motion: reduce)` fallback anywhere**.
- Skeleton script at L1081-1095: reads `document.documentElement.lang`, chooses between Korean/English phase message, appends to `.wrap`. Bilingual!
- Final line L1097 injects skeleton CSS via `str.replace("</head>", ...)` — fragile string-replace pattern.

## Patterns & Problems Observed (iteration 0 baseline)

### Strengths
- Skeleton page reuses `render_result()` — zero CLS on real-content swap (best practice).
- All 7 form inputs have `<label for="...">` associations.
- HTML escape on all user echo-back (`html.escape` in v() and esc()).
- CSS custom properties for palette tokens (albeit duplicated across 3 templates).
- Pretendard loaded with `system-ui, -apple-system, sans-serif` fallback stack.
- Form submits use fetch() + document.write rather than full page nav — fast perceived.
- `localStorage['qra-lang']` persists language preference.
- setLang() correctly updates `document.documentElement.lang`.
- `url` input type on service_url.
- Priority badges and score chips include text labels beside color (passes WCAG 1.4.1).

### Weaknesses / Recurring Issues
1. **Bilingual coverage is form-page-only**: render_persona_card and render_result have no data-en/data-ko attributes and do not read `qra-lang` on load. A Korean user drops back into English after step 1.
2. **No `prefers-reduced-motion` fallback** for skel-shimmer, spin, skel-fade-in, skel-dot-anim keyframes (L450, L960, L964, L1076).
3. **Health poller never pauses on `document.hidden`** (L63). Hard `window.location.reload()` on recovery (L49).
4. **Regenerate button is a no-op** — `onclick="location.reload()"` at L829 reloads the same persona page, does not re-POST /persona.
5. **No semantic landmarks** (`<main>`, `<header>`, `<nav>`, `<footer>`) on any template.
6. **Static `<html lang="en">`** on render_persona_card (L739) and render_result (L593).
7. **Error block (L185) lacks `role="alert"` / `aria-live="assertive"`**. Polling banner (L24-39) lacks `role="status"` / `aria-live="polite"`.
8. **Inline onclick=** on 3 buttons (L355, L356, L829).
9. **Inline style=""** on many elements: AUTO_RECONNECT_SCRIPT banner (L28-38), showPersonaLoading overlay (L443-447), score chip color (L528-529), cf-pri (L548), confidence pill (L669), persona grid-column overrides (L812, L818), error fallbacks (L472, L859).
10. **Confidence pill alpha background** `{conf_color}18` (L669) likely fails WCAG 1.4.11 3:1 non-text contrast.
11. **`document.write`** used in 3 places (L469, L846-847, L855-857) — WHATWG discouraged.
12. **CSS variables duplicated** across render_form / render_result / render_persona_card — not DRY.
13. **Media queries use `max-width` (desktop-first)**, not mobile-first `min-width`.
14. **Breakpoint values arbitrary-looking**: 860px / 768px / 720px — three different numbers with no content-driven justification.
15. **Three media-query values for different templates** may create dead zones.
16. **Lang-switch buttons lack `aria-pressed`** to convey active state to SR users.
17. **Stale comment 'Step 1: Generate persona first'** at L461 — mismatched with 'Step 2 of 3' labeling on persona page.
18. **Base font-size 14px** in render_result (L601) — should be rem/em.
19. **Emoji section headers** (📊 ✅ ❓ 🔍 🚀) have no `aria-hidden` / visually-hidden text alternatives.
20. **Only one phase message for 30-60s wait** — no progressive 'Crawling…' → 'Analyzing…' → 'Generating…' sequencing.

## Iteration 0 Scores (baseline)

| Criterion | Score | Weight |
|---|---|---|
| form_ux_flow | 3.5 | 0.22 |
| loading_feedback | 3.0 | 0.18 |
| visual_language | 4.0 | 0.15 |
| responsive_layout | 3.5 | 0.12 |
| accessibility | 3.0 | 0.18 |
| i18n_bilingual | 2.5 | 0.08 |
| frontend_code_quality | 3.5 | 0.07 |
| **Aggregate** | **3.315** | 1.00 |

Target score: **4.2** (realistic within 5-iteration budget given high-leverage mechanical fixes).

## Priority Fixes Requested (active criteria only — early phase)

1. (accessibility, high) Add semantic landmarks + role="alert"/aria-live to error + polling banner + aria-pressed to lang toggle.
2. (accessibility, high) Propagate `<html lang>` and data-en/data-ko to persona card and result page.
3. (accessibility, medium) Replace inline onclick= with addEventListener + wire Regenerate to actually re-POST /persona.
4. (loading_feedback, high) Add `@media (prefers-reduced-motion: reduce)` fallback for all four keyframes.
5. (loading_feedback, medium) Pause health poll on `document.hidden`; soften forced reload on recovery.
6. (form_ux_flow, medium) Disable + aria-busy submit button on pre-navigation; add visible `*` required indicators.
7. (form_ux_flow, medium) Make 'Regenerate' actually re-call /persona instead of location.reload().

## Focus for Next Iteration (iter 1)

- Re-verify that fixes landed correctly: grep for `prefers-reduced-motion`, `visibilitychange`, `role="alert"`, `aria-live`, `aria-pressed`, `<main>`, data-ko on persona/result templates.
- Check that Regenerate button now performs a functional re-POST.
- Check that confidence pill contrast was addressed (or note as remaining).
- Mid phase (iter 2+) adds `visual_language` + `responsive_layout` to active list — start watching CSS token duplication, breakpoint rationale, confidence pill contrast.
- Late phase (iter 4) adds `i18n_bilingual` + `frontend_code_quality` — expect the big bilingual-propagation fix to land then if not earlier.
