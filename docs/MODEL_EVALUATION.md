# Phase 2: baseline evaluation and artifact sensitivity

**Verification:** a local run on 2026-10-15 (macOS, 10 CPUs, Python 3.13.7, scikit-learn 1.9.1, pandas 3.0.6),
at code commit `e19b8cc` with a clean tree. **This has not been verified in Colab yet.**
Numbers are copied from `reports/phase2_metrics.json`, which the notebook wrote during that run.

## What these numbers mean
This is a **confounded benchmark**. Every phishing email comes from the Nazario honeypot corpus (2015–2022), and
every legitimate email from SpamAssassin mailing-list ham (about 2002). Grouped splitting stops duplicates and
near-duplicates from crossing splits. It does **not** remove the source–label confound.

The scores below therefore measure how well the two corpora can be told apart. They are **not** real-world
phishing-detection accuracy, and they say nothing about generalization to unseen sources. Leave-one-source-out
evaluation was not run, because each source contains only one class.

## Protocol (fixed before the test run)
- **Data:** the committed `reports/split_manifest.csv`: train 3,949, dev 846, test 847.
  Test has 614 legitimate and 233 phishing emails (27.5% phishing).
- **Pipeline:** `TextPreprocessor → TfidfVectorizer → classifier`. The vectorizer uses word 1–2-grams,
  min_df 2, max_df 0.95, at most 50k features, sublinear TF and float32 sparse matrices. Everything learned
  is fitted on **train only**. The only input is `text` (subject + body).
- **Selection:** grid points scored by dev average precision. The threshold is the one maximizing dev phishing-F1.
  The configurations were then frozen and hashed (`reports/frozen_configs.json`) before the test split was used.
- **Test:** each configuration was evaluated on test once. No calibration was done, because there is no separate
  calibration partition. Scores are uncalibrated `predict_proba` estimates.
- **Input-length policy:** keep the first 20,000 characters and flag the input as truncated. The train 99.5th
  percentile is 19,895 characters. 30 records are affected: train 19 legitimate + 1 phishing, dev 4 + 0,
  test 5 + 1.

## Frozen configurations
| Model | Selected | Dev AP | Threshold | Dev F1 |
|---|---|---|---|---|
| LR, original text | C = 10 | 0.99995 | 0.550 | 0.998 |
| NB, original text | α = 0.1, learned prior | 1.00000 | 0.409 | 1.000 |
| LR, artifact-normalized | C = 10 | 0.99962 | 0.261 | 0.989 |
| NB, artifact-normalized | α = 0.1, learned prior | 0.99863 | 0.929 | 0.987 |

Dev AP is close to 1 everywhere, so the selection only separates near-ties. C = 10 is at the edge of the grid.
NB's prior setting does not change its ranking (a prior shifts every log-odds score equally), so the tie went to
the first option.

## Held-out test results
| Model | Precision | Recall | F1 (phishing) | Macro-F1 | FPR | Avg. precision | FP | FN | Fit (s) | ms/email |
|---|---|---|---|---|---|---|---|---|---|---|
| LR, original | 1.000 | 0.983 | 0.991 | 0.994 | 0.000 | 0.9995 | 0 | 4 | 1.48 | 0.15 |
| NB, original | 0.987 | 0.991 | 0.989 | 0.993 | 0.005 | 0.9973 | 3 | 2 | 1.35 | 0.14 |
| LR, artifact-normalized | 0.983 | 1.000 | 0.991 | 0.994 | 0.007 | 0.9998 | 4 | 0 | 1.79 | 0.31 |
| NB, artifact-normalized | 1.000 | 0.957 | 0.978 | 0.985 | 0.000 | 0.9999 | 0 | 10 | 1.66 | 0.30 |

Timings are wall-clock times on the local machine above. Fitting covers train only, including preprocessing.
Figures: `reports/figures/pr_curves.png` and `reports/figures/confusion_matrices.png`.
With about 4–10 errors per configuration, the differences between models are within noise.

## Artifact-sensitivity findings
- **Normalization effect on train+dev:** prevalence fell from 39.6% to 0.1% for `monkey.org` in phishing, from
  60.8% to 0% for mailing-list footers in legitimate mail, from 86.5% to 0% for literal links in legitimate mail,
  and from 56%/49% to about 0% for years. 5 legitimate texts became empty (train 3, dev 1, test 1).
- **Performance barely moved.** Test F1 and AP stay at about 0.98–1.00. Removing the known cues did **not** make
  the task harder in any meaningful way.
- **Influential LR terms** (training coefficients, top 20 per direction, checked against a predeclared
  artifact-token list):
  - On original text, 20% of the phishing terms are artifacts (`jose`, `monkey`, `monkey org`, `jose monkey`),
    and 55% of the legitimate terms are (`http`, `2002`, `www`, `com`, `list`, `mailman`, `listinfo`, …).
  - After normalization, the shares are 0% (phishing) and 10% (legitimate). The top phishing terms become
    phishing-like language (`your`, `account`, `email`, `payment`, `password`, `click`, `security`, `alert`).
