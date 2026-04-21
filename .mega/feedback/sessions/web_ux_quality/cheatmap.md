# Wisdom Cheatmap — Web UX & Frontend Quality
**Session:** web_ux_quality | **Event:** optimize/step4/curate
**Source:** local_wisdom_store_fallback (PCR unavailable — 914-item local store)
**Agent:** judge-web_ux_quality | **Date:** 2026-04-20

---

## Strategy 1: Add `prefers-reduced-motion` Fallback to All CSS Keyframe Animations
<!-- wisdom_id: ac8a1059a8fbbe71:51eb0b5b0c7422b7:ac8a1059a8fbbe71 -->

**Target:** All four `@keyframes` blocks in `webapp.py` inline CSS
**Fix type:** CSS / Accessibility / WCAG 2.2 AA (2.3.3 Animation from Interactions)

Wrap every CSS animation that uses `@keyframes` with a `prefers-reduced-motion` media query fallback. The default rule should play the animation normally; inside `@media (prefers-reduced-motion: reduce)` set `animation: none` or replace with a simple `opacity` fade.

```css
/* Default: full animation */
.skeleton-shimmer {
  animation: shimmer 1.4s infinite;
}

/* Reduced-motion override */
@media (prefers-reduced-motion: reduce) {
  .skeleton-shimmer,
  .spinner,
  .fade-in,
  .slide-up {
    animation: none;
    transition: none;
  }
}
```

Verified via `@supports` + `@media (prefers-reduced-motion)` cross-browser behavior. Apply to all four keyframe animation classes.

**References:** overdrive#Verify the Result L141-148 · frontend-patterns#Animation Patterns L515-568

---

## Strategy 2: Extend Bilingual Support to `render_persona_card` and `render_result`
<!-- wisdom_id: e011242bced270f7:e011242bced270f7:e011242bced270f7 -->

**Target:** `render_persona_card()`, `render_result()`, `<html lang="en">` in `webapp.py`
**Fix type:** i18n / HTML semantics

Three concrete changes:

1. **Dynamic `html[lang]` attribute** — Read the language preference from `localStorage` on `DOMContentLoaded` and set `document.documentElement.lang` to `'ko'` or `'en'`. This keeps `lang` in sync across SSR and client-side toggle without a full reload.

2. **String table pattern** — Define a JS `STRINGS = { en: {...}, ko: {...} }` object in the inline script. Replace all hard-coded English strings in the persona card and result rendering paths with `STRINGS[currentLang].key`. This covers headings, labels, button text, and error messages produced by `render_result`.

3. **`<html lang>` initial value** — In the SSR path, emit `<html lang="ko">` when the `Accept-Language` header or a `lang` cookie indicates Korean, rather than hard-coding `en`.

**References:** ui-ux-pro-max#Rule Categories by Priority L62-77 · ui-ux-pro-max#Quick Reference L79-139

---

## Strategy 3: Pause Health Poller on `document.hidden` and Fix Force-Reload on Recovery
<!-- wisdom_id: 044c423c8dd59ab0:fffeaa5816aca7ad:044c423c8dd59ab0 -->

**Target:** Health-check `setInterval` / `visibilitychange` handler in inline JS
**Fix type:** JavaScript / Background behaviour / UX

Two fixes in the same polling block:

1. **Pause on hidden** — Register a `visibilitychange` listener. When `document.hidden === true` clear the interval; restart it when `document.visibilityState === 'visible'`. This prevents wasted requests and avoids log spam during background tabs.

2. **Soft recovery instead of `location.reload()`** — When the poller detects the backend has recovered, update a status banner via DOM mutation and/or announce via `aria-live="polite"`. Only force-reload if the session cannot be recovered (e.g., server returns a new session token). Unconditional `location.reload()` discards in-flight form state and is disorienting.

```js
let healthTimer;

function startPoller() {
  healthTimer = setInterval(checkHealth, 10000);
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    clearInterval(healthTimer);
  } else {
    startPoller();
  }
});
```

**References:** ui-ux-pro-max#Quick Reference L193-315 · frontend-patterns#Performance Optimization L296-389

---

## Strategy 4: Fix Regenerate Persona — Replace Reload with Fresh POST
<!-- wisdom_id: 2890bb8597def16e:e20d0a72cd71f638:2890bb8597def16e -->

**Target:** Regenerate button click handler in `webapp.py` inline JS
**Fix type:** JavaScript / Form UX / Idempotency

The Regenerate button currently calls `location.reload()` (or equivalent GET), which reloads the cached persona. Replace with a fresh `fetch` POST to the persona endpoint, passing the original form inputs stored in `sessionStorage` or a hidden data attribute on the result container.

