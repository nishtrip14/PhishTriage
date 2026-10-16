"""Local, offline observations about one case, recorded as typed EvidenceItems.

These observations are separate from the text classifier. The classifier was trained on text whose URLs and
headers were stripped, so URL/header/attachment observations here are NOT covered by its held-out test score.
"""
from __future__ import annotations

import ipaddress
import re
from email.utils import getaddresses, parseaddr
from urllib.parse import urlsplit

from .email_input import escape_excerpt
from .schemas import CaseInput, EmailObservation, EvidenceItem, utc_now
from .text import MAX_INPUT_CHARS, combine

MAX_URLS = 50
MAX_EVIDENCE_PER_CASE = 200
MAX_CASES = 100

_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>\"'()\[\]{}]+", re.I)
_TRAILING = ".,;:!?)]}>'\""
_DOMAINISH = re.compile(r"^(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)(?:[/:?#]|$)", re.I)
_AUTH_TOKEN = re.compile(r"\b(spf|dkim|dmarc|arc)\s*=\s*([a-z]+)", re.I)

NOT_SAFETY = "Absence of this information is not evidence that the email is safe."
HEADER_LIMIT = "Header content is controlled by the sender or relays and is not authenticated by this tool."
AUTH_LIMIT = ("Authentication-Results text can be added or forged by any sender or relay. It was not verified, "
              "and historical SPF/DKIM/DMARC outcomes cannot be reconstructed from current DNS.")
URL_LIMIT = ("Static string inspection only: the URL was not visited, resolved or reputation-checked. "
             "The text classifier was not trained on URLs.")
KEYWORD_LIMIT = "Simple keyword match; not a validated detector. Legitimate mail can use the same words."

CUES = {
    "credential_request_language": r"\b(?:password|passcode|verify (?:your )?(?:account|identity|login)|sign[ -]?in|"
                                   r"log[ -]?in|re-?activate|mailbox (?:is )?(?:full|quota)|account (?:will be )?"
                                   r"(?:suspended|locked|deactivated))\b",
    "payment_change_language": r"\b(?:bank (?:details|account)|account number|iban|swift|wire transfer|"
                               r"remittance|invoice|payment details|new account)\b",
    "urgency_language": r"\b(?:urgent|immediately|within \d+ ?hours|expires? (?:today|soon)|final notice|"
                        r"act now|asap)\b",
    "attachment_lure_language": r"\b(?:see (?:the )?attached|open the attach\w*|attached (?:invoice|document|file))\b",
    "instruction_like_text": r"(?:ignore (?:all |any )?(?:previous|prior|above) instructions|system prompt|"
                             r"you are (?:an? )?(?:ai|assistant|language model)|disregard (?:the )?(?:rules|policy)|"
                             r"classify this (?:email|message) as|mark (?:this|the) (?:email|message) as (?:safe|legitimate))",
}
INSTRUCTION_LIMIT = ("Email content is untrusted data. Instruction-like phrases are reported as evidence and are "
                     "never followed by the tools.")


def _domain(address: str | None) -> str | None:
    if not address or "@" not in address:
        return None
    return address.rsplit("@", 1)[1].strip().strip(">").lower() or None


def extract_urls(text: str, hrefs=()) -> list[str]:
    """URLs written in the text or present as link targets. String extraction only; no network access."""
    seen, out = set(), []
    for raw in [m.group(0) for m in _URL.finditer(text or "")] + [h for h in hrefs if h]:
        url = raw.strip().rstrip(_TRAILING)
        if not re.match(r"(?i)^(?:https?://|www\.)", url) or url.lower() in seen:
            continue
        seen.add(url.lower())
        out.append(url[:2000])
        if len(out) >= MAX_URLS:
            break
    return out


def _safe_host(url: str) -> str | None:
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def describe_url(url: str) -> dict:
    try:
        parsed = urlsplit(url if re.match(r"(?i)^https?://", url) else "http://" + url)
    except ValueError:          # e.g. unbalanced IPv6 brackets in hostile input
        return {"url": url[:300], "parse_error": True}
    host = (parsed.hostname or "").lower()
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    try:
        port = parsed.port
    except ValueError:          # malformed port in hostile input
        port = "invalid"
    return {"url": url[:300], "scheme": parsed.scheme.lower() if re.match(r"(?i)^https?://", url) else None,
            "host": host[:253], "host_is_ip_literal": is_ip, "punycode_host": "xn--" in host,
            "userinfo_in_url": "@" in (parsed.netloc or ""), "explicit_port": port,
            "uses_plain_http": url.lower().startswith("http://"), "path_length": len(parsed.path or "")}


def _addresses(headers: dict, name: str) -> list[tuple[str, str]]:
    values = headers.get(name, [])
    try:
        return [(n, a.lower()) for n, a in getaddresses(values) if a]
    except Exception:
        return []


