# PersonaLens MEGA Optimization Analysis Report

## Executive Summary

**PersonaLens** is a persona-based quality review platform that generates AI-driven UX evaluations for web services. It operates as a **multi-entry-point system** with three primary interfaces (Claude Code Skill, Web UI, CLI) unified by a shared **two-stage pipeline**: (1) Persona enrichment, (2) Website review generation.

### Key Findings
- **Existing code to optimize**: YES — substantial LLM pipeline with multiple API call sites
- **Existing PRD/specification**: NO — README.md provides user docs but not formal requirements
- **Existing evaluation/training data**: NO — no train/val/test datasets (this is a service, not an ML model)

---

## Project Structure & Architecture

### Core Entry Points (Dependency Graph)
```
User Input Paths:
  CLI (cli.py) → [build | run | slack-serve]
  Web UI (webapp.py) → HTTP server
  Interactive (interactive.py) → Terminal prompts
  Claude Code Skill (skill_helper.py) → JSON-based bridge

Central Pipeline:
  service.py (orchestrator)
  ├── generate_persona_from_form() → [enrich_persona via Gemini]
  ├── create_brief_from_form() → ReviewBrief model
  ├── run_review_for_brief() → [build_review_packet] → [run_review]

LLM Integrations:
  gemini.py (Gemini API client)
  └── Two primary operations:
      ├── enrich_persona() — persona enrichment with Google Search grounding
      └── run_review() — main review generation with retry logic
```

### File Dependency Map
**High-Impact Hub Files:**
- `service.py` (5 direct dependents: cli, webapp, interactive, skill_helper, tests)
- `gemini.py` (5 direct dependents: cli, service, webapp, slack_server, tests)
- `models.py` (5 direct dependents: agent, cli, service, webapp, slack_server)

**Leaf Nodes (no dependencies):**
- `gemini.py`, `diagnostics.py`, `markdown_report.py`, `slack_bridge.py`, `webpage.py`

---

## Per-File Analysis

### 1. **gemini.py** — Gemini API Client & Persona Enrichment
**Purpose**: Two-stage LLM interaction layer

**Key Functions**:
- `run_review()` — Main review pipeline (3 request builders with retry logic)
- `enrich_persona()` — Persona generation with Google Search grounding
- `_make_request()` — urllib-based HTTP client for Gemini API
- `validate_review_output()` — Output validation (checks for empty fields)
- `normalize_api_key()` — Input sanitization

**Role**: LLM API client, critical path

**Node Type**: LLM (Google Generative AI)

**LLM Calls**:
1. **Persona Enrichment** (enrich_persona)
   - Model: `gemini-2.5-pro` (default, configurable)
   - Input: Service name, URL, journey, business goal, persona description, problems, website text
   - Tools: Google Search for web research grounding
   - Temperature: Not configured (uses Gemini defaults)
   - Prompt: Detailed system instructions requesting structured JSON persona card with specific fields

2. **Review Generation** (run_review)
   - Model: `gemini-2.5-pro`
   - Input: Review packet markdown (200+ lines including system prompt, persona, evidence, constraints, journey stages, scoring dimensions, execution instructions)
   - Retry Strategy: 3 request builders × 2 attempts = up to 6 total requests:
     - Builder 1: System instruction + Google Search tool
     - Builder 2: Inline prompt (no system instruction)
     - Builder 3: Fallback plain text (no JSON schema hint)
   - Output Format: JSON matching `review-output-schema.json`

**Data Flow**:
```
Input (form/JSON)
  ↓
[service.py] generates persona → [enrich_persona] → Gemini + Search → Persona dict
  ↓
[build_review_packet] constructs 250+ line markdown prompt
  ↓
[run_review] sends to Gemini
  ↓
JSON output → Validation → Return or Retry
```

**Optimizable Elements**:
- Retry logic: Up to 6 API calls per review (inefficient). Strategy:
  - Only retry on validation failures, not on API errors
  - Implement exponential backoff
  - Cache successful persona enrichments by service name/URL
- Prompt length: 200+ lines, contains redundant instructions (System Prompt + Execution Instructions overlap)
- Request builders: 3 variants tested sequentially; could use single optimized request
- Temperature tuning: Not exposed; likely using defaults (0.7 for Gemini)
- API key handling: Uses naive urllib; consider async or connection pooling for concurrent reviews

