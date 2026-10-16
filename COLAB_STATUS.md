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
| 2 | Classifier training & evaluation | **Done; verified locally and in Colab** (Colab scikit-learn 1.6.1 gives slightly different thresholds; see `docs/MODEL_EVALUATION.md`) | `docs/MODEL_EVALUATION.md`, `reports/phase2_metrics.json`, code `e19b8cc` |
| 3 | Local evidence tools & playbook retrieval (RAG over a small, cited playbook corpus) | **Done; verified locally and in Colab.** Live LLM preflight never run. | `docs/TOOLS_AND_EVIDENCE.md`, `reports/retrieval_check.json`, `reports/phase3_summary.json`, code `86993a3` |
| 4 | Bounded investigator and reviewer agents (tool budget, step limit, cited findings) | **Implemented and offline-tested; replay and evidence-only verified in Colab (`9acefcb`).** Quota/batch fixes (`e635833`) not yet run in Colab; live provider never run. | `docs/AGENT_WORKFLOW.md`, `reports/phase4_summary.json`, `reports/colab_run_9acefcb.json`, code `e635833` |
| 5 | Notebook interface, report export & agent evaluation | Not started | |
| 6 | Fresh-runtime verification & final submission (`reports/PhishTriage_Colab_Executed.ipynb`) | Not started | |

## Verification matrix (as of 2026-10-16)
| Stage | Implementation | Offline tests | Local notebook run | Genuine Colab run | Live provider |
|---|---|---|---|---|---|
| 1 Data | done | yes | yes | **yes** (`9acefcb`; identical split) | n/a |
| 2 Classifier | done | yes | yes (reproduced exactly) | **yes** (scikit-learn 1.6.1: small threshold/metric differences, see `docs/MODEL_EVALUATION.md`) | n/a |
| 3 Evidence, retrieval, tools | done | yes | yes | **yes** (results identical) | preflight **never run** |
| 4 Agents | done (+ quota/batch fixes `e635833`) | yes (89 tests total) | yes, at `e635833` | **yes, offline paths only** (replay and evidence-only at `9acefcb`; live skipped) | **never run** |

- **Local:** this Mac (Python 3.13.7, pandas 3.0.6, scikit-learn 1.9.1).
- **Colab:** Python 3.13.16, pandas 2.2.3, scikit-learn 1.6.1, 2 CPUs. The outputs were saved in commit
  `f2b7277`. A sanitized extract is in `reports/colab_run_9acefcb.json`.
- The `e635833` fixes have **not** run in Colab yet.

## Colab verification log
- 2026-10-15: no Colab evidence existed yet; phases 1–4 were verified locally only.
- **2026-10-16:** commit `f2b7277` ("Adding Gemini API", notebook only) contains genuine Colab outputs.
  - **Run:** one consecutive error-free pass over sections 0–27 at code commit `9acefcb`.
  - **Flag edit:** cell 50's source was edited to `RUN_LLM_PREFLIGHT = True` **after** that run; its saved output
    shows the preflight skipped. No live Gemini call is evidenced anywhere.
  - **Raw notebook:** kept untracked in `colab_import/` (SHA-256 `e271c5d2…`).

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

  These scores measure separation between two corpora, **not** real-world phishing detection.
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
- **Live Gemini path is unverified** (no evidenced preflight or live call). The `e635833` fixes have not run in
  Colab yet.
- **Confounded data:** source = label in every split; no external validation set (searched once on 2026-10-15,
  recorded as pending); residual cues `utf`/`url`/topics; a ~15-year date gap.
- **No live LLM call yet (main blocker for the agent demo).** Smallest fix: add the `GEMINI_API_KEY` Colab
  secret, set `RUN_LLM_PREFLIGHT = True` (section 21) and `RUN_LIVE_AGENT = True` (section 26), then run them.
  If `gemini-3.8-flash` is not available to the account, set `PHISHTRIAGE_GEMINI_MODEL` to a model that passes
  the preflight.
- **Colab uses pandas 2.x and possibly a different scikit-learn minor version.** Models are retrained in the
  runtime, so artifacts are never moved across versions.

## Checkpoint for the next phase
- **Branch:** `phishtriage-colab` at the reconciliation commits (see `git log`); `main` untouched at `170260b`.
- **Canonical notebook:** 64 cells, sections 0–27, outputs cleared, `RUN_LLM_PREFLIGHT = False`,
  `RUN_LIVE_AGENT = False`.
- **Tests:** 89 offline tests pass.
- **Frozen phase 2 configurations and reports unchanged.**

## Next action
1. Owner (about 10 minutes):
   1. In a **fresh** runtime, set `PHISHTRIAGE_REVISION` to the latest full SHA and run sections 0–27.
   2. Add the `GEMINI_API_KEY` secret, set `RUN_LLM_PREFLIGHT = True` and run section 21.
   3. If the status is `ok`, set `RUN_LIVE_AGENT = True` with `LIVE_CASES = ["credential_link"]` and run sections 26–27.
   4. Save the notebook to `colab_import/` or GitHub. Reset both flags to False before any commit.
2. Stage 5: notebook interface (ipywidgets), report export and agent evaluation, built on `run_triage` /
   `run_batch_triage`.
