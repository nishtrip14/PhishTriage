"""Grounded recommended actions: references to permitted playbook steps, validated and rendered by the application.

Real validation, orchestration, rendering and export run here; only the model turns are scripted. Synthetic emails."""
import json
import random

import pytest

from phishtriage import agent as A, agent_replays as AR, export as X, retrieval as R, ui as U
from phishtriage.agent_model import ScriptedAdapter, call, calls, text

from test_agent import artifact, tools  # noqa: F401  (shared fixtures)

PB01 = {p["doc_id"]: p for p in R.load_playbooks()["playbooks"]}["PB-01"]
CASE = "case-credential_link"


def investigate():
    return [calls(call("inspect_email"), call("get_prediction"),
                  call("retrieve_playbook", query="verify account password sign in", top_k=1)), text("READY")]


def draft_with(*actions, refs=("PB-01",)):
    def make(req):
        return text(AR.draft("suspicious", [
            AR.finding("The message asks the reader to verify an account password.",
                       AR.evidence_ids(req, "credential_request_language"))],
            [{**AR.playbook(req, d), "reason": "credential request language"} for d in refs if AR.playbook(req, d)],
            actions=[a(req) if callable(a) else a for a in actions]))
    return make


def ref(doc="PB-01", step=1, version="1.0", rationale="The message asks for a password."):
    return {"doc_id": doc, "version": version, "action_id": f"{doc}.S{step}", "rationale": rationale}


def run(tools, steps):
    return A.run_triage(tools, CASE, mode="replay", adapter=ScriptedAdapter(steps), sleep=lambda s: None,
                        rng=random.Random(0)).report


def codes(r):
    return {i["code"] for i in r.review["validation_issues"]}


def test_valid_reference_is_rendered_and_exported_with_canonical_text(tools, no_network):
    r = run(tools, investigate() + [draft_with(ref(step=1), ref(step=2)), AR.approve()])
    assert r.status == "approved" and not codes(r)
    assert [a["action"] for a in r.recommended_actions] == PB01["next_steps"][:2]
    assert r.recommended_actions[0]["rationale"] == "The message asks for a password."
    assert PB01["next_steps"][0] in A.format_report(r)
    attempt = U.Attempt(attempt_id="a1", case_id=CASE, started_at_utc="t", input_source="synthetic",
                        synthetic_case="credential_link", fingerprint="f", mode="replay", model=None,
                        result=A.AgentResult(r, []))
    html = U.render_attempt_html(attempt, tools.store)
    assert U.esc(PB01["next_steps"][0]) in html and "PB-01.S1" in html
    summary = X.report_export(r, [], tools.store, detailed=False)
    assert summary["recommended_action_ids"] == ["PB-01.S1@v1.0", "PB-01.S2@v1.0"]
    assert "password" not in json.dumps(summary)                                     # no rationale or step text
    detailed = X.report_export(r, [], tools.store, detailed=True)
    assert detailed["recommended_actions"][0]["action"] == PB01["next_steps"][0]


@pytest.mark.parametrize("bad, code", [
    (ref(step=9), "unknown_action_id"),                                  # invented identifier
    (ref(doc="PB-05", step=1), "action_playbook_not_retrieved"),         # real step, playbook not retrieved here
    (ref(version="2.0"), "action_playbook_version_mismatch"),            # wrong playbook version
])
def test_invalid_reference_is_rejected_then_corrected(tools, bad, code, no_network):
    r = run(tools, investigate() + [draft_with(bad), AR.approve(), draft_with(ref()), AR.approve()])
    assert r.status == "approved" and r.review["rounds"] == 2            # the bounded revision fixed it
    assert [a["action_id"] for a in r.recommended_actions] == ["PB-01.S1"]
    first = run(tools, investigate() + [draft_with(bad), AR.approve(), draft_with(bad), AR.approve()])
    assert first.status == "needs_human_review" and code in codes(first)
    assert first.recommended_actions == [] and first.action_note == A.NO_ACTION_NOTE


def test_added_deletion_or_blocking_advice_never_reaches_the_report(tools, no_network):
    pushy = ref(rationale="The malicious IP should be blocked and the email deleted.")
    r = run(tools, investigate() + [draft_with(pushy), AR.approve(), draft_with(pushy), AR.approve()])
    assert r.status == "needs_human_review" and r.termination_reason == "review_unresolved"
    assert {"rationale_adds_instruction", "rationale_overclaim"} <= codes(r)
    assert r.recommended_actions[0]["action"] == PB01["next_steps"][0]           # canonical step kept,
    assert r.recommended_actions[0]["rationale"] is None                          # the added advice withheld
    lines = A.format_report(r).split("Recommended human actions")[1].splitlines()[1:]
    shown = "\n".join(next(iter([lines[:i] for i, l in enumerate(lines) if not l.startswith("  ")]), lines))
    assert PB01["next_steps"][0] in shown and "blocked" not in shown and "malicious" not in shown

    def free_text(req):                                                  # old-style free-text action
        d = json.loads(draft_with(ref())(req).text)
        d["recommended_actions"] = [{"action": "Delete the email and block the sender IP.", "playbook_refs": ["PB-01"]}]
        return text(d)
    r = run(tools, investigate() + [free_text, free_text])
    assert r.status == "failed" and r.recommended_actions == [] and "block" not in json.dumps(r.to_dict()).lower()


def test_no_applicable_action_is_stated_not_invented(tools, no_network):
    r = run(tools, investigate() + [draft_with(), AR.approve()])
    assert r.status == "approved" and r.recommended_actions == [] and r.action_note == A.NO_ACTION_NOTE
    assert A.NO_ACTION_NOTE in A.format_report(r)
    ev = A.run_triage(tools, CASE, mode="evidence_only").report             # mechanical mode: canonical steps only
    catalog = R.playbook_actions(R.load_playbooks())
    assert ev.recommended_actions and all(catalog[a["doc_id"]]["actions"][a["action_id"]] == a["action"]
                                          for a in ev.recommended_actions)
