from __future__ import annotations

import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse, urlunparse


USER_AGENT = "Mozilla/5.0 QualityReviewAgent/0.1"
MAX_PAGES = 8
MAX_EXCERPT_CHARS = 2200


def get_registrable_domain(netloc: str) -> str:
    """Extract the base domain to allow subdomain matching (e.g. console.megacode.ai -> megacode.ai)."""
    host = netloc.split(":")[0]
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


@dataclass
class PageSnapshot:
    url: str
    title: str
    text: str
    links: list[str]
    nav_items: list[str]


class PageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.in_title = False
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self.nav_items: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "a":
            href = attrs_dict.get("href", "").strip()
            if href:
                full_url = urljoin(self.base_url, href)
                self.links.append(full_url)
                # Extract navigation context from icon-only links
                label = (
                    attrs_dict.get("aria-label", "")
                    or attrs_dict.get("title", "")
                ).strip()
                if label:
                    self.nav_items.append(f"[Link: {label} → {full_url}]")
                elif not attrs_dict.get("class", ""):
                    pass  # skip unlabeled links without useful info
                else:
                    # Infer purpose from URL for icon-only links
                    domain_hints = {
                        "github.com": "GitHub",
                        "twitter.com": "Twitter/X",
                        "x.com": "Twitter/X",
                        "discord.com": "Discord",
                        "discord.gg": "Discord",
                        "linkedin.com": "LinkedIn",
                        "youtube.com": "YouTube",
                    }
                    for domain, name in domain_hints.items():
                        if domain in full_url:
                            self.nav_items.append(f"[Icon link: {name} → {full_url}]")
                            break
        if tag == "img":
            alt = attrs_dict.get("alt", "").strip()
            if alt and self.skip_depth == 0:
                self.text_parts.append(f"[Image: {alt}]")
        if tag == "button":
            label = (
                attrs_dict.get("aria-label", "")
                or attrs_dict.get("title", "")
            ).strip()
            if label and self.skip_depth == 0:
                self.text_parts.append(f"[Button: {label}]")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth > 0:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip_depth > 0:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        else:
            self.text_parts.append(text)


def fetch_webpage_context(url: str) -> str:
    try:
        snapshots = crawl_same_domain(url, max_pages=MAX_PAGES)
    except Exception:
        return "- Failed to fetch live website content."
    if not snapshots:
        return "- Failed to fetch live website content."

    lines = [
        f"- Crawled pages: {len(snapshots)}",
        "- NOTE: This text was extracted from raw HTML without JavaScript execution. Dynamic content (counters, stats, API-loaded numbers) may show as 0 or empty. Ignore these values.",
    ]
    for index, snapshot in enumerate(snapshots, start=1):
        lines.extend(
            [
                f"- Page {index} URL: {snapshot.url}",
                f"- Page {index} title: {snapshot.title}",
                f"- Page {index} text excerpt: {snapshot.text[:MAX_EXCERPT_CHARS] if snapshot.text else 'No visible page text extracted.'}",
            ]
        )
        if snapshot.nav_items:
            lines.append(f"- Page {index} navigation/icon links: {' | '.join(snapshot.nav_items)}")
    return "\n".join(lines)


def crawl_same_domain(start_url: str, max_pages: int = 4) -> list[PageSnapshot]:
    parsed_start = urlparse(start_url)
    if parsed_start.scheme not in {"http", "https"} or not parsed_start.netloc:
        return []

    queue = [start_url]
    seen: set[str] = set()
    snapshots: list[PageSnapshot] = []

    while queue and len(snapshots) < max_pages:
        current = normalize_url(queue.pop(0))
        if not current or current in seen:
            continue
        seen.add(current)

        snapshot = fetch_page_snapshot(current)
        if not snapshot:
            continue
        snapshots.append(snapshot)

        for link in prioritize_links(snapshot.links, base_netloc=parsed_start.netloc):
            normalized = normalize_url(link)
            if not normalized or normalized in seen or normalized in queue:
                continue
            queue.append(normalized)
            if len(queue) + len(snapshots) >= max_pages * 3:
                break

    return snapshots


def fetch_page_snapshot(url: str) -> PageSnapshot | None:
    try:
        safe_url = prepare_request_url(url)
        if not safe_url:
            return None
        req = urllib.request.Request(safe_url, headers={"User-Agent": USER_AGENT}, method="GET")
        with urllib.request.urlopen(req, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return None
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ValueError, socket.timeout, UnicodeError):
        return None

    parser = PageParser(url)
    parser.feed(html)

    title = " ".join(parser.title_parts).strip() or "Untitled page"
    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    return PageSnapshot(
        url=url,
        title=title,
        text=text,
        links=parser.links,
        nav_items=parser.nav_items,
    )


def prioritize_links(links: list[str], base_netloc: str) -> list[str]:
    base_domain = get_registrable_domain(base_netloc)
    scored: list[tuple[int, str]] = []
    for link in links:
        link = sanitize_url_candidate(link)
        if not link:
            continue
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"}:
            continue
        # Allow same base domain (includes subdomains like console.megacode.ai)
        if get_registrable_domain(parsed.netloc) != base_domain:
            continue
        score = 100
        path = parsed.path.lower()
        # Lower score = higher priority (sorted ascending)
        if path in {"", "/"}:
            score -= 40
        # High-value pre-login pages that reveal the onboarding journey
        if any(token in path for token in ["login", "signin", "sign-in", "signup", "sign-up", "get-started", "start", "register"]):
            score -= 50
        if any(token in path for token in ["pricing", "product", "features", "about", "docs", "onboarding"]):
            score -= 25
        # Deprioritize boilerplate pages
        if any(token in path for token in ["privacy", "terms", "blog", "careers", "cookie"]):
            score += 30
        scored.append((score, link))

    scored.sort(key=lambda item: (item[0], item[1]))
    deduped: list[str] = []
    seen: set[str] = set()
    for _, link in scored:
        normalized = normalize_url(link)
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped


def normalize_url(url: str) -> str:
    url = sanitize_url_candidate(url)
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    cleaned = parsed._replace(fragment="", query="")
    normalized = cleaned.geturl()
    if normalized.endswith("/") and cleaned.path not in {"", "/"}:
        normalized = normalized[:-1]
    return normalized


def sanitize_url_candidate(url: str) -> str:
    cleaned = url.strip().strip("\"'`<>[](){}")
    cleaned = cleaned.lstrip("‘’“”")
    cleaned = cleaned.replace("\\", "/")
    if cleaned.startswith(("mailto:", "tel:", "javascript:", "#")):
        return ""
    return cleaned


def prepare_request_url(url: str) -> str:
    normalized = normalize_url(url)
    if not normalized:
        return ""

    parsed = urlparse(normalized)
    try:
        safe_path = quote(parsed.path or "/", safe="/:%+-._~")
        safe_query = quote(parsed.query, safe="=&:%+-._~")
        safe_fragment = ""
        return urlunparse((parsed.scheme, parsed.netloc.encode("idna").decode("ascii"), safe_path, "", safe_query, safe_fragment))
    except Exception:
        return ""
