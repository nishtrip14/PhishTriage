"""Bounded model comparison: the global request ledger, SDK-retry refusal, plan order and stop rules (offline)."""
import tempfile
from pathlib import Path

import numpy as np
import pytest

from phishtriage import agent as A, agent_model as AM, agent_replays as AR, inference as I, llm_preflight as P
from phishtriage import model_comparison as C, models as M, retrieval as R, tools as T
from phishtriage.agent_model import ProviderError
from phishtriage.evidence import CaseStore

types = pytest.importorskip("google.genai.types")


class FakeModels:
    def __init__(self, outcomes=()):
        self.outcomes, self.calls, self.gets = list(outcomes), 0, 0

    def generate_content(self, model, contents, config=None):
        self.calls += 1
        out = self.outcomes.pop(0) if self.outcomes else function_call("inspect_email")
        if isinstance(out, Exception):
            raise out
        return out

    def get(self, model):
        self.gets += 1
        return type("Info", (), {"supported_actions": ["generateContent"]})()


def function_call(name, args=None):
    content = types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(id="c1", name=name,
                                                                                            args=args or {}))])
    return types.GenerateContentResponse(candidates=[types.Candidate(content=content)])


def single_attempt_config():
    return types.GenerateContentConfig(http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))


def test_ledger_caps_generation_and_counts_metadata(no_network):
    ledger, fake = C.RequestLedger(max_generation=2, max_seconds=60), FakeModels()
    client = C.BudgetedClient(type("Client", (), {"models": fake})(), ledger, client_attempts=1)
    client.models.get(model="m")
    for _ in range(2):
        client.models.generate_content(model="m", contents="x", config=single_attempt_config())
    with pytest.raises(ProviderError):
        client.models.generate_content(model="m", contents="x", config=single_attempt_config())
    assert fake.calls == 2 and ledger.generation == 2 and ledger.metadata == 1 and ledger.refused == 1


def test_budgeted_client_keeps_the_sdk_client_alive(no_network):
    import gc, weakref

    class Client:
        def __init__(self):
            self.models = FakeModels()
    inner = Client()
    ref = weakref.ref(inner)
    wrapped = C.BudgetedClient(inner, C.RequestLedger(1, 60), client_attempts=1)
    del inner
    gc.collect()
    assert ref() is not None and wrapped.models is not None


def test_ledger_refuses_sdk_retries(no_network):
    ledger, fake = C.RequestLedger(max_generation=5, max_seconds=60), FakeModels()
    retrying = types.GenerateContentConfig(http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=3)))
    for client_attempts, config in ((1, retrying), (None, None)):
        client = C.BudgetedClient(type("Client", (), {"models": fake})(), ledger, client_attempts)
        with pytest.raises(ProviderError):
            client.models.generate_content(model="m", contents="x", config=config)
    assert fake.calls == 0 and ledger.generation == 0 and ledger.refused == 2


def test_preflight_through_the_ledger_is_one_generation_request(no_network):
    ledger, fake = C.RequestLedger(max_generation=5, max_seconds=60), FakeModels([function_call(
        "record_check", {"token": P.EXPECTED_TOKEN})])
    factory = C.budgeted_client_factory(ledger, make_client=lambda **kw: type("Client", (), {"models": fake})())
    r = P.preflight(enable_network=True, api_key="synthetic-key-not-real", model="gemini-test",
                    client_factory=factory, max_attempts=1)
    assert r["status"] == "ok" and ledger.generation == 1 and ledger.metadata == 1


PHISH = ["verify your account password now or it will be suspended", "urgent confirm billing details today"] * 5
LEGIT = ["minutes from the weekly team meeting", "lunch on friday let me know"] * 5


@pytest.fixture(scope="module")
def tools():
    frozen = {"model_id": "tfidf_logreg__artifact_normalized", "kind": "tfidf_logreg",
              "variant": "artifact_normalized", "params": {"C": 1.0}, "threshold": 0.5,
              "threshold_rule": "synthetic", "selection_metric": "synthetic"}
    pipe = M.build_pipeline("tfidf_logreg", "artifact_normalized", frozen["params"])
    pipe.fit(PHISH + LEGIT, np.array([1] * 10 + [0] * 10))
    model, manifest = I.load_artifact(I.save_artifact(pipe, frozen, Path(tempfile.mkdtemp()), dataset={},
                                                      results={}, environment="test"))
    store = CaseStore()
    store.add(AR.build_demo_case("credential_link", "case-credential_link"))
    return T.TriageTools(store, model=model, manifest=manifest, index=R.PlaybookIndex())