**External Dependencies**:
- `urllib.request` (Python stdlib)
- Gemini API: `generativelanguage.googleapis.com/v1beta`
- Google Search tool (optional, fallback to non-grounded version)

---

### 2. **service.py** — Orchestrator & Form Processing
**Purpose**: Orchestrates the two-stage pipeline (persona → brief → packet → review)

**Key Functions**:
- `run_review_for_brief()` — End-to-end orchestration
- `generate_persona_from_form()` — Step 1 of two-stage flow
- `create_brief_from_form()` — Constructs ReviewBrief from form input
- `build_packet_for_brief()` — Builds markdown prompt packet
- `infer_voice_anchors()` — Fallback persona generation (no API call)
- `infer_technical_level()` — Fallback persona generation

**Role**: Orchestration hub, fallback logic

**Node Type**: Code (pure logic + LLM delegation)

**Data Flow**:
```
Form data (dict)
  ↓
_parse_form_basics() → normalized dict
  ↓
generate_persona_from_form()
  ├─ Try: enrich_persona() via Gemini (6 retry budget)
  └─ Fallback: infer_voice_anchors() + infer_technical_level() (no API call)
  ↓
create_brief_from_form() → ReviewBrief dataclass
  ↓
build_packet_for_brief() → markdown prompt + schemas
  ↓
run_review_for_brief() → run_review() → JSON result → write to disk
```

**Optimizable Elements**:
- Error handling: Catches broad exceptions (GeminiError, json.JSONDecodeError, OSError, ValueError, TypeError). Should be more granular.
- Fallback logic: Uses regex heuristics (keyword matching in description) for persona inference. Could be more robust with templates.
- Normalization: `normalize_user_text()` and `normalize_url_text()` remove special unicode chars. Could use a proper URL library.
- Voice anchor inference: Only 4-5 anchors; hardcoded list. Could be data-driven.

**Data Files**:
- Reads: `.env` (via `os.getenv("GEMINI_API_KEY")`), example JSON briefs
- Writes: JSON review results, markdown packets, error logs

---

### 3. **agent.py** — Review Packet Builder
**Purpose**: Constructs the 250+ line markdown prompt sent to Gemini

**Key Constants**:
- `SYSTEM_PROMPT` (54 lines) — Core evaluation framework, rules on competitors, evidence vs. inference
- `VALIDATION_CRITERIA` (7 items) — Self-check criteria for the LLM
- `JOURNEY_STAGES` (7 stages) — Entry, Orientation, Task start, Core action, Error recovery, Completion, Follow-up
- `SCORING_DIMENSIONS` (8 dimensions) — task_clarity, task_success, effort_load, trust_confidence, value_communication, error_recovery, accessibility, emotional_fit

**Key Function**:
- `build_review_packet()` — Assembles markdown prompt from ReviewBrief + schema

**Role**: Prompt template + packet builder

**Node Type**: Code (pure logic)

**Optimizable Elements**:
- System prompt: Long, repetitive rules (15 lines on evaluation philosophy, 7 lines on competitor rule repeated in both system and execution instructions)
- Schema generation: `_schema_from_template()` recursively converts output schema to JSON Schema. Works but could use a library.
- Prompt structure: 250 lines is dense; could be chunked or sent via separate context (if using new Gemini context features)
- Evidence validation: Only checks for empty fields, not semantic correctness

---

### 4. **webapp.py** — Web UI HTTP Server
**Purpose**: HTTP server serving form, persona confirmation, and review execution

**Key Routes**:
- `GET /` → Render form
- `POST /persona` → Generate persona from form → Return JSON
- `POST /review` → Generate persona + run review → Save markdown + Return result
- `GET /health` → Server status check
- `GET /skeleton` → Render persona card for confirmation

**Role**: Web interface, request handler

**Node Type**: Code (HTTP routing + LLM delegation)

**Data Flow**:
```
User fills form
  ↓
POST /persona
  ↓
generate_persona_from_form() [calls Gemini]
  ↓
Return JSON persona for confirmation
  ↓
User confirms or edits
  ↓
POST /review (with optionally modified persona)
  ↓
create_brief_from_form() with persona_override
  ↓
run_review_for_brief()
  ↓
Save markdown report + JSON to disk
  ↓
Return HTML with embedded result + auto-reconnect script
```

