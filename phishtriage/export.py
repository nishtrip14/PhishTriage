"""JSON export of triage results.

Default ("summary") exports contain structure only: statuses, codes, counters, evidence IDs and types, playbook
IDs. They omit the email itself, attachments, secrets, case identifiers and any free text that could repeat email
content (finding statements, actions, reviewer details, excerpts). "detailed" exports add those model-written
texts and escaped excerpts of CITED evidence, and only when explicitly requested. Raw subject/body and attachment
content are never exported.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

EXPORT_VERSION = "1.0"
SUMMARY_OMITS = ["email subject and body", "attachment content and filenames", "case identifiers",
                 "finding statements", "recommended-action text and model rationale", "reviewer objection text",
                 "validation details", "evidence excerpts", "agent-listed missing information text"]


def _local(eid: str | None) -> str | None:
    """'case-abc/ev-003' -> 'ev-003': evidence IDs without the case identifier."""
    return eid.split("/")[-1] if eid else eid


def disagreement(report) -> bool:
    label = (report.classifier or {}).get("predicted_label")
    return ((label == "phishing" and report.assessment == "no_strong_indicators")
            or (label == "legitimate" and report.assessment == "suspicious"))


def report_export(report, trace, store=None, *, detailed: bool = False, attempt: dict | None = None,
                  run_info: dict | None = None) -> dict:
    r = report
    evidence = store.evidence(r.case_id) if store is not None and store.has(r.case_id) else {}
    c = r.classifier or {}
    out = {
        "export_version": EXPORT_VERSION, "export_kind": "detailed" if detailed else "summary",
        "attempt": {k: v for k, v in (attempt or {}).items() if k != "case_id"},
        "run": run_info or {},
        "mode": r.execution_mode, "mode_notice": r.mode_notice, "status": r.status,
        "termination_reason": r.termination_reason, "termination_detail": r.termination_detail,
        "provider": {"name": r.provider.get("name"), "model": r.provider.get("model"),
                     "sdk_version": r.provider.get("sdk_version"), "errors": r.provider.get("errors", [])},
        "classifier": {k: c.get(k) for k in ("status", "model_id", "predicted_label", "score", "score_type",
                                             "threshold")},
        "assessment": r.assessment, "assessment_classifier_disagreement": disagreement(r),
        "findings": [{"evidence_ids": [_local(e) for e in f["evidence_ids"]],
                      "evidence_types": [evidence[e].evidence_type for e in f["evidence_ids"] if e in evidence],
                      "has_valid_citation": f["has_valid_citation"],
                      "rejected_citation_count": len(f["rejected_citations"])} for f in r.findings],
        "playbook_refs": [{k: p[k] for k in ("doc_id", "version", "verified_retrieved", "label")}
                          for p in r.playbook_refs],
        "missing_information": [{"source": m["source"], "evidence_id": _local(m.get("evidence_id")),
                                 "evidence_type": evidence[m["evidence_id"]].evidence_type
                                 if m.get("evidence_id") in evidence else None} for m in r.missing_information],
        "recommended_action_count": len(r.recommended_actions),
        "recommended_action_ids": [f"{a['action_id']}@v{a['version']}" for a in r.recommended_actions],
        "action_note": r.action_note,
        "review": {"reviewer_status": r.review.get("reviewer_status"), "rounds": r.review.get("rounds"),
                   "unresolved_objection_types": [o.get("issue_type") for o in r.review.get("unresolved_objections", [])],
                   "validation_issue_codes": [i["code"] for i in r.review.get("validation_issues", [])]},
        "usage": {k: v for k, v in r.usage.items() if k != "budgets"}, "budgets": r.usage.get("budgets"),
        "trace": [{"step": t["step"], "kind": t["kind"], "name": t["name"], "status": t["status"], "ms": t["ms"],
                   "code": t["code"], "evidence_ids": [_local(e) for e in t["evidence_ids"]]} for t in trace],
        "limitations": list(r.limitations),
        "omitted": [] if detailed else SUMMARY_OMITS,
    }
    if detailed:
        out["findings_detail"] = [{"statement": f["statement"], "evidence_ids": [_local(e) for e in f["evidence_ids"]],
                                   "rejected_citations": [_local(e) for e in f["rejected_citations"]]}
                                  for f in r.findings]
        out["recommended_actions"] = r.recommended_actions
        out["playbook_reasons"] = [{"doc_id": p["doc_id"], "reason": p["reason"]} for p in r.playbook_refs]
        out["missing_information_detail"] = [m["item"] for m in r.missing_information]
        out["review_detail"] = {"unresolved_objections": r.review.get("unresolved_objections", []),
                                "validation_issues": r.review.get("validation_issues", [])}
        cited = {e for f in r.findings for e in f["evidence_ids"]}
        out["cited_evidence"] = [{"evidence_id": _local(e), "type": evidence[e].evidence_type,
                                  "status": evidence[e].status, "excerpt_html_escaped": evidence[e].excerpt}
                                 for e in sorted(cited) if e in evidence]
        out["detailed_export_warning"] = ("Contains model-written text and escaped excerpts that may repeat email "
                                          "content. Share only if that is appropriate.")
    return out


def verification_record(report, attempt: dict, run_info: dict) -> dict:
    """Compact record for SYNTHETIC verification runs (no email-derived text)."""
    return {"code_commit": run_info.get("code_commit"), "code_modified": run_info.get("code_modified"),
            "environment": run_info.get("environment"), "model": report.provider.get("model"),
            "sdk_version": report.provider.get("sdk_version"), "mode": report.execution_mode,
            "attempt_id": attempt.get("attempt_id"), "started_at_utc": attempt.get("started_at_utc"),
            "synthetic_case": attempt.get("synthetic_case"), "status": report.status,
            "termination_reason": report.termination_reason,
            "reviewer_status": report.review.get("reviewer_status"), "review_rounds": report.review.get("rounds"),
            "assessment": report.assessment, "classifier_label": (report.classifier or {}).get("predicted_label"),
            "counters": {k: report.usage.get(k) for k in ("model_requests", "tool_rounds", "tool_executions",
                                                          "rejected_tool_calls", "provider_retries", "retry_wait_s")},
            "elapsed_s": report.usage.get("elapsed_s"),
            "provider_errors": report.provider.get("errors", [])}


def write_json(obj: dict, directory: Path, name: str) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:80]
    path = directory / f"{safe}.json"
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")
    return path


LIVE_OUTCOMES = ("attempted", "approved", "needs_human_review", "failed", "skipped")


def live_outcome_counts(section_26_attempts: list[dict], interface_attempts: list) -> dict:
    """Count live cases by their ACTUAL report status, separately for section 26 batches and interface attempts.

    attempted = submitted to the live workflow; approved = report approved by the reviewer; failed includes failure
    reports and internal errors; skipped = never submitted (batch stopped on quota/auth/unavailable model).
    A returned failure report is never counted as a successful completion."""
    def blank():
        return {k: 0 for k in LIVE_OUTCOMES}

    def bucket(status):
        return status if status in ("approved", "needs_human_review") else "failed"

    s26 = blank()
    for attempt in section_26_attempts or []:
        for row in attempt.get("batch") or []:
            if row.get("batch_status") == "ran":
                s26["attempted"] += 1
                s26[bucket(row.get("report_status"))] += 1
            else:
                s26["skipped"] += 1
    ui = blank()
    for a in interface_attempts or []:
        if getattr(a, "mode", None) != "live":
            continue
        ui["attempted"] += 1
        ui[bucket(a.result.report.status if a.result is not None else None)] += 1
    return {"section_26": s26, "interface": ui, "total": {k: s26[k] + ui[k] for k in LIVE_OUTCOMES},
            "definitions": {"attempted": "submitted to the live workflow",
                            "approved": "report approved by the reviewer (not a guarantee of correctness)",
                            "needs_human_review": "report returned for human review (includes partial results)",
                            "failed": "failure report or internal error; never counted as completed",
                            "skipped": "not submitted because an earlier case stopped the batch"}}
