"""Quota handling at two levels, offline.

A. Orchestration: the REAL run_triage with the REAL GeminiAdapter over a fake SDK client that returns HTTP 429.
   This exercises error mapping, retry policy, budgets and termination together.
B. Batch control: run_batch_triage with run_triage stubbed. This tests only iteration and stopping; it says
   nothing about run_triage's internal retry behaviour (that is what A is for).
All emails are synthetic; network access is blocked.
"""
import tempfile
from pathlib import Path

import numpy as np
import pytest

from phishtriage import agent as A, agent_model as AM, agent_replays as AR, inference as I, llm_preflight as P
from phishtriage import models as M, retrieval as R, tools as T
from phishtriage.evidence import CaseStore

types = pytest.importorskip("google.genai.types")
errors = pytest.importorskip("google.genai.errors")

PHISH = ["verify your account password now or it will be suspended", "urgent confirm billing details today"] * 5
LEGIT = ["minutes from the weekly team meeting", "lunch on friday let me know"] * 5
MODEL = "gemini-test-model"


def no_sleep(seconds):
    pass
PASSED = {"status": "ok", "model": MODEL}


@pytest.fixture(scope="module")
def artifact():
    frozen = {"model_id": "tfidf_logreg__artifact_normalized", "kind": "tfidf_logreg",
              "variant": "artifact_normalized", "params": {"C": 1.0}, "threshold": 0.5,
              "threshold_rule": "synthetic", "selection_metric": "synthetic"}
    pipe = M.build_pipeline("tfidf_logreg", "artifact_normalized", frozen["params"])
    pipe.fit(PHISH + LEGIT, np.array([1] * 10 + [0] * 10))
    return I.load_artifact(I.save_artifact(pipe, frozen, Path(tempfile.mkdtemp()), dataset={}, results={},
                                           environment="test"))


@pytest.fixture
def tools(artifact):
    store = CaseStore()
    for name in AR.DEMO_CASES:
        store.add(AR.build_demo_case(name, f"case-{name}"))
    return T.TriageTools(store, model=artifact[0], manifest=artifact[1], index=R.PlaybookIndex())


class FakeModels:
    """Stands in for client.models: replays a list of outcomes (responses or exceptions) and counts calls."""

    def __init__(self, outcomes):
        self.outcomes, self.calls, self.violations = list(outcomes), 0, []

    def generate_content(self, model, contents, config):
        self.calls += 1
        if config.http_options.retry_options.attempts != 1:
            self.violations.append("SDK-level retries enabled")
        if not self.outcomes:
            # Recorded, not raised: the adapter would turn an exception into a provider error and hide it.
            self.violations.append("provider called after the run should have stopped")
            raise RuntimeError("no scripted outcome")
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def quota_error():
    return errors.APIError(429, {"error": {"code": 429, "message": "Resource has been exhausted (synthetic)",
                                           "status": "RESOURCE_EXHAUSTED"}})


def function_call_response(name):
    content = types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(id="c1", name=name, args={}))])
    return types.GenerateContentResponse(candidates=[types.Candidate(content=content)])


def live_adapter(outcomes):
    models = FakeModels(outcomes)
    return AM.GeminiAdapter(MODEL, api_key=None, client=type("Client", (), {"models": models})()), models


# ---------------------------------------------------------------- A. real orchestration

def test_quota_on_first_request_stops_the_case_without_retry(tools, no_network):
    adapter, models = live_adapter([quota_error(), function_call_response("inspect_email")])
    result = A.run_triage(tools, "case-credential_link", mode="live", adapter=adapter, preflight=PASSED,
                          sleep=no_sleep)
    r = result.report
    assert models.calls == 1 and models.violations == []                                  # no hidden or loop-level retry
    assert r.usage["model_requests"] == 1 and r.usage["provider_retries"] == 0
    assert r.status == "failed" and r.termination_reason == "provider_quota"
    assert "429" in r.termination_detail
    assert r.assessment is None and r.findings == [] and r.recommended_actions == []    # nothing fabricated
    assert r.classifier["status"] == "ok"                     # trusted classifier result still reported
    requests = [t for t in result.trace if t["kind"] == "model_request"]
    assert len(requests) == 1 and requests[0]["status"] == "error" and requests[0]["code"] == "quota/unclassified"
    assert r.provider["errors"] == [{"request": "investigate", "http_status": 429, "category": "quota",
                                     "provider_status": "RESOURCE_EXHAUSTED", "quota_category": "unclassified",
                                     "retry_delay_s": None}]


def test_quota_mid_investigation_keeps_evidence_and_makes_no_further_calls(tools, no_network):
    adapter, models = live_adapter([function_call_response("inspect_email"), quota_error(),
                                    function_call_response("get_prediction")])
    result = A.run_triage(tools, "case-credential_link", mode="live", adapter=adapter, preflight=PASSED,
                          sleep=no_sleep)
    r = result.report
    assert models.calls == 2 and len(models.outcomes) == 1 and models.violations == []   # the third outcome was never requested
    assert r.usage["model_requests"] == 2 and r.usage["provider_retries"] == 0
    assert r.usage["tool_executions"] == 1 and r.termination_reason == "provider_quota" and r.status == "failed"
    executed = [t for t in result.trace if t["kind"] == "tool_call"]
    assert [t["name"] for t in executed] == ["inspect_email"] and executed[0]["status"] == "ok"


