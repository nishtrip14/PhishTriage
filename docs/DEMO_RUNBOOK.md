# Demo runbook (Google Colab, CPU)

**Open:** https://colab.research.google.com/github/nishtrip14/PhishTriage/blob/phishtriage-colab/notebooks/PhishTriage_Colab.ipynb

## Before the audience arrives (about 10 minutes)
1. *Runtime → Disconnect and delete runtime*; *Runtime → Change runtime type → CPU*.
2. **Section 0 code:** set `PHISHTRIAGE_REVISION = "<full 40-character SHA>"`. Use the SHA in
   [VERIFICATION.md](VERIFICATION.md), or keep `"phishtriage-colab"` to follow the branch.
3. *Runtime → Run all*. Nothing waits for input, and nothing calls an LLM API.
4. **Section 0 output:** the `code commit used` line must show your SHA, without `(MODIFIED)`.
5. Scroll to **section 28** and check that the form is visible. If you plan a live example, run the section 21
   preflight now (section 5 below), not during the talk.

## Three-minute demo path
| Time | Do | Say |
|---|---|---|
| 0:00–0:30 | Show the README architecture diagram, or section 11's test table | "A classifier is one evidence tool. A bounded investigator uses four read-only tools, a reviewer checks the draft, and the application validates every citation. F1 ≈ 0.99 here, **but** source and class are confounded, so that is not real-world accuracy." |
| 0:30–1:00 | **Section 28:** *Input: Synthetic example* → *SYNTHETIC: Credential request with suspicious link characteristics*; *Mode: Evidence only (no LLM)*; **Analyze** | "This is a synthetic `.eml`. Evidence-only mode uses no language model." |
| 1:00–1:30 | Point to the classifier line, the findings table (credential language, link text naming a different host), *Example playbook guidance* and the recommended steps with their IDs (`PB-01.S1`) | "Each piece of evidence has a status. Playbooks are EXAMPLE POLICY. Recommended steps are the playbook's own words, with step IDs." |
| 1:30–2:15 | *Mode: Scripted replay (synthetic examples only; NOT live)* → **Analyze** on the same email. Open the **trace** | "This is a pre-written replay, labelled NOT live. It shows the protocol: tool calls, a finalize, a reviewer objection to 'definitely a phishing attack', one revision, then approval. Six model requests, the budget limit." |
| 2:15–2:40 | Point to *Recommended human actions*: `PB-01.S1` and `PB-04.S3`, each with a separate model rationale. Then **Export JSON** with *Detailed export* unticked | "The model can only pick step IDs from playbooks it retrieved. The application checks the ID and version and shows the playbook text, so invented advice such as 'block the IP' cannot appear as a playbook step. The summary export holds IDs and counts, no email text." |
| 2:40–3:00 | Choose *SYNTHETIC: Benign notification*, replay, **Analyze** | "Limitation: the classifier says phishing (≈ 0.90) while the agent finds no strong indicators. Both are shown, with a disagreement warning; 'no strong indicators' never means safe. A valid step ID proves the step exists, not that the playbook fits; the reviewer and a human judge that." |

If there is time, edit the subject once to show the **stale** warning and the disabled export.

## API-free fallback (always available)
* **Evidence only** and **Scripted replay** work without a key. Always say "replay" or "evidence only"; never
  present them as live.
* **Saved genuine live results**, each labelled with its revision and date:
  * `reports/live_smoke_20261017.json`: code `6a137d8` (grounded actions), gemini-3.8-flash, 2026-10-17.
    `benign_notification` ended `needs_human_review`: its three playbook steps passed validation, but the reviewer
    objected that PB-06 does not fit, and no request was left for a revision. `credential_link` failed with
    HTTP 503s. No approved live report exists at this revision.
  * `reports/model_comparison_20261017.json`: code `7849593`, agent version 1.0, before grounded actions.
    `credential_link` was approved on three models, but their free-text actions included unsupported steps, which
    is the defect that version 1.1 fixes. Show it only as the "before" picture.

