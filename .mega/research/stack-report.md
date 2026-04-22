# PersonaLens Application Stack Analysis

## Project Overview
PersonaLens is an **AI persona-based quality review tool for web services**. It provides a three-step workflow:
1. User inputs (service info, target persona, business goal)
2. AI-generated persona card confirmation
3. Automated review execution and report generation

Available as: Claude Code skill, web UI, terminal CLI, and Slack bridge.

---

## Backend Stack

### Framework & Language
- **Primary Framework**: Python 3.11+ (standard library only for HTTP server)
- **HTTP Server**: `http.server.BaseHTTPRequestHandler` + `ThreadingHTTPServer` (Python stdlib)
- **LLM Integration**: Google Gemini API (gemini-2.5-pro, gemini-2.5-flash)
- **Package Manager**: setuptools with `pyproject.toml` configuration

### Core Modules
- **`webapp.py`**: ThreadingHTTPServer-based web application
  - GET endpoints: `/` (form), `/health`, `/skeleton` (loading state)
  - POST endpoints: `/persona` (persona generation), `/review` (full review execution)
  - HTML generation via Python string templating
  
- **`gemini.py`**: Gemini API client wrapper
  - Handles authentication, request/response serialization
  - Implements retry logic and error handling
  - Supports multiple request builders for fallback strategies
  - Raw response logging and error diagnostics
  
- **`service.py`**: Two-step pipeline orchestration
  - Step 1: `generate_persona_from_form()` - AI persona enrichment
  - Step 2: `run_review_for_brief()` - Full review execution
  - Webpage context fetching and packet building
  
- **`agent.py`**: Review packet construction
  - System prompts and validation criteria
  - Journey stages and scoring dimensions
  - Review output schema loading
  
- **`webpage.py`**: Web crawler
  - HTML parsing with `HTMLParser`
  - Subdomain-aware domain extraction
  - Navigation extraction from icon links
  - Image alt-text capture
  - Button label extraction (accessibility-aware)
  - Rate limiting to 8 pages max, 2200 char excerpts
  
- **`models.py`**: Data validation
  - Dataclass definitions: `Service`, `Persona`, `ReviewBrief`
  - URL and field validation
  - `from_dict()` and serialization support
  
- **`interactive.py`**: Terminal interactive mode
  - Step-by-step Q&A with the user
  - Persona confirmation before review
  
- **`skill_helper.py`**: Claude Code skill integration
  - JSON-based helper for skill mode
  
- **`slack_bridge.py`**: Slack command parsing + signature verification
- **`slack_server.py`**: Local Slack slash-command bridge
- **`markdown_report.py`**: Markdown report generation
- **`diagnostics.py`**: Error formatting and validation diagnostics
- **`cli.py`**: CLI argument parsing and command routing

### Data & Configuration
- **Output Schema**: `review-output-schema.json` - JSON Schema for Gemini response validation
- **Review Output**: Structured JSON with scores, findings, improvements, open questions
- **Environment Config**: `.env` file (GEMINI_API_KEY)

---

## Frontend Stack

### Architecture
- **Type**: Server-side HTML generation (no separate frontend framework)
- **Rendering**: Python string templating in `webapp.py`
- **Styling**: Embedded CSS in HTML responses
- **JavaScript**: Embedded `<script>` tags in HTML responses

### Key Pages & Components

