# Final verification record

**Code revisions:** the latest code change is `6a137d8` (grounded recommended actions, agent version 1.1). Its
offline tests, fresh-kernel notebook run and bounded live smoke test are recorded below. Later commits change
documentation only. Earlier rows keep their own revisions. There is **no** blanket "fully verified"
claim: each row below has its own scope and evidence.

## Verification matrix
| What | Where and how | Revision | Result | Evidence |
|---|---|---|---|---|
| Offline test suite | Mac, `python -m pytest -q -p no:cacheprovider tests`; google-genai 2.31.0, scikit-learn 1.9.1, pandas 3.0.6, Python 3.13.7 | `6a137d8` | **143 passed** | Test output (2026-10-17) |
| Offline suite, Colab-reported SDK | Mac venv with google-genai 2.12.1 | `6a137d8` | **142 passed, 1 skipped** (ipywidgets absent in that venv) | Same |
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
| Grounded actions (offline) | `tests/test_grounded_actions.py`: valid reference rendered and exported with playbook text; invented ID, unretrieved playbook and wrong version rejected, then corrected or `needs_human_review`; added deletion/blocking rationale withheld; free-text action rejected; no applicable action stated; real validation and orchestration with scripted model turns. A mutation check (validation disabled) fails 4 of the 6 tests | `6a137d8` | Passed | Test output |
| Local notebook from a fresh kernel, sections 0–30 | New Python 3.11.15 venv (ipykernel + nbconvert only), live flags off, exports to a scratch directory | `6a137d8` | 35/35 code cells, no errors; replay and evidence-only reports show step IDs (`PB-01.S1`, `PB-04.S3`, `PB-07.S2`, `PB-02.S2`); section 28 built (`Live mode: model gemini-3.8-flash: no preflight …`); metrics, thresholds and FP/FN identical to the committed evidence (only timings, versions, commit IDs and pickle hashes differ) | Executed copy kept outside the repo (scratch) |
| Final live smoke test | Local, `.env` key, google-genai 2.31.0, `gemini-3.8-flash` (default, no override); ledger: 1 preflight + at most 12 case requests | `6a137d8` | Preflight `ok`. `credential_link` **failed** (`provider_server`, 3 × HTTP 503, 5 requests). `benign_notification` **needs_human_review** (`budget_exhausted`, 6 requests incl. one 429 rate-limit retry): 4 cited findings, no validation issue, 3 valid playbook steps, reviewer objected that PB-06 does not fit; no `MAX_TOKENS`. 12 generation + 1 metadata requests | `reports/live_smoke_20261017.json`, [MODEL_SELECTION.md §10](MODEL_SELECTION.md) |
| Colab run of `6a137d8` or later | — | — | **Not run.** The newest import (`colab_import/local_run_e3dfdc0…`) is an owner's *local* run at `e3dfdc0` that stopped at section 28 (ipywidgets missing), so it is not Colab evidence | — |

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
* An approved live report at the final code: the two smoke cases ended `provider_server` and
  `needs_human_review`. At `7849593` (agent 1.0), three single `credential_link` runs were approved; the revision
  path has not been exercised live.
* Whether a playbook fits a case: a valid step reference proves only that the step exists in a retrieved playbook.
* Reliability ranking of models: one or two cases per model cannot establish one.
* Explanation quality.
* Real-world accuracy: the data is source-confounded and there is no external validation.

## Remaining failures and skips
* User-reported live runs included 1 server failure and 2 quota stops (older code).
* At `256f5b2` (local): preflight ok, then the one authorized live case failed with HTTP 503 after 2 retries.
* At `7849593` (comparison): gemini-3.6-flash `benign_notification` failed (truncated finalize, then daily quota);
  2 planned cases were not run because the quota stop rule ended the comparison.
* At `6a137d8` (smoke test): `credential_link` failed with HTTP 503s; `benign_notification` ended
  `needs_human_review` after a reviewer `playbook_mismatch` objection with no request left for a revision.
* One test is skipped in the 2.12.1 venv because ipywidgets is not installed there.

## To close the open rows
Run the *Colab verification checklist* in [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) at the pushed SHA. Then download the
executed notebook into `colab_import/`, plus `/content/phishtriage/outputs/final_verification.json` and
`phase5_verification.json`. They will be inspected, sanitized and recorded against their actual revision.
