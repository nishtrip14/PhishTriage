# PhishTriage: Colab status

**Deadline:** 19 Oct 2026 (Colab demonstration) · **Last updated:** 2026-10-16

## Project plan
PhishTriage is an **agentic** triage project. The classifier is one evidence tool for the investigator and
reviewer agents; it is not the deliverable on its own.
`PhishTriage_Colab_Roadmap_and_Prompts.txt` is **still not in the repository** (rechecked 2026-10-15). The stages
below follow the owner's prompts.

| # | Stage | Status | Evidence |
|---|-------|--------|----------|
| 0 | Repository & notebook scaffolding | Done | `170260b` on `origin/main` |
| 1 | Data acquisition/audit & Colab verification | **Done; verified locally and in Colab** (`9acefcb`, outputs in `f2b7277`) | `docs/DATASET_CARD.md`, `reports/audit_summary.json`, `reports/split_manifest.csv` |
| 2 | Classifier training & evaluation | **Done; run locally and in Colab.** Thresholds and a few error counts differed between the two environments; the cause is not established (see `docs/MODEL_EVALUATION.md`) | `docs/MODEL_EVALUATION.md`, `reports/phase2_metrics.json`, code `e19b8cc` |
| 3 | Local evidence tools & playbook retrieval (RAG over a small, cited playbook corpus) | **Done; verified locally and in Colab (`9acefcb`).** Live preflight: user-reported `ok` (see below); revision not recorded. | `docs/TOOLS_AND_EVIDENCE.md`, `reports/retrieval_check.json`, `reports/phase3_summary.json`, code `86993a3` |
| 4 | Bounded investigator and reviewer agents (tool budget, step limit, cited findings) | **Implemented and offline-tested; replay and evidence-only verified in Colab (`9acefcb`).** User-reported live results exist (see below; revision not recorded). The quota/batch fixes (`e635833`) have not run in Colab. | `docs/AGENT_WORKFLOW.md`, `reports/phase4_summary.json`, `reports/colab_run_9acefcb.json`, code `e635833` |
| 5 | Reliability, evidence grounding, model configuration, interface & export | **Implemented and offline-tested (`1955903`); local notebook run.** Colab widget rendering and live use of this code not yet verified | `docs/DEMO_RUNBOOK.md`, `docs/AGENT_WORKFLOW.md`, `reports/phase5_verification.json`, `reports/final_verification.json` |
| 6 | Fresh-runtime verification & final submission (`reports/PhishTriage_Colab_Executed.ipynb`) | **Documentation complete; Colab evidence for the current code pending.** The owner reports a successful Colab *Run all* (2026-10-16), but the executed notebook was not supplied | `docs/VERIFICATION.md` |

## Verification matrix (as of 2026-10-16, phase 5)
| Stage | Implementation | Offline tests | Local notebook run | Genuine Colab run | Live provider |
|---|---|---|---|---|---|
| 1 Data | done | yes | yes | **yes** (`9acefcb`; identical split) | n/a |
| 2 Classifier | done | yes | yes (reproduced exactly) | **yes** (thresholds and a few error counts differ from the local run; cause not established) | n/a |
| 3 Evidence, retrieval, tools | done | yes | yes | **yes** (results identical) | preflight **user-reported `ok`** (`gemini-3.6-flash`, SDK 2.12.1); not in any recovered notebook |
| 4 Agents | done (+ quota/batch fixes `e635833`) | yes | yes, at `e635833` and `1955903` | **yes, offline paths only** (replay and evidence-only at `9acefcb`) | **user-reported historical results** (below); code revision not recorded; `e635833`+ not run live |
| 5 Reliability, grounding, config, interface, export | done (`1955903`, prep fixes `f6642c9`) | yes: 119 passed (google-genai 2.31.0); 118 passed + 1 skipped (2.12.1, no ipywidgets there) | yes, sections 0–30 at `f6642c9` (clean); frozen evaluation reproduced | **not yet** (widgets need a person to view them in Colab) | **not yet** |

