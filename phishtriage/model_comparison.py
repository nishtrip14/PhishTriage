"""Bounded, opt-in live comparison of a few Gemini models on the synthetic demo cases.

Not a benchmarking framework: it reuses the preflight, the Gemini adapter, `run_triage` and its budgets unchanged.
What it adds is a global request ledger that every candidate shares, so the whole comparison cannot exceed a fixed
number of generation requests (SDK retries are refused, not merely discouraged), a wall-clock limit, a fixed
order (one case across all eligible models, then the next case), and stop rules for authentication and quota.
Records hold counts, statuses and the model's report text for SYNTHETIC cases only; never keys or email bodies.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .agent_model import ProviderError

# Terminations that describe the account rather than one model or case: the whole comparison stops.
STOP_ALL_TERMINATIONS = {"provider_quota", "provider_auth"}
STOP_ALL_PREFLIGHT = {"auth_error", "quota_exceeded"}


class RequestLedger:
    """Counts every provider call made through `BudgetedClient`. Generation requests are capped globally."""

    def __init__(self, max_generation: int, max_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.max_generation, self.max_seconds, self.clock = max_generation, max_seconds, clock
        self.generation = self.metadata = self.refused = 0
        self.t0 = clock()

    def remaining_generation(self) -> int:
        return self.max_generation - self.generation

    def remaining_seconds(self) -> float:
        return self.max_seconds - (self.clock() - self.t0)

    def charge_generation(self):
        if self.generation >= self.max_generation:
            self.refused += 1
            raise ProviderError("invalid_request", "comparison generation budget exhausted (request not sent)")
        self.generation += 1


def _retry_attempts(http_options) -> int | None:
    ro = getattr(http_options, "retry_options", None) if http_options is not None else None
    return getattr(ro, "attempts", None) if ro is not None else None


class _BudgetedModels:
    def __init__(self, models, ledger: RequestLedger, client_attempts: int | None):
        self._models, self._ledger, self._client_attempts = models, ledger, client_attempts

    def generate_content(self, *, model, contents, config=None):
        per_request = _retry_attempts(getattr(config, "http_options", None))
        attempts = per_request if per_request is not None else self._client_attempts
        if attempts != 1:          # an SDK retry would be an uncounted request: refuse instead of sending
            self._ledger.refused += 1
            raise ProviderError("invalid_request", f"SDK retries must be off in the comparison (attempts={attempts})")
        self._ledger.charge_generation()
        return self._models.generate_content(model=model, contents=contents, config=config)

    def get(self, *, model, **kw):
        self._ledger.metadata += 1
        return self._models.get(model=model, **kw)


class BudgetedClient:
    """Wraps a google-genai Client: generation goes through the ledger; metadata calls are counted."""

    def __init__(self, client, ledger: RequestLedger, client_attempts: int | None):
        self.models = _BudgetedModels(client.models, ledger, client_attempts)


def budgeted_client_factory(ledger: RequestLedger, make_client=None):
    """A `client_factory` for `llm_preflight.preflight` and a client for `GeminiAdapter`, with SDK retries off."""
    def factory(api_key=None, http_options=None):
        from google import genai
        from google.genai import types
        opts = types.HttpOptions(timeout=getattr(http_options, "timeout", None) or 30_000,
                                 retry_options=types.HttpRetryOptions(attempts=1))
        return BudgetedClient((make_client or genai.Client)(api_key=api_key, http_options=opts), ledger, 1)
    return factory


@dataclass
class ComparisonPlan:
    """Frozen before any live call. Order matters: each case runs across all eligible models before the next."""
    candidates: list[str]
    cases: list[str]
    max_generation: int = 39
    max_seconds: float = 900.0
    pause_between_cases_s: float = 5.0
    frozen_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def attempt_record(name: str, model: str, attempt_id: str, result, started_utc: str) -> dict:
    """Sanitized per-attempt record. Report text is the model's output about a SYNTHETIC case."""
    r, trace = result.report, result.trace
    model_steps = [t for t in trace if t["kind"] == "model_request"]
    tool_steps = [t for t in trace if t["kind"] == "tool_call"]
    u = r.usage
    return {
        "attempt_id": attempt_id, "started_at_utc": started_utc, "model": model,
        "sdk_version": r.provider.get("sdk_version"), "synthetic_case": name,
        "status": r.status, "termination_reason": r.termination_reason,
        "termination_detail": r.termination_detail[:200],
        "requests": {"model_requests": u["model_requests"], "ok": sum(t["status"] == "ok" for t in model_steps),
                     "errors": [e.get("http_status") for e in r.provider.get("errors", [])],
                     "retries": u["provider_retries"], "retry_wait_s": u["retry_wait_s"],
                     "abnormal_finish": [t["code"] for t in model_steps if "finish " in str(t.get("code"))]},
        "tools": {"calls": [{"name": t["name"], "status": t["status"], "code": t.get("code")} for t in tool_steps],
                  "executions": u["tool_executions"], "rejected": u["rejected_tool_calls"], "rounds": u["tool_rounds"]},
        "finalize_completed": any(t["name"] in ("finalize", "revise") and t["status"] == "ok" for t in model_steps),
        "review_completed": any(t["name"] == "review" and t["status"] == "ok" for t in model_steps),
        "reviewer_status": r.review.get("reviewer_status"), "review_rounds": r.review.get("rounds"),
        "validation_issues": [{"code": i.get("code"), "severity": i.get("severity")}
                              for i in r.review.get("validation_issues", [])],
        "unresolved_objections": [o.get("issue_type") for o in r.review.get("unresolved_objections", [])],
        "tokens": {k: u.get(k, 0) for k in ("prompt_tokens", "output_tokens", "thought_tokens")},
        "elapsed_s": u["elapsed_s"],
        "classifier": {k: (r.classifier or {}).get(k) for k in ("predicted_label", "score", "threshold")},
        "assessment": r.assessment,
        "report": {"findings": r.findings, "playbook_refs": r.playbook_refs,
                   "missing_information": r.missing_information, "recommended_actions": r.recommended_actions},
    }


