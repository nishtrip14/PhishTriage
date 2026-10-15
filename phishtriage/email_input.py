"""Safe, bounded email input: pasted subject/body or a raw .eml file.

Never fetches URLs, loads remote images, renders HTML, opens/executes attachments or extracts archives.
HTML parts are converted to plain text with the standard-library parser; scripts and styles are dropped.
"""
from __future__ import annotations

import hashlib
import html
import re
import uuid
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser

from .schemas import AttachmentMeta, CaseInput

MAX_EML_BYTES = 2_000_000          # reject larger raw messages outright
MAX_MIME_PARTS = 50                # stop walking after this many parts
MAX_ATTACHMENTS = 20
MAX_BODY_CHARS = 200_000           # stored body text; the classifier applies its own 20,000-char policy
MAX_SUBJECT_CHARS = 1_000
MAX_HEADER_VALUES = 5              # per header name
MAX_HEADER_CHARS = 1_000           # per header value
MAX_LINKS = 100
KEPT_HEADERS = ("From", "Reply-To", "Return-Path", "Sender", "To", "Date", "Message-ID", "Authentication-Results",
                "ARC-Authentication-Results", "Received-SPF", "DKIM-Signature", "Content-Type")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class EmailInputError(ValueError):
    """The input cannot be accepted (too large, empty, or not parseable at all)."""


def new_case_id() -> str:
    return f"case-{uuid.uuid4().hex[:12]}"


def clean_text(s: str) -> str:
    return _CONTROL.sub("", s or "")


def escape_excerpt(s: str, limit: int = 300) -> str:
    """Bounded excerpt of untrusted text, whitespace-collapsed and HTML-escaped for safe display."""
    s = re.sub(r"\s+", " ", clean_text(s)).strip()
    clipped = s[:limit] + ("…" if len(s) > limit else "")
    return html.escape(clipped, quote=True)


class _TextAndLinks(HTMLParser):
    """Extract visible text and (anchor text, href) pairs; ignore script/style; never resolves anything."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self._skip, self._href, self._anchor = [], [], 0, None, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1
        elif tag == "a":
            self._href, self._anchor = dict(attrs).get("href"), []
        elif tag in ("br", "p", "div", "tr", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self._skip:
            self._skip -= 1
        elif tag == "a" and self._href is not None:
            if len(self.links) < MAX_LINKS:
                self.links.append((" ".join("".join(self._anchor).split())[:200], self._href[:2000]))
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._href is not None:
            self._anchor.append(data)


def html_to_text(markup: str) -> tuple[str, list[tuple[str, str]]]:
    p = _TextAndLinks()
    p.feed(markup)
    p.close()
    text = re.sub(r"[ \t]+", " ", "".join(p.parts))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip(), p.links


def from_pasted(subject: str | None, body: str | None, case_id: str | None = None) -> CaseInput:
    subject, body = clean_text(subject or ""), clean_text(body or "")
    warnings = []
    if not subject.strip() and not body.strip():
        raise EmailInputError("Empty input: provide a subject and/or body.")
    if len(subject) > MAX_SUBJECT_CHARS:
        subject, warnings = subject[:MAX_SUBJECT_CHARS], warnings + [f"subject truncated to {MAX_SUBJECT_CHARS} chars"]
    if len(body) > MAX_BODY_CHARS:
        warnings.append(f"body truncated to {MAX_BODY_CHARS:,} of {len(body):,} chars")
        body = body[:MAX_BODY_CHARS]
    warnings.append("pasted input: no headers, sender identity, authentication results or attachments available")
    return CaseInput(case_id=case_id or new_case_id(), input_kind="pasted", subject=subject, body=body,
                     parse_warnings=tuple(warnings))


def parse_eml(raw: bytes, case_id: str | None = None) -> CaseInput:
    if not isinstance(raw, (bytes, bytearray)):
        raise EmailInputError("parse_eml expects bytes")
    if len(raw) == 0:
        raise EmailInputError("Empty .eml input")
    if len(raw) > MAX_EML_BYTES:
        raise EmailInputError(f".eml is {len(raw):,} bytes; the limit is {MAX_EML_BYTES:,}")
    try:
        msg = BytesParser(policy=policy.default).parsebytes(bytes(raw))
    except Exception as e:  # the stdlib parser is lenient; anything raised here is a hard failure
        raise EmailInputError(f"Could not parse .eml: {type(e).__name__}") from e

    warnings = [f"parser defect: {type(d).__name__}" for d in msg.defects][:10]
    headers = {}
    for name in KEPT_HEADERS:
        try:
            values = msg.get_all(name) or []
        except Exception as e:
            warnings.append(f"header {name} unreadable: {type(e).__name__}")
            continue
        if values:
            headers[name] = [clean_text(str(v))[:MAX_HEADER_CHARS] for v in values[:MAX_HEADER_VALUES]]
            if len(values) > MAX_HEADER_VALUES:
                warnings.append(f"only the first {MAX_HEADER_VALUES} {name} headers kept")
    if not headers:
        warnings.append("no recognised headers found; input may not be an email")

    plain, html_texts, links, attachments, n_parts = [], [], [], [], 0
    for part in msg.walk():
        n_parts += 1
        if n_parts > MAX_MIME_PARTS:
            warnings.append(f"stopped after {MAX_MIME_PARTS} MIME parts")
            break
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        if disposition == "attachment" or (filename and disposition != "inline") or not ctype.startswith("text/"):
            if len(attachments) >= MAX_ATTACHMENTS:
                warnings.append(f"only the first {MAX_ATTACHMENTS} attachments recorded")
                continue
            try:
                payload = part.get_payload(decode=True) or b""    # bytes only; never opened or executed
                attachments.append(AttachmentMeta(clean_text(filename)[:200] if filename else None, ctype,
                                                  len(payload), hashlib.sha256(payload).hexdigest()))
            except Exception as e:
                warnings.append(f"attachment metadata unreadable: {type(e).__name__}")
            continue
        try:
            content = part.get_content()
        except Exception as e:
            warnings.append(f"text part ({ctype}) undecodable: {type(e).__name__}")
            continue
        if ctype == "text/html":
            text, part_links = html_to_text(content)
            html_texts.append(text)
            links.extend(part_links)
        else:
            plain.append(content)

    body = "\n\n".join(plain) if plain else "\n\n".join(html_texts)
    if not plain and html_texts:
        warnings.append("body taken from HTML converted to text (not rendered)")
    body = clean_text(body)
    if len(body) > MAX_BODY_CHARS:
        warnings.append(f"body truncated to {MAX_BODY_CHARS:,} of {len(body):,} chars")
        body = body[:MAX_BODY_CHARS]
    subject = clean_text(str(msg.get("Subject", "") or ""))[:MAX_SUBJECT_CHARS]
    if not subject.strip() and not body.strip():
        warnings.append("message has neither subject nor body text")
    return CaseInput(case_id=case_id or new_case_id(), input_kind="eml", subject=subject, body=body,
                     headers=headers, attachments=tuple(attachments), html_links=tuple(links[:MAX_LINKS]),
                     parse_warnings=tuple(warnings))
