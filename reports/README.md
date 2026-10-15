# reports/

Small, non-sensitive evidence only. No message text, raw data or model files.

| File | Content |
|---|---|
| `dataset_provenance.json` | Source URLs, checksums, retrieval status, label mapping, rejected candidates, package versions |
| `audit_summary.json` | Aggregate data-audit counts (phase 1) |
| `split_manifest.csv` | `record_id, group_id, split, mapped_label`. IDs are row indices into the checksum-pinned public files |
| `figures/*.png` | Class balance and text-length plots |
| `PhishTriage_Colab_Executed.ipynb` | *Not created yet.* A sanitized copy of the canonical notebook after a **genuine** *Restart and run all* in Colab. Its outputs must never be fabricated. |

The current files come from a **local** run on 2026-10-15; `environment` in `dataset_provenance.json` says
`local`. Replace them with the Colab-generated versions once the notebook has run in Colab.
