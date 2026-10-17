# Model selection (provisional demonstration default)

**Selected default:** `gemini-3.8-flash`, **provisional**. The comparison below is far too small to rank models
with confidence or to estimate reliability. It shows that three stable Flash-family models can run the PhishTriage
protocol end to end on this account, and it surfaced two defects that are now fixed. Raw, sanitized records:
[`reports/model_comparison_20261017.json`](../reports/model_comparison_20261017.json).

## 1. Candidate eligibility
Sources (checked 2026-10-17): [models](https://ai.google.dev/gemini-api/docs/models),
[pricing](https://ai.google.dev/gemini-api/docs/pricing), [thinking](https://ai.google.dev/gemini-api/docs/thinking),
[what's new in Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.8), and the model pages for
[3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash),
[3.6 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash) and
[3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite).

`client.models.list()` (google-genai 2.31.0) returned 63 models. Chosen candidates, in the predeclared order:

| # | Model ID (as returned) | Docs status | Function calling / structured output | Default thinking | Paid price per 1M tokens, in / out |
|---|---|---|---|---|---|
| 1 | `gemini-3.6-flash` (version `3.6-flash-07-2026`) | Stable, previous-generation Flash | Supported / supported | medium | $0.75 / $3.75 until 31 Dec 2026 |
| 2 | `gemini-3.8-flash` | Stable, current Flash | Supported / supported | medium (`minimal` not supported) | $0.75 / $3.75 until 31 Dec 2026 |
| 3 | `gemini-3.5-flash-lite` (version `3.5-flash-lite-07-2026`) | Stable, low-cost | Supported / supported | minimal | $0.30 / $2.50 |

**Not tested, and why:**
* `gemini-3.1-flash-lite`: stable but older than 3.5 Flash-Lite, and the three-candidate limit applied.
* `gemini-3.7-flash` and `gemini-3.5-flash`: returned by the API but not listed on the current models page.
* `gemini-flash-latest` and similar aliases: they move between models, so a run is not reproducible.
* `gemini-4-argon` and Pro models: not economical Flash-family models.
* Preview, image, TTS, audio and agent-product models: not general-purpose text models, or preview.

**Pricing and access.** A free tier is published for all three candidates. On the free tier, Google says content
may be used to improve its products. **This project's billing status is unknown.** It was not inspected or changed,
so the test is not described as free. The daily-quota error seen (below) refers to "plan and billing details".

## 2. Compatibility review (before any live call)
| Item | Finding | Action |
|---|---|---|
| Function declarations | `parameters_json_schema` with `AUTO` / `NONE` modes; preflight uses `ANY` | none |
| Multi-turn function responses | All responses for a step go in one user turn after the calls, with `id` and `name` | none |
| Thought signatures | The model's returned `Content` is replayed unchanged | none |
| Structured finalize and review | `response_mime_type="application/json"` + `response_json_schema`, tools off | none |
| `temperature=0` | Gemini 3 guidance keeps the default; the 3.8 Flash guide lists `temperature`/`top_p`/`top_k` as deprecated | **removed** (adapter and preflight), `c49d844` |
| Thinking | Left at each model's default; no unsupported `thinking_level` is sent | none |
| Retries | SDK retries off in the adapter; preflight now takes `max_attempts` (1 in the comparison) | parameter added, `c49d844` |
| `ProviderError` inside the client | Was remapped to a retryable `server` error | re-raised unchanged, `c49d844` |

## 3. Frozen comparison setup
* **Plan**, frozen at 2026-10-17T06:00:41Z, before any generation request: candidates in the order above; cases
  `credential_link` across all eligible models, **then** `benign_notification`.
* **Held constant:**
  * the synthetic inputs and the classifier artifact (`tfidf_logreg__artifact_normalized`, frozen run A);
  * the four tools, the PB-01..PB-08 index, and the prompts and validation of agent version 1.0;
  * `AgentConfig` defaults: 3 rounds, 5 tools, 6 requests per case including retries, 90 s, and token caps of
    1024 / 2048 at that revision.
* **Global limits, enforced in code** (`phishtriage/model_comparison.py`):
  * at most 39 generation requests (3 preflights + 6 cases × 6) and 900 s;
  * a client wrapper refuses any request whose SDK retry setting is not 1;
  * a case starts only if 6 requests and 100 s remain.
* **Stop rules:** authentication failures and quota terminations stop the whole comparison; models are never rotated
  to get around quota.
* **Execution:** sequential, with a 5 s pause between cases.
* **Code:** first attempt at `c49d844`, aborted by a harness defect (the SDK client was garbage-collected, so 0
  requests were sent); fixed in `7849593`, which is the revision of every result below.

## 4. Outcomes (`7849593`, google-genai 2.31.0, local Mac)
| Attempt | Model | Case | Report status | Requests (ok) | Provider errors | Tools (rejected) | Finalize / review | Elapsed | Tokens prompt / output / thinking |
|---|---|---|---|---|---|---|---|---|---|
| preflight | each of the three | — | `ok` ×3 | 1 each (1) | none | `record_check` returned | — | — | not recorded |
| cmp-01 | gemini-3.6-flash | credential_link | **approved** | 5 (4) | 1 × HTTP 503, retried | 3: inspect_email, get_prediction, retrieve_playbook (0) | yes / yes, 1 round | 30.2 s | 11,019 / 565 / 2,232 |
| cmp-02 | gemini-3.8-flash | credential_link | **approved** | 5 (4) | 1 non-HTTP transport error, retried (category not recorded) | 3, same tools (0) | yes / yes, 1 round | 61.2 s | 11,228 / 608 / 2,496 |
| cmp-03 | gemini-3.5-flash-lite | credential_link | **approved** | 4 (4) | none | 1: inspect_email (0) | yes / yes, 1 round | 6.1 s | 8,509 / 392 / 0 |
| cmp-04 | gemini-3.6-flash | benign_notification | **failed** (`provider_quota`) | 5 (3) | 1 × HTTP 503 (retried), then HTTP 429, daily quota | 3 (0) | finalize returned truncated (`MAX_TOKENS`) and was rejected / review not reached | 18.4 s | 7,216 / 557 / 1,738 |
| cmp-05, cmp-06 | 3.8-flash, 3.5-flash-lite | benign_notification | **not run** (comparison stopped on quota) | 0 | — | — | — | — | — |

**Totals:** 22 generation requests out of 39 (3 preflight + 19 case requests). There were 4 metadata requests: one
`models.list` and three `models.get`. The aborted first attempt's 3 lookups failed locally and were never sent. Case
tokens: 37,972 prompt, 2,122 output and 6,466 thinking. The comparison ran for 145 s.

## 5. Availability versus report quality (separate measures)
| Measure | 3.6 Flash | 3.8 Flash | 3.5 Flash-Lite |
|---|---|---|---|
| Transport: successful responses / requests (incl. preflight) | 8 / 11 | 5 / 6 | 5 / 5 |
| Tool calls: valid / issued | 6 / 6 | 3 / 3 | 1 / 1 |
| Workflow completed (finalize + review, approved) / cases run | 1 / 2 | 1 / 1 | 1 / 1 |
| Grounded findings in completed reports | 5 / 5 | 5 / 5 | 3 / 3 |
| Recommended actions fully supported by the cited playbook | 1 / 3 | 1 / 3 | 0 / 1 (no playbook retrieved) |

**Engineering review** of each report, by the coding assistant against the extracted evidence and the playbook
text. This is **not** an independent human evaluation.
* **All three completed reports:**
  * findings cite real, matching evidence, with no invented evidence IDs, playbook IDs or tool runs;
  * no authentication was claimed as verified: `Authentication-Results` was reported absent and SPF/DKIM/DMARC as
    unknown;
  * "no attachments" was scoped to the parts of the supplied `.eml`, which is correct for this input;
  * the classifier output (`phishing`, 0.9997, threshold 0.261) was unchanged.
* **Shared weakness:** the reviewer approved actions such as "block the IP at the firewall" or "remove the email
  from mailboxes" that cite PB-01 although PB-01 does not contain them. Validation checks only that a cited playbook
  was retrieved, not that it supports the action. **Fixed after the comparison** in `6a137d8` (agent version 1.1,
  section 6 item 4). These results, and `reports/model_comparison_20261017.json`, are from agent version 1.0, whose
  actions were free text; they are kept unchanged.
* **3.8 Flash:** one action calls the message "the phishing email" while the assessment is `suspicious`.
* **3.5 Flash-Lite:** a thin investigation (only `inspect_email`), no playbook retrieval, and an action with no
  playbook reference that calls the host "malicious".
* **Benign case:** no completed report exists for any model, so benign/classifier disagreement handling was not
  observed live in this comparison.

**Earlier live data on 3.6 Flash, kept for context:**
* 2026-10-16, local, code `256f5b2`: preflight `ok`, then `credential_link` failed with 3 × HTTP 503.
* User-reported, older code: one approved case, one server failure and two quota stops.

## 6. Defects found and fixed
1. **Harness:** the wrapped SDK client was closed before use. Fixed in `7849593`, with a test.
2. **Thinking versus output cap:** Gemini counts thinking tokens against `max_output_tokens`. cmp-04's finalize
   reply ended with `MAX_TOKENS` and was rejected. The caps were raised from 1024 / 2048 to 4096 / 8192 in `3e7cbe1`.
   Only generated tokens are billed, and the request, tool and time budgets are unchanged. **This change has not run
   live.**
3. **Records:** error categories are now stored, because cmp-02's non-HTTP error lost its category.
4. **Unsupported recommended actions** (all three models): fixed in `6a137d8`, agent version 1.1. A recommended
   action is now a reference (`doc_id`, `version`, `action_id`, `rationale`) to a numbered next step of a playbook
   retrieved in the same run, for example `PB-01.S1`. Application code validates it and shows the playbook's own
   wording; a rationale that adds steps such as deleting or blocking, or certainty such as "malicious", is rejected.
   Playbook text was not changed. Details: [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md).

## 7. Selection and rationale
Priority order: protocol compatibility and grounding, then completed investigations, then observed errors, then
latency and cost.
* **Compatibility and grounding:**
  * All three passed preflight with valid tool calls.
  * 3.6 and 3.8 produced findings of comparable quality, with the same kind of guidance-attribution flaw. The
    sample cannot separate them.
  * 3.5 Flash-Lite's report was thinner and its guidance unsupported, so it ranks below them on the top priority
    despite being fastest and cheapest.
* **Completed investigations:**
  * 3.8: 1 of 1.
  * 3.6: 1 of 2 in this comparison (and 0 of 1 on 2026-10-16).
* **Observed errors in this window:**
  * 3.6: 5 HTTP 503s across 13 case requests over two days, plus a daily-quota stop.
  * 3.8: no HTTP errors and one transport error in 6 requests.
* **Latency:** 3.8's only case took 61.2 s, including one failed request and a retry. That is within the 90 s
  deadline but leaves little headroom. 3.6 took 30.2 s.

**Decision:** `gemini-3.8-flash` as the provisional demonstration default. The tie on report quality was broken
by completion and error observations from a very small, two-day sample. That is not evidence of general
reliability and does not guarantee the absence of future 503s or timeouts.

**Manual alternative:** `gemini-3.6-flash` (set `MODEL_OVERRIDE = "gemini-3.6-flash"` in section 21, then run its
preflight). It passed preflight and completed `credential_link` with grounded findings at `7849593`. Its daily
quota was exhausted at 06:02 UTC on 2026-10-17; the provider asked for a wait of about 18 hours. There is no
automatic fallback.

## 8. Limitations
* There were one or two cases per model, a single benign attempt (failed), and one time window on one account.
* At the final code (`6a137d8`) only the two-case smoke test in section 10 has run live: no approved live report
  exists at that revision.
* The review is an engineering review by the assistant, not a human evaluation.
* Live behaviour can change with provider load and quota. Evidence-only and replay modes stay available without a key.

## 9. Colab smoke test for the selected model
1. Open the notebook from the README link in a fresh CPU runtime. In section 0, set `PHISHTRIAGE_REVISION` to the
   pushed SHA, then *Run all*. The flags stay `False`, so there are no API calls.
2. The `GEMINI_API_KEY` Colab Secret must have *Notebook access* on. Never upload `.env` to Colab.
3. **Section 21:** `RUN_LLM_PREFLIGHT = True`, then run it. Expect `"status": "ok"` and `model: gemini-3.8-flash`.
   If it fails, record the status. Don't repeat it in a loop.
4. **Section 26:** `RUN_LIVE_AGENT = True`, keep `LIVE_CASE = "credential_link"`, then run **once**. Note the status,
   termination, requests and elapsed time.
5. **Section 28:** *Live agent*, acknowledgement ticked, **SYNTHETIC: Benign notification**, then **Analyze once**.
   Check that *Model used* shows `gemini-3.8-flash`, that the disagreement warning is visible, that nothing
   says "safe", and that each recommended action shows a playbook step ID such as `PB-07.S2`.
6. If a report says `provider_quota`, stop. Use evidence-only or replay, labelled as such.
7. Set the flags back to `False`. Set `WIDGETS_CONFIRMED_BY_PERSON = True` only if you saw the form work.

## 10. Final smoke test at the grounded-action code (2026-10-17)
Not a comparison and not a reliability measurement. Code `6a137d8` (agent 1.1), google-genai 2.31.0, local Mac,
`gemini-3.8-flash` from `DEFAULT_MODEL` (no override). Limits enforced by the request ledger: 1 preflight and at
most 12 case requests, SDK retries off. Record: `reports/live_smoke_20261017.json`.

| Step | Started (UTC) | Outcome | Requests (ok) | Provider errors | Tools | Elapsed | Tokens prompt / output / thinking |
|---|---|---|---|---|---|---|---|
| preflight | 07:12 | `ok`, `record_check` returned | 1 (1) | none | — | — | not recorded |
| credential_link | 07:13:07 | **failed** (`provider_server`) | 5 (2) | 3 × HTTP 503 (1 during investigation, 2 on finalize); retry budget of 2 used | inspect_email, get_prediction, retrieve_playbook | 17.4 s | 5,223 / 42 / 183 |
| benign_notification | 07:13:29 | **needs_human_review** (`budget_exhausted`) | 6 (5) | 1 × HTTP 429 per-minute rate limit, retried after the provider's 29 s delay | 4 (2 playbook searches) | 70.4 s | 15,388 / 933 / 3,261 |

**Totals:** 12 generation requests (1 preflight + 11 case), 1 metadata request, 108 s.

**Engineering review of the benign report** (assistant, not a human evaluation):
* finalize and review completed; no `MAX_TOKENS` finish with the 4096 / 8192 caps;
* assessment `insufficient_evidence`; classifier `phishing`, 0.898, unchanged from trusted state;
* four findings, all cited, and no deterministic validation issue. "No URLs were found" cites the
  `observed_absent` URL item. Headers, authentication and attachments are listed as unavailable, not absent. There
  is no "safe" wording and no invented authentication result;
* three canonical actions passed reference validation: PB-07.S1, PB-07.S2 and PB-06.S1;
* the reviewer objected (`playbook_mismatch`) that PB-06, "Legitimate urgent communication", does not fit a
  non-urgent notice. With 6 of 6 requests used, no revision was possible, so the report correctly ended as
  `needs_human_review`. This shows the limit in practice: a valid reference proves the step exists, not that the
  playbook applies.

The credential_link failure was a provider overload; nothing was fabricated, and no retry beyond the budget was made.