def run_comparison(plan: ComparisonPlan, *, tools, add_case: Callable[[str, str], None], ledger: RequestLedger,
                   preflight_fn: Callable[[str], dict], adapter_fn: Callable[[str, dict], object],
                   run_case: Callable[[str, object, dict], object],
                   sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> dict:
    """Run the frozen plan sequentially. Dependencies are injected so the control flow is testable offline.

    preflight_fn(model) -> preflight dict (one generation request, no retries)
    adapter_fn(model, preflight) -> adapter
    run_case(case_id, adapter, preflight) -> AgentResult
    """
    out = {"plan": {**plan.__dict__}, "preflights": {}, "attempts": [], "skipped": [], "stopped": None}
    eligible = []
    for model in plan.candidates:
        if out["stopped"]:
            out["skipped"].append({"model": model, "what": "preflight", "reason": out["stopped"]})
            continue
        if ledger.remaining_generation() < 1 or ledger.remaining_seconds() <= 0:
            out["skipped"].append({"model": model, "what": "preflight", "reason": "comparison budget exhausted"})
            continue
        pf = preflight_fn(model)
        out["preflights"][model] = pf
        log(f"preflight {model}: {pf.get('status')}")
        if pf.get("status") == "ok":
            eligible.append(model)
        elif pf.get("status") in STOP_ALL_PREFLIGHT:
            out["stopped"] = f"preflight {pf.get('status')} on {model}: comparison stopped (no model rotation)"
    adapters = {m: adapter_fn(m, out["preflights"][m]) for m in eligible}
    dead: set[str] = set()
    n = 0
    for case in plan.cases:
        for model in eligible:
            n += 1
            attempt_id = f"cmp-{n:02d}"
            reason = (out["stopped"] or ("model unavailable earlier" if model in dead else None)
                      or ("generation budget cannot cover a full case" if ledger.remaining_generation() < 6 else None)
                      or ("time limit would be exceeded" if ledger.remaining_seconds() < 100 else None))
            if reason:
                out["skipped"].append({"model": model, "what": case, "attempt_id": attempt_id, "reason": reason})
                continue
            case_id = f"{attempt_id}-{case}"
            add_case(case, case_id)
            started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            result = run_case(case_id, adapters[model], out["preflights"][model])
            rec = attempt_record(case, model, attempt_id, result, started)
            out["attempts"].append(rec)
            log(f"{attempt_id} {model} {case}: {rec['status']} / {rec['termination_reason']} "
                f"({rec['requests']['model_requests']} requests)")
            term = rec["termination_reason"]
            if term in STOP_ALL_TERMINATIONS:
                out["stopped"] = f"{term} on {model} ({attempt_id}): comparison stopped (no model rotation)"
            elif term == "provider_model_unavailable":
                dead.add(model)
            sleep(plan.pause_between_cases_s)
    out["ledger"] = {"generation_requests": ledger.generation, "metadata_requests": ledger.metadata,
                     "refused_by_ledger": ledger.refused, "max_generation": ledger.max_generation,
                     "elapsed_s": round(ledger.clock() - ledger.t0, 1)}
    return out
