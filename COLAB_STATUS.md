# PhishTriage: Colab status

**Deadline:** 19 Oct 2026 (Colab demonstration) · **Last updated:** 2026-10-15

## Project plan
PhishTriage is an **agentic** triage project. The classifier is one evidence tool for the investigator and
reviewer agents; it is not the deliverable on its own.
`PhishTriage_Colab_Roadmap_and_Prompts.txt` is **still not in the repository** (rechecked 2026-10-15). The stages
below follow the owner's prompts.

| # | Stage | Status | Evidence |
|---|-------|--------|----------|
| 0 | Repository & notebook scaffolding | Done | `170260b` on `origin/main` |
| 1 | Data acquisition/audit & Colab verification | **Done locally; Colab verification pending** (no executed Colab notebook supplied yet) | `docs/DATASET_CARD.md`, `reports/audit_summary.json`, `reports/split_manifest.csv` |
| 2 | Classifier training & evaluation | **Done locally; Colab verification pending** | `docs/MODEL_EVALUATION.md`, `reports/phase2_metrics.json`, code `e19b8cc` |
| 3 | Local evidence tools & playbook retrieval (RAG over a small, cited playbook corpus) | **Done locally; Colab verification pending.** Live LLM preflight unverified (no credentials). | `docs/TOOLS_AND_EVIDENCE.md`, `reports/retrieval_check.json`, `reports/phase3_summary.json`, code `86993a3` |
| 4 | Bounded investigator and reviewer agents (tool budget, step limit, cited findings) | **Implemented; offline-tested; local notebook run.** Colab and live-provider verification pending. | `docs/AGENT_WORKFLOW.md`, `reports/phase4_summary.json`, code `30a2378` |
| 5 | Notebook interface, report export & agent evaluation | Not started | |
| 6 | Fresh-runtime verification & final submission (`reports/PhishTriage_Colab_Executed.ipynb`) | Not started | |

## Verification matrix (as of 2026-10-15)
| Stage | Implementation | Offline tests | Local notebook run | Genuine Colab run | Live provider |
|---|---|---|---|---|---|
| 1 Data | done | yes | yes | **pending** | n/a |
| 2 Classifier | done | yes | yes (reproduced exactly) | **pending** | n/a |
| 3 Evidence, retrieval, tools | done | yes | yes | **pending** | preflight **never run** (no key) |
| 4 Agents | done | yes (80 tests total) | yes, at `30a2378` | **pending** | **never run** (no key) |

"Local" means this Mac (Python 3.13.7, pandas 3.0.6, scikit-learn 1.9.1). Nothing here has been verified in
Google Colab or against the Gemini API.

## Colab verification log
- Rechecked 2026-10-15 (phases 3 and 4): still no `colab_import/` folder and no run output from the owner.
  Nothing has been verified in Colab yet, and everything below ran **locally**.

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
- **No Colab run of any phase yet.** Stages 1–4 stay "pending" until an executed Colab notebook or the run
  output is supplied.
- **Confounded data:** source = label in every split; no external validation set (searched once on 2026-10-15,
  recorded as pending); residual cues `utf`/`url`/topics; a ~15-year date gap.
- **No live LLM call yet (main blocker for the agent demo).** Smallest fix: add the `GEMINI_API_KEY` Colab
  secret, set `RUN_LLM_PREFLIGHT = True` (section 21) and `RUN_LIVE_AGENT = True` (section 26), then run them.
  If `gemini-3.8-flash` is not available to the account, set `PHISHTRIAGE_GEMINI_MODEL` to a model that passes
  the preflight.
- **Colab uses pandas 2.x and possibly a different scikit-learn minor version.** Models are retrained in the
  runtime, so artifacts are never moved across versions.

## Next action
1. Owner: in a fresh Colab runtime, run sections 0–27. Then, with the secret configured, run section 21
   (`RUN_LLM_PREFLIGHT = True`) and section 26 (`RUN_LIVE_AGENT = True`), and section 27 again. Send back the
   outputs listed in the handoff, or place the downloaded notebook in `colab_import/`.
2. Stage 5: notebook interface (ipywidgets), report export and agent evaluation.
