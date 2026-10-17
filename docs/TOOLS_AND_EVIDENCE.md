# Phase 3: evidence, playbooks, retrieval and tools

Everything here runs **inside the Colab runtime** (or locally) from the `phishtriage/` package. There is no hosted
backend, database or vector store.

## Schemas (`phishtriage/schemas.py`)
Frozen dataclasses with `to_dict()`, all JSON-serialisable.

| Type | Key fields |
|---|---|
| `CaseInput` | `case_id`, `input_kind` (`pasted`/`eml`), `subject`, `body`, selected `headers`, `attachments` (metadata), `html_links`, `parse_warnings`, `received_at`. **No label field**: ground truth never enters a case. |
| `EmailObservation` | per-case summary: subject excerpt, body length, truncation, From / Reply-To, URLs, attachment count, warnings, evidence IDs |
| `EvidenceItem` | `evidence_id` (`<case_id>/ev-NNN`), `case_id`, `evidence_type`, `source`, `status`, `value`, `excerpt` (bounded, HTML-escaped), `observed_at`, `limitations` |
| `ToolResult` | `tool`, `status` (`ok`/`unavailable`/`error`/`rejected`), `data`, `error`, `evidence_ids`, `limitations`, `truncated_output` |
| `RetrievalHit` | `doc_id`, `chunk_id`, `title`, `version`, `section`, `excerpt`, `relevance`, `relevance_type`, `source_ref` |

**Evidence status:**
- `observed`: present in the input and read by a local check.
- `unverified_claim`: present but asserted by an unverifiable party, such as `Authentication-Results`.
- `unavailable`: absent. **Missing information is not evidence of safety.**
- `error`: a failed check. It is never turned into a successful result.

`ToolResult` enforces two rules: an `ok` result carries no error, and every non-ok result explains itself.

**Phase 5 addition, `observed_absent`:** "checked and not found within `value.scope`". It separates observed
absence (no URL text in the provided text; no attachment parts in a supplied `.eml`; a header missing from a
supplied `.eml`) from `unavailable` (not provided: presence and absence are both unknown). A `cue_scan` item lists
which keyword cues were checked and matched. `inspect_email` returns `status_meanings` with each result.

## Safe input (`phishtriage/email_input.py`)
- **Pasted subject/body** is always supported. Empty input is rejected, and the result records that headers,
  sender identity, authentication results and attachments are unavailable.
- **`.eml`** is parsed with the standard library's `email` package:
  - Size and count limits: 2 MB raw, 50 MIME parts, 20 attachments, 200,000 body characters, 1,000 characters
    per header value, and the first 5 values per header.
  - Parser defects become warnings. Malformed input is parsed leniently or rejected with a clear error.
- **HTML** is converted to text with `html.parser`. Script, style, noscript and template contents are dropped,
  link (text, href) pairs are recorded, and nothing is rendered.
- **Never done:** fetching URLs, loading remote images, opening, executing or extracting attachments, or
  re-checking SPF/DKIM/DMARC against current DNS.
- Attachments are recorded as filename, declared type, size and SHA-256 only.

## Local observations (`phishtriage/evidence.py`)
| Evidence type | Status | Notes |
|---|---|---|
| `sender_address`, `reply_to`, `return_path`, `sender` | observed / unavailable | header text; sender-controlled and unauthenticated |
| `sender_reply_to_mismatch`, `display_name_address_mismatch` | observed | benign causes listed in limitations (lists, help desks) |
| `authentication_results_claim`, `conflicting_authentication_claims` | **unverified_claim** | spf/dkim/dmarc tokens as *claimed* |
| `url` | observed | string inspection: scheme, host, IP literal, punycode, userinfo, port, plain HTTP |
| `link_text_target_mismatch` | observed | visible domain ≠ href host (HTML only) |
| `attachment` | observed | metadata only |
| `credential_request_language`, `payment_change_language`, `urgency_language`, `attachment_lure_language` | observed | keyword cues; explicitly not validated detectors |
| `instruction_like_text` | observed | email text that tries to instruct an AI; reported as data, never followed |
| `parse_warning` | observed | parser and size-limit warnings |
| `classifier_prediction` | observed / unavailable | added by `get_prediction` |

**These observations are separate from the classifier.** The classifier was trained on bodies whose link targets
were stripped, so its phase 2 test score says nothing about URL, header or attachment evidence.

## Example playbooks (`phishtriage/playbooks/example_playbooks.json`, collection v1.0)
There are eight original documents, labelled **EXAMPLE POLICY**. They are illustrative teaching material, not an
institutional policy or official standard:

| ID | Title |
|---|---|
| PB-01 | Suspected credential theft |
| PB-02 | Invoice or payment-detail change |
| PB-03 | Sender or Reply-To mismatch |
| PB-04 | Suspicious link presentation |
| PB-05 | Unexpected attachment |
| PB-06 | Legitimate urgent communication |
| PB-07 | Missing or conflicting evidence |
| PB-08 | Human escalation and verification |

