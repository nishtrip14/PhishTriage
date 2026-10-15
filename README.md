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

## Current results (local run, not yet verified in Colab)
Two TF-IDF baselines (logistic regression, multinomial NB) score F1 ≈ 0.98–0.99 on the held-out test split,
with original and artifact-normalized text alike. Because the phishing and legitimate emails come from different
corpora, **this measures corpus separation, not real-world phishing-detection accuracy.**
See [docs/MODEL_EVALUATION.md](docs/MODEL_EVALUATION.md).

**Evidence and tools (phase 3, local):** pasted or `.eml` input is inspected offline, with no URL fetching,
HTML rendering or attachment opening. The results are typed evidence items marked observed, unverified claim,
unavailable or error. Eight original *example* playbooks are searched with a separate TF-IDF index, and four
read-only, typed tools (`get_prediction`, `inspect_email`, `retrieve_playbook`, `get_evidence`) are ready for
the agent phase. See [docs/TOOLS_AND_EVIDENCE.md](docs/TOOLS_AND_EVIDENCE.md).

**Reproducible Colab runs:** set `PHISHTRIAGE_REVISION` (section 0) to a full commit SHA. The default
`phishtriage-colab` branch moves with every push.

**Agents (phase 4, local; not yet run live):** a bounded investigator chooses among the four tools for one
application-bound case. Its draft goes through deterministic citation checks and a separate reviewer pass, with at
most one revision; otherwise the case is marked *needs human review*. Modes: live Gemini (opt-in, gated by the
preflight), clearly labelled scripted replay, and an evidence-only mode with no LLM. "No strong indicators" is
never proof of safety. See [docs/AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md).

Next stage: a notebook interface with report export ([COLAB_STATUS.md](COLAB_STATUS.md)).

## Repository layout

| Path | Purpose |
|------|---------|
| `notebooks/PhishTriage_Colab.ipynb` | Canonical development notebook (source of truth) |
| `reports/PhishTriage_Colab_Executed.ipynb` | Sanitized, genuinely executed demo copy (created after a real Colab run) |
| `phishtriage/` | Library code imported by the notebook: data, text, models, inference, evidence, retrieval, tools, agent |
| `tests/` | Offline tests (`pytest tests`) |
| `docs/DATASET_CARD.md`, `docs/MODEL_EVALUATION.md` | Data provenance and limitations; baseline evaluation |
| `docs/TOOLS_AND_EVIDENCE.md` | Evidence schemas, safe input, playbooks, retrieval, tools, LLM preflight |
| `docs/AGENT_WORKFLOW.md` | Agent state machine, report contract, budgets, modes, failure behaviour |
| `phishtriage/playbooks/` | Example playbooks (labelled EXAMPLE POLICY) and the retrieval check set |
| `docs/COLAB_WORKFLOW.md` | How to sync changes between GitHub and Colab safely |
| `COLAB_STATUS.md` | Phase progress, evidence, blockers, next action |
| `CLAUDE.md` | Project rules for AI-assisted development |

Deadline for the Colab demonstration: **19 October 2026**.
