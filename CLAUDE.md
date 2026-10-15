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
Mark a new command as verified only after running it.

## Status tracking
Update `COLAB_STATUS.md` after each phase, with evidence (a commit hash, a Colab run date, metrics).