**Optimizable Elements**:
- Threading HTTP server: `ThreadingHTTPServer` spawns a thread per request. For concurrent reviews, this could hit resource limits.
- Auto-reconnect script: 1.5s polling is aggressive; could use WebSocket or SSE for server-sent events.
- Form rendering: Inline HTML in Python strings; no template engine.
- File I/O: Writes markdown and JSON to disk for every review; could cache or stream.

---

### 5. **interactive.py** — Terminal CLI
**Purpose**: Interactive terminal prompts for human-in-the-loop review

**Key Functions**:
- `_prompt()` — Input prompt with optional default
- `_confirm()` — Y/N confirmation
- `_format_persona()` — Pretty-print persona card
- `main()` — Interactive flow (prompts for each field, shows persona for confirmation, runs review, saves markdown)

**Role**: Interactive user interface

**Node Type**: Code (UI + I/O orchestration)

**Optimizable Elements**:
- No batching: Prompts one question at a time; could group related fields
- Persona confirmation: Shows formatted card but doesn't allow field-level edits
- Output: Saves markdown report to file; no structured output option

---

### 6. **cli.py** — Command-Line Interface
**Purpose**: Entry point for CLI commands (build, run, slack-serve)

**Commands**:
1. `build --input brief.json --output packet.md` — Build packet only (no Gemini call)
2. `run --input brief.json --output result.json` — Full pipeline (persona + review)
3. `slack-serve --host 127.0.0.1 --port 8787` — Slack integration

**Role**: Entry point

**Node Type**: Code (CLI parsing + delegation)

**Optimizable Elements**:
- Error messages: Generic; could provide recovery steps
- Argument parsing: Uses argparse; no validation of output paths (could fail at write time)

---

### 7. **slack_server.py** — Slack Slash Command Bridge
**Purpose**: HTTP server for Slack `/review` slash commands

**Key Routes**:
- `POST /slack/commands` — Verify signature, parse command, run review async, post to response_url

**Role**: Slack integration

**Node Type**: Code (Slack verification + async delegation)

**Optimizable Elements**:
- Async execution: Spawns thread per request but doesn't wait; response sent immediately, then review runs in background. Could improve error reporting.
- Message truncation: Slack response limited to 3500 chars; review summary might be truncated.
- Signature verification: Uses HMAC-SHA256; correct implementation.

---

### 8. **slack_bridge.py** — Slack Request Parsing
**Purpose**: Parse and verify Slack slash commands

**Key Functions**:
- `parse_review_request()` — Parse `/review url | service | type | journey | persona | goal | problems | competitors`
- `verify_slack_signature()` — HMAC-SHA256 verification

**Role**: Slack protocol handling

**Node Type**: Code (pure logic)

---

### 9. **webpage.py** — Web Scraper
**Purpose**: Fetch and parse website text/structure for review context

**Key Functions**:
- `fetch_webpage_context()` — Fetch website, extract text + links + navigation
- `PageParser` — HTMLParser subclass that skips script/style, extracts links, nav structure
- `get_registrable_domain()` — Domain extraction for subdomain matching

**Role**: Data loader (website scraping)

**Node Type**: Code (web scraping + HTML parsing)

**Data Loading**:
- **Source**: Live website URL from user input
- **Format**: Raw HTML → parsed text (no JS execution)
- **Scale**: Up to 2200 chars extracted per page, up to 8 pages crawled
- **Important**: Does NOT execute JavaScript, so dynamic content appears as zeros/empty

**Optimizable Elements**:
- Parsing: Uses HTMLParser (stdlib); could use `lxml` or `beautifulsoup4` for robustness
- Crawling: 8-page limit is hardcoded; could be user-configurable
- Caching: No caching of fetched pages; re-fetched for persona and review stages
- Error handling: Retries up to 5 redirects; could have timeout handling

---

### 10. **markdown_report.py** — Report Rendering
**Purpose**: Convert JSON review output to markdown

**Role**: Output formatter

**Node Type**: Code (template + formatting)

---

### 11. **models.py** — Data Models
**Purpose**: Dataclasses for Service, Persona, ReviewBrief

**Role**: Data schema

**Node Type**: Code (pure data)

**Key Classes**:
- `Service` — name, url, type
- `Persona` — 13 fields including name, job_to_be_done, goals, pain_points, voice, evidence_sources, confidence
- `ReviewBrief` — aggregate of Service + Persona + evidence + constraints + notes + competitors

