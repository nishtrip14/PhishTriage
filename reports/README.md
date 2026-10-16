# reports/

Small, non-sensitive evidence only. No message text, raw data or model binaries.

| File | Content |
|---|---|
| `dataset_provenance.json` | Source URLs, checksums, retrieval status, label mapping, rejected candidates, environment, code commit |
| `audit_summary.json` | Aggregate data-audit counts (phase 1) |
| `split_manifest.csv` | `record_id, group_id, split, mapped_label`. IDs are row indices into the checksum-pinned public files |
| `frozen_configs.json` | Dev-selected parameters, thresholds and the dev grid, frozen before the test evaluation |
| `phase2_metrics.json` | Protocol, length policy, normalization effect, dev and test metrics, timings, influential terms |
| `phase2_model_comparison.csv` | One row per frozen configuration (test metrics) |
| `model_manifests.json` | Manifests of the locally saved models (no binaries) |
| `retrieval_check.json` | Phase 3 retrieval check-set results (16 predeclared queries) |
| `phase3_summary.json` | Phase 3 tool failure checks, synthetic demo evidence counts, pipeline summary, LLM preflight status |
| `phase4_summary.json` | Phase 4 runs kept separate by mode: scripted replay (not live), evidence-only, live (skipped so far) |
| `colab_run_9acefcb.json` | Sanitized, text-free extract of the **genuine Colab run** (outputs saved in `f2b7277`, code `9acefcb`): environment, partitions, phase 2 tables, retrieval and phase 3/4 summaries |
| `phase5_verification.json` | Synthetic verification records from the interface session (evidence-only and replay; **no live records locally**) and automated interface/export checks |
| `final_verification.json` | Section 30 summary: environment, commit and dirty state, versions, configured model, preflight status in that runtime, live attempts, check results |
| `figures/*.png` | Class balance, text length, test PR curves, test confusion matrices |
| `PhishTriage_Colab_Executed.ipynb` | *Not created yet.* A sanitized copy of the notebook after a **genuine** fresh-runtime Colab run. Its outputs must never be fabricated. |

**Source versions verified (all local runs on 2026-10-15, `environment: local`):**
- Phase 1–2 files: code commit `e19b8cc`, clean tree. Re-running at `86993a3` reproduced them exactly, apart from
  timings, so they were left unchanged.
- Phase 3 files: code commit `86993a3`, clean tree. Reproduced exactly at `30a2378`.
- `phase3_summary`: code commit `1955903` (reproduced at `f6642c9`). `phase4_summary`, `phase5_verification`,
  `final_verification`: code commit `f6642c9`, clean tree, local, live flags off. Widget rendering is recorded
  as UNVERIFIED. The phase 3 counts changed by design: `observed_absent` and
  `cue_scan` were added.
- `colab_run_9acefcb.json`: genuine Colab outputs at code `9acefcb` (run B in `docs/MODEL_EVALUATION.md`). The
  differences from the local run are observed across environments; the cause is not established.
- User-reported live preflight and agent results are recorded in `COLAB_STATUS.md` only. No artifact for them exists here.

The local reports stay canonical. Colab evidence is kept alongside them, not swapped in.
