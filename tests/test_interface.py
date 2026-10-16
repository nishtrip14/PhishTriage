"""Model configuration, interface session logic, safe rendering, export defaults and widget callbacks (offline)."""
import json
import tempfile
from pathlib import Path

import pytest

from phishtriage import agent as A, agent_replays as AR, export as X, llm_preflight as LP, ui as U


# ---------------------------------------------------------------- one configuration path

def test_settings_resolution_is_explicit(monkeypatch):
    monkeypatch.delenv(LP.MODEL_ENV, raising=False)
    assert LP.LLMSettings.resolve().model == LP.DEFAULT_MODEL == "gemini-3.6-flash"
    monkeypatch.setenv(LP.MODEL_ENV, "gemini-3.8-flash")
    assert LP.LLMSettings.resolve().model == "gemini-3.8-flash"
    assert LP.LLMSettings.resolve("gemini-3.5-flash-lite").model == "gemini-3.5-flash-lite"
    with pytest.raises(ValueError):
        LP.LLMSettings.resolve("not a model; rm -rf")


def test_preflight_approval_is_bound_to_model_and_sdk(monkeypatch, no_network):
    reg = LP.PreflightRegistry()
    monkeypatch.setattr(LP, "installed_sdk_version", lambda: "2.12.1")
    a, b = LP.LLMSettings("gemini-3.6-flash"), LP.LLMSettings("gemini-3.8-flash")
    reg.record({"status": "ok", "model": a.model, "sdk_version": "2.12.1"})
    assert reg.approval_for(a) and reg.approval_for(b) is None          # model change invalidates approval
    calls = []
    monkeypatch.setattr(LP, "preflight", lambda **kw: calls.append(kw) or {"status": "x"})
    cached = reg.run(a, enable_network=True)
    assert cached["status"] == "ok" and cached["reused_from_cache"] and calls == []   # no needless rerun
    monkeypatch.setattr(LP, "installed_sdk_version", lambda: "2.31.0")
    assert reg.approval_for(a) is None                                   # SDK change invalidates approval too


def test_live_adapter_refuses_mismatched_model_or_sdk(monkeypatch, no_network):
    monkeypatch.setattr(LP, "installed_sdk_version", lambda: "2.12.1")
    monkeypatch.setattr(LP, "get_api_key", lambda: None)
    approved = {"status": "ok", "model": "gemini-3.6-flash", "sdk_version": "2.12.1"}
    adapter, why = A.make_live_adapter(approved, LP.LLMSettings("gemini-3.8-flash"))
    assert adapter is None and "configured model" in why
    adapter, why = A.make_live_adapter({**approved, "sdk_version": "2.0.0"}, LP.LLMSettings("gemini-3.6-flash"))
    assert adapter is None and "run the preflight again" in why
    adapter, why = A.make_live_adapter(approved, LP.LLMSettings("gemini-3.6-flash"))
    assert adapter is None and "GEMINI_API_KEY" in why                   # key only from Secrets / environment


# ---------------------------------------------------------------- session logic

@pytest.fixture
def session(demo_tools):
    return U.TriageSession(demo_tools, settings=LP.LLMSettings("gemini-3.6-flash"), preflights=LP.PreflightRegistry(),
                           run_info={"code_commit": "test", "code_modified": False, "environment": "local"})


def test_input_validation(session):
    with pytest.raises(U.InputError):
        session.analyze(source="pasted", mode="evidence_only", subject="", body="  ")
    with pytest.raises(U.InputError):
        session.analyze(source="eml", mode="evidence_only")
    with pytest.raises(U.InputError):
        session.analyze(source="eml", mode="evidence_only", eml_bytes=b"x" * (U.EI.MAX_EML_BYTES + 1))
    with pytest.raises(U.InputError):
        session.analyze(source="synthetic", mode="evidence_only", synthetic_name="not-a-case")
    with pytest.raises(U.InputError):
        session.analyze(source="pasted", mode="evidence_only", subject="s", body="b", eml_bytes=b"From: a")
    assert session.attempts == [] and not session.busy


