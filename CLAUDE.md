# PhishTriage: project rules

Academic phishing-email triage project. **Deliverable:** a notebook that runs top to
bottom in Google-hosted Colab by **19 Oct 2026**.

## Hard constraints
- Everything runs in Colab: no local server, separately hosted backend, Docker or database server.
  Dependencies must be pip-installable in a notebook cell.
- `notebooks/PhishTriage_Colab.ipynb` is the single canonical notebook. Don't create parallel copies.
- `reports/PhishTriage_Colab_Executed.ipynb` holds only **real** Colab-executed, sanitized output.
  Never fabricate or hand-edit its outputs.
- Never commit secrets, `.env`, API keys, raw datasets, or large model files (see `.gitignore`).
  In Colab, read secrets via `google.colab.userdata`, not hard-coded strings.
- Commit the canonical notebook with outputs **cleared**, to keep diffs reviewable.

## Git
- Branches: `main` (stable), `phishtriage-colab` (development). Merge to `main` only when a phase works in Colab.
- Repo: `https://github.com/nishtrip14/PhishTriage`. No force-pushes to `main`.
- Stage files explicitly (`git add <path>`); don't blanket-stage unrelated changes.
- Before pulling Colab edits back, follow `docs/COLAB_WORKFLOW.md`.

## Verified commands
```bash
# Validate notebook structure (needs nbformat, available locally)
python3 -c "import nbformat,sys; [nbformat.validate(nbformat.read(p,4)) for p in sys.argv[1:]]; print('ok')" notebooks/PhishTriage_Colab.ipynb

# Clear outputs before committing the canonical notebook
jupyter nbconvert --clear-output --inplace notebooks/PhishTriage_Colab.ipynb
```
Both commands were verified locally on 2026-10-15 (Python 3.13.7, Homebrew jupyter).

```bash
# Execute the notebook locally (needs a venv with numpy pandas scipy matplotlib requests nbconvert ipykernel).
# Raw data goes to PHISHTRIAGE_WORKDIR (default ~/.cache/phishtriage), never into the repo.
# PHISHTRIAGE_EXPORT_DIR refreshes the small evidence files in reports/. It must be an absolute path,
# because the kernel runs from notebooks/.
PHISHTRIAGE_EXPORT_DIR="$PWD/reports" jupyter nbconvert --to notebook --execute \
  --ExecutePreprocessor.timeout=900 --output-dir "$HOME/.cache/phishtriage-exec" notebooks/PhishTriage_Colab.ipynb
```
Verified on 2026-10-15 with these flags in a venv (pandas 3.0.6, scipy 1.18.1), using scratch directories for
the workdir and output. Write the executed copy outside the repository and keep the canonical notebook cleared.
Mark a new command as verified only after running it.

## Data rules
- The dataset is Zenodo 8339691 (Nazario phishing vs SpamAssassin ham), pinned by SHA-256; see `docs/DATASET_CARD.md`.
  Never relabel generic spam as phishing.
- The model input is the `text` column only. Source, labels, IDs, dates and the URL flag are never features.
- Fit any learned preprocessing on `train` only. The splits are fixed by `reports/split_manifest.csv` (seed 42).

## Status tracking
Update `COLAB_STATUS.md` after each phase, with evidence (a commit hash, a Colab run date, metrics).
