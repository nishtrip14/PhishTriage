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
| 2 | Classifier training & evaluation | **Done locally (this phase); Colab verification pending** | `docs/MODEL_EVALUATION.md`, `reports/phase2_metrics.json`, code `e19b8cc` |
| 3 | Local evidence tools & playbook retrieval (RAG over a small, cited playbook corpus) | Not started | |
| 4 | Bounded investigator and reviewer agents (tool budget, step limit, cited findings) | Not started | |
| 5 | Notebook interface, report export & agent evaluation | Not started | |
| 6 | Fresh-runtime verification & final submission (`reports/PhishTriage_Colab_Executed.ipynb`) | Not started | |

## Colab verification log
- No Colab evidence yet: there is no `colab_import/` folder and no run output from the owner. Everything below
  ran **locally**.

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

## Blockers and open risks
- **No Colab run of either phase yet.** Both stages stay "pending" until an executed Colab notebook or the run
  output is supplied.
- **Confounded data:** source = label in every split; no external validation set (searched once on 2026-10-15,
  recorded as pending); residual cues `utf`/`url`/topics; a ~15-year date gap.
- **Colab uses pandas 2.x and possibly a different scikit-learn minor version.** Models are retrained in the
  runtime, so artifacts are never moved across versions.

## Next action
1. Owner: run sections 0–15 in a fresh Colab runtime and send back the outputs requested in the handoff.
2. Stage 3: build local evidence tools (classifier tool around `predict()`, header/text indicator extractors)
   and playbook retrieval with citations.