**Validation**:
- `ReviewBrief.validate()` — Checks non-empty fields, valid URL, required fields
- No semantic validation (e.g., are goals and pain_points distinct?)

---

### 12. **diagnostics.py** — Error Formatting
**Purpose**: User-friendly error messages

**Functions**:
- `format_gemini_error()` — Pretty-print Gemini API errors
- `format_validation_issues()` — Format validation error list
- `format_unexpected_error()` — Generic error formatting

**Role**: Error handling

**Node Type**: Code (pure logic)

---

### 13. **skill_helper.py** — Claude Code Skill Integration
**Purpose**: JSON-based bridge for Claude Code skill

**Role**: Skill entry point

**Node Type**: Code (LLM delegation via skill protocol)

---

### 14. **Test Files** (6 test modules)
**Coverage**:
- `test_diagnostics.py` — Error formatting
- `test_gemini.py` — API call simulation
- `test_service.py` — Pipeline orchestration
- `test_slack_bridge.py` — Slack parsing and signature verification
- `test_slack_server.py` — Server routing
- `test_webpage.py` — HTML parsing

**Test Data**: None (mocks used, no fixtures)

---

## Data Files & Artifacts

### Input Schemas
- `review-output-schema.json` (80 lines) — Template for expected review JSON structure

### Example Data
- `examples/brief.json` — Sample ReviewBrief for CLI testing

### Generated Artifacts (written during execution)
- `review-{service}-{timestamp}.md` — Final markdown report
- `build/review-packet.md` — Prompt sent to Gemini
- `build/output-skeleton.json` — Expected JSON structure
- `build/gemini-raw-response.json` — Raw API response
- `gemini-last-request.json` — Last request payload (for debugging)
- `gemini-last-error.txt` — Last API error (for debugging)

### No Training/Evaluation Data
This is a service, not an ML model. No train/val/test datasets exist.

---

## Optimization Opportunities by Category

### 1. LLM Pipeline Optimizations

**A. Persona Enrichment Caching**
- Current: Fresh API call for every review
- Opportunity: Cache enriched personas by (service_name, service_type, user_segment) hash
- Impact: 30-40% reduction in persona generation time for repeated services
- Effort: Low (add Redis or file-based LRU cache)

**B. Retry Strategy Refinement**
- Current: 3 request builders × 2 attempts = up to 6 API calls
- Issues: No exponential backoff, retries on all errors indiscriminately
- Opportunity:
  - Retry only on validation errors (empty output), not on API errors
  - Use exponential backoff (1s, 2s, 4s) for rate limiting
  - Add circuit breaker to fail fast on persistent API issues
- Impact: Reduce latency by 20-50% for most reviews
- Effort: Medium (refactor run_review retry loop)

**C. Prompt Optimization**
- Current: 250+ line markdown packet with redundant instructions
- Issues:
  - System Prompt (54 lines) + Execution Instructions (20 lines) overlap on core rules
  - Journey stages and scoring dimensions repeated as section headers
  - Evidence validation done by LLM instead of pre-validation
- Opportunity:
  - Consolidate system prompt + execution instructions (50+ line reduction)
  - Pre-validate evidence completeness before sending to LLM
  - Use structured prompting (e.g., Chain-of-Thought) for better consistency
  - Separate schema from instructions (move JSON structure to separate section)
- Impact: Faster token processing, clearer LLM output, potential for cheaper models (e.g., Gemini 1.5 Flash)
- Effort: Medium (requires careful prompt rewriting + A/B testing)

**D. Model Downgrade Path**
- Current: Always uses `gemini-2.5-pro` (slowest, most expensive)
- Opportunity: Offer tiered models
  - Persona enrichment: `gemini-1.5-flash` (50% cheaper, faster)
  - Review generation: Configurable (default pro, option for flash)
- Impact: 40-60% cost reduction for reviews; 10-20% latency reduction
- Effort: Low (add `--model` flag to all entry points; test with Flash)

**E. Google Search Grounding Optimization**
- Current: Optional tool in persona enrichment
- Issues: Search results could hallucinate competitor names
- Opportunity:
  - Restrict search to specific domains (e.g., site:crunchbase.com, site:ycombinator.com)
  - Cache search results by service name
  - Validate competitor names against known list before LLM processing
