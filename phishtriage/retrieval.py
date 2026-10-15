"""Local playbook retrieval: a TF-IDF/cosine index fitted only on the example playbooks.

It never touches the classifier's vectorizer. Scores are retrieval relevance between a query and a playbook
section, not a probability that an email is phishing.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from .email_input import escape_excerpt
from .schemas import RetrievalHit

PLAYBOOK_PATH = Path(__file__).resolve().parent / "playbooks" / "example_playbooks.json"
SECTIONS = ("situation", "observations", "benign_alternatives", "next_steps", "limitations")
RELEVANCE_TYPE = "tfidf_cosine_retrieval_relevance"
MIN_RELEVANCE = 0.10        # fixed before running the retrieval check set; below this, report "no relevant match"
MAX_QUERY_CHARS = 1_000
DEFAULT_TOP_K = 3


def load_playbooks(path: Path = PLAYBOOK_PATH) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [p["doc_id"] for p in doc["playbooks"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate playbook doc_id")
    for p in doc["playbooks"]:
        missing = {"doc_id", "version", "title", *SECTIONS} - set(p)
        if missing:
            raise ValueError(f"{p.get('doc_id')}: missing fields {sorted(missing)}")
    return doc


def chunk_playbooks(doc: dict) -> list[dict]:
    chunks = []
    for p in doc["playbooks"]:
        for section in SECTIONS:
            body = p[section] if isinstance(p[section], str) else "; ".join(p[section])
            chunks.append({"doc_id": p["doc_id"], "chunk_id": f"{p['doc_id']}#{section}", "title": p["title"],
                           "version": p["version"], "section": section, "text": f"{p['title']}. {body}",
                           "source_ref": f"phishtriage/playbooks/{PLAYBOOK_PATH.name}#{p['doc_id']}/{section} "
                                         f"(collection v{doc['collection_version']})"})
    return chunks


class PlaybookIndex:
    def __init__(self, doc: dict | None = None):
        self.doc = doc or load_playbooks()
        self.label = self.doc["label"]
        self.chunks = chunk_playbooks(self.doc)
        self.vectorizer = TfidfVectorizer(lowercase=True, stop_words="english", ngram_range=(1, 2),
                                          sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform([c["text"] for c in self.chunks])

    def search(self, query: str, top_k: int = DEFAULT_TOP_K, min_relevance: float = MIN_RELEVANCE) -> dict:
        """Returns {"status": ok|empty_query|no_relevant_match, "hits": [...], "notes": [...]}.

        At most one hit (its best section) per playbook; weak matches are dropped, not forced."""
        query = (query or "").strip()
        notes = [f"Relevance is {RELEVANCE_TYPE}, not a probability of phishing.", self.label]
        if not query:
            return {"status": "empty_query", "hits": [], "notes": notes}
        if len(query) > MAX_QUERY_CHARS:
            query = query[:MAX_QUERY_CHARS]
            notes.append(f"query truncated to {MAX_QUERY_CHARS} characters")
        q = self.vectorizer.transform([query])
        if q.nnz == 0:
            return {"status": "no_relevant_match", "hits": [], "notes": notes + ["no query terms occur in any playbook"]}
        scores = linear_kernel(q, self.matrix).ravel()
        best = {}
        for i in np.argsort(-scores, kind="stable"):
            c = self.chunks[i]
            if scores[i] >= min_relevance and c["doc_id"] not in best:
                best[c["doc_id"]] = (float(scores[i]), c)
        hits = [RetrievalHit(doc_id=c["doc_id"], chunk_id=c["chunk_id"], title=c["title"], version=c["version"],
                             section=c["section"], excerpt=escape_excerpt(c["text"], 400), relevance=round(s, 4),
                             relevance_type=RELEVANCE_TYPE, source_ref=c["source_ref"])
                for s, c in list(best.values())[:max(1, min(top_k, 5))]]
        if not hits:
            return {"status": "no_relevant_match", "hits": [],
                    "notes": notes + [f"best relevance {scores.max():.3f} < threshold {min_relevance}"]}
        return {"status": "ok", "hits": hits, "notes": notes}


CHECKS_PATH = Path(__file__).resolve().parent / "playbooks" / "retrieval_checks.json"


def run_retrieval_checks(index: PlaybookIndex, path: Path = CHECKS_PATH) -> dict:
    """Score the predeclared check set: top-1 / top-3 hits for answerable queries, correct abstention otherwise."""
    checks = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = []
    for c in checks["checks"]:
        res = index.search(c["query"])
        got = [h.doc_id for h in res["hits"]]
        if c["expected"]:
            passed_top1, passed_top3 = bool(got) and got[0] in c["expected"], any(g in c["expected"] for g in got[:3])
        else:
            passed_top1 = passed_top3 = res["status"] == c.get("expected_status", "no_relevant_match")
        rows.append({"id": c["id"], "query": c["query"], "expected": c["expected"],
                     "expected_status": c.get("expected_status"), "status": res["status"], "returned": got,
                     "top_relevance": res["hits"][0].relevance if res["hits"] else None,
                     "pass_top1": passed_top1, "pass_top3": passed_top3})
    answerable = [r for r in rows if r["expected"]]
    abstain = [r for r in rows if not r["expected"]]
    return {"check_set_version": checks["version"], "min_relevance": MIN_RELEVANCE, "n_checks": len(rows),
            "answerable": len(answerable), "top1_hits": sum(r["pass_top1"] for r in answerable),
            "top3_hits": sum(r["pass_top3"] for r in answerable),
            "abstention_checks": len(abstain), "correct_abstentions": sum(r["pass_top1"] for r in abstain),
            "rows": rows}
