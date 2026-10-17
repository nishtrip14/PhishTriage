# Final verification record

**Code revisions:** the latest code change is `3e7cbe1` (provisional default `gemini-3.8-flash`, larger
output-token caps). Its full offline notebook run, from a fresh kernel, is recorded below. Earlier rows keep their own
revisions. There is **no** blanket "fully verified"
claim: each row below has its own scope and evidence.

## Verification matrix
| What | Where and how | Revision | Result | Evidence |
|---|---|---|---|---|
| Offline test suite | Mac, `python -m pytest -q -p no:cacheprovider tests`; google-genai 2.31.0, scikit-learn 1.9.1, pandas 3.0.6, Python 3.13.7 | current HEAD | **137 passed** | Test output (2026-10-17, at `3e7cbe1`) |
| Offline suite, Colab-reported SDK | Mac venv with google-genai 2.12.1 | current HEAD | **136 passed, 1 skipped** (ipywidgets absent in that venv) | Same |
| Local notebook, sections 0–30 | `jupyter nbconvert --execute`, live flags `False` | `f6642c9` (clean tree) | No errors; frozen evaluation, audit, split, retrieval and phase 3 evidence reproduced exactly | `reports/final_verification.json`, `reports/phase5_verification.json` |
| Colab notebook (offline paths) | Executed notebook saved in commit `f2b7277` | `9acefcb` | Sections 0–27 ran without errors; same data and split; thresholds and a few error counts differ from the local run (cause not established) | `reports/colab_run_9acefcb.json` |
| Colab run of the current code | Owner reports a successful *Run all* on 2026-10-16 | unknown | **Evidence not supplied:** no executed notebook in `colab_import/` or Downloads, and no new commit | — |
| Widget interaction | Requires a person (`WIDGETS_CONFIRMED_BY_PERSON` in section 30) | — | **Unverified** | — |
| Widget construction and callbacks | Offline test drives real ipywidgets callbacks (`tests/test_interface.py`) | current HEAD | Passed (does not prove Colab rendering) | Test output |
| Provider preflight | Owner report: `ok`, `gemini-3.6-flash`, SDK 2.12.1, `record_check` returned, 2 network calls | not recorded | User-reported | `COLAB_STATUS.md` |
| Live cases | Owner report, older code: benign_notification **approved** (5 requests, 3 tools); credential_link `provider_server` (3 requests); ambiguous `provider_quota` after a server error (4 requests); prompt_injection `provider_quota` (2 requests) | not recorded (before `e635833`) | 1 approved, 1 server failure, 2 quota stops | `COLAB_STATUS.md` (user-reported) |
| Local `.env` key loading (section 21) | Mac, notebook executed with the shell variable unset; `load_local_env` reported `loaded: ['GEMINI_API_KEY']`; outputs and work files scanned: key not present | `256f5b2` | Works locally; Colab Secrets path unchanged (not re-run in Colab) | Executed copy kept outside the repo (scratch) |
| Provider preflight, current code | Same local run, google-genai 2.31.0 | `256f5b2` | **ok**: `gemini-3.6-flash`, `model_lookup` ok, forced `record_check` returned, 2 network calls | Same |
| One live synthetic case | Same run, section 26, `credential_link` only | `256f5b2` | **failed / `provider_server`**: 3 × HTTP 503 UNAVAILABLE ("high demand"); 2 jittered retries (4.1 s waited), 3 requests, 0 tool calls, 8.4 s; nothing fabricated; no further cases attempted | Same |

| Bounded model comparison | Local, google-genai 2.31.0, `phishtriage.model_comparison`; 22 of at most 39 generation requests, 4 metadata requests | `7849593` | 3/3 preflights ok; `credential_link` **approved** on 3.6-flash, 3.8-flash, 3.5-flash-lite; 3.6 `benign_notification` failed (finalize `MAX_TOKENS`, then HTTP 429 daily quota); remaining 2 cases not run (stop rule) | `reports/model_comparison_20261017.json`, [MODEL_SELECTION.md](MODEL_SELECTION.md) |
| Report content of those runs | Engineering review by the coding assistant (not a human evaluation) | `7849593` | Findings grounded and cited; no invented IDs, tools or authentication; classifier unchanged. Some actions cite playbooks that don't contain them | Same |
| Local notebook from a fresh kernel, sections 0–30 | New Python 3.11.15 venv with only ipykernel + nbconvert; section 0 installed the rest **including ipywidgets**; live flags off | `3e7cbe1` | 35/35 code cells, no errors; section 28 built the interface (`Live mode: model gemini-3.8-flash: no preflight …`); test metrics, thresholds and FP/FN identical to the frozen run (only timing fields differ) | Executed copy kept outside the repo (scratch) |
| Token caps 4096/8192, default `gemini-3.8-flash` | Offline tests only | `3e7cbe1` | **Not run live** | — |

## What the evidence supports
* **Implemented and offline-tested:**
  * the data pipeline, training and evaluation protocol;
  * parsing limits and evidence statuses;
  * retrieval and tools;
  * the agent loop with scripted and fake-Gemini adapters, including the multi-turn protocol, budgets, retries,
    quota and batch stopping;
  * the configuration lifecycle;
  * interface logic and export privacy.
* **Run end to end:** locally at the current code; in Colab at `9acefcb`, offline paths only.

## What it does not support
* Colab execution of the current code (pending the executed notebook).
* Widget interaction.
* Live behaviour at `3e7cbe1` (new token caps and default): not run live. At `7849593`, three single
  `credential_link` runs completed; no benign case completed, and the revision path was not exercised live.
* Reliability ranking of models: one or two cases per model cannot establish one.
* Explanation quality.
* Real-world accuracy: the data is source-confounded and there is no external validation.

## Remaining failures and skips
* User-reported live runs included 1 server failure and 2 quota stops (older code).
* At `256f5b2` (local): preflight ok, then the one authorized live case failed with HTTP 503 after 2 retries.
* At `7849593` (comparison): gemini-3.6-flash `benign_notification` failed (truncated finalize, then daily quota);
  2 planned cases were not run because the quota stop rule ended the comparison.
* One test is skipped in the 2.12.1 venv because ipywidgets is not installed there.

## To close the open rows
Download the executed notebook from your Colab run (*File → Download → Download .ipynb*) into `colab_import/`,
plus `/content/phishtriage/outputs/final_verification.json` and `phase5_verification.json`. They will be inspected,
sanitized and recorded against their actual revision.