- **Local:** this Mac (Python 3.13.7, pandas 3.0.6, scikit-learn 1.9.1).
- **Colab:** Python 3.13.16, pandas 2.2.3, scikit-learn 1.6.1, 2 CPUs. The outputs were saved in commit
  `f2b7277`. A sanitized extract is in `reports/colab_run_9acefcb.json`.
- The `e635833` fixes have **not** run in Colab yet.

## Colab verification log
- 2026-10-15: no Colab evidence existed yet; phases 1–4 were verified locally only.
- **2026-10-16:** commit `f2b7277` ("Adding Gemini API", notebook only) contains genuine Colab outputs.
  - **Run:** one consecutive error-free pass over sections 0–27 at code commit `9acefcb`.
  - **Flag edit:** cell 50's source was edited to `RUN_LLM_PREFLIGHT = True` **after** that run; its saved output
    shows the preflight skipped. This notebook contains no live Gemini call. Separately, the owner reported live
    preflight and agent runs (see "User-reported historical live results").
  - **Raw notebook:** kept untracked in `colab_import/` (SHA-256 `e271c5d2…`).

## Verification by revision
| Revision | What ran | Where | Evidence |
|---|---|---|---|
| `9acefcb` | Sections 0–27, offline paths (live sections skipped) | Google Colab | saved outputs in `f2b7277`; extract `reports/colab_run_9acefcb.json` |
| *not recorded* | Section 21 preflight and section 26 live agent | Google Colab | **user-reported** only (below); no executed notebook recovered |
| `e635833` | Quota/batch fixes; 89 offline tests; notebook sections 0–27 (live skipped) | local Mac | test output in this session; `reports/phase4_summary.json` |
| `9283ce1`, `17826ac` | Documentation and evidence only (no code change from `e635833`) | n/a | |
| `1955903` | Phase 5 code; 115 offline tests; notebook sections 0–30 (live flags off) | local Mac | superseded by `f6642c9` evidence |
| `f6642c9` | Final-verification prep: status-based live counts, config propagation, full provider delays; 119 offline tests; notebook sections 0–30 (live flags off) | local Mac | `reports/final_verification.json`, `reports/phase5_verification.json`, `reports/phase4_summary.json` |

**Updated code (`e635833` and later, including `1955903`) still needs a fresh Colab run**, offline and live.

## User-reported historical live results (Colab)
These were reported by the owner. They are **not** contained in the recovered notebook. The code revision,
timestamps and executed notebook were not recorded, and none is inferred here.

**Section 21 preflight:**
- `status: ok`, model `gemini-3.6-flash`, google-genai SDK `2.12.1`.
- `model_lookup` ok; `function_call` ok and returned `record_check`.
- `network_calls: 2`.

**Section 26 live agent:**

| Case | Outcome | Model requests | Tool executions |
|---|---|---|---|
| credential_link | `provider_server` | 3 | 3 |
| benign_notification | approved; assessment `no_strong_indicators`; one reviewer pass | 5 | 3 |
| ambiguous | `provider_quota` after a server error | 4 | not reported |
| prompt_injection | `provider_quota` before investigation | 2 | not reported |

**Observations.** These are interpretations of the reported results, not established facts.
- **Quota requests consumed:** the request counts for the quota cases are consistent with the earlier behaviour
  that retried quota errors once. `e635833` stops after the first 429, and `run_batch_triage` would not have
  submitted the later cases.
- **Unsupported "no attachments" claim (historical, code at the time of the report; revision not recorded):** the
  approved benign report contained an apparent "no attachments" claim while attachment metadata was
  `unavailable` (pasted input). **Status now:** addressed in `1955903` (the `observed_absent` vs `unavailable`
  statuses, plus a deterministic absence-claim check covering common phrasings), offline-tested but not yet
  re-run live.
  - Neither the deterministic checks nor the reviewer caught it. **Reviewer approval does not establish that an
    explanation is correct.**
  - At that time absence claims were not checked against `unavailable` evidence.
- **Model mismatch (historical):** the model that passed the preflight (`gemini-3.6-flash`) differed from the
  code default at the time (`gemini-3.8-flash`). **Status now:** since `1955903` the single configured default is
  `gemini-3.6-flash` (section 21 `MODEL_OVERRIDE`), and approval is bound to the model and SDK.
