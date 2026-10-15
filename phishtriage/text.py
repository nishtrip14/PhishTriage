"""Text preparation shared by training and inference: length policy, artifact normalization, redaction.

Every function here is label-independent: it sees only text, never a source or label.
"""
from __future__ import annotations

import re

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

PREPROCESSING_VERSION = "2.0"   # bump whenever any rule below changes; stored in model manifests
ARTIFACT_RULES_VERSION = "1.0"

# Input-length policy. Chosen from train/dev inspection: 99.5% of included texts are shorter. The longest are
# a 4.6M-char spam-filter log dump (phishing) and encoded binary/long digests (legitimate). Longer inputs keep
# their first MAX_INPUT_CHARS characters and are always flagged as truncated.
MAX_INPUT_CHARS = 20_000

VARIANTS = ("original", "artifact_normalized")


def combine(subject: str | None = "", body: str | None = "") -> str:
    """Same combination as phase 1: stripped subject, blank line, stripped body."""
    def clean(x):
        return "" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x).strip()
    return (clean(subject) + "\n\n" + clean(body)).strip()


def apply_length_policy(text: str, max_chars: int = MAX_INPUT_CHARS) -> tuple[str, bool]:
    return (text[:max_chars], True) if len(text) > max_chars else (text, False)


# --------------------------------------------------------------------------- artifact normalization
# Rules come from the documented collection artifacts (docs/DATASET_CARD.md) and from inspecting frequent lines in
# train+dev only. They apply identically to every text. They remove source cues; they cannot recover link
# targets that the dataset curators already stripped from the phishing bodies.

_FOOTER_LINE = re.compile(
    r"mailing list|listinfo|unsubscribe|list maintainer|mailman|sponsored by|yahoo! groups|egroups\.com"
    r"|you (?:have )?received this message because you subscribed|change your preferences"
    r"|^\s*date:\s*not supplied\s*$", re.I)
_SEPARATOR_LINE = re.compile(r"^[\W_]{3,}$")                     # ----, ____, ---|---|---, =====
_LIST_TAG = re.compile(r"^(\s*(?:(?:re|fwd?|aw)\s*:\s*)*)\[[^\]\n]{1,40}\]\s*", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|ftp://|www\.)\S+", re.I)
_DOMAIN = re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com|org|net|edu|gov|mil|int|info|biz|io|co|us|uk|ie|de|fr|nl|au|ca"
                     r"|ru|cn|jp)\b", re.I)
_COLLECTION_TERMS = re.compile(r"\b(?:jose|monkey|spamassassin|sourceforge|sf\.net)\b", re.I)
_YEAR = re.compile(r"\b(?:19[89]\d|20[0-2]\d)\b")
_SPACES = re.compile(r"[ \t\r\f\v]+")

ARTIFACT_RULES = [
    "drop lines containing mailing-list footer phrases (listinfo, unsubscribe, mailman, list maintainer, "
    "sponsored by, Yahoo! Groups, egroups, subscription notices, 'date: not supplied')",
    "drop separator lines made only of punctuation",
    "drop a bracketed list tag at the start of a line, e.g. '[ILUG]' (keeps a 'Re:' prefix)",
    "remove email addresses",
    "remove visible URLs (http/https/ftp/www)",
    "remove bare domain names with common TLDs",
    "remove collection-identifying terms: jose, monkey, spamassassin, sourceforge, sf.net",
    "remove four-digit years 1980-2029",
]


def normalize_artifacts(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        if _FOOTER_LINE.search(line) or _SEPARATOR_LINE.match(line.strip()):
            continue
        lines.append(_LIST_TAG.sub(r"\1", line))
    t = "\n".join(lines)
    for pattern in (_EMAIL, _URL, _DOMAIN, _COLLECTION_TERMS, _YEAR):
        t = pattern.sub(" ", t)
    t = "\n".join(_SPACES.sub(" ", ln).strip() for ln in t.split("\n"))
    return re.sub(r"\n{2,}", "\n", t).strip()


def prepare(text: str, variant: str) -> tuple[str, dict]:
    """Length policy, then (optionally) artifact normalization. Returns (prepared text, info)."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {VARIANTS}")
    text = "" if text is None else str(text)
    clipped, truncated = apply_length_policy(text)
    prepared = normalize_artifacts(clipped) if variant == "artifact_normalized" else clipped
    return prepared, {"input_chars": len(text), "truncated": truncated, "prepared_chars": len(prepared)}


class TextPreprocessor(BaseEstimator, TransformerMixin):
    """Stateless pipeline step so training and inference apply exactly the same preparation."""

    def __init__(self, variant: str = "original"):
        self.variant = variant

    def fit(self, X, y=None):
        if self.variant not in VARIANTS:
            raise ValueError(f"unknown variant {self.variant!r}")
        return self

    def transform(self, X):
        return [prepare(x, self.variant)[0] for x in X]


# --------------------------------------------------------------------------- display redaction

REDACTIONS = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL]"),
    (re.compile(r"(?:https?://|www\.)\S+", re.I), "[URL]"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "[IP]"),
    (re.compile(r"\+?\d[\d ().-]{7,}\d"), "[NUMBER]"),
    # Names in reply attributions ("Jane Doe wrote:", '"J" == Jane writes:') and forwarded headers.
    (re.compile(r"(?:\"\w+\"\s*==\s*)?(?:[A-Z][\w.'-]*\s+){0,3}[A-Z][\w.'-]*\s+(?=(?:wrote|writes)\b)"), "[NAME] "),
    (re.compile(r"\b(From|To|Cc):\s*.*?(?=\s+(?:From|To|Cc|Sent|Date|Subject):|$)"), r"\1: [REDACTED]"),
]


def sanitize(t: str, limit: int = 160) -> str:
    """Heuristic redaction for display only. A person must still review outputs before publishing."""
    t = re.sub(r"\s+", " ", t).strip()
    for pattern, token in REDACTIONS:
        t = pattern.sub(token, t)
    return t[:limit] + ("…" if len(t) > limit else "")
