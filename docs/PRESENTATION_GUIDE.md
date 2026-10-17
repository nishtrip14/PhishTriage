# Presentation guide (speaking notes, not slides)

All claims here match the code and the recorded evidence. Numbers come from [MODEL_EVALUATION.md](MODEL_EVALUATION.md)
(run A: canonical local run) and the verification status from [VERIFICATION.md](VERIFICATION.md).

## 30-second introduction
"PhishTriage is a decision-support tool for suspicious email, built for the title *Agentic AI-Based Phishing Email
Detection and Explanation System*. It combines a TF-IDF classifier, safe offline evidence extraction, retrieval of
example playbooks, and a bounded Gemini agent that chooses its own tool calls and has its draft checked by a
reviewer pass. The output is a cited triage report for a human. It runs in Google Colab on CPU, and everything
except the optional language-model calls runs in the notebook."

## Two-minute overview
1. **Problem:** a phishing score alone doesn't tell a person *why* or *what to check*.
2. **Approach:** classifier, evidence, playbook retrieval, then an investigator agent, deterministic checks, a
   reviewer and at most one revision.
3. **Honest evaluation:** test F1 ≈ 0.99, but phishing and legitimate mail come from different corpora, so the score
   cannot be attributed to generalizable detection. There is no external validation.
4. **Safety:**
   * Read-only, case-bound tools; budgets of 3 rounds, 5 tools, 6 requests and 90 s.
   * Untrusted-content markers; escaped output.
   * The classifier result is immutable.
   * `no_strong_indicators` is never "safe".
5. **Demo:** the API-free interface; live mode if a key is configured.

## Suggested 8–10 minute structure
| # | Slide title | Key points | Show |
|---|---|---|---|
| 1 | The problem | Phishing triage needs reasons and next steps, not just a score | — |
| 2 | Scope | Decision support only; no mailbox access, no automatic actions | README §1 |
| 3 | Architecture | Mac → GitHub → Colab; Gemini optional at the provider | README architecture diagram |
| 4 | Data and splits | Zenodo 8339691; spam excluded; near-duplicate groups; 3,949 / 846 / 847 | `reports/figures/class_balance.png` |
| 5 | Classifier | TF-IDF; LR vs NB; dev-only selection; one test run | Run A table (MODEL_EVALUATION) |
| 6 | What the score means | Uncalibrated; source/class confound; artifact test barely changed scores | `reports/figures/pr_curves.png`, influential terms |
| 7 | Evidence | Five statuses; absence vs unknown; nothing fetched or opened | Section 16 table |
| 8 | Agent and RAG | Model-chosen tool calls; retrieved playbooks; validation; reviewer; one revision | Sequence diagram (README), state diagram (ARCHITECTURE) |
| 9 | Safety and reliability | Budgets, retries, quota stop, prompt-injection handling (not immunity) | AGENT_WORKFLOW retry table |
| 10 | Demo | Interface: evidence-only → replay → (live) → export | Notebook section 28 |
| 11 | Verification | What is offline-tested, run locally, run in Colab, user-reported live | VERIFICATION matrix |
| 12 | Contributions and limits | See closing | — |

## Demo narration (section 28, matching the current interface)
1. "This is the interface. *Input: Synthetic example*, *SYNTHETIC: Benign notification*, *Mode: Evidence only*.
   Analyze."
2. "Top: the status, *Completed: evidence only*, and *Model used: none*. The classifier says **phishing**, with an
   uncalibrated score of about 0.90. That is a known weakness: this modern notification resembles the phishing
   corpus."
3. "Missing information: sender, authentication and attachments are **unknown** for pasted text, not absent."
4. "Now *Mode: Scripted replay*. Analyze. This is pre-written agent output, clearly labelled NOT live. The agent
   assessment is *no_strong_indicators*, with a **disagreement warning**. Expand the trace: every tool call,
   request count and evidence ID is visible."
5. *(Only if the preflight in section 21 shows ok)* "*Mode: Live agent*. I tick the acknowledgement that the
   content goes to Gemini. Analyze a synthetic example. The report shows the model actually used, and the
   reviewer outcome."
6. "Export JSON: the summary contains no email text. Detailed export is opt-in."
7. **If live fails:** "The provider returned a quota or server error. The report says so, and no result was
   invented. Evidence-only and replay remain available, and I've labelled them."

## Closing: contributions and limitations
* **Contributions (implemented and tested):**
  * A reproducible, leakage-aware data pipeline.
  * An honest baseline evaluation with an artifact-sensitivity analysis.
  * A safe evidence model that separates absent from unknown.
  * Validated retrieval citations.
  * A bounded agent loop with reviewer and revision, budgets, quota and retry policy.
  * A safe notebook interface and privacy-preserving export.
  * 137 offline tests.
* **Limitations:**
  * Source-confounded data; no external validation.
  * Uncalibrated scores.
  * Pattern-based grounding checks.
  * The reviewer uses the same model.
  * Live evidence is small: in a bounded comparison three models each completed one synthetic case; the default
    model is a provisional choice (docs/MODEL_SELECTION.md).
  * Not production-ready.