```js
document.getElementById('btn-regenerate').addEventListener('click', async () => {
  const payload = JSON.parse(document.getElementById('result-container').dataset.formPayload);
  showSkeleton();
  const res = await fetch('/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, seed: Date.now() }) // force new generation
  });
  const html = await res.text();
  renderResult(html);
});
```

Disable the button with `aria-disabled="true"` and `pointer-events: none` while the request is in-flight to prevent double-submission.

**References:** design-to-component-translator#Interaction States L244-288 · web-frameworks#Best Practices L313-320

---

## Strategy 5: Add ARIA Landmarks, `aria-live` Regions, and `aria-pressed` on Lang Toggle
<!-- wisdom_id: 44fead57f3c10752:44fead57f3c10752:44fead57f3c10752 -->

**Target:** Page structure HTML in `webapp.py` — `render_page_shell()` or equivalent
**Fix type:** Accessibility / WCAG 2.2 AA (1.3.1 Info and Relationships, 4.1.3 Status Messages)

Three targeted additions:

1. **Semantic landmarks** — Wrap the form in `<main>`, navigation in `<nav>`, header in `<header>`, and footer in `<footer>`. Use `<section aria-labelledby="...">` for the persona result area. This gives screen-reader users jump-navigation.

2. **`aria-live` on status/error zones** — Add `role="status" aria-live="polite"` to the health-status banner and `role="alert" aria-live="assertive"` to error message containers. Screen readers announce changes without requiring focus movement.

3. **`aria-pressed` on language toggle** — The KO/EN toggle button must carry `aria-pressed="true"` when Korean is active and `aria-pressed="false"` when English is active, updated synchronously with the language switch.

```html
<button id="lang-toggle"
        role="button"
        aria-pressed="false"
        aria-label="Switch language to Korean">KO</button>

<div role="status" aria-live="polite" id="health-status"></div>
<div role="alert" aria-live="assertive" id="error-banner"></div>
```

**References:** web-perf#Phase 4: Accessibility Snapshot L132-144 · frontend-patterns#Accessibility Patterns L569-645

---

## Strategy 6: Add ETA Text to Skeleton Loader for 30–60 s Wait Times
<!-- wisdom_id: 044c423c8dd59ab0:fffeaa5816aca7ad:044c423c8dd59ab0 -->

**Target:** Skeleton loader HTML in `webapp.py`
**Fix type:** Perceived Performance / Form UX

For operations known to take 30–60 seconds, the skeleton alone is insufficient — users interpret prolonged skeletons as errors. Add:

1. **Progressive ETA message** — A text node under the skeleton that updates at predictable intervals:
   - 0–5 s: "Generating your persona…"
   - 5–15 s: "Analyzing inputs…"
   - 15–30 s: "Almost there — this can take up to 30 s…"
   - 30 s+: "Still working — thank you for your patience."

2. **Announce to screen readers** — Wrap the ETA text in the same `role="status" aria-live="polite"` region (or a sibling one) so screen-reader users receive progress updates without focus interruption.

3. **Cancel affordance** — At the 30 s mark, show a "Cancel" button that aborts the in-flight request via `AbortController` and returns to the form.

```js
const messages = [
  [0,   'Generating your persona…'],
  [5,   'Analyzing inputs…'],
  [15,  'Almost there — this can take up to 30 s…'],
  [30,  'Still working — thank you for your patience.'],
];
```

**References:** ui-ux-pro-max#Quick Reference L193-315 · frontend-patterns#Performance Optimization L296-389

---

## Strategy 7: Lower Responsive Breakpoint to ≤ 600 px (Mobile-First)
<!-- wisdom_id: ac8a1059a8fbbe71:12eecc819b32f050:a5844caa2048e128 -->

**Target:** CSS media query `@media (max-width: 860px)` in `webapp.py`
**Fix type:** Responsive Design / Mobile-First

860 px is a tablet-landscape threshold, not a mobile threshold. Most smartphones are 360–428 px wide. Change the single-column breakpoint to `600px` and audit the form layout at 320 px (minimum supported width per WCAG 1.4.10 Reflow).

```css
/* Before */
@media (max-width: 860px) { .form-grid { grid-template-columns: 1fr; } }

/* After — mobile-first */
.form-grid { grid-template-columns: 1fr; }                    /* default: single column */
@media (min-width: 600px) { .form-grid { grid-template-columns: 1fr 1fr; } }
@media (min-width: 1024px) { .form-grid { grid-template-columns: repeat(3, 1fr); } }
```

Also verify base font size ≥ 16 px across all form inputs to prevent iOS Safari auto-zoom on focus.

**References:** seo-technical-audit#Phase 4: Mobile-First Readiness L98-108 · design-to-component-translator#Responsive Design Translation L289-327
