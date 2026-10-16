# Final verification record

**Code revision verified locally:** `f6642c99cbf61365ec173edbc3de5a3b1252487c` (latest code change), plus the
documentation and focused tests committed after it (see `git log`). There is **no** blanket "fully verified"
claim: each row below has its own scope and evidence.

## Verification matrix
| What | Where and how | Revision | Result | Evidence |
|---|---|---|---|---|
| Offline test suite | Mac, `python -m pytest -q -p no:cacheprovider tests`; google-genai 2.31.0, scikit-learn 1.9.1, pandas 3.0.6, Python 3.13.7 | current HEAD | **122 passed** | Test output in this session (2026-10-16) |
| Offline suite, Colab-reported SDK | Mac venv with google-genai 2.12.1 | current HEAD | **121 passed, 1 skipped** (ipywidgets absent in that venv) | Same |
| Local notebook, sections 0–30 | `jupyter nbconvert --execute`, live flags `False` | `f6642c9` (clean tree) | No errors; frozen evaluation, audit, split, retrieval and phase 3 evidence reproduced exactly | `reports/final_verification.json`, `reports/phase5_verification.json` |
| Colab notebook (offline paths) | Executed notebook saved in commit `f2b7277` | `9acefcb` | Sections 0–27 ran without errors; same data and split; thresholds and a few error counts differ from the local run (cause not established) | `reports/colab_run_9acefcb.json` |
| Colab run of the current code | Owner reports a successful *Run all* on 2026-10-16 | unknown | **Evidence not supplied:** no executed notebook in `colab_import/` or Downloads, and no new commit | — |
| Widget interaction | Requires a person (`WIDGETS_CONFIRMED_BY_PERSON` in section 30) | — | **Unverified** | — |
| Widget construction and callbacks | Offline test drives real ipywidgets callbacks (`tests/test_interface.py`) | current HEAD | Passed (does not prove Colab rendering) | Test output |
| Provider preflight | Owner report: `ok`, `gemini-3.6-flash`, SDK 2.12.1, `record_check` returned, 2 network calls | not recorded | User-reported | `COLAB_STATUS.md` |
| Live cases | Owner report, older code: benign_notification **approved** (5 requests, 3 tools); credential_link `provider_server` (3 requests); ambiguous `provider_quota` after a server error (4 requests); prompt_injection `provider_quota` (2 requests) | not recorded (before `e635833`) | 1 approved, 1 server failure, 2 quota stops | `COLAB_STATUS.md` (user-reported) |
| Current retry/quota/grounding code, live | — | `e635833`+ | **Not run live** | — |

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
* Live behaviour of the current code.
* Explanation quality.
* Real-world accuracy: the data is source-confounded and there is no external validation.

## Remaining failures and skips
* User-reported live runs included 1 server failure and 2 quota stops (older code). No newer live data exists.
* One test is skipped in the 2.12.1 venv because ipywidgets is not installed there.

## To close the open rows
Download the executed notebook from your Colab run (*File → Download → Download .ipynb*) into `colab_import/`,
plus `/content/phishtriage/outputs/final_verification.json` and `phase5_verification.json`. They will be inspected,
sanitized and recorded against their actual revision.