class EvidenceBuilder:
    def __init__(self, case: CaseInput):
        self.case, self.items = case, []

    def add(self, evidence_type, source, status, value, excerpt="", limitations=()):
        n = len(self.items) + 1
        if n > MAX_EVIDENCE_PER_CASE:
            return None
        item = EvidenceItem(evidence_id=f"{self.case.case_id}/ev-{n:03d}", case_id=self.case.case_id,
                            evidence_type=evidence_type, source=source, status=status, value=value,
                            excerpt=excerpt, observed_at=utc_now(), limitations=tuple(limitations))
        self.items.append(item)
        return item


def observe(case: CaseInput) -> tuple[EmailObservation, list[EvidenceItem]]:
    b = EvidenceBuilder(case)
    text = combine(case.subject, case.body)

    b.add("subject", "subject", "observed" if case.subject.strip() else "unavailable",
          {"chars": len(case.subject)}, escape_excerpt(case.subject, 200),
          () if case.subject.strip() else ("No subject present.",))
    b.add("body_excerpt", "body", "observed" if case.body.strip() else "unavailable",
          {"chars": len(case.body), "classifier_truncation": len(text) > MAX_INPUT_CHARS},
          escape_excerpt(case.body, 300),
          (f"The classifier scores only the first {MAX_INPUT_CHARS:,} characters.",) if len(text) > MAX_INPUT_CHARS else ())

    # ---- sender identity (headers) ----
    from_addr, reply_to = None, []
    if case.input_kind == "pasted":
        for kind in ("sender_address", "reply_to", "authentication_results", "attachments"):
            b.add(kind, "input", "unavailable", None, "", ("Pasted input has no headers or attachments.", NOT_SAFETY))
    else:
        froms = _addresses(case.headers, "From")
        if froms:
            name, from_addr = froms[0]
            b.add("sender_address", "header:From", "observed", {"address": from_addr, "domain": _domain(from_addr),
                  "display_name": name[:200]}, escape_excerpt(case.headers["From"][0], 200), (HEADER_LIMIT,))
            shown = parseaddr(name)[1] if "@" in name else None
            if shown and shown.lower() != from_addr:
                b.add("display_name_address_mismatch", "header:From", "observed",
                      {"display_name_address": shown.lower(), "actual_address": from_addr}, "",
                      (HEADER_LIMIT, "Mailing lists and forwarding services can produce this legitimately."))
        else:
            b.add("sender_address", "header:From", "observed_absent",
                  {"scope": "headers of the supplied .eml: no parseable From header"}, "", (HEADER_LIMIT, NOT_SAFETY))
        reply_to = [a for _, a in _addresses(case.headers, "Reply-To")]
        if reply_to:
            b.add("reply_to", "header:Reply-To", "observed", {"addresses": reply_to[:5],
                  "domains": sorted({_domain(a) for a in reply_to if _domain(a)})},
                  escape_excerpt(case.headers["Reply-To"][0], 200), (HEADER_LIMIT,))
            fd = _domain(from_addr)
            mismatched = sorted({_domain(a) for a in reply_to if _domain(a) and _domain(a) != fd})
            if fd and mismatched:
                b.add("sender_reply_to_mismatch", "header:From+Reply-To", "observed",
                      {"from_domain": fd, "reply_to_domains": mismatched}, "",
                      (HEADER_LIMIT, "Help desks, ticketing systems and mailing lists set Reply-To legitimately."))
        else:
            b.add("reply_to", "header:Reply-To", "observed_absent",
                  {"scope": "headers of the supplied .eml: no Reply-To header"}, "", (HEADER_LIMIT,))
        for name in ("Return-Path", "Sender"):
            addrs = _addresses(case.headers, name)
            if addrs:
                b.add(name.lower().replace("-", "_"), f"header:{name}", "observed",
                      {"address": addrs[0][1], "domain": _domain(addrs[0][1])},
                      escape_excerpt(case.headers[name][0], 200), (HEADER_LIMIT,))

        claims = case.headers.get("Authentication-Results", []) + case.headers.get("ARC-Authentication-Results", [])
        if claims:
            parsed = []
            for raw in claims:
                tokens = {k.lower(): v.lower() for k, v in _AUTH_TOKEN.findall(raw)}
                parsed.append(tokens)
                b.add("authentication_results_claim", "header:Authentication-Results", "unverified_claim",
                      {"claimed_results": tokens}, escape_excerpt(raw, 200), (AUTH_LIMIT,))
            for mech in ("spf", "dkim", "dmarc"):
                outcomes = sorted({p[mech] for p in parsed if mech in p})
                if len(outcomes) > 1:
                    b.add("conflicting_authentication_claims", "header:Authentication-Results", "unverified_claim",
                          {"mechanism": mech, "claimed_outcomes": outcomes}, "", (AUTH_LIMIT,))
        else:
            b.add("authentication_results", "header:Authentication-Results", "observed_absent",
                  {"scope": "headers of the supplied .eml: no Authentication-Results header"}, "",
                  ("Many relays do not add this header; its absence says nothing about the sender.", NOT_SAFETY))

        if case.attachments:
            for att in case.attachments:
                b.add("attachment", "mime", "observed", att.to_dict(), escape_excerpt(att.filename or "", 120),
                      ("Metadata only: the attachment was not opened, scanned, executed or extracted.",
                       "Content-Type and filename are sender-declared."))
        else:
            part_limited = any("MIME parts" in w or "attachments recorded" in w for w in case.parse_warnings)
            b.add("attachments", "mime", "observed_absent",
                  {"count": 0, "scope": "attachment parts among the MIME parts inspected in the supplied .eml"
                                        + (" (part limit reached: later parts not inspected)" if part_limited else "")},
                  "", ("Only the supplied .eml was inspected.", NOT_SAFETY))

    # ---- URLs (static) ----
    urls = extract_urls(text, [h for _, h in case.html_links])
    for url in urls:
        b.add("url", "body" if url in text else "html:href", "observed", describe_url(url), escape_excerpt(url, 200),
              (URL_LIMIT,))
    if not urls:
        scope = "URL text in the subject and body as provided" + (" and HTML link targets" if case.html_links else "")
        if any("truncated" in w for w in case.parse_warnings):
            scope += " (input was truncated; the rest was not inspected)"
        b.add("urls", "body", "observed_absent", {"count": 0, "scope": scope}, "",
              ("Links may still exist in content that was not provided.", NOT_SAFETY))
    for anchor, href in case.html_links:
        shown = _DOMAINISH.match(anchor.strip())
        target = _safe_host(href) if re.match(r"(?i)^https?://", href or "") else None
        if shown and target and shown.group(1).lower().removeprefix("www.") != target.lower().removeprefix("www."):
            b.add("link_text_target_mismatch", "html:a", "observed",
                  {"visible_domain": shown.group(1).lower(), "target_host": target.lower()},
                  escape_excerpt(anchor, 120), (URL_LIMIT, "Tracking and redirect services also cause this."))

    # ---- simple, explainable language cues ----
    matched = []
    for cue, pattern in CUES.items():
        hits = sorted({m.group(0).lower() for m in re.finditer(pattern, text, re.I)})[:10]
        if hits:
            matched.append(cue)
            b.add(cue, "subject+body", "observed", {"matched_phrases": hits}, "",
                  (INSTRUCTION_LIMIT if cue == "instruction_like_text" else KEYWORD_LIMIT,))
    # One record of what the keyword scan covered, so "no credential request wording" can be cited precisely.
    b.add("cue_scan", "subject+body", "observed",
          {"checked": list(CUES), "matched": matched, "not_matched": [c for c in CUES if c not in matched],
           "scope": "fixed keyword patterns over the subject and body text as provided"}, "",
          (KEYWORD_LIMIT, "A pattern not matching does not mean the email lacks that intent."))

    for w in case.parse_warnings:
        b.add("parse_warning", "parser", "observed", {"warning": w[:300]}, "", ())

    obs = EmailObservation(
        case_id=case.case_id, input_kind=case.input_kind, subject_excerpt=escape_excerpt(case.subject, 200),
        body_chars=len(case.body), truncated=len(text) > MAX_INPUT_CHARS, from_address=from_addr,
        reply_to_addresses=tuple(reply_to[:5]), urls=tuple(u[:300] for u in urls),
        attachment_count=len(case.attachments), html_present=bool(case.html_links) or any(
            "HTML" in w for w in case.parse_warnings),
        warnings=case.parse_warnings, evidence_ids=tuple(i.evidence_id for i in b.items))
    return obs, b.items


