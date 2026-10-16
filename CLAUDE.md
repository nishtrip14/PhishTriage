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
- Reusable logic lives in the `phishtriage/` package; the notebook imports it. In Colab, section 0 checks out
  `PHISHTRIAGE_REVISION` (default branch `phishtriage-colab`; use a full SHA for reproducible runs). It never
  resets a modified checkout.
- Scope is agentic (see the `COLAB_STATUS.md` plan): the classifier is one evidence tool, not the whole deliverable.

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
# Offline test suite (needs pytest, scikit-learn, pandas, scipy, requests, joblib)
python -m pytest -q -p no:cacheprovider tests

# Execute the notebook locally (also needs matplotlib, pyarrow, nbconvert, ipykernel).
# Raw data goes to PHISHTRIAGE_WORKDIR (default ~/.cache/phishtriage), never into the repo.
# PHISHTRIAGE_EXPORT_DIR refreshes the small evidence files in reports/. It must be an absolute path,
# because the kernel runs from notebooks/.
PHISHTRIAGE_EXPORT_DIR="$PWD/reports" jupyter nbconvert --to notebook --execute \
  --ExecutePreprocessor.timeout=1800 --output-dir "$HOME/.cache/phishtriage-exec" notebooks/PhishTriage_Colab.ipynb
```
Both were verified on 2026-10-16 in a venv (pandas 3.0.6, scikit-learn 1.9.1, google-genai 2.31.0, ipywidgets 8),
with scratch directories for the workdir and output. If you execute a *copy* of the notebook from outside the repo, set `PHISHTRIAGE_REPO`. Write the executed copy outside the repository and keep the canonical notebook cleared.
Mark a new command as verified only after running it.

## Data rules
- The dataset is Zenodo 8339691 (Nazario phishing vs SpamAssassin ham), pinned by SHA-256; see `docs/DATASET_CARD.md`.
  Never relabel generic spam as phishing.
- The model input is the `text` column only. Source, labels, IDs, dates and the URL flag are never features.
- Fit any learned preprocessing on `train` only. The splits are fixed by `reports/split_manifest.csv` (seed 42).
- Choose parameters, thresholds and normalization rules on dev only. Freeze them before test; never retune after
  seeing test results. Record a rule change as a new `PREPROCESSING_VERSION`.
- Never describe test scores as real-world accuracy: source = label in this dataset (`docs/MODEL_EVALUATION.md`).
- Model artifacts (`model.joblib` + `manifest.json`) stay outside Git; load them only via `inference.load_artifact`,
  which verifies the SHA-256 before unpickling.

## Evidence and tool rules
- Never fetch URLs, render HTML, open attachments or treat `Authentication-Results` as verified. Missing data
  is `unavailable`, not safe. Tool failures are non-ok `ToolResult`s, never fabricated successes.
- Playbooks are labelled EXAMPLE POLICY. Retrieval relevance is not a phishing probability.
- External LLM calls are opt-in. Read `GEMINI_API_KEY` from Colab Secrets only, and never print or commit it.
  Phase 4 uses the official `google-genai` SDK (CrewAI was rejected over dependency conflicts).

## Handoff rules
- Never treat an assistant transcript or saved execution counts as evidence. Verify files, commits and test
  output. Runtime-only edits are recovered with `docs/colab_recovery_cell.py`, or reimplemented and labelled as such.
- Raw imported notebooks and archives stay untracked in `colab_import/`; only sanitized, text-free extracts go
  in `reports/`.
- Before committing the canonical notebook, reset API flags (`RUN_LLM_PREFLIGHT`, `RUN_LIVE_AGENT`) to False.

## Agent rules
- Agents use only the four read-only tools, with the case bound by application code. No mailbox access, sending,
  deleting, link visits, attachment execution or autonomous remediation.
- Classifier fields in reports come from trusted state only. Replay output is never live-agent validation, and
  `no_strong_indicators` is never "safe".
- Keep the budgets (3 rounds, 5 tools, 6 requests, 90 s) unless the owner asks to change them. SDK retries stay
  off, and quota (429) is never retried. Run multiple live cases through `run_batch_triage`, which stops on quota.
- Add phase cells to the notebook by appending or editing in place; preserve existing cell IDs.
- Live model: one setting (`LLMSettings`, section 21). Never switch models silently. Approval is bound to
  (model, installed SDK) through `PreflightRegistry`.
- Evidence statuses: `observed_absent` (checked, not found within a scope) is not `unavailable` (unknown).
  Never let a report claim absence from unavailable evidence.
- Interface and export: escape everything; summary exports carry no email text; the detailed export is opt-in.
  Submitted cases stay in session memory and are never committed.

## Documentation map
README.md (entry point) → docs/PROJECT_EXPLAINED.md → docs/ARCHITECTURE.md → docs/VERIFICATION.md (current
matrix). Demo and viva: docs/DEMO_RUNBOOK.md, docs/PRESENTATION_GUIDE.md, docs/VIVA_QUESTIONS.md. Keep section
numbers, variable names and test counts in these files synchronized with the notebook and the latest test run.

## Status tracking
Update `COLAB_STATUS.md` after each phase, with evidence (a commit hash, a Colab run date, metrics).
