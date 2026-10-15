"""Typed, JSON-serialisable records shared by evidence extraction, retrieval and the agent-ready tools.

Status vocabulary for evidence:
  observed          - present in the submitted input and read by a local, offline check
  unverified_claim  - present in the input but asserted by a party we cannot verify (e.g. Authentication-Results)
  unavailable       - the information is absent from this input; absence is NOT evidence of safety
  error             - a check failed; it never turns into a successful result
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

EvidenceStatus = Literal["observed", "unverified_claim", "unavailable", "error"]
ToolStatus = Literal["ok", "unavailable", "error", "rejected"]
EVIDENCE_STATUSES = ("observed", "unverified_claim", "unavailable", "error")
TOOL_STATUSES = ("ok", "unavailable", "error", "rejected")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Record:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AttachmentMeta(Record):
    """Metadata only. Attachment content is never opened, executed or extracted."""
    filename: str | None
    content_type: str
    size_bytes: int
    sha256: str | None


@dataclass(frozen=True)
class CaseInput(Record):
    """What the user submitted. There is deliberately no label field: ground truth never enters a case."""
    case_id: str
    input_kind: Literal["pasted", "eml"]
    subject: str
    body: str                                   # plain text; HTML is converted to text, never rendered
    headers: dict[str, list[str]] = field(default_factory=dict)   # bounded, selected headers (.eml only)
    attachments: tuple[AttachmentMeta, ...] = ()
    html_links: tuple[tuple[str, str], ...] = ()                   # (visible text, href) pairs from HTML parts
    parse_warnings: tuple[str, ...] = ()
    received_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class EmailObservation(Record):
    """Summary of what local, offline inspection found in one case."""
    case_id: str
    input_kind: str
    subject_excerpt: str
    body_chars: int
    truncated: bool
    from_address: str | None
    reply_to_addresses: tuple[str, ...]
    urls: tuple[str, ...]
    attachment_count: int
    html_present: bool
    warnings: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceItem(Record):
    evidence_id: str
    case_id: str
    evidence_type: str
    source: str                   # where it came from, e.g. "header:Reply-To", "body", "classifier"
    status: EvidenceStatus
    value: Any                    # small structured value (JSON-serialisable)
    excerpt: str                  # bounded, HTML-escaped excerpt of untrusted input ("" if none)
    observed_at: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self):
        if self.status not in EVIDENCE_STATUSES:
            raise ValueError(f"invalid evidence status {self.status!r}")


@dataclass(frozen=True)
class RetrievalHit(Record):
    doc_id: str
    chunk_id: str
    title: str
    version: str
    section: str
    excerpt: str
    relevance: float              # TF-IDF cosine similarity between query and chunk
    relevance_type: str           # always "tfidf_cosine_retrieval_relevance" - not a phishing probability
    source_ref: str


@dataclass(frozen=True)
class ToolResult(Record):
    tool: str
    status: ToolStatus
    data: Any = None
    error: str | None = None
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    truncated_output: bool = False

    def __post_init__(self):
        if self.status not in TOOL_STATUSES:
            raise ValueError(f"invalid tool status {self.status!r}")
        if self.status == "ok" and self.error:
            raise ValueError("an ok result cannot carry an error")
        if self.status != "ok" and not self.error:
            raise ValueError("a non-ok result must explain itself in `error`")
