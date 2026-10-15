# PhishTriage

PhishTriage is an academic project that triages suspicious email for phishing risk.
It runs entirely in **Google Colab**: no local backend, Docker or database server.

**Status:** initial setup. See [COLAB_STATUS.md](COLAB_STATUS.md).

## Run in Colab

1. Open `notebooks/PhishTriage_Colab.ipynb` in Colab
   (*File → Open notebook → GitHub*, repository `nishtrip14/PhishTriage`,
   branch `phishtriage-colab` or `main`).
2. *Runtime → Run all*.

Data is downloaded at runtime from Zenodo, checked against a pinned checksum, and never committed:
Nazario phishing vs SpamAssassin legitimate mail, from the *Phishing Email Curated Datasets* record
(10.5281/zenodo.8339691, CC-BY-4.0). See [docs/DATASET_CARD.md](docs/DATASET_CARD.md) for provenance,
label mapping, audit counts and known confounds.

## Repository layout

| Path | Purpose |
|------|---------|
| `notebooks/PhishTriage_Colab.ipynb` | Canonical development notebook (source of truth) |
| `reports/PhishTriage_Colab_Executed.ipynb` | Sanitized, genuinely executed demo copy (created after a real Colab run) |
| `docs/COLAB_WORKFLOW.md` | How to sync changes between GitHub and Colab safely |
| `COLAB_STATUS.md` | Phase progress, evidence, blockers, next action |
| `CLAUDE.md` | Project rules for AI-assisted development |

Deadline for the Colab demonstration: **19 October 2026**.
