# PhishTriage: Colab status

**Deadline:** 19 Oct 2026 (Colab demonstration) · **Last updated:** 2026-10-15

## Phases
`PhishTriage_Colab_Roadmap_and_Prompts.txt` is **still not in the repository** (rechecked 2026-10-15).
The phases follow the owner's prompts. Phase 1 took in the old "preprocessing" step, and the old
"baseline model" and "evaluation" steps are now one phase, matching the owner's stated next phase.

| # | Phase | Status | Evidence |
|---|-------|--------|----------|
| 0 | Repository & notebook scaffolding | Done | Commit `170260b` on `origin/main` |
| 1 | Data acquisition, audit & leakage-resistant splits | **Done locally; waiting for the first Colab run** | `docs/DATASET_CARD.md`, `reports/audit_summary.json`, `reports/dataset_provenance.json` (`environment: local`) |
| 2 | Classifier training & evaluation (dev/test, confound stress tests) | Not started | |
| 3 | Triage: risk score, verdict and indicator explanations | Not started | |
| 4 | Interactive demo in Colab (ipywidgets) | Not started | |
| 5 | Executed, sanitized report notebook | Not started | `reports/PhishTriage_Colab_Executed.ipynb` doesn't exist yet |

## Phase 1 evidence (local run, 2026-10-15; Python 3.13.7, pandas 3.0.6)
- **Dataset:** Champa *Phishing Email Curated Datasets* (Zenodo 8339691, CC-BY-4.0). Nazario = phishing,
  SpamAssassin ham = legitimate, SpamAssassin spam excluded.
  MeAJOR v2.0 was rejected because its data file contains only TREC spam/ham. See the dataset card.
- **Counts:** 7,374 loaded → 5,642 included (4,090 legitimate / 1,552 phishing).
  Excluded: 1,718 spam, 14 exact-duplicate copies.
- **Splits:** train 3,949 / dev 846 / test 847, grouped by near-duplicate clusters (Jaccard ≥ 0.8).
  All leakage, coverage and reproducibility assertions passed.
- **Downloader:** a fresh run downloaded both files and verified their SHA-256. A second run reused the
  verified cache. The split manifest and audit summary were byte-identical across runs.
- **Failure-path harness:** 13/13 checks passed (scratch script, not committed). It covered corrupted-cache
  re-download, cache reuse, a 404 with no retries, the size-mismatch guard, the upload fallback (clear error
  when the file is missing; checksum mismatch flagged), schema rejection of bad files, and sanitizer redaction.
- **Not yet verified:** execution in Google Colab, including the `files.upload()` fallback and pandas 2.x
  compatibility (Colab ships pandas 2.x; the local run used 3.0.6).

## Setup log
- 2026-10-15: Local repository initialized on `main` at `~/Desktop/PhisingMail_project`.
  Local author name set to `Nishant Tripathi`; global config left unchanged.
- 2026-10-15: Scaffolding created. The notebook skeleton passes `nbformat.validate`.
  Its environment-check cell ran locally. It has **not yet run in Colab**.
- 2026-10-15: GitHub repository `nishtrip14/PhishTriage` already existed
  (created 2026-10-15 12:16 UTC). It was empty, with no branches, and its visibility is **PUBLIC**.
  The owner chose to keep it public and use it as `origin`.
- 2026-10-15: Initial commit `170260b` pushed to `https://github.com/nishtrip14/PhishTriage` (`main`).
  Checked with `git ls-remote`. Local development branch `phishtriage-colab` created.
- 2026-10-15: Phase 1 implemented on `phishtriage-colab` and pushed to `origin/phishtriage-colab`.

## Blockers
- **No Colab run yet.** Phase 1 cannot be marked fully done until the notebook runs in a fresh Colab runtime.
- **Dataset confounds** (source = label, collection artifacts, a temporal gap of about 15 years) are documented,
  not fixed. Phase 2 must report them and stress-test models against them.

## Next action
1. Owner: open the notebook in Colab from `phishtriage-colab`, *Runtime → Run all*, and send back the outputs
   requested in the handoff.
2. Then phase 2: train and evaluate classifiers. Fit only on `train`, tune on `dev`, report `test` once, and add
   artifact-masked stress tests.