def test_mode_restrictions(session, no_network):
    with pytest.raises(U.InputError, match="replay only"):
        session.analyze(source="pasted", mode="replay", subject="s", body="b")
    with pytest.raises(U.InputError, match="live mode unavailable"):
        session.analyze(source="synthetic", mode="live", synthetic_name="ambiguous", live_acknowledged=True)
    session.preflights.record({"status": "ok", "model": "gemini-3.6-flash", "sdk_version": LP.installed_sdk_version()})
    with pytest.raises(U.InputError, match="acknowledgement"):
        session.analyze(source="synthetic", mode="live", synthetic_name="ambiguous", live_acknowledged=False)
    a = session.analyze(source="synthetic", mode="replay", synthetic_name="ambiguous")
    assert a.result.report.execution_mode == "replay" and "NOT live" in a.result.report.mode_notice


def test_unique_attempts_history_and_staleness(session):
    first = session.analyze(source="pasted", mode="evidence_only", subject="Hi", body="verify your password")
    second = session.analyze(source="pasted", mode="evidence_only", subject="Hi", body="verify your password")
    assert first.attempt_id != second.attempt_id and first.case_id != second.case_id
    assert len(session.attempts) == 2 and first.result is not None          # history kept, not overwritten
    same = dict(source="pasted", subject="Hi", body="verify your password")
    assert not session.is_stale(second, **same)
    assert session.is_stale(second, **{**same, "body": "verify your password!"})


def test_duplicate_submission_and_error_recovery(session):
    session.busy = True
    with pytest.raises(U.InputError, match="already running"):
        session.analyze(source="pasted", mode="evidence_only", subject="s", body="b")
    session.busy = False

    def broken_runner(*a, **k):
        raise RuntimeError("boom")
    session.runner = broken_runner
    a = session.analyze(source="pasted", mode="evidence_only", subject="s", body="b")
    assert a.result is None and a.error == "internal error: RuntimeError" and not session.busy
    with pytest.raises(U.InputError):
        session.export(a)


# ---------------------------------------------------------------- rendering and export

HOSTILE = '<img src="https://tracker.example.com/p.gif" onerror=alert(1)><a href="http://198.51.100.9/x">go</a>'


def test_rendering_escapes_untrusted_content(session):
    a = session.analyze(source="pasted", mode="evidence_only", subject=HOSTILE, body=HOSTILE + " verify your password")
    page = U.render_attempt_html(a, session.store)
    for raw in ("<img", "<a href", "onerror=alert(1)>", "<script"):
        assert raw not in page
    assert "uncalibrated" in page and "EXAMPLE POLICY" in page and "<details>" in page


def test_export_defaults_omit_email_content(session):
    a = session.analyze(source="synthetic", mode="replay", synthetic_name="prompt_injection")
    summary = session.export(a)
    blob = json.dumps(summary)
    case = session.store.case(a.case_id)
    assert summary["export_kind"] == "summary" and summary["omitted"]
    assert case.body[:40] not in blob and "bank details" not in blob and a.case_id not in blob
    assert "findings_detail" not in summary and "cited_evidence" not in summary
    assert summary["classifier"]["score_type"] == "model_estimated_probability_uncalibrated"
    detailed = session.export(a, detailed=True)
    assert detailed["export_kind"] == "detailed" and detailed["findings_detail"] and detailed["detailed_export_warning"]
    assert case.body not in json.dumps(detailed)                         # raw body never exported
    target = Path(tempfile.mkdtemp())
    path = X.write_json(summary, target, "a/../b")
    assert path.parent == target and "/" not in path.name


def test_verification_records_are_synthetic_only(session):
    session.analyze(source="pasted", mode="evidence_only", subject="s", body="b")
    session.analyze(source="synthetic", mode="replay", synthetic_name="credential_link")
    records = session.verification_records()
    assert len(records) == 1 and records[0]["synthetic_case"] == "credential_link"
    assert {"code_commit", "model", "sdk_version", "mode", "started_at_utc", "status", "termination_reason",
            "reviewer_status", "counters", "elapsed_s"} <= set(records[0])


# ---------------------------------------------------------------- widgets (only if ipywidgets is installed)

