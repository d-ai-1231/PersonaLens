from __future__ import annotations

import html
import json
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .gemini import GeminiError
from .models import ValidationError
from .service import create_brief_from_form, generate_persona_from_form, review_brief_to_json, run_review_for_brief


APP_TITLE = "PersonaLens"
AUTO_RECONNECT_SCRIPT = """
<script>
(() => {
  let failed = false;

  function ensureBanner() {
    let banner = document.getElementById("server-status-banner");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "server-status-banner";
      banner.style.position = "fixed";
      banner.style.right = "18px";
      banner.style.bottom = "18px";
      banner.style.zIndex = "9999";
      banner.style.padding = "12px 14px";
      banner.style.borderRadius = "14px";
      banner.style.background = "rgba(31,27,22,.92)";
      banner.style.color = "white";
      banner.style.font = "600 14px/1.4 Georgia, serif";
      banner.style.boxShadow = "0 8px 24px rgba(0,0,0,.18)";
      banner.style.display = "none";
      document.body.appendChild(banner);
    }
    return banner;
  }

  async function poll() {
    try {
      const res = await fetch("/health", { cache: "no-store" });
      if (!res.ok) throw new Error("health failed");
      if (failed) {
        window.location.reload();
      }
      failed = false;
      const banner = ensureBanner();
      banner.style.display = "none";
    } catch (err) {
      failed = true;
      const banner = ensureBanner();
      banner.textContent = "Server restarting. Reconnecting automatically...";
      banner.style.display = "block";
    }
  }

  poll();
  setInterval(poll, 1500);
})();
</script>
"""


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(render_form())
            return
        if parsed.path == "/health":
            self._send_text("ok")
            return
        if parsed.path == "/skeleton":
            qs = parse_qs(parsed.query)
            service_name = qs.get("name", [""])[0]
            self._send_html(render_skeleton(service_name))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        form = {key: values[0] for key, values in parse_qs(body).items()}

        if parsed.path == "/persona":
            self._handle_persona(form)
            return
        if parsed.path == "/review":
            self._handle_review(form)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _handle_persona(self, form: dict[str, str]) -> None:
        try:
            persona_dict = generate_persona_from_form(form, model=form.get("model", "gemini-2.5-pro"))
        except GeminiError as exc:
            self._send_html(render_form(error=f"Gemini request failed: {exc}", values=form), status=HTTPStatus.BAD_GATEWAY)
            return
        except Exception as exc:  # pragma: no cover
            self._send_html(render_form(error=f"Unexpected error: {exc}", values=form), status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_html(render_persona_card(form, persona_dict))

    def _handle_review(self, form: dict[str, str]) -> None:
        persona_override = None
        persona_json = form.pop("persona_json", "")
        if persona_json:
            try:
                persona_override = json.loads(persona_json)
            except json.JSONDecodeError:
                persona_override = None

        try:
            brief = create_brief_from_form(
                form,
                model=form.get("model", "gemini-2.5-pro"),
                persona_override=persona_override,
            )
            build_dir = Path("build/web")
            result = run_review_for_brief(
                brief=brief,
                schema_path=Path("review-output-schema.json"),
                model=form.get("model", "gemini-2.5-pro"),
                packet_output=build_dir / "review-packet.md",
                skeleton_output=build_dir / "output-skeleton.json",
                result_output=build_dir / "review-result.json",
                raw_output=build_dir / "gemini-raw-response.json",
            )
        except KeyError as exc:
            self._send_html(render_form(error=f"Missing field: {exc.args[0]}", values=form), status=HTTPStatus.BAD_REQUEST)
            return
        except ValidationError as exc:
            self._send_html(render_form(error=" / ".join(exc.issues), values=form), status=HTTPStatus.BAD_REQUEST)
            return
        except GeminiError as exc:
            self._send_html(render_form(error=f"Gemini request failed: {exc}", values=form), status=HTTPStatus.BAD_GATEWAY)
            return
        except Exception as exc:  # pragma: no cover
            build_dir = Path("build/web")
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "last-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            self._send_html(render_form(error=f"Unexpected error: {exc}", values=form), status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_html(render_result(form, brief, result))

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_html(self, content: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_text(self, content: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def serve(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"PersonaLens running at http://{host}:{port}")
    server.serve_forever()


def render_form(error: str = "", values: dict[str, str] | None = None) -> str:
    values = values or {}

    def v(key: str, default: str = "") -> str:
        return html.escape(values.get(key, default))

    error_block = f'<div class="error">{html.escape(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{APP_TITLE}</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --panel: #fffaf2;
      --ink: #1f1b16;
      --muted: #6b6258;
      --accent: #0e6b58;
      --accent-2: #d97a2b;
      --line: #d8cec0;
      --error: #a83131;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: 'Pretendard', system-ui, -apple-system, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(217,122,43,.18), transparent 32%),
        radial-gradient(circle at top right, rgba(14,107,88,.12), transparent 28%),
        linear-gradient(180deg, #efe5d5 0%, var(--bg) 48%, #f8f3eb 100%);
    }}
    .wrap {{
      max-width: 980px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}
    .hero {{
      display: grid;
      gap: 12px;
      margin-bottom: 24px;
    }}
    .hero-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(1.8rem, 4vw, 3.5rem);
      line-height: 1;
      letter-spacing: -0.03em;
    }}
    .sub {{
      max-width: 760px;
      color: var(--muted);
      font-size: 1.05rem;
      line-height: 1.5;
    }}
    .lang-switch {{
      display: flex;
      gap: 4px;
      padding: 3px;
      background: rgba(31,27,22,.06);
      border-radius: 999px;
      flex-shrink: 0;
    }}
    .lang-switch button {{
      margin: 0;
      padding: 6px 12px;
      border: 0;
      border-radius: 999px;
      font: 600 .82rem/1 'Pretendard', system-ui, sans-serif;
      cursor: pointer;
      background: transparent;
      color: var(--muted);
      transition: all .2s;
    }}
    .lang-switch button.active {{
      background: white;
      color: var(--ink);
      box-shadow: 0 1px 4px rgba(0,0,0,.1);
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.15fr .85fr;
      gap: 18px;
    }}
    .card {{
      background: color-mix(in srgb, var(--panel) 92%, white);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 22px;
      box-shadow: 0 10px 40px rgba(31,27,22,.07);
    }}
    .tips {{
      align-self: start;
      position: sticky;
      top: 20px;
    }}
    label {{
      display: block;
      margin: 14px 0 6px;
      font-weight: 700;
    }}
    input, textarea, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 13px 14px;
      font: inherit;
      color: var(--ink);
      background: #fffdf9;
    }}
    textarea {{
      min-height: 110px;
      resize: vertical;
    }}
    .hint {{
      color: var(--muted);
      font-size: .92rem;
      line-height: 1.45;
    }}
    .error {{
      margin-bottom: 16px;
      padding: 14px 16px;
      border-radius: 16px;
      background: #fff1f1;
      border: 1px solid #efc8c8;
      color: var(--error);
      font-weight: 700;
    }}
    .submit-btn {{
      margin-top: 18px;
      border: 0;
      border-radius: 999px;
      padding: 14px 22px;
      font: inherit;
      font-weight: 700;
      color: white;
      background: linear-gradient(135deg, var(--accent), #1d8a74);
      cursor: pointer;
    }}
    ul {{
      margin: 12px 0 0;
      padding-left: 20px;
      color: var(--muted);
      line-height: 1.5;
    }}
    .badge {{
      display: inline-block;
      margin-bottom: 10px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(217,122,43,.12);
      color: #8a4e1e;
      font-size: .82rem;
      font-weight: 700;
      letter-spacing: .04em;
      text-transform: uppercase;
    }}
    @media (max-width: 860px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .tips {{ position: static; }}
    }}
  </style>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard-dynamic-subset.css">
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="hero-top">
        <div class="badge" data-en="Non-Developer Friendly" data-ko="비개발자도 OK">Non-Developer Friendly</div>
        <div class="lang-switch">
          <button class="active" onclick="setLang('en')">English</button>
          <button onclick="setLang('ko')">한국어</button>
        </div>
      </div>
      <h1 data-en="Review your service like a real user would." data-ko="실제 사용자의 눈으로 서비스를 리뷰하세요.">Review your service like a real user would.</h1>
      <div class="sub" data-en="Put in a few plain-language answers. The agent will review your service from the target user's point of view, explain what feels unclear or weak, and suggest concrete improvements." data-ko="간단한 정보 몇 가지만 입력하세요. AI 에이전트가 타겟 사용자의 관점에서 서비스를 리뷰하고, 불명확한 부분을 짚어주고, 구체적인 개선안을 제안합니다.">Put in a few plain-language answers. The agent will review your service from the target user's point of view, explain what feels unclear or weak, and suggest concrete improvements.</div>
    </div>
    <div class="grid">
      <form class="card" method="post" action="/review">
        {error_block}
        <label for="service_name" data-en="Service name" data-ko="서비스 이름">Service name</label>
        <input id="service_name" name="service_name" value="{v('service_name')}" required>

        <label for="service_url" data-en="Service URL" data-ko="서비스 URL">Service URL</label>
        <input id="service_url" name="service_url" type="url" placeholder="https://example.com" value="{v('service_url')}" required>

        <label for="service_type" data-en="Service type" data-ko="서비스 유형">Service type</label>
        <input id="service_type" name="service_type" data-placeholder-en="web app, SaaS, marketplace..." data-placeholder-ko="웹앱, SaaS, 마켓플레이스..." placeholder="web app, SaaS, marketplace..." value="{v('service_type', 'web product')}" required>

        <label for="core_journey" data-en="Most important user action" data-ko="가장 중요한 사용자 행동">Most important user action</label>
        <textarea id="core_journey" name="core_journey" required>{v('core_journey')}</textarea>
        <div class="hint" data-en="Example: Sign up, understand the product, and start onboarding through GitHub." data-ko="예: 회원가입 후 제품을 이해하고 GitHub을 통해 온보딩을 시작한다.">Example: Sign up, understand the product, and start onboarding through GitHub.</div>

        <label for="persona_description" data-en="Who is the main user?" data-ko="주요 사용자는 누구인가요?">Who is the main user?</label>
        <textarea id="persona_description" name="persona_description" required>{v('persona_description')}</textarea>
        <div class="hint" data-en="Describe them like a real person. Example: A developer evaluating agent tools who leaves quickly if value feels vague." data-ko="실제 사람처럼 묘사해주세요. 예: 에이전트 도구를 평가하는 개발자. 가치가 모호하면 바로 떠남.">Describe them like a real person. Example: A developer evaluating agent tools who leaves quickly if value feels vague.</div>

        <label for="business_goal" data-en="Business goal" data-ko="비즈니스 목표">Business goal</label>
        <textarea id="business_goal" name="business_goal">{v('business_goal')}</textarea>
        <div class="hint" data-en="Example: Increase onboarding start rate from landing page visitors." data-ko="예: 랜딩 페이지 방문자의 온보딩 시작률을 높인다.">Example: Increase onboarding start rate from landing page visitors.</div>

        <label for="problems" data-en="Known user problems (optional)" data-ko="알려진 사용자 문제점 (선택)">Known user problems (optional)</label>
        <textarea id="problems" name="problems">{v('problems')}</textarea>
        <div class="hint" data-en="If you have team-specific complaints or VOC, please include them. Leave blank if unsure. One per line, 2–5 recommended. Example: Users are not sure if this is useful. People hesitate before logging in." data-ko="팀만 아는 구체적 불만이나 VOC가 있다면 꼭 적어주세요. 없으면 비워두셔도 됩니다. 한 줄에 하나씩, 2~5개 권장. 예: 이게 유용한지 잘 모르겠다. 로그인하기 전에 망설인다.">If you have team-specific complaints or VOC, please include them. Leave blank if unsure. One per line, 2–5 recommended. Example: Users are not sure if this is useful. People hesitate before logging in.</div>

        <label for="competitors" data-en="Competitors or alternatives (optional)" data-ko="경쟁 제품 또는 대안 (선택)">Competitors or alternatives (optional)</label>
        <textarea id="competitors" name="competitors">{v('competitors')}</textarea>
        <div class="hint" data-en="Comma-separated list of real competitors or alternatives. Leave blank if unsure — the AI will not guess. Example: Cursor, GitHub Copilot" data-ko="실제 경쟁 제품이나 대안 도구를 쉼표로 구분해서 적어주세요. 비워두면 AI가 추측하지 않습니다. 예: Cursor, GitHub Copilot">Comma-separated list of real competitors or alternatives. Leave blank if unsure — the AI will not guess. Example: Cursor, GitHub Copilot</div>

        <label for="model" data-en="Gemini model" data-ko="Gemini 모델">Gemini model</label>
        <select id="model" name="model">
          <option value="gemini-2.5-pro" {"selected" if v('model', 'gemini-2.5-pro') == 'gemini-2.5-pro' else ""}>gemini-2.5-pro</option>
          <option value="gemini-2.5-flash" {"selected" if v('model') == 'gemini-2.5-flash' else ""}>gemini-2.5-flash</option>
        </select>

        <button class="submit-btn" type="submit" data-en="Run review" data-ko="리뷰 실행">Run review</button>
      </form>
      <div class="card tips">
        <div class="badge" data-en="What You Get" data-ko="결과 미리보기">What You Get</div>
        <h2 data-en="One review, three outputs." data-ko="한 번의 리뷰, 세 가지 결과.">One review, three outputs.</h2>
        <ul>
          <li data-en="A user-perspective summary of what works and what does not." data-ko="사용자 관점에서 무엇이 잘 되고 안 되는지 요약합니다.">A user-perspective summary of what works and what does not.</li>
          <li data-en="Prioritized findings with severity and business impact." data-ko="심각도와 비즈니스 영향을 기준으로 우선순위가 매겨진 발견 사항.">Prioritized findings with severity and business impact.</li>
          <li data-en="Improvement ideas grouped into quick wins, bigger fixes, and experiments." data-ko="빠른 개선, 구조적 수정, 검증 실험으로 그룹화된 개선 아이디어.">Improvement ideas grouped into quick wins, bigger fixes, and experiments.</li>
        </ul>
        <ul>
          <li data-en="The app also saves raw files under <code>build/web</code>." data-ko="원본 파일은 <code>build/web</code> 폴더에 저장됩니다.">The app also saves raw files under <code>build/web</code>.</li>
          <li data-en="If the model lacks enough evidence, it should say so instead of faking certainty." data-ko="근거가 부족하면 확신하는 척하지 않고 솔직하게 말합니다.">If the model lacks enough evidence, it should say so instead of faking certainty.</li>
        </ul>
      </div>
    </div>
  </div>
