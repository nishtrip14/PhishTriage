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
| `figures/*.png` | Class balance, text length, test PR curves, test confusion matrices |
| `PhishTriage_Colab_Executed.ipynb` | *Not created yet.* A sanitized copy of the notebook after a **genuine** fresh-runtime Colab run. Its outputs must never be fabricated. |

**Source version verified:** the current files come from a **local** run on 2026-10-15 at code commit `e19b8cc`
(clean tree), with `environment: local`. Colab-generated versions will replace them once a Colab run is supplied.
