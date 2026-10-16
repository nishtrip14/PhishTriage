# PhishTriage demo runbook (Google Colab, CPU)

**Open in Colab (development branch `phishtriage-colab`):**
https://colab.research.google.com/github/nishtrip14/PhishTriage/blob/phishtriage-colab/notebooks/PhishTriage_Colab.ipynb

## 1. Fresh CPU runtime (about 1 minute)
1. *Runtime → Disconnect and delete runtime*, then *Runtime → Change runtime type → CPU*. No GPU is needed.
2. Optional, for an exact version: in the section 0 code cell, set
   `PHISHTRIAGE_REVISION = "<full 40-character commit SHA>"`. The branch name moves with every push.
3. If you change the revision or the code during a session: *Runtime → Restart session*, then *Run all*.
   Section 0 warns when it detects code from an earlier load.

## 2. API-free demonstration (default; no key needed; about 3–5 minutes)
*Runtime → Run all.* Nothing waits for input, and nothing calls an LLM API.

| Show | Section | Point to make |
|---|---|---|
| Verified data and grouped splits | 2, 5 | Pinned checksums; near-duplicate groups never cross splits |
| Baseline results | 11–12 | F1 ≈ 0.98–0.99, **but** phishing and legitimate mail come from different corpora (source = label), so the scores cannot be attributed to generalizable phishing detection. There is no external validation. |
| Safe evidence | 16 | Statuses: observed / observed_absent (checked, not found) / unavailable (unknown) / unverified_claim / error |
| Playbooks and retrieval | 17–18 | EXAMPLE POLICY documents; retrieval relevance is not phishing probability |
| Tools | 19–20 | Four read-only tools; cross-case and unknown calls are rejected |
| Agent workflow | 23–24 | Bounded investigator plus reviewer. **Replay is scripted, NOT live.** |
| Evidence-only fallback | 25 | No LLM, no assessment |
| Interface | 28 | Paste text or choose a SYNTHETIC example → Analyze → expand the trace → Export JSON (summary) |
| Final record | 30 | What ran, where, at which commit |

Good interface examples:
* **SYNTHETIC: Benign notification.** The classifier says *phishing* (≈ 0.90), while the replay assessment is
  *no_strong_indicators*. The disagreement warning shows the dataset confound.
* **SYNTHETIC: Prompt-injection attempt.** The injected instruction is cited as evidence, not obeyed.

## 3. Live demonstration (optional; needs your Gemini key)
1. Google AI Studio → create an API key with your own account.
2. Colab left sidebar → key icon (*Secrets*) → add `GEMINI_API_KEY` → turn on *Notebook access*.
   Never paste the key into a cell, an output or a chat.
3. Section 21: keep `MODEL_OVERRIDE = None` (model `gemini-3.6-flash`), set `RUN_LLM_PREFLIGHT = True`, and run
   the cell. Expect `"status": "ok"`. This makes 2 small synthetic requests, and the result is reused for the rest
   of the runtime.
4. Either:
   * **Section 26:** set `RUN_LIVE_AGENT = True` (one case, `LIVE_CASE = "credential_link"`) and run it, or
   * **Section 28 interface:** choose *Live agent*, tick the acknowledgement (the content is sent to Google's
     Gemini API), then Analyze a **synthetic** example.
5. Show the report's **Model used** line, the reviewer outcome and the trace counters (≤ 6 requests, ≤ 5 tools,
   90 s).
6. Afterwards, set both flags back to `False` before saving anything to GitHub.

## 4. If the provider fails during the demo
| Symptom (report termination) | Meaning | What to do |
|---|---|---|
| `preflight_not_passed` | No passed preflight for the configured model and SDK in this runtime | Run section 21 with `RUN_LLM_PREFLIGHT = True` |
| `provider_quota` (quota: daily / unclassified) | Quota is exhausted; it is not retried, and a batch stops | Switch the interface to **Evidence only** or **Scripted replay** (both clearly labelled), or try later |
| `provider_quota` (quota: rate_limit) | Short-term limit; retried once if the provider delay fits the budget | Wait a minute, then retry |
| `provider_server` | 5xx or overload after bounded backoff retries (at most 2 per run; a provider-requested delay is waited in full only if it fits the deadline, never shortened) | Retry later, or set `MODEL_OVERRIDE` to another listed model **and re-run its preflight** (there is no automatic switch) |
| `budget_exhausted` / `deadline_exceeded` | A partial result, marked needs human review | Explain the budgets; this is intended behaviour |

Never present a replay or evidence-only result as a live result.

## 5. What not to claim
* Production readiness, or real-world detection accuracy: because of the source/class confound, the 0.99 test F1
  cannot be attributed to generalizable phishing detection.
* Calibrated probabilities: scores are uncalibrated model estimates.
* Immunity to prompt injection: the handling reduces risk but does not eliminate it.
* That reviewer approval guarantees correctness. A user-reported live run approved an unsupported
  "no attachments" claim; that case is now caught deterministically, but other phrasings may not be.
* That "no strong indicators" means safe.

## 6. After the demo
* Download the executed notebook into `colab_import/` (git-ignored) if it should become evidence.
* Never commit it directly: outputs are sanitized first. Canonical notebook outputs stay cleared, with the API
  flags False.