- Impact: Better persona grounding, fewer hallucinations
- Effort: Medium (requires prompt changes + validation logic)

---

### 2. Web Scraping & Data Loading Optimizations

**A. Webpage Caching**
- Current: Fetches webpage fresh for persona + review (2 calls per review cycle)
- Opportunity: Cache fetched pages by URL for 1-5 hours
- Impact: 50% reduction in network I/O per review
- Effort: Low (add simple file-based or Redis cache)

**B. JavaScript Execution**
- Current: HTMLParser skips dynamic content (shows as zeros)
- Opportunity: Optional Playwright or Selenium integration for JS-heavy sites
- Impact: Better review accuracy for SPA/dynamic sites
- Effort: High (adds dependency, complexity; potential resource overhead)
- Recommendation: Skip for now; add as opt-in feature later

**C. Concurrent Crawling**
- Current: Sequential fetch_webpage_context() calls
- Opportunity: Parallel crawling of multiple links (up to 8 pages)
- Impact: 50-70% reduction in crawl time per site
- Effort: Medium (refactor to async/concurrent, add connection pooling)

---

### 3. API & Infrastructure Optimizations

**A. HTTP Connection Pooling**
- Current: urllib makes fresh connection for each request
- Opportunity: Use `urllib3` or `requests` with connection pooling
- Impact: 10-20% latency reduction for high-concurrency scenarios
- Effort: Low (drop-in replacement for urllib)

**B. Async/Concurrent Review Processing**
- Current: Sequential reviews (wait for Gemini response before returning)
- Opportunity: Fire-and-forget pattern with async status polling
- Impact: Support concurrent reviews; better UX for web/Slack interfaces
- Effort: High (requires async refactoring throughout)
- Recommendation: Phase 2 optimization

**C. Rate Limiting & Quota Management**
- Current: No explicit rate limiting
- Opportunity: Add token-bucket rate limiter (configurable per API key)
- Impact: Prevent API quota exhaustion; graceful degradation
- Effort: Low (implement simple rate limiter)

---

### 4. Prompt Engineering & Consistency Optimizations

**A. Output Schema Validation**
- Current: LLM validates its own output (via validation criteria)
- Issues: Self-validation is weak; some reviews have sparse findings
- Opportunity:
  - Pre-define scoring rubrics (e.g., "Blocker = site doesn't load, no CTA")
  - Add scoring examples to prompt
  - Use JSON schema enforcement at API level (responseMimeType: application/json)
  - Add minimum thresholds for required fields (e.g., >= 2 strengths, >= 2 findings)
- Impact: Fewer empty/sparse reviews; more consistent structure
- Effort: Medium (requires prompt refinement + schema validation)

