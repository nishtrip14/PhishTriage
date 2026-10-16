# Final verification record

**Code revisions:** the full offline notebook run is at `f6642c99cbf61365ec173edbc3de5a3b1252487c`; the latest code
change is `256f5b2` (local `.env` loading, ipywidgets install), which ran end to end locally with the live flags on
(rows below). There is **no** blanket "fully verified"
claim: each row below has its own scope and evidence.

## Verification matrix
| What | Where and how | Revision | Result | Evidence |
|---|---|---|---|---|
| Offline test suite | Mac, `python -m pytest -q -p no:cacheprovider tests`; google-genai 2.31.0, scikit-learn 1.9.1, pandas 3.0.6, Python 3.13.7 | current HEAD | **127 passed** | Test output in this session (2026-10-16, at `256f5b2`) |
| Offline suite, Colab-reported SDK | Mac venv with google-genai 2.12.1 | current HEAD | **126 passed, 1 skipped** (ipywidgets absent in that venv) | Same |
| Local notebook, sections 0–30 | `jupyter nbconvert --execute`, live flags `False` | `f6642c9` (clean tree) | No errors; frozen evaluation, audit, split, retrieval and phase 3 evidence reproduced exactly | `reports/final_verification.json`, `reports/phase5_verification.json` |
| Colab notebook (offline paths) | Executed notebook saved in commit `f2b7277` | `9acefcb` | Sections 0–27 ran without errors; same data and split; thresholds and a few error counts differ from the local run (cause not established) | `reports/colab_run_9acefcb.json` |
| Colab run of the current code | Owner reports a successful *Run all* on 2026-10-16 | unknown | **Evidence not supplied:** no executed notebook in `colab_import/` or Downloads, and no new commit | — |
| Widget interaction | Requires a person (`WIDGETS_CONFIRMED_BY_PERSON` in section 30) | — | **Unverified** | — |
| Widget construction and callbacks | Offline test drives real ipywidgets callbacks (`tests/test_interface.py`) | current HEAD | Passed (does not prove Colab rendering) | Test output |
| Provider preflight | Owner report: `ok`, `gemini-3.6-flash`, SDK 2.12.1, `record_check` returned, 2 network calls | not recorded | User-reported | `COLAB_STATUS.md` |
| Live cases | Owner report, older code: benign_notification **approved** (5 requests, 3 tools); credential_link `provider_server` (3 requests); ambiguous `provider_quota` after a server error (4 requests); prompt_injection `provider_quota` (2 requests) | not recorded (before `e635833`) | 1 approved, 1 server failure, 2 quota stops | `COLAB_STATUS.md` (user-reported) |
| Local `.env` key loading (section 21) | Mac, notebook executed with the shell variable unset; `load_local_env` reported `loaded: ['GEMINI_API_KEY']`; outputs and work files scanned: key not present | `256f5b2` | Works locally; Colab Secrets path unchanged (not re-run in Colab) | Executed copy kept outside the repo (scratch) |
| Provider preflight, current code | Same local run, google-genai 2.31.0 | `256f5b2` | **ok**: `gemini-3.6-flash`, `model_lookup` ok, forced `record_check` returned, 2 network calls | Same |
| One live synthetic case, current code | Same run, section 26, `credential_link` only | `256f5b2` | **failed / `provider_server`**: 3 × HTTP 503 UNAVAILABLE ("high demand"); 2 jittered retries (4.1 s waited), 3 requests, 0 tool calls, 8.4 s; nothing fabricated; no further cases attempted | Same |

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
* Successful live behaviour of the current code: its only live case so far ended in provider 503 errors, so the
  investigator, tools, reviewer and revision path have not run live at this revision.
* Explanation quality.
* Real-world accuracy: the data is source-confounded and there is no external validation.

## Remaining failures and skips
* User-reported live runs included 1 server failure and 2 quota stops (older code).
* At `256f5b2` (local): preflight ok, then the one authorized live case failed with HTTP 503 after 2 retries.
* One test is skipped in the 2.12.1 venv because ipywidgets is not installed there.

## To close the open rows
Download the executed notebook from your Colab run (*File → Download → Download .ipynb*) into `colab_import/`,
plus `/content/phishtriage/outputs/final_verification.json` and `phase5_verification.json`. They will be inspected,
sanitized and recorded against their actual revision.