<script>
function setLang(lang) {{
  document.querySelectorAll('[data-ko]').forEach(el => {{
    el.textContent = el.getAttribute('data-' + lang) || el.textContent;
  }});
  document.querySelectorAll('[data-placeholder-ko]').forEach(el => {{
    el.placeholder = el.getAttribute('data-placeholder-' + lang) || el.placeholder;
  }});
  document.querySelectorAll('.lang-switch button').forEach(btn => {{
    btn.classList.toggle('active', btn.textContent === (lang === 'ko' ? '한국어' : 'English'));
  }});
  document.documentElement.lang = lang;
  localStorage.setItem('qra-lang', lang);
}}
(function() {{
  const saved = localStorage.getItem('qra-lang');
  if (saved && saved !== 'en') setLang(saved);
}})();


function showPersonaLoading() {{
  const lang = document.documentElement.lang || 'en';
  const msg = lang === 'ko'
    ? '페르소나 생성 중 — 잠시만 기다려 주세요'
    : 'Generating persona — one moment';
  document.body.innerHTML = `
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:'Pretendard',system-ui,sans-serif;background:linear-gradient(180deg,#f0e6d7,#f7f3ec);padding:40px 20px;">
      <div style="text-align:center;max-width:420px;">
        <div style="display:inline-block;width:44px;height:44px;border:3px solid #d8cec0;border-top-color:#0e6b58;border-radius:50%;animation:spin 1s linear infinite;margin-bottom:18px;"></div>
        <div style="font-size:1.05rem;font-weight:700;color:#1e1a16;margin-bottom:6px;">${{msg}}</div>
        <div style="font-size:.85rem;color:#6d645a;">AI가 서비스와 사용자를 분석하고 있습니다...</div>
      </div>
    </div>
    <style>@keyframes spin {{ to {{ transform:rotate(360deg); }} }}</style>
  `;
}}

