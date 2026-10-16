"""Evidence availability semantics and the 'no attachments' regression (offline, synthetic inputs)."""
import random
from email.message import EmailMessage

from phishtriage import agent as A, agent_replays as AR, email_input as E, evidence as V
from phishtriage.agent_model import ScriptedAdapter, call, calls, text


def eml(attach=False, reply_to=None) -> bytes:
    m = EmailMessage()
    m["From"] = "Team <team@example.com>"
    m["To"] = "sam@example.org"
    m["Subject"] = "Report"
    if reply_to:
        m["Reply-To"] = reply_to
    m.set_content("Please see the report.")
    if attach:
        m.add_attachment(b"%PDF synthetic", maintype="application", subtype="pdf", filename="report.pdf")
    return bytes(m)


def by_type(case):
    return {i.evidence_type: i for i in V.observe(case)[1]}


def test_status_semantics_distinguish_unavailable_absent_and_present():
    pasted = by_type(E.from_pasted("Hello", "No links here."))
    assert pasted["attachments"].status == "unavailable"            # not provided: unknown
    assert pasted["urls"].status == "observed_absent" and "scope" in pasted["urls"].value
    plain = by_type(E.parse_eml(eml()))
    assert plain["attachments"].status == "observed_absent" and "MIME" in plain["attachments"].value["scope"]
    assert plain["reply_to"].status == "observed_absent" and plain["authentication_results"].status == "observed_absent"
    with_file = by_type(E.parse_eml(eml(attach=True, reply_to="r@example.net")))
    assert with_file["attachment"].status == "observed" and "attachments" not in with_file
    assert with_file["reply_to"].status == "observed"
    scan = pasted["cue_scan"]
    assert scan.status == "observed" and "credential_request_language" in scan.value["not_matched"]


def run(tools, case_id, statement, cite_type, reviewer="approve"):
    def finalize(req):
        return text(AR.draft("no_strong_indicators", [AR.finding(statement, AR.evidence_ids(req, cite_type))], []))
    verdict = AR.approve() if reviewer == "approve" else text({"decision": "revise", "objections": []})
    adapter = ScriptedAdapter([calls(call("inspect_email")), text("READY"), finalize, verdict, finalize, verdict])
    return A.run_triage(tools, case_id, mode="replay", adapter=adapter, sleep=lambda s: None,
                        rng=random.Random(0)).report


def codes(report):
    return {i["code"] for i in report.review["validation_issues"]}


def test_regression_no_attachments_claim_on_pasted_input_is_not_approved(demo_tools):
    # The observed live defect: a reviewer approved "no attachments" although attachments were unavailable.
    r = run(demo_tools, "case-benign_notification", "The email has no attachments.", "attachments")
    assert "absence_claim_on_unavailable_evidence" in codes(r)
    assert r.status == "needs_human_review"                         # reviewer "approve" cannot override this


def test_absence_claims_need_cited_observed_absence(demo_tools):
    demo_tools.store.add(E.parse_eml(eml(), case_id="case-plain"))
    ok = run(demo_tools, "case-plain", "The message contains no attachments.", "attachments")
    assert "absence_claim_on_unavailable_evidence" not in codes(ok) and "absence_claim_not_cited" not in codes(ok)
    uncited = run(demo_tools, "case-plain", "The message contains no attachments.", "sender_address")
    assert "absence_claim_not_cited" in codes(uncited)
    demo_tools.store.add(E.parse_eml(eml(attach=True), case_id="case-file"))
    contradicted = run(demo_tools, "case-file", "There are no attachments.", "attachment")
    assert "absence_claim_contradicts_evidence" in codes(contradicted)
    links = run(demo_tools, "case-benign_notification", "The text contains no links.", "urls")
    assert not {"absence_claim_on_unavailable_evidence", "absence_claim_not_cited"} & codes(links)


def test_paraphrased_absence_is_not_caught_deterministically(demo_tools):
    # Documented limitation: the deterministic check covers common phrasings only; the reviewer and the human
    # reader remain responsible for other wordings.
    r = run(demo_tools, "case-benign_notification", "Nothing was attached to this message.", "attachments")
    assert not any(c.startswith("absence_claim") for c in codes(r))


def test_benign_replay_keeps_disagreement_and_cites_grounded_evidence(demo_tools):
    res = A.run_triage(demo_tools, "case-benign_notification", mode="replay",
                       adapter=AR.replay_adapter("benign_notification"))
    r = res.report
    assert r.status == "approved" and r.assessment == "no_strong_indicators"
    assert [p["doc_id"] for p in r.playbook_refs] == ["PB-07"]       # PB-06 (urgent/action) does not fit this case
    cited_types = {demo_tools.store.evidence(r.case_id)[e].evidence_type for f in r.findings for e in f["evidence_ids"]}
    assert {"urls", "cue_scan", "attachments"} <= cited_types
    disagree = r.classifier["predicted_label"] == "phishing"
    assert disagree == any(i["code"] == "assessment_classifier_disagreement" for i in r.review["validation_issues"])


def test_inspect_email_explains_status_meanings(demo_tools):
    data = demo_tools.call("inspect_email", {"case_id": "case-benign_notification"}).data
    assert "UNKNOWN" in data["status_meanings"]["unavailable"]
    assert "observed_absent" in data["status_meanings"]