- **SDK version:** the Colab SDK (2.12.1) is older than the version the adapter was checked against offline (2.31.0).

## Final engineering verification (2026-10-16)
- **Owner report:** all notebook code ran successfully in Colab. **Evidence check:** no new executed notebook
  in `colab_import/`, no PhishTriage files in Downloads, and no new commit on the remote. That run is therefore
  **not recorded as evidence**; its revision, outputs, live statuses and widget confirmation are unknown here.
- **Added:** README rewrite, `docs/PROJECT_EXPLAINED.md`, `docs/ARCHITECTURE.md`, `docs/PRESENTATION_GUIDE.md`,
  `docs/VIVA_QUESTIONS.md`, `docs/VERIFICATION.md`, and an updated `docs/DEMO_RUNBOOK.md`.
- **Focused tests** (`tests/test_data_rules.py`): label and exclusion rules, train-only fitting with dev-only
  selection, `.eml` part and attachment limits. Full suite: 122 passed (2.31.0); 121 passed + 1 skipped (2.12.1).
- **Current matrix:** [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Local live check (2026-10-16, code `256f5b2`)
- **Change:** `llm_preflight.load_local_env` copies `GEMINI_API_KEY` (and `PHISHTRIAGE_GEMINI_MODEL`) from the
  git-ignored project-root `.env` with python-dotenv, never overwrites an existing variable, returns names only,
  and does nothing in Colab (Secrets loading unchanged). Section 21 calls it only outside Colab. Section 0 now
  installs `ipywidgets` if missing: an owner's local run had failed at section 28 with `ModuleNotFoundError`.
- **Tests:** 127 passed (2.31.0); 126 passed + 1 skipped (2.12.1).
- **Bounded live run** (Mac, google-genai 2.31.0, scratch copy of the notebook with only `RUN_LLM_PREFLIGHT` and
  `RUN_LIVE_AGENT` on): preflight **ok** for `gemini-3.6-flash` (2 network calls). The one synthetic case
  (`credential_link`) ended **failed / `provider_server`**: 3 × HTTP 503 "high demand", 2 jittered retries, 3
  requests, 0 tool calls. No quota error occurred. No further case was attempted. The key was not found in any
  output or work file.
- **Not shown by this:** a completed live investigation, review or revision at the current code.

## Model comparison and selection (2026-10-17)
- **Comparison** (`7849593`, local, google-genai 2.31.0; [docs/MODEL_SELECTION.md](docs/MODEL_SELECTION.md),
  `reports/model_comparison_20261017.json`): plan frozen first; at most 39 generation requests, enforced by a
  ledger that refuses SDK retries. 22 generation and 4 metadata requests were used.
  - Preflight `ok` for gemini-3.6-flash, gemini-3.8-flash and gemini-3.5-flash-lite.
  - `credential_link` **approved** on all three: 5, 5 and 4 requests; 30.2, 61.2 and 6.1 s.
  - gemini-3.6-flash `benign_notification` **failed**: finalize truncated (`MAX_TOKENS`), then HTTP 429 daily quota.
    That stopped the comparison, and the other two benign cases were not run.
  - A first attempt at `c49d844` sent nothing: the harness let the SDK client close. Fixed.
- **Engineering review** by the assistant (not a human evaluation): findings grounded, no invented IDs, tools or
  authentication, classifier unchanged. Some recommended actions cite playbooks that do not contain them.
- **Fixes:**
  - `temperature` removed (deprecated for Gemini 3.8 Flash);
  - output-token caps raised to 4096/8192, because thinking counts against them;
  - error categories now recorded.
- **Default:** `gemini-3.8-flash`, provisional (`3e7cbe1`). Not yet run live with the new caps.
- **Tests:** 137 passed (2.31.0); 136 + 1 skipped (2.12.1).
- **Local notebook:** a fresh Python 3.11 kernel ran sections 0–30 with no errors, and section 0 installed ipywidgets.
  Colab rendering is still unverified.

## Recovery and reconciliation (2026-10-16)
- **Gemini's runtime work:** reported as a quota-abort patch in `agent.py`, `run_batch_triage`,
  `tests/test_quota_handling.py`, repeated `preflight_not_passed` runs, mocking of `run_triage`, a final
  `AttributeError` on `.report`, and `/content/phishtriage_handoff_package.tar.gz`.
- **None of it reached GitHub or this Mac.** `f2b7277` changed only the notebook; there was no `colab_import/`
  folder and no matching file in Downloads. **Nothing was recovered.**
- **Reimplemented and verified here (`e635833`):**
  - **Quota:** 429 is no longer retried and ends the case with `provider_quota`.
  - **Batch:** `run_batch_triage` stops later submissions after quota, auth or unavailable-model errors, and
    marks those cases skipped. Its entries expose `.result` and `.report`, which are `None` when skipped.
  - **Diagnostics:** reports carry a `termination_detail`; the preflight reports `quota_exceeded`.
  - **Tests:** real-orchestration and batch-control tests.
- **Not adopted:** weakening the preflight gate or mocking `run_triage` to test retries. The live gate is
  unchanged.
- **Optional:** if that Colab runtime still exists, `docs/colab_recovery_cell.py` archives its edits read-only
  for comparison.

## Stage 2 evidence (local, 2026-10-15)
- **Environment:** macOS, 10 CPUs, Python 3.13.7, scikit-learn 1.9.1, pandas 3.0.6, numpy 2.5.4.
  The notebook ran end to end from a clean tree at code commit `e19b8cc`.
- **Phase 1 reproduced:** the refactored package regenerates `split_manifest.csv` and `audit_summary.json`
  byte-for-byte.
- **Test set (847 emails: 614 legitimate / 233 phishing), evaluated once with frozen configurations:**

  | Model | F1 (phishing) | FPR | Avg. precision | FP / FN |
  |---|---|---|---|---|
  | LR, original | 0.991 | 0.000 | 0.9995 | 0 / 4 |
  | NB, original | 0.989 | 0.005 | 0.9973 | 3 / 2 |
  | LR, artifact-normalized (primary) | 0.991 | 0.007 | 0.9998 | 4 / 0 |
  | NB, artifact-normalized | 0.978 | 0.000 | 0.9999 | 0 / 10 |

  Because source and class are perfectly confounded, these scores cannot be attributed to generalizable
  phishing detection.
  Removing the known artifacts barely changed them, and residual corpus cues remain. See `docs/MODEL_EVALUATION.md`.
- **Tests:** `pytest tests` → 33 passed (local, offline).

## Stage 3 evidence (local, 2026-10-15)
- **Run:** the full notebook ran end to end (sections 0–22) at code commit `86993a3` with a clean tree. Phase 1–2
  outputs reproduced exactly: the metrics, frozen configurations, audit and split manifest are identical apart
  from timings and timestamps.
- **Tools:** `get_prediction`, `inspect_email`, `retrieve_playbook`, `get_evidence`.
  - In the failure checks, the unknown case, cross-case evidence, unknown evidence ID, unknown tool, unexpected
    argument and empty query were all `rejected`, and the irrelevant query returned `unavailable`.
  - Synthetic demo cases: the `.eml` case had 13 observed items and 1 unverified claim. The pasted case had
    5 observed and 4 unavailable.
- **Retrieval check set** (16 queries, written before running): 12/12 top-1, 4/4 correct abstentions.
  I wrote both the playbooks and the queries, so this shows vocabulary consistency, not real retrieval quality.
- **Colab bootstrap:** the checkout logic was exercised against GitHub in a scratch folder. It covered a fresh
  checkout, re-runs fetching the requested revision, a full SHA, a short SHA being rejected, a modified checkout
  being left untouched, a non-git folder not being overwritten, and a wrong remote being refused.
  This ran outside Colab.
- **LLM preflight:** **unverified.** There was no `GEMINI_API_KEY` in this environment. The request objects were
  validated offline against `google-genai` 2.31.0. CrewAI was not adopted: its `google-genai~=1.65` pin conflicts
  with 2.31.0, and it brings about 141 packages.
- **Tests:** `pytest tests` → 57 passed (local, offline; network blocked in the phase 3 tests).

## Stage 4 evidence (local, 2026-10-15)
- **Workflow:** the model chooses tool calls within budgets (3 rounds, 5 executions, 6 requests, 90 s), with the
  case bound by the application. Finalization runs with tools disabled and a JSON schema. Deterministic citation
  and claim checks follow, then a separate reviewer, at most one revision, and otherwise needs_human_review.
- **Modes:** live (Gemini, preflight-gated), scripted replay (labelled not live), evidence-only (no LLM).
- **Replay demos** (synthetic emails, scripted turns, workflow only):
  - The credential case was approved after one reviewer correction.
  - The prompt-injection case cited the injected instruction as evidence and did not obey it.
  - The ambiguous case returned insufficient_evidence.
  - In the benign notification, the classifier says **phishing** (≈ 0.90) while the replay assessment is
    no_strong_indicators. The report surfaces this as a warning, consistent with the dataset confound.
- **Tests:** `pytest tests` → 80 passed (local, offline). The 23 agent tests cover multi-turn tool use, reviewer
  correction, unresolved review, cross-case and invented citations, invalid and duplicate calls, the tool, request
  and deadline budgets, timeout retry, non-retryable provider errors, malformed output, modes and missing
  credentials, prompt injection, and the Gemini protocol (via a fake client).
- **Notebook:** sections 0–27 ran locally at `30a2378`, and phase 1–3 outputs reproduced exactly.
  The live agent was skipped (`RUN_LIVE_AGENT = False`, no key).

## Blockers and open risks
- **Live path:** only user-reported historical results exist (above), at an unrecorded revision. The `e635833`
  fixes have not run in Colab.
- **Addressed in `1955903` (offline-tested, not yet verified live):**
  - Absence claims are now checked against evidence status (`observed_absent` vs `unavailable`).
  - Server errors use bounded jittered backoff.
  - Request and time capacity is reserved for finalize and review.
  - The model configuration has one source, with approval bound to the model and SDK.
  - The deterministic absence check covers common phrasings only.
- **Confounded data:** source = label in every split; no external validation set (searched once on 2026-10-15,
  recorded as pending); residual cues `utf`/`url`/topics; a ~15-year date gap.
- **Fresh live verification of the current code** is still useful, but it is not a prerequisite for offline
  implementation work. The key lives in Colab Secrets only; live calls stay opt-in.
- **Colab uses pandas 2.x and possibly a different scikit-learn minor version.** Models are retrained in the
  runtime, so artifacts are never moved across versions.

## Checkpoint (2026-10-16, after phase 5)
- **Branch:** `phishtriage-colab`. The latest code is `f6642c9` (final-verification prep, on top of phase 5
  `1955903`); the evidence commit follows it (see `git log`). `main` is untouched at `170260b`.
- **Notebook:** 70 cells, sections 0–30, outputs cleared, `RUN_LLM_PREFLIGHT`, `RUN_LIVE_AGENT`,
  `RUN_ALL_LIVE_CASES` and `WIDGETS_CONFIRMED_BY_PERSON` all `False`. *Run all* never calls the API or waits for input.
- **Configured live model:** `gemini-3.6-flash` at that checkpoint (since `3e7cbe1`: `gemini-3.8-flash`; see
  the model-comparison entry). Section 21 `MODEL_OVERRIDE` changes it; a new preflight is then required.
- **Tests:** 119 offline tests pass (google-genai 2.31.0); 118 pass + 1 skipped on google-genai 2.12.1.
- **Widget rendering in Colab:** UNVERIFIED until a person confirms it in section 30.
- **Unchanged:** the frozen phase 2 configurations, thresholds and reports, and the split manifest. Re-runs
  reproduce them exactly.

## Next action (owner)
1. Download the executed notebook from your successful Colab run (*File → Download → Download .ipynb*) into
   `colab_import/`, plus `/content/phishtriage/outputs/final_verification.json` and `phase5_verification.json`
   if the runtime is still alive. These close the open rows in `docs/VERIFICATION.md`.
2. If that runtime is gone: follow `docs/DEMO_RUNBOOK.md` steps 1–6 in a fresh runtime pinned to the latest SHA,
   then download the same files.
