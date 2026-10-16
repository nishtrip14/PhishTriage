# PhishTriage

PhishTriage is an academic project that triages suspicious email with a bounded, evidence-grounded agent workflow.
It runs entirely in a **CPU Google Colab runtime**: there is no separate backend, database, Docker, mailbox
integration or agent framework.

**Open in Colab (development branch):**
https://colab.research.google.com/github/nishtrip14/PhishTriage/blob/phishtriage-colab/notebooks/PhishTriage_Colab.ipynb

Status and verification by revision: [COLAB_STATUS.md](COLAB_STATUS.md). Demo steps:
[docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md).

## Run it
* **API-free (default):** start a fresh CPU runtime, then *Runtime → Run all*. Nothing waits for input, and
  nothing calls an LLM API.
* **Live (optional):** add the `GEMINI_API_KEY` Colab Secret (key icon, *Notebook access* on; never paste the key
  into a cell). Run the section 21 preflight with `RUN_LLM_PREFLIGHT = True`, then either section 26
  (`RUN_LIVE_AGENT = True`, one synthetic case by default) or the section 28 interface in *Live* mode with the
  acknowledgement ticked. The configured model is `gemini-3.6-flash` unless you set `MODEL_OVERRIDE`.
* **Reproducible run:** set `PHISHTRIAGE_REVISION` (section 0) to a full commit SHA.

## Architecture
```
Zenodo data (pinned SHA-256) ─► grouped splits ─► TF-IDF + logistic regression (selected before test)
                                                              │ get_prediction
pasted text / .eml ─► safe parsing ─► typed evidence ─────────┤ inspect_email, get_evidence
example playbooks ─► separate TF-IDF retrieval ───────────────┘ retrieve_playbook
                    ▼
investigator (Gemini, bounded tool loop, case bound by the app) ─► draft report
  ─► deterministic checks (citations, absence claims, classifier consistency)
  ─► reviewer (separate request) ─► ≤ 1 revision ─► approved | needs human review | failed
                    ▼
ipywidgets interface (escaped output, stale-input guard) ─► JSON export (summary by default)
```

**Agent limits:**
* 3 tool rounds, 5 tool executions, 6 model requests (finalize and review capacity reserved), a 90-second
  deadline.
* Bounded, jittered retries for server errors (at most 2 per run). Quota is never retried immediately: daily or
  unclassified quota stops the case, and a batch.
* Three modes: **live**, **scripted replay** (labelled NOT live) and **evidence-only** (no LLM).

## Honest evaluation
* **Data:** Nazario phishing vs SpamAssassin ham (Zenodo 10.5281/zenodo.8339691, CC-BY-4.0); see
  [docs/DATASET_CARD.md](docs/DATASET_CARD.md).
* **Baselines:** two TF-IDF baselines reach test F1 ≈ 0.98–0.99. **Every phishing email comes from one corpus and
  every legitimate email from another**. This source/class confound means the high scores **cannot be attributed
  to generalizable phishing detection**: the models may rely partly or wholly on differences between the corpora.
  There is **no external validation**.
* **Artifact sensitivity:** removing known collection artifacts barely changed the scores, and residual cues remain.
* **Score type:** uncalibrated model estimates, not probabilities.
* **Runs across environments:** a local run and a Colab run gave slightly different thresholds and error counts.
  The cause is not established. See [docs/MODEL_EVALUATION.md](docs/MODEL_EVALUATION.md).
* **Synthetic demos:** the demo emails are synthetic workflow tests, never accuracy evidence. For example, the
  classifier labels the synthetic benign notification *phishing* (≈ 0.90), and the report shows that
  disagreement with the agent.

## Not claimed
Production readiness; real-world accuracy; calibrated scores; immunity to prompt injection; that reviewer approval
guarantees correctness; that "no strong indicators" means safe.

## Repository layout
| Path | Purpose |
|------|---------|
| `notebooks/PhishTriage_Colab.ipynb` | Canonical notebook, sections 0–30 (outputs cleared, API flags off) |
| `phishtriage/` | Package: data, text, models, inference, evidence, retrieval, tools, agent, llm_preflight, ui, export |
| `phishtriage/playbooks/` | Example playbooks (labelled EXAMPLE POLICY) and the retrieval check set |
| `tests/` | Offline tests (`python -m pytest -q tests`); network access is blocked in the agent and provider tests |
| `docs/DEMO_RUNBOOK.md` | Fresh-runtime setup, API-free and live demo paths, provider-failure fallback |
| `docs/AGENT_WORKFLOW.md` | Agent states, report contract, budgets, retries, grounding, modes, interface |
| `docs/TOOLS_AND_EVIDENCE.md` | Evidence statuses, safe input, playbooks, retrieval, tools, preflight |
| `docs/DATASET_CARD.md`, `docs/MODEL_EVALUATION.md` | Data provenance and confounds; baseline evaluation per run |
| `docs/COLAB_WORKFLOW.md`, `docs/colab_recovery_cell.py` | Syncing with Colab; read-only runtime recovery |
| `reports/` | Small, text-free evidence files |
| `COLAB_STATUS.md` | Verification matrix by revision, logs, checkpoint |