## Optional live example (only if the section 21 preflight shows `ok` in this runtime)
1. The `GEMINI_API_KEY` Colab Secret must exist with *Notebook access* on. Never upload `.env` to Colab.
2. **Section 21:** `RUN_LLM_PREFLIGHT = True`, then run the cell. Expect `"status": "ok"` for `gemini-3.8-flash`
   (provisional default; [MODEL_SELECTION.md](MODEL_SELECTION.md)).
3. **Section 28:** *Mode: Live agent*, tick the acknowledgement, choose a **synthetic** example, then **Analyze**
   once. Show **Model used**, the reviewer outcome and the step IDs. Any outcome, including `needs_human_review`
   or a provider error, is a valid thing to show.

## Honest fallback when something fails
| Report says | Say | Do |
|---|---|---|
| `provider_quota` | "Quota is exhausted; the system stopped instead of retrying and skips later batch cases" | Continue with evidence-only and replay, labelled |
| `provider_server` | "The provider failed after bounded retries; nothing was invented" | Same |
| `preflight_not_passed` | "Live mode is gated on a passed preflight for the configured model" | Run section 21, or stay API-free |
| `needs_human_review` | "The review was unresolved or the budget ran out; this is the intended safe outcome" | Show the trace and the objection |

Afterwards, set all flags back to `False`. If the widgets rendered and worked, set
`WIDGETS_CONFIRMED_BY_PERSON = True` in section 30, then re-run sections 29 and 30.

## Colab verification checklist (once, before the presentation)
This is the only remaining verification step: the current code has run locally (tests, notebook, smoke test) but
**not in Colab**. Record what you actually see; a local widget test is not Colab verification.

| # | Where | Do | Expect |
|---|---|---|---|
| 1 | Runtime | Fresh CPU runtime; section 0 `PHISHTRIAGE_REVISION` = the pushed SHA; *Run all* | `code commit used: <SHA>` without `(MODIFIED)` |
| 2 | Sections 0–30 | Let *Run all* finish | No error cell. Section 26: `LIVE AGENT: skipped: RUN_LIVE_AGENT is False`. Section 29: `8 synthetic verification records`. Section 30: `offline_interface_checks_passed: true`, `widget_rendering: UNVERIFIED …` |
| 3 | Section 28 | Look at the form | Input toggle, Example, Mode, Analyze, Clear, Detailed export and Export JSON are visible; live notice says `no preflight for this model yet` |
| 4 | Section 28 | *Synthetic example* → *Credential request…*, *Evidence only*, **Analyze** | `Completed: evidence only (no LLM)` banner; classifier `phishing`; steps `PB-01.S1`, `PB-04.S1`, `PB-03.S1`, `PB-06.S1` |
| 5 | Section 28 | Same email, *Scripted replay*, **Analyze** | `Completed: reviewer approved`, with mode `SCRIPTED REPLAY … NOT live-agent validation`; 2 reviews; steps `PB-01.S1` and `PB-04.S3` with separate model rationales; trace lists 6 model requests |
| 6 | Section 28 | **Export JSON** (detailed unticked) | `Exported summary JSON: …` and a download; the file has `recommended_action_ids` and no email text |
| 7 | Section 28 | Switch *Input* to *Paste text* and type one character in the subject | "Input changed since this result was produced" warning; Export JSON disabled |
| 8 | Section 28 | *Mode: Live agent* without a preflight, **Analyze** | Warning `live mode unavailable: … no preflight …`; nothing sent; the form still works |
| 9 | Section 28 | Choose *Paste text* with *Scripted replay*, **Analyze** | Warning that replay only works for synthetic examples; the form still works |
| 10 | Optional live | Section 21 preflight, then one live *Benign notification* in section 28 (acknowledgement ticked) | Any outcome. A `needs_human_review` or `failed` report must render with its trace and export |
| 11 | Section 30 | Re-run section 30 | `Live outcomes` counts match what you ran (0 unless step 10 ran; failures never counted as approved) |
| 12 | Afterwards | Flags back to `False`; only if steps 3–9 worked, set `WIDGETS_CONFIRMED_BY_PERSON = True` and re-run 29–30 | `widget_rendering` records your confirmation |

Download the executed notebook (*File → Download → Download .ipynb*) into `colab_import/` so it can be recorded
against its revision. Without step 10, the `needs_human_review` and `failed` renderings are covered only by
offline tests.
