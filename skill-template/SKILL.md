---
name: review-service
description: Interactive persona-based UX/quality review for any web service. Asks the user about the service (URL, target persona, core journey, etc.), generates an AI persona for confirmation, then runs a detailed review and saves a Korean markdown report. Triggers on "리뷰해줘", "review this site", "UX 리뷰", "품질 리뷰".
---

# Service Quality Review

Interactive persona-based quality review agent for web services. Runs the Quality Review Agent Python project to generate an AI persona, then performs a detailed review anchored to the user's business goals.

## When to use

Invoke this skill when the user wants to:
- Review a website's UX, clarity, trust signals, and onboarding flow
- Get a persona-based quality assessment of their service
- Evaluate landing-to-onboarding conversion path
- Produce a Korean markdown report of findings and improvements

## Preconditions

- The `Quality Review Agent` project must exist at `{{PROJECT_DIR}}`
- `GEMINI_API_KEY` must be set in the project's `.env` file
- Python 3 must be available
- The user should be able to answer basic questions about their service (target user, business goal, etc.)

## Workflow

### Step 1: Collect inputs interactively

Ask the user these questions **one at a time** in a natural conversation. Be friendly and efficient — don't dump all questions at once. Some fields are optional (mark them as "선택" when asking).

Required:
1. **서비스 URL** (if not already provided in the command)
2. **서비스 이름** (can suggest based on URL domain)
3. **서비스 유형** (e.g., "SaaS", "커머스", "랜딩페이지", "모바일 앱")
4. **가장 중요한 사용자 행동** (핵심 여정, e.g., "회원가입 후 온보딩 시작")
5. **주요 사용자는 누구인가요?** (페르소나 설명, e.g., "생산성 높이려는 개발자")

Optional (tell user they can skip):
6. **비즈니스 목표** (e.g., "온보딩 완료율 향상")
7. **알려진 사용자 문제 / VOC** — 팀만 아는 구체적 불만이 있다면
8. **경쟁 제품 또는 대안 도구** — 실제 경쟁사만 입력 (AI가 추측하지 않도록)

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

Ask: **"이 페르소나로 리뷰를 진행할까요?"**

Options:
- **예** → proceed to Step 3
- **다시 생성** → re-run the persona command and show again
- **아니오 / 수정** → ask what to change, update `form.json`, re-run persona command

### Step 3: Run the review

Once the user confirms the persona:

```bash
OUTPUT_MD="$PWD/review-$(date +%Y%m%d-%H%M).md"
cd "$PROJECT_DIR" && set -a && source .env && set +a && \
  PYTHONPATH=src python3 -m quality_review_agent.skill_helper review \
    "$FORM_JSON" "$PERSONA_JSON" "$OUTPUT_MD"
```

This will take 30–60 seconds. Tell the user it's running and what it's doing ("웹사이트 크롤링 → 페르소나 기반 분석 → 개선안 생성").

The command outputs a JSON summary to stdout with:
- `markdown_path`: absolute path to the saved report
- `verdict`, `confidence`, `finding_count`, `strength_count`

### Step 4: Present results

After the review completes:
1. Tell the user the markdown file path: **"✅ 리뷰 리포트가 저장되었습니다: `{path}`"**
2. Briefly summarize: verdict, number of findings, overall confidence
3. Ask if they want to open the file or see a specific section (강점 / 발견 사항 / 개선 제안)
4. Clean up the temp directory: `rm -rf "$TMPDIR"`

## Rules

### Always
- **Collect answers one at a time** — conversational, not a form dump
- **Use Korean for the conversation and final report** — matches user preference
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
User: /review-service https://megacode.ai

Claude: [asks questions one by one, collects answers]
Claude: [generates persona, shows it]
Claude: 이 페르소나가 맞나요?
User: 네

Claude: [runs review, ~45 seconds]
Claude: ✅ 완료! 리뷰 리포트: review-megacode-20260414-1530.md

판정: 가치 제안은 명확하나 전환 경로에 마찰이 있음
신뢰도: medium
발견 사항: 7개 (Blocker 1, High 2, Medium 3, Nit 1)
강점: 3개

어떤 섹션부터 보시겠어요?
```
