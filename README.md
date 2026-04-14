# 🔍 Quality Review Agent

AI persona-based quality review tool for web services. Provide a few basic inputs and the agent will generate a specific target persona, evaluate your website from that perspective, and produce a detailed markdown report.

Three ways to use it:
- **Claude Code skill** — conversational flow inside Claude Code
- **Web UI** — simple browser form
- **CLI** — run directly from the terminal

---

## 🚀 Install in one line

Copy and paste this into your terminal (or Claude Code):

```bash
git clone https://github.com/d-ai-1231/PersonaLens.git && cd PersonaLens && ./install.sh
```

The installer will ask for your free [Gemini API key](https://aistudio.google.com/apikey) and set everything up. Done.

---

## 🤖 Option 1: Claude Code Skill (recommended)

After restarting Claude Code, just ask:

```
Review this site: https://example.com
```

The agent will:
1. Ask you questions about your service (name, type, core journey, target user, etc.) **one at a time**
2. Generate an **AI persona card** and show it for your confirmation
3. After confirmation, run the full review (~30–60 seconds)
4. Save a markdown report to `review-{service}-{timestamp}.md` in your current directory

## 🌐 Option 2: Web UI

```bash
./start-web.sh
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080) in your browser. Fill in the form and click "Run review".

Includes a Korean/English toggle and the persona confirmation step.

## 💻 Option 3: Terminal CLI

Interactive mode:
```bash
PYTHONPATH=src python3 -m quality_review_agent interactive https://example.com
```

Or JSON-driven automation:
```bash
PYTHONPATH=src python3 -m quality_review_agent run \
  --input examples/brief.json \
  --output build/review-result.json
```

---

## 📋 What the report contains

Each review is saved as a markdown report with:

- **Summary** — verdict, first impression, why it matters
- **Target persona** — name, job-to-be-done, goals, pain points, success definition
- **Scores** across 8 dimensions — task clarity, task success, effort load, trust confidence, value communication, error recovery, accessibility, emotional fit
- **Strengths** — what's currently working well
- **Findings** — prioritized issues (Blocker / High / Medium / Nit)
- **Improvements** — quick wins, structural fixes, validation experiments
- **Open questions** — things the AI couldn't verify

## 🎯 Design principles

This is not a generic UX checklist:

- **Evaluator, not expander** — the agent evaluates whether the website serves your stated business goal and persona, it does NOT suggest enhancing random content just because it exists
- **Evidence-based** — the agent only mentions products or facts that come from your input or the target website's own text. No guessing competitors from Google Search
- **Human-in-the-loop** — the AI-generated persona is shown to you for confirmation before the review runs
- **Quality first** — defaults to `gemini-2.5-pro` for higher-quality analysis

## 🛠️ Requirements

- Python 3.10+
- Gemini API key (free tier works) — [get one here](https://aistudio.google.com/apikey)
- Claude Code (only if using the skill mode)

## 📁 Project structure

```
quality-review-agent/
├── install.sh                # One-command installer
├── skill-template/
│   └── SKILL.md              # Claude Code skill template
├── src/quality_review_agent/
│   ├── agent.py              # Review packet builder
│   ├── gemini.py             # Gemini API client + persona enrichment
│   ├── service.py             # Two-step pipeline (persona → review)
│   ├── webapp.py             # Web UI
│   ├── interactive.py        # Terminal interactive CLI
│   ├── skill_helper.py       # JSON-based helper for the Claude Code skill
│   ├── markdown_report.py    # Markdown report generator
│   └── webpage.py            # Web crawler (subdomain + icon link aware)
└── review-output-schema.json
```

## 🔧 Troubleshooting

**The skill doesn't appear in Claude Code:**
- Fully restart Claude Code
- Verify `~/.claude/skills/review-service/SKILL.md` exists

**Gemini API errors:**
- Check that `.env` contains `GEMINI_API_KEY='...'` in the correct format
- Make sure there are no trailing spaces or special characters in the key

**Review results feel off:**
- In the persona confirmation step, click "Regenerate" to try again
- Fill the "competitors" field with real competitor names to prevent hallucinations
- Add team-specific VOC in the "known problems" field for sharper feedback

## 📜 License

Personal use.
