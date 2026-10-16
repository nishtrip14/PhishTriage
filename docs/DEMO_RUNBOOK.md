# Demo runbook (Google Colab, CPU)

**Open:** https://colab.research.google.com/github/nishtrip14/PhishTriage/blob/phishtriage-colab/notebooks/PhishTriage_Colab.ipynb

## 1. Fresh setup and revision (about 1 minute, plus a few minutes for Run all)
1. *Runtime → Disconnect and delete runtime*; *Runtime → Change runtime type → CPU*.
2. **Section 0 code:** set `PHISHTRIAGE_REVISION = "<full 40-character SHA>"`. Use the SHA in
   [VERIFICATION.md](VERIFICATION.md), or keep `"phishtriage-colab"` to follow the branch.
3. *Runtime → Run all*. Nothing waits for input, and nothing calls an LLM API.
4. **Section 0 output:** the `code commit used` line must show your SHA, without `(MODIFIED)`.

## 2. API-free example (sections 11, 24, 28)
1. **Section 11:** the test table. Say it plainly: F1 ≈ 0.99, **but** source and class are confounded, so the
   scores cannot be attributed to generalizable detection.
2. **Section 28, interface:** *Input: Synthetic example* → *SYNTHETIC: Benign notification*; *Mode: Evidence only*;
   **Analyze**.

## 3. Evidence inspection
In the report, point to:
* the classifier line (*phishing*, ≈ 0.90, uncalibrated);
* **Missing information:** sender, authentication and attachments are *unknown* for pasted text, not absent;
* *Example playbook guidance* (EXAMPLE POLICY);
* the collapsible **trace**.

## 4. Reviewer, disagreement and missing evidence (replay; labelled NOT live)
1. *Mode: Scripted replay* → **Analyze** on the same example. The assessment is *no_strong_indicators*, with a
   **Disagreement** warning, and the findings cite `observed_absent` / `cue_scan` evidence and PB-07.
2. *SYNTHETIC: Credential request…* → replay. The reviewer first objects to an overconfident sentence, and the
   one revision fixes it (6 model requests in total).
3. *SYNTHETIC: Prompt-injection attempt* → replay. The injected instruction is cited as evidence, not obeyed.

## 5. Live example (only if the section 21 preflight shows `ok` in this runtime)
1. The `GEMINI_API_KEY` Colab Secret must exist with *Notebook access* on.
2. **Section 21:** `RUN_LLM_PREFLIGHT = True`, then run the cell. Expect `"status": "ok"` for `gemini-3.6-flash`.
3. **Section 28:** *Mode: Live agent*, tick the acknowledgement, choose a **synthetic** example, then **Analyze**.
   Show **Model used** and the reviewer outcome.

## 6. Export
1. **Export JSON**, with *Detailed export* unticked: the summary has no email text.
2. Edit the input once to show the **stale** warning and the disabled export.

## 7. Honest fallback
| Report says | Say | Do |
|---|---|---|
| `provider_quota` | "Quota is exhausted; the system stopped instead of retrying and skips later batch cases" | Continue with evidence-only and replay, labelled |
| `provider_server` | "The provider failed after bounded retries; nothing was invented" | Same |
| `preflight_not_passed` | "Live mode is gated on a passed preflight for the configured model" | Run section 21, or stay API-free |
| `needs_human_review` | "The review was unresolved or the budget ran out; this is the intended safe outcome" | Show the trace |

Never present replay or evidence-only output as live. Afterwards, set all flags back to `False`. If the widgets
rendered and worked, set `WIDGETS_CONFIRMED_BY_PERSON = True` in section 30, then re-run sections 29 and 30.
