# Phase 4: bounded investigator and reviewer agents

Code: `phishtriage/agent.py` (workflow, report contract, validation), `phishtriage/agent_model.py` (Gemini and
scripted adapters), `phishtriage/agent_replays.py` (synthetic demo emails and scripted turns).
Notebook: sections 23–27 (agents) and 28–30 (interface, checks, final summary). Entry point:

```python
from phishtriage import agent as A
result = A.run_triage(tools, case_id, mode="evidence_only" | "replay" | "live", adapter=..., preflight=...)
print(A.format_report(result.report)); result.trace   # observable actions only
```

## Verification status
The current verification matrix is maintained in [VERIFICATION.md](VERIFICATION.md), including test counts, the
local and Colab notebook runs, widget status and user-reported live results. This document describes behaviour.

## State transitions
```
START ─► trusted get_prediction (application)
  ├─ mode=evidence_only ─► EVIDENCE_ONLY report (no LLM, no assessment)
  └─ INVESTIGATE (≤ max_tool_rounds requests, tools AUTO; the model chooses calls)
        │  each call: name/args/range checked → duplicate? → tool budget? → deadline? → execute for the BOUND case
        ▼  (model replies without calls, rounds exhausted, or too many rejected calls)
     FINALIZE (tools disabled: mode NONE + JSON schema) ─► draft
        ▼
     VALIDATE (deterministic) ─► REVIEW (separate request, no tools)
        ├─ approve and no validation errors ─► APPROVED
        └─ otherwise, if a revision is left and ≥ 2 requests remain:
              REVISE (tools disabled) ─► VALIDATE ─► REVIEW ─► APPROVED | NEEDS_HUMAN_REVIEW
           else ─► NEEDS_HUMAN_REVIEW (review_unresolved | budget_exhausted)
  budget or deadline exhausted ─► NEEDS_HUMAN_REVIEW (partial result)
  provider abort ─► NEEDS_HUMAN_REVIEW (if a draft exists) or FAILED
```

## Report contract (`TriageReport`)
| Field | Source |
|---|---|
| `case_id`, `execution_mode`, `mode_notice`, `status`, `termination_reason`, `usage`, `provider` | trusted application state |
| `classifier` (`model_id`, `predicted_label`, `score`, `score_type = model_estimated_probability_uncalibrated`, `threshold`, `evidence_id`) | trusted call to the phase 2 model; the draft schema has no classifier fields, so the model cannot overwrite them |
| `assessment` | model: `suspicious` / `no_strong_indicators` (not proof of safety) / `insufficient_evidence`; `None` in evidence-only mode |
| `findings[]` (`statement`, `evidence_ids`, `rejected_citations`, `has_valid_citation`) | model statements; invalid citations are removed and listed |
| `playbook_refs[]` (`doc_id`, `version`, `title`, `reason`, `verified_retrieved`, label EXAMPLE POLICY) | model, checked against what `retrieve_playbook` returned |
| `missing_information[]` | `unavailable`/`error` evidence (trusted) plus model-listed gaps (marked `agent`) |
| `recommended_actions[]` | model, for a human; actions may only reference cited playbooks |
| `review` (`reviewer_status`, `rounds`, `unresolved_objections`, `validation_issues`) | reviewer output plus deterministic checks |
| `limitations` | fixed list (classifier confound, not proof of safety, example policy, prompt-injection caveat, reviewer is not a guarantee) |

## Deterministic validation vs semantic review
**Deterministic checks** (`validate_draft`) produce errors that block approval:
- Citation problems: `unknown_citation`, `cross_case_citation`, `citation_not_retrieved` (the ID exists but no
  tool returned it this run), and `finding_without_citation`.
- Playbook problems: `unsupported_playbook_citation`, `playbook_version_mismatch`, and
  `action_cites_uncited_playbook`.