Each has: situation, observations, benign alternatives, human next steps and limitations.

## Retrieval (`phishtriage/retrieval.py`)
- **Index:** a separate TF-IDF index (word 1–2-grams, English stop words, sublinear TF) over 40 playbook
  sections (8 × 5). It never reuses or refits the classifier's vectorizer.
- **Scoring:** cosine similarity, reported as `tfidf_cosine_retrieval_relevance`. That is retrieval relevance,
  **not** a phishing probability. At most one section per playbook is returned.
- **Threshold:** `MIN_RELEVANCE = 0.10`, fixed before the check set was run. Weaker matches are dropped, which
  gives `no_relevant_match`. An empty query gives `empty_query`.
- **Check set** (`playbooks/retrieval_checks.json`, 16 queries, expectations written before running), local run
  on 2026-10-15:
  - 12/12 answerable queries had a correct top-1 playbook (12/12 within the top 3).
  - 4/4 empty or irrelevant queries correctly returned nothing.
  - Full results: `reports/retrieval_check.json`.
- **Limitations of the check:** I wrote both the playbooks and the queries, so this mainly shows vocabulary
  consistency. It is not a measure of retrieval quality on real reports. The three irrelevant queries share no
  terms with the playbooks, so the 0.10 threshold has not been tested on near misses. Long concatenated queries
  dilute relevance, so callers should send one focused query per question.

## Tools (`phishtriage/tools.py`)
`TriageTools(store, model, manifest, index)` exposes exactly four read-only tools. Their JSON schemas are in
`TOOL_SPECS`. Call them through `call(name, arguments)`, which validates names, argument names and types:

| Tool | Behaviour |
|---|---|
| `get_prediction(case_id)` | Scores subject+body with the preselected `tfidf_logreg__artifact_normalized` model (loaded via SHA-256-checked `load_artifact`). Keeps `score_type = model_estimated_probability_uncalibrated` and all limitations. Cached per case, and stored as a `classifier_prediction` evidence item. With no model it returns `unavailable`; on abstention it returns `unavailable` with the warnings. |
| `inspect_email(case_id)` | Observation summary plus every evidence item, with escaped excerpts marked as untrusted content |
| `retrieve_playbook(query, top_k≤5)` | Hits with version and source reference; `rejected` for an empty query, `unavailable` when nothing is relevant |
| `get_evidence(case_id, evidence_id)` | One item. IDs from another case, unknown IDs and unknown cases are `rejected`. |

**Guarantees:**
- Output is JSON-serialisable and capped at 12,000 characters. Long lists are trimmed, with `truncated_output=True`.
- Internal exceptions become `error` results that report only the exception type.
- There are no shell, HTTP, filesystem or mail-sending tools, and cases carry no labels.

**Not claimed:** prompt-injection resistance of a future agent. The tools enforce case boundaries and report
instruction-like text as evidence. Whether an LLM agent ignores such text is something phase 4 must test.

## Optional LLM preflight (`phishtriage/llm_preflight.py`)
- **Opt-in:** `RUN_LLM_PREFLIGHT = True` in notebook section 21.
- **Key:** read from the Colab Secret `GEMINI_API_KEY` (or the environment). It is never printed, saved or
  returned, and error text is redacted.
- **Model:** at phase 3 (`86993a3`) the default was `gemini-3.8-flash`. **Since `1955903`** the single configured
  default was `gemini-3.6-flash`; **since `3e7cbe1`** it is `gemini-3.8-flash`, a provisional choice
  ([MODEL_SELECTION.md](MODEL_SELECTION.md)) (`LLMSettings`, section 21 `MODEL_OVERRIDE`).
  Override it with `PHISHTRIAGE_GEMINI_MODEL`.
- **Steps:**
  1. `models.get(model)` rejects an invalid ID before any generation call.
  2. One synthetic `generate_content` request with a single function declaration, `mode=ANY`, automatic function
     calling disabled, temperature 0 and `max_output_tokens=1024`. It must return `record_check(token="preflight-ok")`.
- **Bounds:** a 30 s timeout and at most 2 attempts, retrying only 429 and 5xx. 400/401/403/404 are reported
  without retry.
- **SDK:** checked offline against `google-genai` 2.31.0 (config objects build, and `response.function_calls`
  parses).
- **Live result:** the owner later reported a successful Colab preflight (`status: ok`, `gemini-3.6-flash`,
  SDK 2.12.1, `record_check` returned, 2 network calls). The revision is not recorded; see `COLAB_STATUS.md`.
- **CrewAI not adopted:** `crewai[google-genai]` 1.15.28 pins `google-genai~=1.65.0`, which pip cannot resolve
  together with 2.31.0. On its own it installs about 141 packages (chromadb, onnxruntime, Kubernetes client,
  OpenTelemetry) and pins pydantic < 2.13. Phase 4 will use the official SDK with explicit, bounded tool calls.
