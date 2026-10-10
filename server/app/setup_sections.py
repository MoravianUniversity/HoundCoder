"""Load and render markdown setup sections for the post-login success page."""
from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass

import markdown

from . import settings
from .nginx_config import get_base_url

SECTIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "setup-sections")

_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_DOWNLOAD_FENCE_RE = re.compile(
    r"^```([^\n]*?)\bdownload=([^\s`]+)([^\n]*)\n(.*?)(?<!`)```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


@dataclass
class SetupSection:
    title: str
    html: str


def apply_placeholders(text: str, placeholders: dict[str, str]) -> str:
    for key, value in placeholders.items():
        text = text.replace(f"<{key}>", value)
    return text


def build_placeholders(*, api_key: str) -> dict[str, str]:
    return {
        "SERVER_BASE_URL": get_base_url(),
        "YOUR_API_KEY": api_key,
        "SERVICE_NAME": settings.service_name(),
    }


def _download_widget(filename: str, content: str, language: str) -> str:
    safe_name = html.escape(filename, quote=True)
    lang_class = f' class="language-{html.escape(language)}"' if language else ""
    escaped_content = html.escape(content)
    return (
        f'<div class="downloadable">'
        f'<div class="downloadable-bar">'
        f'<span class="downloadable-name">{html.escape(filename)}</span>'
        f'<button type="button" class="button download-btn" '
        f'data-filename="{safe_name}">Download</button>'
        f"</div>"
        f"<details>"
        f"<summary>Preview</summary>"
        f"<pre><code{lang_class}>{escaped_content}</code></pre>"
        f"</details>"
        f"</div>"
    )


def _language_from_info(info: str) -> str:
    for part in info.split():
        if part.startswith("download="):
            continue
        return part
    return ""


def render_section_body(body: str) -> str:
    """Render markdown body, turning download= fences into download widgets."""
    replacements: list[str] = []

    def _replace_fence(match: re.Match[str]) -> str:
        info_before = match.group(1)
        filename = match.group(2)
        info_after = match.group(3)
        content = match.group(4)
        if content.endswith("\n"):
            content = content[:-1]
        language = _language_from_info(f"{info_before} {info_after}".strip())
        token = f"\n\nDOWNLOADABLEBLOCK{len(replacements)}END\n\n"
        replacements.append(_download_widget(filename, content, language))
        return token

    prepared = _DOWNLOAD_FENCE_RE.sub(_replace_fence, body)
    rendered = markdown.markdown(
        prepared,
        extensions=["fenced_code", "tables", "nl2br"],
    )
    for i, widget in enumerate(replacements):
        rendered = rendered.replace(f"<p>DOWNLOADABLEBLOCK{i}END</p>", widget)
        rendered = rendered.replace(f"DOWNLOADABLEBLOCK{i}END", widget)
    return rendered


def load_sections(placeholders: dict[str, str]) -> list[SetupSection]:
    if not os.path.isdir(SECTIONS_DIR):
        return []

    sections: list[SetupSection] = []
    for name in sorted(os.listdir(SECTIONS_DIR)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(SECTIONS_DIR, name)
        with open(path, encoding="utf-8") as f:
            raw = f.read()

        raw = apply_placeholders(raw, placeholders)
        heading = _HEADING_RE.search(raw)
        if heading:
            title = heading.group(1).strip()
            body = raw[heading.end() :].lstrip("\n")
        else:
            title = os.path.splitext(name)[0]
            body = raw

        sections.append(SetupSection(title=title, html=render_section_body(body)))
    return sections