class CaseStore:
    """In-memory, per-runtime store. Evidence is only ever looked up within its own case."""

    def __init__(self, max_cases: int = MAX_CASES):
        self.max_cases, self._cases = max_cases, {}

    def add(self, case: CaseInput) -> EmailObservation:
        if case.case_id in self._cases:
            raise ValueError(f"case {case.case_id} already exists")
        if len(self._cases) >= self.max_cases:
            raise ValueError(f"case limit ({self.max_cases}) reached")
        obs, items = observe(case)
        self._cases[case.case_id] = {"case": case, "observation": obs, "evidence": {i.evidence_id: i for i in items}}
        return obs

    def has(self, case_id: str) -> bool:
        return case_id in self._cases

    def case(self, case_id: str) -> CaseInput:
        return self._cases[case_id]["case"]

    def observation(self, case_id: str) -> EmailObservation:
        return self._cases[case_id]["observation"]

    def evidence(self, case_id: str) -> dict[str, EvidenceItem]:
        return self._cases[case_id]["evidence"]

    def add_evidence(self, case_id: str, evidence_type: str, source: str, status: str, value, limitations=()):
        items = self._cases[case_id]["evidence"]
        if len(items) >= MAX_EVIDENCE_PER_CASE:
            raise ValueError("evidence limit reached for this case")
        item = EvidenceItem(evidence_id=f"{case_id}/ev-{len(items) + 1:03d}", case_id=case_id,
                            evidence_type=evidence_type, source=source, status=status, value=value, excerpt="",
                            observed_at=utc_now(), limitations=tuple(limitations))
        items[item.evidence_id] = item
        return item