def test_transient_server_errors_are_retried_within_the_run_limit(tools, no_network):
    server = errors.APIError(503, {"error": {"code": 503, "message": "unavailable (synthetic)"}})
    adapter, models = live_adapter([server, server, server])
    waits = []
    r = A.run_triage(tools, "case-ambiguous", mode="live", adapter=adapter, preflight=PASSED,
                     sleep=waits.append).report
    assert models.calls == 3 and models.violations == [] and len(waits) == 2
    assert r.usage["provider_retries"] == 2 and r.termination_reason == "provider_server"


def test_live_mode_still_requires_a_passed_preflight_for_the_same_model(tools, no_network):
    adapter, models = live_adapter([function_call_response("inspect_email")])
    for preflight in (None, {"status": "skipped_opt_in_required", "model": MODEL},
                      {"status": "quota_exceeded", "model": MODEL}, {"status": "ok", "model": "another-model"}):
        r = A.run_triage(tools, "case-ambiguous", mode="live", adapter=adapter, preflight=preflight, sleep=no_sleep).report
        assert r.termination_reason == "preflight_not_passed" and "section 21" in r.termination_detail
    assert models.calls == 0


def test_preflight_reports_quota_without_retrying(no_network):
    class Models:
        def __init__(self):
            self.generate_calls = 0
        def get(self, model):
            return type("Info", (), {"supported_actions": ["generateContent"]})()
        def generate_content(self, model, config, contents):
            self.generate_calls += 1
            raise quota_error()
    models = Models()
    seen = {}
    def factory(api_key, http_options):
        seen["retry_codes"] = http_options.retry_options.http_status_codes
        return type("Client", (), {"models": models})()
    r = P.preflight(enable_network=True, api_key="synthetic-key-not-real", model=MODEL, client_factory=factory)
    assert r["status"] == "quota_exceeded" and "quota" in r["error"].lower()
    assert models.generate_calls == 1 and 429 not in seen["retry_codes"]
    assert r["checks"][-1]["retryable"] is False


# ---------------------------------------------------------------- B. batch control (run_triage stubbed)

def fake_result(case_id, termination, status="approved"):
    report = A.TriageReport(case_id=case_id, execution_mode="live", mode_notice="stub", status=status,
                            termination_reason=termination, classifier=None, assessment=None, assessment_note="",
                            findings=[], playbook_refs=[], missing_information=[], recommended_actions=[],
                            review={}, limitations=[], usage={}, provider={})
    return A.AgentResult(report=report, trace=[])


def test_batch_stops_submitting_after_quota(monkeypatch):
    submitted = []
    outcomes = {"c1": ("approved", "approved"), "c2": ("provider_quota", "failed")}
    def stub(tools, case_id, **kwargs):
        submitted.append(case_id)
        termination, status = outcomes[case_id]
        return fake_result(case_id, termination, status)
    monkeypatch.setattr(A, "run_triage", stub)
    batch = A.run_batch_triage(tools=None, case_ids=["c1", "c2", "c3", "c4"], mode="live")
    assert submitted == ["c1", "c2"]                                     # later cases never submitted
    assert [e.status for e in batch.entries] == ["ran", "ran", "skipped_due_to_quota", "skipped_due_to_quota"]
    assert batch.stopped_early and batch.stop_reason == "provider_quota"
    assert batch.entries[0].report.status == "approved"                  # earlier result intact
    assert batch.entries[1].report.termination_reason == "provider_quota"
    assert batch.entries[2].report is None and batch.entries[2].result is None   # no fabricated report
    assert "provider_quota" in batch.entries[3].skip_reason
    assert [row["batch_status"] for row in batch.summary()] == [e.status for e in batch.entries]


def test_batch_continues_after_case_level_failures(monkeypatch):
    submitted = []
    def stub(tools, case_id, **kwargs):
        submitted.append(case_id)
        return fake_result(case_id, "review_unresolved" if case_id == "c1" else "approved",
                           "needs_human_review" if case_id == "c1" else "approved")
    monkeypatch.setattr(A, "run_triage", stub)
    batch = A.run_batch_triage(tools=None, case_ids=["c1", "c2"], mode="live")
    assert submitted == ["c1", "c2"] and not batch.stopped_early


def test_batch_with_real_runs_and_a_quota_adapter(tools, no_network):
    """Integration (not stubbed): one shared live adapter; the quota on case 1 stops the rest."""
    adapter, models = live_adapter([quota_error()])
    names = ["case-credential_link", "case-ambiguous", "case-benign_notification"]
    batch = A.run_batch_triage(tools, names, mode="live", adapter=adapter, preflight=PASSED, sleep=no_sleep)
    assert models.calls == 1 and models.violations == []
    assert [e.status for e in batch.entries] == ["ran", "skipped_due_to_quota", "skipped_due_to_quota"]
    assert batch.entries[0].report.termination_reason == "provider_quota"