def test_widget_callbacks_recover_and_never_auto_run(session, no_network):
    pytest.importorskip("ipywidgets")
    calls = []
    real = session.runner
    session.runner = lambda *a, **k: calls.append(k["mode"]) or real(*a, **k)
    box = U.build_interface(session, export_dir=Path(tempfile.mkdtemp()))
    w = box._phishtriage
    assert calls == [] and w["mode"].value == "evidence_only"            # building the UI runs nothing
    w["analyze"].click()                                                 # empty input -> message, controls restored
    assert "warn" in w["message"].value and not w["analyze"].disabled and calls == []
    w["subject"].value, w["body"].value = "Alert", "verify your password"
    w["analyze"].click()
    assert calls == ["evidence_only"] and not w["export"].disabled and not w["analyze"].disabled
    w["body"].value = "edited text"
    assert w["export"].disabled and "Input changed" in w["result"].value  # stale result cannot be exported
    session.runner = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    w["analyze"].click()
    assert not w["analyze"].disabled and "Failed" in w["result"].value   # error recorded, controls restored
    w["mode"].value = "live"
    w["analyze"].click()
    assert "live mode unavailable" in w["message"].value                 # no preflight -> no API call


# ---------------------------------------------------------------- configuration propagation and outcome counts

def test_interface_follows_current_configuration_and_keeps_history(demo_tools, monkeypatch, no_network):
    monkeypatch.setattr(LP, "installed_sdk_version", lambda: "2.12.1")
    cfg = {"settings": LP.LLMSettings("gemini-3.6-flash"), "registry": LP.PreflightRegistry()}
    seen = []

    def factory(approval, settings):
        seen.append(settings.model)
        return None, "no key in tests"
    session = U.TriageSession(demo_tools, settings=lambda: cfg["settings"], preflights=lambda: cfg["registry"],
                              live_adapter_factory=factory)
    first = session.analyze(source="pasted", mode="evidence_only", subject="s", body="b")
    assert session.live_status()[0] is False                        # created before any preflight
    cfg["registry"].record({"status": "ok", "model": "gemini-3.6-flash", "sdk_version": "2.12.1"})
    assert session.live_status()[0] is True                         # later approval recognised, no rebuild
    with pytest.raises(U.InputError):
        session.analyze(source="synthetic", mode="live", synthetic_name="ambiguous", live_acknowledged=True)
    assert seen == ["gemini-3.6-flash"]
    cfg["settings"] = LP.LLMSettings("gemini-3.8-flash")            # model changed in section 21
    ok, why = session.live_status()
    assert not ok and "gemini-3.8-flash" in why                      # approval for the old model does not carry over
    assert session.attempts == [first]                              # history kept


def _report(status):
    from phishtriage.agent import TriageReport
    return TriageReport(case_id="c", execution_mode="live", mode_notice="", status=status, termination_reason="x",
                        classifier=None, assessment=None, assessment_note="", findings=[], playbook_refs=[],
                        missing_information=[], recommended_actions=[], review={}, limitations=[], usage={},
                        provider={})


def test_live_outcome_counts_use_actual_statuses():
    s26 = [{"batch": [{"batch_status": "ran", "report_status": "approved"},
                      {"batch_status": "ran", "report_status": "failed"},
                      {"batch_status": "skipped_due_to_quota", "report_status": None}]},
           {"batch": [{"batch_status": "ran", "report_status": "needs_human_review"}]}]
    result = type("R", (), {})
    def attempt(mode, status=None):
        a = U.Attempt("a", "c", "t", "pasted", None, "f", mode, None)
        if status:
            a.result = type("Res", (), {"report": _report(status)})()
        return a
    ui_attempts = [attempt("live", "approved"), attempt("live"), attempt("replay", "approved"),
                   attempt("live", "failed")]
    counts = X.live_outcome_counts(s26, ui_attempts)
    assert counts["section_26"] == {"attempted": 3, "approved": 1, "needs_human_review": 1, "failed": 1, "skipped": 1}
    assert counts["interface"] == {"attempted": 3, "approved": 1, "needs_human_review": 0, "failed": 2, "skipped": 0}
    assert counts["total"]["approved"] == 2 and counts["total"]["failed"] == 3   # failures never counted as completed