(function() {{
  const form = document.querySelector('form[action="/review"]');
  if (!form) return;
  form.addEventListener('submit', async (e) => {{
    e.preventDefault();
    showPersonaLoading();
    try {{
      // Step 1: Generate persona first, let user confirm
      const response = await fetch('/persona', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
        body: new URLSearchParams(new FormData(form)),
      }});
      const html = await response.text();
      document.open();
      document.write(html);
      document.close();
    }} catch (err) {{
      document.body.innerHTML = '<div style="padding:40px;text-align:center;color:#a83131;font-size:1.1rem;">Request failed: ' + err.message + '</div>';
    }}
  }});
}})();
</script>
</body>
{AUTO_RECONNECT_SCRIPT}
</html>"""


def render_result(form: dict[str, str], brief, result: dict) -> str:
    summary = result.get("review_summary") or {}
    scores = result.get("scores") or {}
    strengths = result.get("strengths") or []
    findings = result.get("findings") or []
    improvements = result.get("prioritized_improvements") or {}
    open_questions = result.get("open_questions") or []

    def esc(value: str) -> str:
        return html.escape(value or "")

    # Score labels in English
    score_labels = {
        "task_clarity": "Task clarity",
        "task_success": "Task success",
        "effort_load": "Effort load",
        "trust_confidence": "Trust & confidence",
        "value_communication": "Value communication",
        "error_recovery": "Error recovery",
        "accessibility": "Accessibility",
        "emotional_fit": "Emotional fit",
    }

    # Priority colors
    priority_colors = {
        "Blocker": ("#a83131", "#fff1f1"),
        "High": ("#9d4f1f", "#fff6ed"),
        "Medium": ("#7a6c00", "#fffde6"),
        "Nit": ("#4a6a5a", "#f0f7f4"),
    }

    def score_color(val: int) -> str:
        if val >= 4: return "#0e6b58"
        if val >= 3: return "#7a6c00"
        return "#a83131"

    def render_score_bar() -> str:
        items = []
        for key, payload in scores.items():
            if not isinstance(payload, dict):
                continue
            s = payload.get("score", 0)
            label = score_labels.get(key, key.replace("_", " "))
            color = score_color(s)
            items.append(
                f"<div class='sc'><div class='sc-top'><span class='sc-label'>{esc(label)}</span>"
                f"<span class='sc-num' style='color:{color}'>{s}/5</span></div>"
                f"<div class='sc-bar'><div class='sc-fill' style='width:{s*20}%;background:{color}'></div></div>"
                f"<div class='sc-reason'>{esc(payload.get('reason', ''))}</div></div>"
            )
        return "".join(items)

    def render_compact_findings(items: list[dict], is_strength: bool = False) -> str:
        blocks = []
        for item in items:
            if is_strength:
                blocks.append(
                    f"<div class='cf'><span class='cf-stage'>{esc(item.get('journey_stage', ''))}</span>"
                    f"<strong>{esc(item.get('title', ''))}</strong>"
                    f"<span class='cf-detail'>{esc(item.get('persona_reason', ''))}</span></div>"
                )
            else:
                pri = item.get("priority", "Medium")
                pc, pbg = priority_colors.get(pri, ("#6d645a", "#f5f5f5"))
                blocks.append(
                    f"<div class='cf'>"
                    f"<span class='cf-pri' style='color:{pc};background:{pbg}'>{esc(pri)}</span>"
                    f"<strong>{esc(item.get('title', ''))}</strong>"
                    f"<span class='cf-detail'>{esc(item.get('problem', ''))}</span>"
                    f"<span class='cf-action'>{esc(item.get('improvement_direction', ''))}</span>"
                    f"</div>"
                )
        return "".join(blocks) or "<p class='empty'>No items</p>"

    def render_compact_improvements() -> str:
        blocks = []
        qw = improvements.get("quick_wins") or []
        sf = improvements.get("structural_fixes") or []
        ve = improvements.get("validation_experiments") or []
        if qw:
            blocks.append("<div class='imp-group'><h3>⚡ Quick wins</h3>")
            for item in qw:
                effort = item.get("estimated_effort", "")
                blocks.append(
                    f"<div class='imp'><strong>{esc(item.get('change', ''))}</strong>"
                    f"<span class='imp-meta'>Outcome: {esc(item.get('expected_user_outcome', ''))} · Effort: {esc(effort)}</span></div>"
                )
            blocks.append("</div>")
        if sf:
            blocks.append("<div class='imp-group'><h3>🔧 Structural fixes</h3>")
            for item in sf:
                effort = item.get("estimated_effort", "")
                blocks.append(
                    f"<div class='imp'><strong>{esc(item.get('change', ''))}</strong>"
                    f"<span class='imp-meta'>Outcome: {esc(item.get('expected_user_outcome', ''))} · Effort: {esc(effort)}</span></div>"
                )
            blocks.append("</div>")
        if ve:
            blocks.append("<div class='imp-group'><h3>🧪 Validation experiments</h3>")
            for item in ve:
                blocks.append(
                    f"<div class='imp'><strong>{esc(item.get('experiment', ''))}</strong>"
                    f"<span class='imp-meta'>Hypothesis: {esc(item.get('hypothesis', ''))} · Metric: {esc(item.get('success_metric', ''))}</span></div>"
                )
            blocks.append("</div>")
        return "".join(blocks) or "<p class='empty'>No improvement items</p>"

    confidence = summary.get("confidence", "")
    conf_color = {"high": "#0e6b58", "medium": "#7a6c00", "low": "#a83131"}.get(confidence.lower(), "#6d645a")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(form.get('service_name', ''))} — Review Result</title>
  <style>
    :root {{ --bg:#f7f3ec; --panel:#fffdf9; --ink:#1e1a16; --muted:#6d645a; --line:#d8cec0; --accent:#0e6b58; }}
    * {{ box-sizing:border-box; margin:0; }}
    body {{ font-family:'Pretendard',system-ui,-apple-system,sans-serif; color:var(--ink); background:linear-gradient(180deg,#f0e6d7,var(--bg)); font-size:14px; line-height:1.5; }}
    .wrap {{ max-width:1080px; margin:0 auto; padding:24px 16px 40px; }}

    /* Hero */
    .hero {{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:20px; }}
    .hero h1 {{ font-size:1.6rem; letter-spacing:-0.02em; margin-bottom:4px; }}
    .verdict {{ font-size:1rem; color:var(--muted); margin-bottom:8px; }}
    .conf {{ display:inline-block; padding:3px 10px; border-radius:999px; font-size:.78rem; font-weight:700; }}
    .btn {{ display:inline-block; padding:10px 16px; border-radius:999px; background:var(--accent); color:white; text-decoration:none; font-weight:700; font-size:.85rem; white-space:nowrap; }}

    /* Cards */
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:16px; box-shadow:0 6px 20px rgba(30,26,22,.05); margin-bottom:12px; }}
    .card h2 {{ font-size:.95rem; margin-bottom:10px; color:var(--accent); }}

    /* Layout */
    .row {{ display:grid; gap:12px; }}
    .row-2 {{ grid-template-columns:1fr 1fr; }}
    .row-3 {{ grid-template-columns:1fr 1fr 1fr; }}

    /* First impression */
    .fi {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
    .fi-item {{ padding:10px; background:#f9f6f0; border-radius:12px; }}
    .fi-label {{ font-size:.75rem; color:var(--muted); font-weight:700; text-transform:uppercase; letter-spacing:.04em; margin-bottom:2px; }}

    /* Scores */
    .sc {{ margin-bottom:8px; }}
    .sc-top {{ display:flex; justify-content:space-between; align-items:center; }}
    .sc-label {{ font-size:.82rem; color:var(--muted); }}
    .sc-num {{ font-size:.82rem; font-weight:700; }}
    .sc-bar {{ height:4px; background:#e8e2d8; border-radius:4px; margin:3px 0 2px; }}
    .sc-fill {{ height:100%; border-radius:4px; transition:width .3s; }}
    .sc-reason {{ font-size:.75rem; color:var(--muted); }}

    /* Compact findings */
    .cf {{ padding:8px 0; border-bottom:1px solid #ece7df; }}
    .cf:last-child {{ border-bottom:none; }}
    .cf strong {{ display:block; font-size:.88rem; margin-bottom:2px; }}
    .cf-stage {{ display:inline-block; font-size:.7rem; padding:1px 6px; border-radius:999px; background:rgba(14,107,88,.1); color:var(--accent); font-weight:600; margin-bottom:4px; }}
    .cf-pri {{ display:inline-block; font-size:.7rem; padding:1px 6px; border-radius:999px; font-weight:700; margin-bottom:4px; }}
    .cf-detail {{ display:block; font-size:.82rem; color:var(--muted); }}
    .cf-action {{ display:block; font-size:.8rem; color:var(--accent); margin-top:2px; }}

    /* Improvements */
    .imp-group h3 {{ font-size:.85rem; margin-bottom:6px; }}
    .imp {{ padding:6px 0; border-bottom:1px solid #ece7df; }}
    .imp:last-child {{ border-bottom:none; }}
    .imp strong {{ font-size:.85rem; }}
    .imp-meta {{ display:block; font-size:.78rem; color:var(--muted); }}

    /* Open questions */
    .oq {{ padding:4px 0; font-size:.85rem; color:var(--muted); border-bottom:1px solid #ece7df; }}
    .oq:last-child {{ border-bottom:none; }}

    .empty {{ color:var(--muted); font-style:italic; }}

    @media (max-width:768px) {{
      .row-2,.row-3 {{ grid-template-columns:1fr; }}
      .fi {{ grid-template-columns:1fr; }}
    }}
  </style>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard-dynamic-subset.css">
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div>
        <h1>{esc(form.get('service_name', 'Service Review'))}</h1>
        <div class="verdict">{esc(summary.get('verdict', ''))}</div>
        <span class="conf" style="color:{conf_color};background:{conf_color}18">Confidence: {esc(confidence)}</span>
      </div>
      <a class="btn" href="/">Run another review</a>
    </div>

    <div class="card">
      <div class="fi">
        <div class="fi-item">
          <div class="fi-label">First impression</div>
          {esc(summary.get('first_impression', ''))}
        </div>
        <div class="fi-item">
          <div class="fi-label">Why it matters</div>
          {esc(summary.get('why_it_matters', ''))}
        </div>
      </div>
    </div>

    <div class="row row-2">
      <div class="card">
        <h2>📊 Scores</h2>
        {render_score_bar()}
      </div>
      <div>
        <div class="card">
          <h2>✅ Strengths</h2>
          {render_compact_findings(strengths, is_strength=True)}
        </div>
        <div class="card">
          <h2>❓ Open questions</h2>
          {"".join(f"<div class='oq'>{esc(q)}</div>" for q in open_questions) or "<p class='empty'>None</p>"}
        </div>
      </div>
    </div>

    <div class="card">
      <h2>🔍 Findings</h2>
      {render_compact_findings(findings, is_strength=False)}
    </div>

    <div class="card">
      <h2>🚀 Improvements</h2>
      {render_compact_improvements()}
    </div>
  </div>
</body>
{AUTO_RECONNECT_SCRIPT}
</html>"""