- **Cues left over after normalization, not on the predeclared list:** `utf` is a strong phishing term,
  probably encoding residue from HTML-to-text conversion. `url` is the top legitimate term: SpamAssassin posts
  contain the literal label "URL:" even after the link is removed. Mailing-list topic words also remain
  (`apt`, `linux`, `cvs`, `razor`, `irish`, `wrote`).
  These were found **after** the test run, so the rules were not changed. They are candidates for a future rule
  revision, which must be checked on dev only.
- **Conclusion:** normalization removes the obvious collection cues but not the corpus separation. Style, topic
  and encoding still identify the source. This is a sensitivity analysis. It does not show that the confound has
  been eliminated.

## Error notes (LR models, sanitized in the notebook)
- **Original:** 4 false negatives. One is a Nazario mailbox-format pseudo-message ("DON'T DELETE THIS MESSAGE --
  FOLDER INTERNAL DATA"), which is a label-quality problem, not phishing. Others are a password-alert phishing
  email whose recipient list is entirely addresses, and a "purchase order" file-share lure.
- **Normalized:** 4 false positives, all promotional or automated legitimate mail (a Red Hat errata alert, a
  German job-fair announcement, a horoscope newsletter).

## Inference contract (`phishtriage.inference`)
`predict(model, manifest, subject=..., body=...)` returns:
- `model_id`, `predicted_label` (`phishing` / `legitimate`, or `None` when it abstains), `score`
- `score_type = model_estimated_probability_uncalibrated`, `threshold`
- `warnings`: missing subject/body, truncation, empty input, empty after normalization
- fixed `limitations`, `input_chars`, `truncated` and `preprocessing_version`

Artifacts (`model.joblib` + `manifest.json`, 2–3.5 MB each) stay in the working directory, outside Git. Loading
checks the SHA-256, the preprocessing version and the scikit-learn minor version, and raises `ArtifactError`
otherwise. **Primary model for later agent tools** (declared before the test run): LR on artifact-normalized text.

## Runs across environments
The historical results above are the canonical local run and are left unchanged. Each run is recorded separately,
and nothing was retuned after any test evaluation.

| | Run A: local (canonical reports) | Run B: Google Colab |
|---|---|---|
| Code revision | `e19b8cc` (re-run with identical results at `86993a3`, `30a2378`, `e635833`) | `9acefcb` (outputs saved in `f2b7277`) |
| Environment | macOS, 10 CPUs, Python 3.13.7, numpy 2.5.4, scipy 1.18.1, pandas 3.0.6, scikit-learn 1.9.1 | Colab, 2 CPUs, Python 3.13.16, numpy 2.1.3, scipy 1.16.3, pandas 2.2.3, scikit-learn 1.6.1 |
| Data and split | pinned SHA-256 files; manifest `dd51c8e6…` | same files (verified); same manifest SHA-256 |
| Selected hyperparameters | LR C=10; NB α=0.1, learned prior (both variants) | identical |

| Model | Threshold A → B | Test FP / FN A → B | Test F1 A → B | Test AP A → B |
|---|---|---|---|---|
| LR, original | 0.5499 → 0.5488 | 0/4 → 0/3 | 0.9913 → 0.9935 | 0.9995 → 0.9995 |
| NB, original | 0.4086 → 0.4688 | 3/2 → 3/2 | 0.9893 → 0.9893 | 0.9973 → 0.9973 |
| **LR, artifact-normalized (primary)** | 0.2606 → 0.2547 | 4/0 → 4/0 | 0.9915 → 0.9915 | 0.9998 → 0.9998 |
| NB, artifact-normalized | 0.9285 → 0.8471 | 0/10 → 1/4 | 0.9781 → 0.9892 | 0.9999 → 0.9999 |

**Interpretation.** The differences were *observed across environments* that differ in several library versions
and CPU count. Library-version differences (for example in the TF-IDF or liblinear implementations) are a
**plausible explanation**, but it is **not established**: no controlled run varied one factor at a time.

The differences are a handful of errors at most and do not change any conclusion. Quote any number together with
its run (A or B). Run B evidence: `reports/colab_run_9acefcb.json` (sanitized extract).

## Validity limitations still open
1. Source = label in every split. No external or unseen-source validation exists yet. One focused search on
   2026-10-15 found only feature-only, URL-only, SMS or LLM-generated sets, or sets that reuse Nazario.
2. Residual cues remain after normalization: style, topic and encoding (`utf`, `url`).
3. There is a temporal gap of about 15 years between the classes.
4. Link targets were stripped from the phishing bodies, so URL analysis is impossible with this data.
5. Labels contain some noise (for example, mailbox pseudo-messages labelled as phishing).
6. Scores are uncalibrated, and thresholds come from a dev set where performance was near the ceiling.
7. All results are from a local run. Colab verification is still pending.