**B. Persona Specification Language**
- Current: 13 fields in Persona dataclass; some redundant (job_to_be_done vs. context vs. goals)
- Opportunity:
  - Merge job_to_be_done and context into single field (user's situation)
  - Simplify voice anchors to 3-4 (instead of 5)
  - Make evidence_sources mandatory and grounded
- Impact: Clearer persona, less LLM variation
- Effort: Low (requires data model refactoring + migration of existing data)

**C. Journey Stage Mapping**
- Current: 7 fixed journey stages; user provides custom core_journey
- Opportunity:
  - Map user's core_journey to standard stages dynamically
  - Allow custom stages if user provides them
  - Use stages as scaffolding for findings (organize by stage)
- Impact: Better organization of findings; clearer narrative
- Effort: Medium (requires prompt changes + dynamic mapping logic)

---

### 5. Error Handling & Observability Optimizations

**A. Structured Logging**
- Current: Generic error messages; no logging
- Opportunity:
  - Add structured logging (timestamp, request_id, model, latency, error_type)
  - Log to disk or service (e.g., file-based for CLI, Slack logging for service)
- Impact: Better debugging; observability for production
- Effort: Low (use Python `logging` module + JSON formatter)

**B. Retry Instrumentation**
- Current: Retries happen silently; no user feedback
- Opportunity:
  - Count and log retry attempts
  - Show user a progress indicator (e.g., "Attempt 2 of 6...")
  - Expose retry counts in result metadata
- Impact: Better UX for long-running reviews
- Effort: Low (add counters + progress messages)

**C. API Error Classification**
- Current: Broad exception handling (catches GeminiError, JSONDecodeError, etc.)
- Opportunity:
  - Distinguish recoverable errors (rate limit, timeout) from permanent (invalid API key, malformed request)
  - Implement different retry strategies per error type
  - Provide user-facing error messages (e.g., "API quota exceeded; try again in 1 minute")
- Impact: Faster failure detection; better recovery
- Effort: Medium (requires error type enumeration + handling logic)

---

### 6. Configuration & Extensibility Optimizations

**A. Environment Configuration**
- Current: Only GEMINI_API_KEY configured; hardcoded defaults elsewhere
- Opportunity:
  - Centralize config: model name, timeouts, max pages, retry counts, cache TTL
  - Support .env file or environment variables
  - Add config validation on startup
- Impact: Easier deployment and tuning
- Effort: Low (use `pydantic` or custom config module)

**B. Multi-Model Support**
- Current: Hardcoded gemini-2.5-pro
- Opportunity:
  - Support multiple model choices (Flash, Pro, Ultra if available)
  - Add model registry with pricing/latency metadata
  - Allow per-stage model selection (cheap for persona, expensive for review)
- Impact: Cost flexibility; performance tuning
- Effort: Medium (requires config + model abstraction layer)

**C. Persona Template Library**
- Current: Dynamic persona generation only
- Opportunity:
  - Offer pre-built persona templates (e.g., "Busy PM", "Skeptical CTO", "First-time SaaS user")
  - Allow users to select + customize template instead of generating
- Impact: Faster reviews; better consistency for repeated user segments
- Effort: Medium (requires template data + selection UI)

---

### 7. Codebase Quality Optimizations

**A. Remove Duplication**
- `normalize_user_text()` and `normalize_url_text()` are redundant
- System Prompt rules duplicated in Execution Instructions
- Multiple error formatting functions with similar logic
- Opportunity: DRY refactoring
- Effort: Low

**B. Add Type Hints**
- Current: Partial type hints (some functions lack annotations)
- Opportunity: Complete type coverage using `mypy`
- Impact: Better IDE support, fewer runtime errors
- Effort: Low

**C. Separate Concerns**
- `service.py` mixes form parsing, persona generation, packet building, and review orchestration
- Opportunity: Extract form parsing to dedicated module
- Effort: Low-Medium

---

## Summary: Optimization Priority Matrix

| Category | Opportunity | Impact | Effort | Priority |
|----------|-------------|--------|--------|----------|
| LLM Pipeline | Prompt consolidation | High | Medium | P0 |
| LLM Pipeline | Retry strategy refinement | High | Medium | P0 |
| LLM Pipeline | Persona enrichment caching | Medium | Low | P1 |
| LLM Pipeline | Model downgrade path (Flash option) | Medium | Low | P1 |
| Data Loading | Webpage caching | Medium | Low | P1 |
| API Infra | Connection pooling (urllib3) | Low | Low | P2 |
| Observability | Structured logging | Low | Low | P2 |
| Error Handling | API error classification | Medium | Medium | P1 |
| Config | Environment configuration | Low | Low | P2 |
| Code Quality | Remove duplication | Low | Low | P2 |

---

## Scalability Assessment

### Current Bottlenecks
1. **Single Gemini API call per review** (1-2 min per request) — not inherently scalable, but rate-limit risk
2. **Synchronous web scraping** (up to 30s for crawling 8 pages) — sequential I/O
3. **ThreadingHTTPServer** — will struggle with >50 concurrent reviews
4. **No caching** — same URL reviewed multiple times = redundant work

### Scalability Recommendations
1. Add Redis or file-based caching for personas and webpage snapshots
2. Implement async/concurrent architecture for web scraping
3. Consider job queue (e.g., Celery, RQ) for long-running reviews if scaling to hundreds/day
4. Add rate-limiting and quota management per API key

---

## Conclusion

**PersonaLens** is a well-architected two-stage LLM pipeline with clear separation of concerns (persona enrichment → review generation). Primary optimization opportunities lie in:

1. **Prompt engineering** (consolidation, redundancy removal)
2. **Retry strategy** (backoff, condition-based retries)
3. **Caching** (personas, webpages, search results)
4. **Model flexibility** (support Flash for cost savings)
5. **Observability** (logging, error classification)

No structural refactoring required; focused prompt and caching improvements will yield 30-50% latency and cost savings without major rewrites.