def render_persona_card(form: dict[str, str], persona: dict) -> str:
    """Render the AI-generated persona for user validation before running the review."""
    def esc(v: str) -> str:
        return html.escape(v or "")

    def list_items(items: list) -> str:
        if not items:
            return "<li class='empty'>-</li>"
        return "".join(f"<li>{esc(str(x))}</li>" for x in items)

    persona_json = html.escape(json.dumps(persona, ensure_ascii=False), quote=True)
    service_name = esc(form.get("service_name", ""))

    # Hidden fields to carry form data forward to /review
    hidden_fields = "".join(
        f'<input type="hidden" name="{esc(k)}" value="{esc(v)}">'
        for k, v in form.items()
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{service_name} — Persona Check</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard-dynamic-subset.css">
  <style>
    :root {{ --bg:#f7f3ec; --panel:#fffdf9; --ink:#1e1a16; --muted:#6d645a; --line:#d8cec0; --accent:#0e6b58; --warn:#9d4f1f; }}
    * {{ box-sizing:border-box; margin:0; }}
    body {{ font-family:'Pretendard',system-ui,-apple-system,sans-serif; color:var(--ink); background:linear-gradient(180deg,#f0e6d7,var(--bg)); font-size:14px; line-height:1.55; min-height:100vh; }}
    .wrap {{ max-width:920px; margin:0 auto; padding:28px 16px 48px; }}
    .hero {{ margin-bottom:20px; }}
    .hero h1 {{ font-size:1.55rem; letter-spacing:-0.02em; margin-bottom:6px; }}
    .hero p {{ color:var(--muted); font-size:.95rem; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:20px; padding:22px; box-shadow:0 8px 24px rgba(30,26,22,.06); margin-bottom:14px; }}
    .p-name {{ font-size:1.2rem; font-weight:800; margin-bottom:4px; color:var(--accent); }}
    .p-segment {{ color:var(--muted); font-size:.9rem; margin-bottom:14px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    .field {{ padding:12px; background:#f9f6f0; border-radius:12px; }}
    .field label {{ display:block; font-size:.72rem; color:var(--muted); font-weight:700; text-transform:uppercase; letter-spacing:.04em; margin-bottom:4px; }}
    .field .val {{ font-size:.9rem; }}
    .field ul {{ margin:0; padding-left:18px; font-size:.88rem; }}
    .field ul li {{ margin-bottom:2px; }}
    .empty {{ color:var(--muted); font-style:italic; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:5px; margin-top:2px; }}
    .chip {{ display:inline-block; padding:3px 9px; border-radius:999px; background:rgba(14,107,88,.1); color:var(--accent); font-size:.74rem; font-weight:600; }}
    .actions {{ display:flex; gap:10px; margin-top:18px; flex-wrap:wrap; }}
    .btn {{ display:inline-flex; align-items:center; gap:6px; padding:12px 20px; border-radius:999px; border:0; cursor:pointer; font: inherit; font-weight:700; font-size:.9rem; text-decoration:none; }}
    .btn-primary {{ background:linear-gradient(135deg, var(--accent), #1d8a74); color:white; }}
    .btn-ghost {{ background:transparent; color:var(--muted); border:1px solid var(--line); }}
    .btn-warn {{ background:#fff1ea; color:var(--warn); border:1px solid #f0d0ba; }}
    .hint {{ color:var(--muted); font-size:.85rem; margin-top:10px; }}
    .badge {{ display:inline-block; padding:4px 10px; border-radius:999px; background:rgba(217,122,43,.14); color:#8a4e1e; font-size:.72rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; margin-bottom:8px; }}
    @media (max-width:720px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="badge">Step 2 of 3 — Persona Check</div>
      <h1>Does this persona look right?</h1>
      <p>Based on your inputs and the website content, the AI generated a specific target user. Confirm to run the review, or regenerate if needed.</p>
    </div>

    <div class="card">
      <div class="p-name">{esc(persona.get('name', ''))}</div>
      <div class="p-segment">{esc(persona.get('segment', ''))}</div>

      <div class="grid">
        <div class="field">
          <label>Job to be done</label>
          <div class="val">{esc(persona.get('job_to_be_done', ''))}</div>
        </div>
        <div class="field">
          <label>Context</label>
          <div class="val">{esc(persona.get('context', ''))}</div>
        </div>
        <div class="field">
          <label>Goals</label>
          <ul>{list_items(persona.get('goals') or [])}</ul>
        </div>
        <div class="field">
          <label>Pain points</label>
          <ul>{list_items(persona.get('pain_points') or [])}</ul>
        </div>
        <div class="field">
          <label>Success definition</label>
          <div class="val">{esc(persona.get('success_definition', ''))}</div>
        </div>
        <div class="field">
          <label>Decision style / Tech level / Device</label>
          <div class="val">{esc(persona.get('decision_style', ''))} · {esc(persona.get('technical_level', ''))} · {esc(persona.get('device_context', ''))}</div>
        </div>
        <div class="field" style="grid-column:1/-1">
          <label>Voice anchors</label>
          <div class="chips">
            {''.join(f'<span class="chip">{esc(str(v))}</span>' for v in (persona.get('voice') or []))}
          </div>
        </div>
        <div class="field" style="grid-column:1/-1">
          <label>Accessibility needs</label>
          <ul>{list_items(persona.get('access_needs') or [])}</ul>
        </div>
      </div>

      <form method="post" action="/review" id="confirm-form">
        {hidden_fields}
        <input type="hidden" name="persona_json" value="{persona_json}">
        <div class="actions">
          <button class="btn btn-primary" type="submit">👍 Looks good, run review</button>
          <button class="btn btn-ghost" type="button" onclick="location.reload()">🔄 Regenerate</button>
          <a class="btn btn-warn" href="/">✏️ Back to form</a>
        </div>
        <div class="hint">The review may take up to a minute to generate.</div>
      </form>
    </div>
  </div>
<script>
(function() {{
  const form = document.getElementById('confirm-form');
  if (!form) return;
  form.addEventListener('submit', async (e) => {{
    e.preventDefault();
    try {{
      const skelResponse = await fetch('/skeleton?name=' + encodeURIComponent('{service_name}'));
      const skelHtml = await skelResponse.text();
      document.open();
      document.write(skelHtml);
      document.close();

      const response = await fetch('/review', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
        body: new URLSearchParams(new FormData(form)),
      }});
      const html = await response.text();
      document.open();
      document.write(html);
      document.close();
    }} catch (err) {{
      document.body.innerHTML = '<div style="padding:40px;text-align:center;color:#a83131;font-size:1.1rem;">Request failed: ' + err.message + '</div>';
    }}
  }});
}})();
</script>
{AUTO_RECONNECT_SCRIPT}
</body>
</html>"""


def render_skeleton(service_name: str = "") -> str:
    """Render the result page with placeholder content + skeleton CSS overlay.
    Guarantees pixel-perfect match with the real result page since it uses render_result()."""
    from .models import Persona, ReviewBrief, Service

    # Use block characters with spaces so the browser can wrap them naturally
    def ph(length: int) -> str:
        # Group into chunks of 4 with spaces to allow word-wrap
        chunks = ["▇▇▇▇" for _ in range(max(1, length // 4))]
        return " ".join(chunks)

    fake_form = {"service_name": service_name or "서비스"}
    fake_brief = ReviewBrief(
        service=Service(name=service_name or "서비스", url="https://example.com", type="web"),
        review_goal=ph(20),
        core_journey=ph(20),
        business_goal=ph(20),
        persona=Persona(
            name=ph(8), segment=ph(15), job_to_be_done=ph(20), context=ph(30),
            goals=[ph(15), ph(15), ph(15)],
            pain_points=[ph(15), ph(15), ph(15)],
            technical_level="medium",
            decision_style=ph(10),
            device_context="desktop",
            access_needs=[ph(10)],
            success_definition=ph(30),
            voice=[ph(8), ph(8), ph(8)],
            evidence_sources=[ph(10)],
            confidence="medium",
        ),
        evidence=[ph(20)],
        known_constraints=[ph(20)],
        notes=[ph(20)],
    )

    score_keys = [
        "task_clarity", "task_success", "effort_load", "trust_confidence",
        "value_communication", "error_recovery", "accessibility", "emotional_fit",
    ]
    fake_result = {
        "review_summary": {
            "verdict": ph(60),
            "scope": ph(20),
            "persona_name": ph(10),
            "persona_segment": ph(15),
            "confidence": "medium",
            "first_impression": ph(80),
            "why_it_matters": ph(70),
        },
        "scores": {k: {"score": 3, "reason": ph(50)} for k in score_keys},
        "strengths": [
            {"title": ph(25), "journey_stage": ph(8), "persona_reason": ph(60), "evidence": ph(30)}
            for _ in range(3)
        ],
        "findings": [
            {
                "priority": "Medium",
                "title": ph(30),
                "journey_stage": ph(8),
                "problem": ph(80),
                "persona_voice": ph(40),
                "evidence": ph(30),
                "impact_on_user": ph(40),
                "impact_on_business": ph(40),
                "improvement_direction": ph(60),
            }
            for _ in range(4)
        ],
        "prioritized_improvements": {
            "quick_wins": [
                {"change": ph(35), "expected_user_outcome": ph(50), "expected_business_outcome": ph(40), "estimated_effort": "low"}
                for _ in range(2)
            ],
            "structural_fixes": [
                {"change": ph(35), "expected_user_outcome": ph(50), "expected_business_outcome": ph(40), "estimated_effort": "medium"}
                for _ in range(2)
            ],
            "validation_experiments": [
                {"experiment": ph(35), "hypothesis": ph(50), "success_metric": ph(30)}
                for _ in range(1)
            ],
        },
        "open_questions": [ph(70) for _ in range(3)],
    }

    html_str = render_result(fake_form, fake_brief, fake_result)

    # Inject skeleton CSS overlay that turns text content into shimmer bars
    # while preserving section headers, labels, and the rerun button.
    skeleton_css = """
<style>
@keyframes skel-shimmer {
  0% { background-position: -800px 0; }
  100% { background-position: 800px 0; }
}
@keyframes skel-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
body { animation: skel-fade-in .25s ease; }

/* Force wrap on placeholder text so it never overflows */
.hero h1,
.verdict,
.fi-item,
.sc-label,
.sc-num,
.sc-reason,
.cf strong,
.cf-detail,
.cf-action,
.cf-stage,
.cf-pri,
.imp strong,
.imp-meta,
.oq {
  word-break: break-all !important;
  overflow-wrap: anywhere !important;
}

/* Turn dynamic text into shimmer bars */
.hero h1,
.verdict,
.sc-label,
.sc-num,
.sc-reason,
.cf strong,
.cf-detail,
.cf-action,
.cf-stage,
.cf-pri,
.imp strong,
.imp-meta,
.oq {
  color: transparent !important;
  background: linear-gradient(90deg, #ebe5d8 0%, #f6f1e7 50%, #ebe5d8 100%) !important;
  background-size: 1200px 100% !important;
  animation: skel-shimmer 1.6s infinite linear !important;
  border-radius: 4px !important;
  text-shadow: none !important;
  border-color: transparent !important;
}

/* fi-item is a container, not text — only shimmer the text inside */
.fi-item {
  position: relative;
}
.fi-item::after {
  content: '';
  display: block;
  height: 32px;
  margin-top: 4px;
  background: linear-gradient(90deg, #ebe5d8 0%, #f6f1e7 50%, #ebe5d8 100%);
  background-size: 1200px 100%;
  animation: skel-shimmer 1.6s infinite linear;
  border-radius: 4px;
}
.fi-item {
  color: transparent !important;
  font-size: 0 !important;
}
.fi-item .fi-label {
  font-size: .75rem !important;
  color: #6d645a !important;
}

/* Keep first-impression label visible */
.fi-label { color: #6d645a !important; background: transparent !important; animation: none !important; }

/* Confidence pill becomes shimmer */
.conf {
  color: transparent !important;
  background: linear-gradient(90deg, #ebe5d8 0%, #f6f1e7 50%, #ebe5d8 100%) !important;
  background-size: 1200px 100% !important;
  animation: skel-shimmer 1.6s infinite linear !important;
}

/* Score bars: hide the colored fill, show shimmer */
.sc-bar { background: #e8e2d8 !important; }
.sc-fill {
  background: linear-gradient(90deg, #ebe5d8 0%, #f6f1e7 50%, #ebe5d8 100%) !important;
  background-size: 1200px 100% !important;
  animation: skel-shimmer 1.6s infinite linear !important;
  width: 60% !important;
}

/* Improvement group headers stay visible */
.imp-group h3 { color: #1e1a16 !important; background: transparent !important; animation: none !important; }

/* Progress message */
.skel-progress {
  text-align: center;
  margin-top: 24px;
  color: #6d645a;
  font-size: .9rem;
  font-weight: 600;
}
.skel-dot {
  display: inline-block;
  width: 6px; height: 6px;
  margin: 0 2px;
  background: #0e6b58;
  border-radius: 50%;
  animation: skel-dot-anim 1.2s infinite ease-in-out;
}
.skel-dot:nth-child(2) { animation-delay: .2s; }
.skel-dot:nth-child(3) { animation-delay: .4s; }
@keyframes skel-dot-anim {
  0%, 80%, 100% { transform: scale(.6); opacity: .4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
<script>
document.addEventListener('DOMContentLoaded', () => {
  const wrap = document.querySelector('.wrap');
  if (wrap) {
    const lang = document.documentElement.lang || 'en';
    const msg = lang === 'ko'
      ? '리뷰 생성 중 — 최대 1분 정도 걸릴 수 있습니다'
      : 'Generating review — this may take up to a minute';
    const div = document.createElement('div');
    div.className = 'skel-progress';
    div.innerHTML = msg + ' <span class="skel-dot"></span><span class="skel-dot"></span><span class="skel-dot"></span>';
    wrap.appendChild(div);
  }
});
</script>
"""
    html_str = html_str.replace("</head>", skeleton_css + "</head>")
    return html_str
