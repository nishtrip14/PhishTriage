"""Backoff, retry delays, deadlines, request reservation and sanitized diagnostics (offline, fake clock)."""
import random

import pytest

from phishtriage import agent as A, agent_model as AM, agent_replays as AR
from phishtriage.agent_model import ProviderError, ScriptedAdapter, call, calls, text


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.t += seconds

    waits: list


def clock():
    c = FakeClock()
    c.waits = []
    return c


def good_draft(req):
    return text(AR.draft("insufficient_evidence", [AR.finding("Sender information is unavailable for pasted text.",
                                                              AR.evidence_ids(req, "sender_address"))], []))


def run(tools, steps, c=None, case="case-ambiguous", **cfg):
    c = c or clock()
    adapter = ScriptedAdapter(steps)
    res = A.run_triage(tools, case, mode="replay", adapter=adapter, config=A.AgentConfig(**cfg),
                       clock=c, sleep=c.sleep, rng=random.Random(1))
    return res, adapter, c


# ---------------------------------------------------------------- classification and diagnostics

def test_quota_classification_needs_explicit_diagnostics():
    per_minute = {"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "12s"}]}}
    per_day = {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                                      "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}]}]}}
    e = AM.classify_api_error(429, "RESOURCE_EXHAUSTED", per_minute)
    assert (e.kind, e.quota_category, e.retry_delay_s, e.retryable) == ("quota", "rate_limit", 12.0, True)
    e = AM.classify_api_error(429, "RESOURCE_EXHAUSTED", per_day)
    assert (e.quota_category, e.retryable) == ("daily", False)
    e = AM.classify_api_error(429, None, {"error": {"code": "quota_exceeded"}})
    assert e.quota_category == "daily" and not e.retryable
    e = AM.classify_api_error(429, "RESOURCE_EXHAUSTED", {"error": {"message": "Resource exhausted"}})
    assert (e.quota_category, e.retryable) == ("unclassified", False)        # conservative stop
    assert AM.classify_api_error(503, "UNAVAILABLE", {}).retryable
    assert AM.classify_api_error(404, "NOT_FOUND", {}).kind == "model_unavailable"


def test_diagnostics_are_sanitized():
    key = "AIza" + "k" * 35
    e = AM.classify_api_error(429, "RESOURCE_EXHAUSTED", {"error": {}},
                              f"Quota exceeded for projects/987654321 consumer 123456789012 key {key}")
    text_out = e.detail + repr(e.diagnostics())
    assert key not in text_out and "987654321" not in text_out and "123456789012" not in text_out
    assert set(e.diagnostics()) == {"http_status", "category", "provider_status", "quota_category", "retry_delay_s"}


# ---------------------------------------------------------------- backoff and deadlines

def test_server_errors_back_off_with_bounded_jitter(demo_tools):
    steps = [ProviderError("server", "503"), ProviderError("server", "503"),
             calls(call("inspect_email")), text("READY"), good_draft, AR.approve()]
    res, _, c = run(demo_tools, steps)
    assert res.report.status == "approved" and res.report.usage["provider_retries"] == 2
    assert len(c.waits) == 2 and 1.0 <= c.waits[0] <= 2.0 and 2.0 <= c.waits[1] <= 4.0   # base 2s, doubling
    assert res.report.usage["retry_wait_s"] == pytest.approx(sum(c.waits), abs=0.01)
    assert [t["kind"] for t in res.trace].count("retry_wait") == 2


def test_provider_retry_delay_is_honoured_for_rate_limits_only(demo_tools):
    rate = ProviderError("quota", "429", http_status=429, quota_category="rate_limit", retry_delay_s=7.0)
    res, _, c = run(demo_tools, [rate, calls(call("inspect_email")), text("READY"), good_draft, AR.approve()])
    assert res.report.status == "approved" and 7.0 <= c.waits[0] <= 8.0
    daily = ProviderError("quota", "429", http_status=429, quota_category="daily", retry_delay_s=7.0)
    res, adapter, c = run(demo_tools, [daily, text("never used")])
    assert res.report.termination_reason == "provider_quota" and c.waits == [] and len(adapter.requests) == 1


def test_long_provider_delay_is_honoured_in_full_when_the_budget_allows(demo_tools):
    slow = ProviderError("server", "503", retry_delay_s=30.0)
    res, adapter, c = run(demo_tools, [slow, calls(call("inspect_email")), text("READY"), good_draft, AR.approve()])
    assert len(c.waits) == 1 and c.waits[0] >= 30.0            # never shortened; jitter only adds time
    assert res.report.status == "approved" and res.report.usage["provider_retries"] == 1


def test_provider_delay_that_does_not_fit_is_not_retried_early(demo_tools):
    # 90 s deadline: waiting 75 s would leave < 20 s reserve + 2 s window, so there is no retry at all (not a
    # shorter wait); investigation ends and the case finishes as a partial result.
    slow = ProviderError("server", "503", retry_delay_s=75.0)
    res, adapter, c = run(demo_tools, [slow, good_draft, AR.approve()])
    assert c.waits == [] and [q.kind for q in adapter.requests][:3] == ["investigate", "finalize", "review"]
    assert any(t["kind"] == "budget_reserve" and "deadline" in t["code"] for t in res.trace)
    assert res.report.status == "needs_human_review"           # nothing gathered: no valid citation


def test_optional_wait_cap_is_respected_when_configured(demo_tools):
    slow = ProviderError("server", "503", retry_delay_s=30.0)
    res, adapter, c = run(demo_tools, [slow, good_draft, AR.approve()], max_retry_wait_s=10.0)
    assert c.waits == [] and any("configured wait cap" in (t["code"] or "") for t in res.trace)


def test_retry_wait_cannot_overrun_the_deadline(demo_tools):
    c = clock()
    c.t = 0.0
    slow = ProviderError("server", "503", retry_delay_s=15.0)
    # 16s left, a 15s+ provider delay would leave < 2s for the retried request: not retried. During
    # investigation that ends investigation (nothing gathered yet -> finalize still runs if time allows).
    adapter = ScriptedAdapter([slow, text("never used")])
    res = A.run_triage(demo_tools, "case-ambiguous", mode="replay", adapter=adapter, clock=c, sleep=c.sleep,
                       rng=random.Random(1), config=A.AgentConfig(deadline_s=16.0, finish_reserve_s=0.0))
    assert c.waits == [] and any(t["kind"] == "budget_reserve" and "deadline" in t["code"] for t in res.trace)


def test_investigation_stops_to_reserve_time_for_finishing(demo_tools):
    c = clock()

    def slow_round(req):
        c.t += 35.0                                  # each investigation request takes 35 simulated seconds
        return calls(call("inspect_email")) if not req.history[1:] else calls(call("get_prediction"))
    res, adapter, c = run(demo_tools, [slow_round, slow_round, good_draft, AR.approve()], c=c)
    kinds = [r.kind for r in adapter.requests]
    assert kinds == ["investigate", "investigate", "finalize", "review"]   # 20s left < 20s reserve + 2s window
    assert any(t["kind"] == "budget_reserve" for t in res.trace) and res.report.status == "approved"


def test_retries_respect_the_request_reservation(demo_tools):
    # inspect ok (1); error (2) + retry ok (3); error (4): a retry would leave fewer than finalize + review, so
    # investigation ends and the case still finishes with the evidence gathered (5 finalize, 6 review).
    steps = [calls(call("inspect_email")), ProviderError("server", "503"), calls(call("get_prediction")),
             ProviderError("server", "503"), good_draft, AR.approve()]
    res, adapter, c = run(demo_tools, steps)
    r = res.report
    assert [q.kind for q in adapter.requests] == ["investigate"] * 4 + ["finalize", "review"]
    assert r.status == "approved" and r.usage["provider_retries"] == 1 and r.usage["model_requests"] == 6
    assert any(t["kind"] == "budget_reserve" and "not retried" in t["code"] for t in res.trace)


def test_errors_after_investigation_still_abort_honestly(demo_tools):
    steps = [calls(call("inspect_email")), text("READY"), ProviderError("auth", "401"), text("never used")]
    res, adapter, c = run(demo_tools, steps)
    assert res.report.termination_reason == "provider_auth" and res.report.status == "failed" and c.waits == []
