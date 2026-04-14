---
name: review-service
description: Interactive persona-based UX/quality review for any web service. Asks the user about the service (URL, target persona, core journey, etc.), generates an AI persona for confirmation, then runs a detailed review and saves a markdown report. Triggers on "review this site", "UX review", "quality review", "리뷰해줘".
---

# Service Quality Review

Interactive persona-based quality review agent for web services. Runs the Quality Review Agent Python project to generate an AI persona, then performs a detailed review anchored to the user's business goals.

## When to use

Invoke this skill when the user wants to:
- Review a website's UX, clarity, trust signals, and onboarding flow
- Get a persona-based quality assessment of their service
- Evaluate landing-to-onboarding conversion path
- Produce a markdown report of findings and improvements

## Preconditions

- The `Quality Review Agent` project must exist at `{{PROJECT_DIR}}`
- `GEMINI_API_KEY` must be set in the project's `.env` file
- Python 3 must be available
- The user should be able to answer basic questions about their service (target user, business goal, etc.)

## Workflow

### Step 1: Collect inputs interactively

Ask the user these questions **one at a time** in a natural conversation. Be friendly and efficient. Match the user's language (Korean or English). Some fields are optional.

**IMPORTANT — Use AskUserQuestion when the answer fits a small set of options.** This gives the user clickable choices instead of typing. Use plain text questions only for open-ended answers (URL, names, descriptions).

Question-by-question guide:

1. **Service URL** — plain text (skip if already provided in the command)
2. **Service name** — plain text (suggest based on URL domain as default)
3. **Service type** — **use AskUserQuestion** with options:
   - "SaaS / Web app"
   - "E-commerce"
   - "Landing / Marketing page"
   - "Mobile app"
   (Users can pick "Other" to type a custom value)
4. **Most important user action** — plain text (core journey, e.g., "sign up and start onboarding")
5. **Who is the main user?** — plain text (persona description, e.g., "developers looking to boost productivity")
6. **Business goal** — plain text, **optional** (tell user they can skip)
7. **Known user problems / VOC** — plain text, **optional** (only fill if there are team-specific complaints)
8. **Competitors or alternatives** — plain text, **optional** (only real competitors — never let the AI guess)

After collecting, save the answers to a temporary JSON file:

```bash
PROJECT_DIR="{{PROJECT_DIR}}"
TMPDIR=$(mktemp -d)
FORM_JSON="$TMPDIR/form.json"
PERSONA_JSON="$TMPDIR/persona.json"
```

Write `form.json` using the Write tool with this structure:
```json
{
  "service_name": "...",
  "service_url": "...",
  "service_type": "...",
  "core_journey": "...",
  "persona_description": "...",
  "business_goal": "...",
  "problems": "...",
  "competitors": "...",
  "model": "gemini-2.5-pro"
}
```

### Step 2: Generate and confirm persona

Run the persona generator:

```bash
cd "$PROJECT_DIR" && set -a && source .env && set +a && \
  PYTHONPATH=src python3 -m quality_review_agent.skill_helper persona "$FORM_JSON" > "$PERSONA_JSON"
```

Read the generated persona from `$PERSONA_JSON` and present it to the user in a nicely formatted way (show name, JTBD, context, goals, pain points, success definition, decision style, voice anchors).

**Use AskUserQuestion** to ask: "Does this persona look right?"

Options:
- "Looks good — run review"
- "Regenerate persona"
- "Edit inputs and retry"

Based on their choice:
- **Looks good** → proceed to Step 3
- **Regenerate** → re-run the persona command and show the new persona again
- **Edit inputs** → ask what to change, update `form.json`, re-run persona generation

### Step 3: Run the review

Once the user confirms the persona:

```bash
OUTPUT_MD="$PWD/review-$(date +%Y%m%d-%H%M).md"
cd "$PROJECT_DIR" && set -a && source .env && set +a && \
  PYTHONPATH=src python3 -m quality_review_agent.skill_helper review \
    "$FORM_JSON" "$PERSONA_JSON" "$OUTPUT_MD"
```

This will take 30–60 seconds. Tell the user it's running and what it's doing ("crawling the website → persona-based analysis → generating improvements").

The command outputs a JSON summary to stdout with:
- `markdown_path`: absolute path to the saved report
- `verdict`, `confidence`, `finding_count`, `strength_count`

### Step 4: Present results

After the review completes:
1. Tell the user the markdown file path: **"✅ Review report saved: `{path}`"**
2. Briefly summarize: verdict, number of findings, overall confidence
3. **Use AskUserQuestion** to ask: "What would you like to see first?"
   - "Findings (prioritized issues)"
   - "Improvements (suggestions)"
   - "Strengths"
   - "Open the full report file"
4. Based on their choice, read the relevant section from the markdown file and paste it into chat (or open the file)
5. Clean up the temp directory: `rm -rf "$TMPDIR"`

## Rules

### Always
- **Collect answers one at a time** — conversational, not a form dump
- **Match the user's language** — if they write in Korean, respond in Korean; otherwise English
- **Ask permission to proceed** after showing the persona — never skip validation
- **Save the markdown report in the current working directory** — so the user can easily find it
- **Use gemini-2.5-pro** — quality is prioritized for reviews

### Never
- **Don't hallucinate answers** — if user skips an optional field, pass an empty string
- **Don't guess competitor names** — only use what the user explicitly provided
- **Don't inline the review result** — always save to markdown file first, then summarize
- **Don't re-ask the URL** if it was provided in the initial command

## Example Invocation

```
User: /review-service https://example.com

Claude: [asks questions one by one, collects answers]
Claude: [generates persona, shows it]
Claude: Does this persona look right?
User: Yes

Claude: [runs review, ~45 seconds]
Claude: ✅ Done! Report: review-example-20260414-1530.md

Verdict: Value proposition is clear but conversion path has friction
Confidence: medium
Findings: 7 (1 Blocker, 2 High, 3 Medium, 1 Nit)
Strengths: 3

Which section would you like to see first?
```