def test_exhausted_ledger_ends_a_live_case_without_sending(tools, no_network):
    ledger, fake = C.RequestLedger(max_generation=1, max_seconds=60), FakeModels()
    client = C.BudgetedClient(type("Client", (), {"models": fake})(), ledger, client_attempts=1)
    adapter = AM.GeminiAdapter("gemini-test", api_key=None, client=client)
    result = A.run_triage(tools, "case-credential_link", mode="live", adapter=adapter,
                          preflight={"status": "ok", "model": "gemini-test"}, sleep=lambda s: None)
    assert fake.calls == 1 and ledger.refused >= 1                 # the refused request never reached the provider
    assert result.report.status != "approved"


def test_thought_tokens_and_abnormal_finish_are_recorded(tools, no_network):
    turn = AM.ModelTurn(function_calls=[], text="", usage={"prompt_token_count": 7, "candidates_token_count": 0,
                                                           "thoughts_token_count": 900}, finish_reason="MAX_TOKENS")
    adapter = AM.ScriptedAdapter([turn] * 6)
    result = A.run_triage(tools, "case-credential_link", mode="replay", adapter=adapter)
    assert result.report.usage["thought_tokens"] >= 900
    assert any("finish MAX_TOKENS" in str(t["code"]) for t in result.trace if t["kind"] == "model_request")


def stub_result(case_id, termination, status="approved"):
    usage = {"model_requests": 3, "provider_retries": 0, "retry_wait_s": 0.0, "tool_executions": 1,
             "rejected_tool_calls": 0, "tool_rounds": 1, "elapsed_s": 1.0}
    report = A.TriageReport(case_id=case_id, execution_mode="live", mode_notice="stub", status=status,
                            termination_reason=termination, classifier=None, assessment=None, assessment_note="",
                            findings=[], playbook_refs=[], missing_information=[], recommended_actions=[],
                            review={"reviewer_status": "approve", "rounds": 1}, limitations=[], usage=usage,
                            provider={"sdk_version": "x", "errors": []})
    return A.AgentResult(report=report, trace=[])


def run_plan(preflight_status, terminations, budget=39, charge=0):
    ledger = C.RequestLedger(max_generation=budget, max_seconds=900)
    order, added = [], []
    plan = C.ComparisonPlan(candidates=["m1", "m2", "m3"], cases=["credential_link", "benign_notification"])

    def run_case(case_id, adapter, pf):
        order.append((adapter, case_id.split("-", 2)[-1]))
        ledger.generation += charge
        return stub_result(case_id, terminations.get((adapter, case_id.split("-", 2)[-1]), "approved"))
    out = C.run_comparison(plan, tools=None, add_case=lambda n, cid: added.append(cid), ledger=ledger,
                           preflight_fn=lambda m: {"status": preflight_status.get(m, "ok"), "model": m},
                           adapter_fn=lambda m, pf: m, run_case=run_case, sleep=lambda s: None, log=lambda s: None)
    return out, order


def test_plan_runs_each_case_across_eligible_models_first():
    out, order = run_plan({"m2": "model_unavailable"}, {})
    assert order == [("m1", "credential_link"), ("m3", "credential_link"),
                     ("m1", "benign_notification"), ("m3", "benign_notification")]
    assert "m2" not in {a["model"] for a in out["attempts"]} and out["stopped"] is None


def test_quota_stops_the_whole_comparison_without_rotation():
    out, order = run_plan({}, {("m2", "credential_link"): "provider_quota"})
    assert order == [("m1", "credential_link"), ("m2", "credential_link")]
    assert "provider_quota" in out["stopped"] and len(out["skipped"]) == 4


def test_auth_failure_at_preflight_stops_before_any_case():
    out, order = run_plan({"m1": "auth_error"}, {})
    assert order == [] and list(out["preflights"]) == ["m1"] and out["stopped"]


def test_cases_are_skipped_when_the_budget_cannot_cover_them():
    out, order = run_plan({}, {}, budget=12, charge=6)            # each stub case uses a full 6-request budget
    assert len(order) == 2 and len(out["skipped"]) == 4
    assert all("budget" in s["reason"] for s in out["skipped"])