- Overclaims and contradictions: `safety_overclaim` ("email is safe", "no risk", …) and
  `classifier_value_mismatch` (a statement contradicting the classifier's label or score).
- Structure: `suspicious_without_findings`, and `invalid_model_output` (JSON or schema violations, including any
  attempt to add fields such as `classifier`).

There is one non-blocking warning, `assessment_classifier_disagreement`: both values are shown for a human to weigh.

These checks prove that citations are well-formed and belong to this run. **They do not prove a claim is true.**
The **reviewer** (a separate model request with no tools) judges support, contradictions, overconfidence,
consistency with the playbooks, and whether the draft followed instructions from the email. It is a second pass,
not an independent guarantee.

## Budgets (`AgentConfig` defaults)
| Budget | Value |
|---|---|
| Investigator tool rounds | 3 |
| Tool executions | 5 (rejected calls are not executed; they count separately, with a limit of 4) |
| Model requests | 6, including finalize, review, revision and retries. **Reserved capacity:** an investigation request (or its retry) needs 2 requests left over for finalize + review; finalize and revise need 1 left for review. Otherwise investigation ends early and the case finishes |
| Deadline | 90 s, checked before every request, retry wait and tool execution; a request needs ≥ 2 s left; investigation stops when < 20 s + 2 s remain (`finish_reserve_s`) |
| Per-request timeout | min(30 s, time remaining); the SDK HTTP timeout is in ms and SDK retries are off (`attempts=1`) |
| Provider retries | At most 2 per run, each counted as a request, and the wait counted against the deadline. See the retry policy below |
| Output tokens | 1,024 for tool rounds and review, 2,048 for draft reports |
| Email in prompt | first 6,000 characters (the tools still see the stored text) |

## Modes
- **`live`:** `GeminiAdapter` over `google-genai`. The model must equal the one that passed the section 21
  preflight in this runtime (`make_live_adapter`), with no silent model or provider switch. Live mode refuses a
  scripted adapter.
- **`replay`:** `ScriptedAdapter` with turns pre-written in `agent_replays.py`. Reports carry "SCRIPTED REPLAY …
  NOT live-agent validation". The tools, validation, budgets and report assembly are real.
- **`evidence_only`:** no LLM. The classifier result, observed cues as findings, and mechanically retrieved
  playbooks; the assessment is `None`.

## Gemini protocol (generate_content)
- The model's returned `Content` is appended to history **unchanged**, which preserves the thought signatures
  that Gemini 3+ requires for function calling.
- All function responses for one step go in a single user turn after the calls, in call order. A following
  instruction is merged into that same turn.
- Automatic function calling is disabled; the application executes every call itself.
- Thought parts are excluded from visible text and never logged. The trace records only the step kind, tool or
  request name, status, time, evidence IDs and counters.
- **Error mapping:** 401/403 → `auth`, 404 → `model_unavailable`, 429 → `quota`, 400 → `invalid_request`,
  5xx → `server`, timeouts → `timeout`. Non-retryable errors stop the run immediately.

## Quota and batch behaviour (added in `e635833`)
- **Quota (HTTP 429) is not retried.** The case ends after that request with `provider_quota`. An immediate retry
  has no backoff, spends another request, and cannot clear daily or per-minute limits inside a 90-second run.
  Timeout, network and 5xx errors still get one counted retry. The preflight also reports 429 as
  `quota_exceeded` and never retries it.
- **`run_batch_triage(tools, case_ids, mode, ...)`** runs cases one at a time. After a `provider_quota`,
  `provider_auth` or `provider_model_unavailable` termination, later cases are **not submitted**. They are recorded
  as `skipped_due_to_quota` / `skipped_due_to_provider_error`, and earlier results are unchanged.
- Each `BatchEntry` has `.status` (`ran` or skipped), `.result` (an `AgentResult` or `None`) and `.report`
  (`None` when skipped), so callers never have to guess the return type.
- `TriageReport.termination_detail` explains failures, for example why the live preflight gate was not passed.
  The gate itself is unchanged: live mode still needs `status == "ok"` for the same model in this runtime.
- **Tests (`tests/test_quota_handling.py`):**
  - The real `run_triage` and `GeminiAdapter` over a fake 429 client: exactly one or two provider calls, zero
    retries, `provider_quota`, and no fabricated findings.
  - A stubbed batch-control test.
  - An unstubbed batch integration test.
  - With the old retry-on-quota behaviour restored in-process, all three orchestration tests fail.

## Retry policy and diagnostics (phase 5)
| Error | Policy |
|---|---|
| timeout, network, HTTP 5xx | Retry with jittered exponential backoff (base 2 s, cap 8 s). A provider `RetryInfo.retryDelay` is a minimum: it is waited **in full** (jitter only adds time) if the wait still leaves the deadline window and finish reserve; otherwise there is no early retry, and the case finishes or stops with a partial result. An optional `max_retry_wait_s` cap is off by default |
| HTTP 429, classified as a **rate limit** by the error body (`rate_limit_exceeded`, `too_many_requests`, or a `QuotaFailure` quotaId with `PerMinute`/`PerSecond`) | Retry once the provider delay or backoff has passed, if the wait fits the deadline and request reservation |
| HTTP 429, **daily** (`quota_exceeded`, quotaId `PerDay`) or **unclassified** | **Not retried.** The case ends with `provider_quota`, and `run_batch_triage` skips the later cases |
| 401/403/404/400 | Not retried |

- **Blocked retry during investigation:** if a retry would break the reservation or the deadline, investigation
  ends and the case finishes with the evidence already gathered.
- **SDK retries** stay disabled (`attempts=1`). The official Python SDK would otherwise retry up to four times
  outside the budget.
- **Diagnostics:** every provider error is recorded in `report.provider["errors"]` as
  `{request, http_status, category, provider_status, quota_category, retry_delay_s}`. These are read from
  specific fields only (`str(error)` embeds the whole response). Messages are redacted of keys, `projects/...`
  identifiers and long numbers.

## Evidence grounding (phase 5)
- **The defect:** a user-reported live run approved a report claiming "no attachments" for pasted text, whose
  attachment information was `unavailable`.
- **New status:** evidence now distinguishes `observed_absent` ("checked, not found", with `value.scope`) from
  `unavailable` ("not provided: unknown"). Examples of observed absence: no URL text in the provided text, no
  attachment parts in a supplied `.eml`, or a header missing from a supplied `.eml`.
- **`cue_scan`:** a new evidence item records which keyword cues were checked and which matched.
- **Prompts:** the investigator and reviewer prompts state these meanings explicitly.
- **Deterministic check (`ABSENCE_TOPICS`):** it looks for absence statements about attachments, URLs/links,
  Reply-To and authentication results.
  - It flags `absence_claim_on_unavailable_evidence`, `absence_claim_contradicts_evidence` and
    `absence_claim_not_cited`. These are errors that block approval.
  - It is a heuristic over common English phrasings. Paraphrases ("nothing was attached") are not caught, and a
    test documents that limitation.
- **Playbook fix:** PB-06 ("urgent or asks for action but may be genuine") does not fit the non-urgent, no-action
  benign example. The benign replay now cites PB-07 (missing information) instead. PB-06 itself is unchanged.

## Model configuration (phase 5)
- **One setting:** `LLMSettings` (section 21: `MODEL_OVERRIDE`, else `$PHISHTRIAGE_GEMINI_MODEL`, else
  `gemini-3.6-flash`) feeds the preflight, the live adapter, the interface and the reports.
- **Approval:** `PreflightRegistry` keys approval by (model, installed google-genai version).
  - A model or SDK change has no approval until its own preflight passes.
  - An unchanged, approved configuration is reused without network calls.
  - `make_live_adapter(approval, settings)` refuses a mismatch.
- **Reports** show the model and SDK actually used (`provider.model`, `provider.sdk_version`).

## Interface and export (phase 5)
- **Logic:** `phishtriage.ui.TriageSession` holds input validation (source selection, bounded `.eml`),
  mode gating, the live acknowledgement, the duplicate-submission guard, unique attempt and case IDs, the
  stale-input fingerprint, and session-memory history.
- **Widgets:** `build_interface()` only wires ipywidgets to it. Errors re-enable the controls, and displaying the
  widgets runs nothing.
- **Rendering:** `render_attempt_html` escapes every value and creates no links, images, scripts or iframes.
  The trace is a native `<details>` element, and no model reasoning is shown.
- **Export:** `phishtriage.export`. The default summary has structure only. The detailed export (opt-in) adds
  model text and the escaped excerpts of cited evidence. The raw email body and attachments are never exported.
  `verification_record()` holds the compact synthetic-run records (revision, model, SDK, mode, time, status,
  termination, review, counters, elapsed).

## Failure behaviour
| Situation | Result |
|---|---|
| No key, preflight not passed, or wrong model | `failed` with `missing_credentials` / `preflight_not_passed`, and no request is made |
| Auth, quota, unavailable model, timeout after retry | `failed`, or `needs_human_review` if a draft exists, with `provider_<kind>` |
| Invalid JSON draft | one revision; then `needs_human_review`, or `failed` if no draft parses |
| Invalid reviewer output | treated as an unresolved objection |
| Unknown tool, bad arguments, cross-case IDs, duplicates, tool budget | the call is rejected with a structured error; nothing is executed |
| Budget or deadline exhausted | `needs_human_review` (a partial result) with the reason; nothing is invented |
| Unknown case | `failed`, `invalid_input`. Empty input is rejected earlier by `email_input`, and oversized input is truncated with a note |

## Synthetic demonstrations (replay; current scripts, local run at `f6642c9`)
| Case | Assessment | Classifier | Playbooks | Requests |
|---|---|---|---|---|
| Credential request with link mismatch | suspicious, after one reviewer correction | phishing | PB-01, PB-04 | 6 |
| Benign notification | no_strong_indicators **(with a disagreement warning)** | **phishing** | PB-07 (PB-06 until `1955903`) | 5 |
| Ambiguous message | insufficient_evidence | legitimate | PB-07 | 4 |
| Prompt-injection attempt | suspicious; the injection is cited as evidence | phishing | PB-02 | 4 |

The model turns were scripted, so this shows workflow behaviour only. The phase 2 classifier labels the
**synthetic benign notification as phishing** (score ≈ 0.90). That is consistent with the documented confound:
modern notification-style text resembles the 2015–2022 Nazario phishing more than the 2002 SpamAssassin ham.
These synthetic results are not detection evidence and are never combined with the held-out metrics.

## Known limitations
- Live behaviour is known only from user-reported historical results (unrecorded revision): one approved case,
  one server error and two quota stops. In the approved case the report made an apparent unsupported "no
  attachments" claim while attachment metadata was unavailable, and the reviewer approved it. **Reviewer approval
  does not establish that an explanation is correct**. Since `1955903`, absence claims are checked
  deterministically for common phrasings (see "Evidence grounding"); other phrasings still depend on the reviewer
  and the human reader.
- The prompt-injection handling (delimiters, tools bound to the case, validation, reviewer) reduces risk but does
  not make the system immune. Only scripted behaviour has been tested.
- Deterministic checks catch invalid citations and a few overclaim patterns. They cannot judge truth.
- The classifier and dataset caveats from `docs/MODEL_EVALUATION.md` still apply in full.
- CrewAI and other frameworks are deliberately not used (dependency conflict, see `docs/TOOLS_AND_EVIDENCE.md`).
