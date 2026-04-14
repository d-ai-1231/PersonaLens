# 🔍 Quality Review Agent

AI 페르소나 기반 웹 서비스 품질 리뷰 도구. 간단한 정보만 입력하면 AI가 구체적인 타겟 사용자를 생성하고, 그 관점에서 웹사이트를 평가하여 한국어 리포트를 만들어줍니다.

세 가지 방식으로 사용할 수 있습니다:
- **Claude Code 스킬** — 대화형으로 질문 주고받으며 실행
- **웹 UI** — 브라우저 폼 입력
- **CLI** — 터미널에서 직접 실행

---

## 🚀 빠른 설치 (Quick Start)

```bash
git clone <repo-url>
cd quality-review-agent
./install.sh
```

설치 스크립트가 자동으로:
1. Python 3 설치 여부 확인
2. `GEMINI_API_KEY`를 물어보고 `.env`에 저장 ([Google AI Studio에서 무료 발급](https://aistudio.google.com/apikey))
3. Claude Code 스킬을 `~/.claude/skills/review-service/`에 설치

끝! 이제 바로 쓸 수 있습니다.

---

## 🤖 사용 방법 1: Claude Code 스킬 (추천)

Claude Code를 재시작한 뒤, 아래처럼 대화하세요:

```
리뷰해줘 https://example.com
```

에이전트가 대화형으로:
1. 서비스 이름, 유형, 핵심 여정, 타겟 사용자 등을 **하나씩 질문**
2. 입력을 기반으로 **AI 페르소나 카드를 생성**하고 보여줌
3. 확인 후 **30-60초간 리뷰 실행**
4. `review-{서비스명}-{날짜}.md` 파일로 **한국어 마크다운 리포트 저장**

## 🌐 사용 방법 2: 웹 UI

```bash
./start-web.sh
```

브라우저에서 [http://127.0.0.1:8080](http://127.0.0.1:8080) 접속. 폼을 채우고 "리뷰 실행" 클릭.

한국어/영어 토글 지원, 페르소나 확인 단계 포함.

## 💻 사용 방법 3: 터미널 CLI

```bash
PYTHONPATH=src python3 -m quality_review_agent interactive https://example.com
```

또는 JSON 입력으로 자동화:

```bash
PYTHONPATH=src python3 -m quality_review_agent run \
  --input examples/brief.json \
  --output build/review-result.json
```

---

## 📋 리뷰 결과물

각 리뷰는 다음 정보를 포함하는 **한국어 마크다운 리포트**로 저장됩니다:

- **요약** — 판정, 첫인상, 왜 중요한가
- **타겟 페르소나** — 이름, Job-to-be-done, 목표, 불편, 성공 정의
- **평가 점수** (8개 차원) — 작업 명확성, 신뢰 확신, 가치 전달력, 오류 복구, 접근성 등
- **강점** — 현재 잘 작동하는 부분
- **발견 사항** — 우선순위별 (Blocker/High/Medium/Nit)
- **개선 제안** — 빠른 개선, 구조적 개선, 검증 실험
- **열린 질문** — AI가 확인 못한 부분

## 🎯 에이전트의 원칙

이 도구는 단순한 UX 체크리스트가 아닙니다:

- **평가자 역할** — 웹사이트 콘텐츠를 확장하는 게 아니라, 사용자가 명시한 비즈니스 목표/페르소나에 맞는지 **평가**
- **증거 기반** — 사용자 입력이나 웹사이트 실제 텍스트에 있는 것만 언급. 구글 검색으로 경쟁사 추측 금지
- **Human-in-the-loop** — AI가 생성한 페르소나를 사용자에게 보여주고 확인 받음
- **정확도 우선** — 기본 모델 `gemini-2.5-pro` 사용

## 🛠️ 요구사항

- Python 3.10+
- Gemini API Key (무료 tier 가능) — [발급하기](https://aistudio.google.com/apikey)
- Claude Code (스킬 사용 시)

## 📁 프로젝트 구조

```
quality-review-agent/
├── install.sh              # 설치 스크립트
├── skill-template/
│   └── SKILL.md           # Claude Code 스킬 템플릿
├── src/quality_review_agent/
│   ├── agent.py           # 리뷰 패킷 빌더
│   ├── gemini.py          # Gemini API 클라이언트 + 페르소나 정교화
│   ├── service.py         # 2단계 파이프라인 (페르소나 → 리뷰)
│   ├── webapp.py          # 웹 UI
│   ├── interactive.py     # 터미널 인터랙티브 CLI
│   ├── skill_helper.py    # Claude Code 스킬용 JSON 헬퍼
│   ├── markdown_report.py # 한국어 MD 리포트 생성기
│   └── webpage.py         # 웹 크롤러 (서브도메인, 아이콘 링크 지원)
└── review-output-schema.json
```

## 🔧 문제 해결

**스킬이 Claude Code에 안 보이면:**
- Claude Code를 완전히 재시작
- `~/.claude/skills/review-service/SKILL.md` 파일이 존재하는지 확인

**Gemini API 에러가 나면:**
- `.env` 파일에 `GEMINI_API_KEY='...'` 형식으로 키가 제대로 들어갔는지 확인
- API 키 끝에 공백이나 특수문자가 없는지 확인

**리뷰 결과가 부정확하면:**
- 페르소나 확인 단계에서 "다시 생성"으로 재시도
- 경쟁 제품 필드에 실제 경쟁사를 명시
- 알려진 사용자 문제 필드에 팀만 아는 VOC 추가

## 📜 라이선스

Personal use.