#### 1. Main Form Page (`render_form()`)
- **Purpose**: Service metadata + persona description collection
- **Styling**:
  - CSS Grid layout (1.15fr / 0.85fr two-column)
  - Custom color palette (earth tones: #f4efe6, #1f1b16, #0e6b58)
  - Radial gradients for background
  - Responsive breakpoint at 860px
- **Inputs**: Service name, URL, type, core journey, persona description, business goal, known problems, competitors, model selection
- **Interactions**:
  - JavaScript form submission handler
  - Persona loading spinner (`showPersonaLoading()`)
  - Fetches `/persona` endpoint on form submit
  - Language toggle (English/Korean) via `setLang()`
  - Sticky sidebar with tips and expected outputs
  
#### 2. Persona Confirmation Page (`render_persona_card()`)
- **Purpose**: Display AI-generated persona for user validation
- **Layout**: Persona name, segment, fields grid (2-column, responsive)
- **Fields Displayed**:
  - Job to be done, context
  - Goals (list), pain points (list)
  - Success definition, decision style, technical level, device context
  - Voice anchors (chips), accessibility needs
  - Evidence sources, confidence level
- **Actions**:
  - "Looks good, run review" → submits to `/review` with persona JSON
  - "Regenerate" → reloads page to request new persona
  - "Back to form" → returns to initial form
- **Interactions**:
  - Skeleton loader shown while review generates (blocks completion for up to 1 minute)
  - Health check polling via `/health` endpoint with reconnection banner

#### 3. Review Results Page (`render_result()`)
- **Purpose**: Display comprehensive review output
- **Sections**:
  - Hero: Service name, verdict, confidence badge, "run another review" button
  - First impression / Why it matters (2-column cards)
  - Scores dashboard (8 dimensions: task clarity, task success, effort load, trust, value communication, error recovery, accessibility, emotional fit)
  - Strengths (compact findings with journey stage, reason)
  - Findings (prioritized by severity: Blocker, High, Medium, Nit)
  - Improvements (quick wins, structural fixes, validation experiments)
  - Open questions (for incomplete evidence)
- **Styling**:
  - Color-coded scores (green ≥4, yellow ≥3, red <3)
  - Priority badges with context colors
  - Compact text layout for dense information
  - Mobile responsive (stacks to 1 column)
- **Data Binding**: Direct mapping from JSON result to HTML via Python string interpolation

#### 4. Skeleton Loader (`render_skeleton()`)
- **Purpose**: Progressive rendering while review generates
- **Visual Effect**: Shimmer animation on placeholder blocks
- **Animation**: CSS `skel-shimmer` keyframe animation (1.6s infinite)
- **Progress Indicator**: Animated dots at bottom during generation
- **Preserves**: Section headers, labels (e.g., "Scores", "Findings")
- **Blocks**: Dynamic text content (verdict, scores, finding titles)

#### 5. Health Check & Auto-Reconnect
- **Script**: Embedded in all pages (`AUTO_RECONNECT_SCRIPT`)
- **Behavior**:
  - Polls `/health` every 1.5 seconds
  - Displays reconnection banner if server is down
  - Auto-reloads when server recovers
  - Toast notification: "Server restarting. Reconnecting automatically..."

### UI/UX Elements

#### Design System
- **Typography**: Pretendard font (Korean/Latin) via CDN
- **Color Palette**:
  - Background: #f4efe6 (warm beige)
  - Panel: #fffaf2 (off-white)
  - Text: #1f1b16 (dark brown)
  - Muted: #6b6258 (taupe)
  - Accent: #0e6b58 (teal)
  - Accent-2: #d97a2b (orange)
  - Error: #a83131 (red)
  - Line: #d8cec0 (light tan)

#### Interaction Patterns
- **Form Validation**: HTML5 `required` attributes
- **Dual Language**: Data attributes (`data-en`, `data-ko`) with JavaScript swap
- **Loading States**: Spinner with centering layout
- **Error Display**: Error blocks with colored background (#fff1f1, red text)
- **Buttons**: Gradient background, rounded corners (999px), white text
- **Cards**: Border radius 18-24px, subtle shadow, light background

#### Accessibility Considerations
- **Semantic HTML**: Form labels with `<label for="">` associations
- **Input Types**: URL validation via `type="url"`
- **Mobile Viewport**: `<meta name="viewport">` configured
- **Button Labels**: Clear action text (e.g., "Run review", "Run another review")
- **Persona Persona Page**: Aria-label extracted from icon links in crawled content
- **Color Contrast**: Dark text on light backgrounds

#### Responsive Design
- **Mobile Breakpoint**: 860px (form), 768px (results)
- **Grid Collapse**: 2-column → 1-column on small screens
- **Sticky Elements**: Tips sidebar becomes static on mobile
- **Font Scaling**: Clamp() used for hero heading (scales with viewport)

### Frontend Logic (JavaScript)
1. **Form Submission Handler** (`render_form()`):
   - Prevents default submission
   - Shows loading spinner
   - POSTs form data to `/persona` endpoint
   - Replaces page with persona card response
   - Fallback error message if request fails

2. **Persona Confirmation Handler** (`render_persona_card()`):
   - "Looks good" button fetches skeleton loader from `/skeleton`
   - Then POSTs to `/review` with persona_json hidden field
   - Replaces page with results
   - Error handling for request failures

3. **Language Toggle** (`setLang(lang)`):
   - Swaps `data-en` / `data-ko` attributes
   - Updates button active states
   - Persists to localStorage (`qra-lang`)
   - Loads saved preference on page load

4. **Health Check Polling** (`AUTO_RECONNECT_SCRIPT`):
   - IIFE polls `/health` every 1.5 seconds
   - Manages banner visibility
   - Full page reload on recovery

### No Separate Frontend Build
- No build step, no bundler, no Node.js dependency
- All CSS and JavaScript embedded in Python strings
- HTML generated on-the-fly server-side
- Single-page-like UX via `document.open()` / `document.write()` (deprecated but functional)

---

## Non-Algorithm Elements Requiring Expert Evaluation

### 1. Information Architecture & Content Organization
- **Form Field Order**: Persona description before business goal—does this order match user mental models?
- **Sticky Tips Sidebar**: Is the "What You Get" preview effective at building confidence before running the review?
- **Persona Confirmation Step**: Extra step required for validation—user friction vs. trust trade-off?
- **Two-Stage Submission**: Form → Persona → Review—does this match user expectations or feel overly complex?

### 2. Visual Design & Aesthetic
- **Color Palette**: Warm earth tones (taupe, teal, orange) vs. modern minimalism—perception of professionalism?
- **Typography Choices**: Pretendard font for CJK + Latin—appropriate for global audience?
- **Card Spacing & Shadow**: Does the visual hierarchy clearly distinguish primary form from secondary tips?
- **Mobile Layout**: Sticky sidebar collapse—does it feel natural or jarring?

### 3. User Experience Flow
- **Loading States**: Spinner + "generating persona" message—clear enough?
- **Error Messages**: Generic error format vs. actionable guidance
- **Persona Regenerate vs. Back**: Does the three-button set (confirm / regenerate / back) feel clear?
- **Results Navigation**: Single "Run another review" button at top-right—easy to find?

### 4. Messaging & Tone
- **Hero Copy**: "Review your service like a real user would"—sets expectations for AI-driven evaluation
- **Form Hints**: Example text for each field—helpful or condescending?
- **Bilingual UI**: English / Korean toggle—is the translation quality consistent?
- **Badge Language**: "Non-Developer Friendly" / "What You Get"—clear category labels?

### 5. Accessibility & Inclusivity
- **Color Contrast**: Dark text on light backgrounds meets WCAG AA?
- **Focus States**: Tab navigation for form fields—visible focus indicators?
- **Icon-Only Links**: Navigation extraction from alt-text and aria-label—adequate labels on social links?
- **Placeholder Text**: Form instructions in placeholders vs. labels—mobile-friendly?

### 6. Skeleton Loader Visual Feedback
- **Shimmer Duration**: 1.6s animation—too fast / too slow for perceived responsiveness?
- **Placeholder Block Heights**: Generated with fixed 32px—matches actual content height variance?
- **Progress Dots**: Animated dots at bottom—perceived wait time accuracy?

### 7. Trust & Credibility Signals
- **Confidence Pill**: Color-coded (high = green, medium = yellow, low = red)—does color alone convey trust?
- **Methodology Transparency**: "Why it matters" section—builds trust in reasoning?
- **Error Recovery**: Reconnection banner appearance—reassures user the tool is working?

### 8. Language & Localization
- **Korean Support**: Full bilingual UI (form, results, persona card)
- **Example Text**: Culturally specific examples for Korean and English
- **RTL Readiness**: Not designed for RTL languages (not in scope)

### 9. Device Context & Responsive Behavior
- **Desktop-First Design**: Optimized for form entry on desktop
- **Mobile Usability**: Sticky sidebar removal on small screens
- **Touch Targets**: Button sizes (12-20px padding)—adequate for touch?
- **Viewport Meta Tag**: Correctly configured for mobile scaling

### 10. Performance & Perceived Speed
- **Page Transition**: `document.open()`/`document.write()`—instant transition or perceived as glitchy?
- **Skeleton Loader**: Does shimmer provide sense of progress during 30-60s review wait?
- **Health Check Frequency**: 1.5s polling interval—unnecessary overhead?

---

## Summary

PersonaLens is a **backend-driven Python web application** with minimal frontend complexity:
- **Server**: Stdlib HTTP server, no framework
- **Frontend**: Server-side HTML generation, no SPA framework
- **Interactions**: Form submission → API calls → HTML replacement
- **Styling**: Embedded CSS with design system (earth-tone palette, responsive grid)
- **Language**: Python backend, HTML/CSS/JS frontend
- **Key UX Principle**: Progressive disclosure (form → persona review → results)

The non-algorithm elements focus on **trust-building, information hierarchy, and user confidence** in an AI-driven evaluation tool. Success depends on persona confirmation step credibility, clear error messaging, and visual feedback during long waits.
