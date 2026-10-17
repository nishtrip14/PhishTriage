# PhishTriage explained (start here)

This guide explains the project from first principles, in the order you would explain it to someone else. Every
number and name comes from the current code or the recorded evidence in [`reports/`](../reports).

## 1. The problem
People receive emails that might be phishing: messages designed to steal passwords, money or data. Deciding
quickly is hard. A single "phishing: yes or no" score does not help much, because the person also needs to know
**why**, what is **unknown**, and **what to check next**.

PhishTriage produces a **triage report** to support a human decision. It never acts on email by itself.

## 2. The overall approach
There are four ingredients, combined in one workflow:
1. **A text classifier.** It scores how much the subject and body resemble the phishing examples it was trained on.
2. **Offline evidence extraction.** It records what is actually in the email: sender fields, links as text,
   attachment metadata, keyword cues, and what is missing.
3. **Example playbooks** and **retrieval.** Eight short documents describe situations such as credential theft or
   a payment-detail change, and the matching one is found by text similarity.
4. **An agent workflow.** A language model (Gemini) acts as an *investigator*: it chooses which tools to call and
   drafts a report. A second pass acts as a *reviewer*. The application enforces strict limits and checks
   citations.

## 3. The components
| Component | What it does in plain words | File |
|---|---|---|
| Data pipeline | Downloads the dataset, checks its fingerprint (SHA-256), removes spam and duplicates, and splits it so near-identical emails never land in two splits | `phishtriage/data.py` |
| Classifier | Turns text into word-weight vectors (TF-IDF) and applies logistic regression | `models.py`, `text.py`, `inference.py` |
| Email input | Reads pasted text or an `.eml` file safely: HTML becomes plain text, attachments are never opened | `email_input.py` |
| Evidence | Makes a numbered list of observations with a status (observed, absent, unknown, claim, error) | `evidence.py`, `schemas.py` |
| Playbooks and retrieval | Finds the most relevant example guidance by text similarity | `retrieval.py`, `playbooks/` |
| Tools | Four read-only functions the agent may call, always for one fixed email | `tools.py` |
| Agent workflow | The investigate → draft → check → review → revise loop with budgets | `agent.py`, `agent_model.py` |
| Interface and export | The form in notebook section 28, the readable report and the JSON download | `ui.py`, `export.py` |

## 4. What happens during training (notebook sections 1–15)
1. Two public CSV files are downloaded from Zenodo and checked against pinned SHA-256 fingerprints.
   * Nazario rows are labelled **phishing**, and SpamAssassin *ham* rows **legitimate**.
   * SpamAssassin *spam* rows are removed, because spam is not the same as phishing.
2. Exact duplicates are collapsed. Near-duplicates (emails sharing ≥ 80% of their 5-word phrases) are grouped.
3. **Whole groups** are split 70/15/15 into train, dev and test, so a near-copy of a test email can never appear in
   training. The result is 3,949 / 846 / 847 emails.
4. The vectorizer and classifier are **fitted on train only**.
5. Several settings are tried, and the one with the best average precision **on dev** is kept. The decision
   threshold is the dev value that maximizes F1 for phishing.
6. These choices are frozen and saved with a hash. **Then** the test set is scored exactly once.
7. The chosen model is saved with a manifest (versions, data fingerprints, settings, results). Loading it later
   re-checks its SHA-256.

## 5. What happens when you submit an email (sections 16–28)
1. The input becomes a `CaseInput` with a unique case ID, and `observe()` creates evidence items such as
   `ev-001 … ev-014`.
2. The application calls the classifier itself, so this result is trusted and cannot be changed by the agent.
3. **In live mode:**
   1. The language model receives the email between `<<<UNTRUSTED_EMAIL_START>>>` markers and four tool
      descriptions, then decides which tools to call.
   2. The application validates each call and runs it for this case only.
   3. When the model is done, the application asks for a JSON report with tools switched off.
   4. Deterministic checks verify that every cited evidence ID exists, belongs to the case and was actually
      returned, that playbook citations match what was retrieved, and that the report contains no "no
      attachments"-style claim without matching evidence.
   5. A separate reviewer request approves the draft or requests a revision. At most one revision is allowed;
      otherwise the report is marked **needs human review**.
4. **In evidence-only mode:** no language model is used, and there is no agent assessment.
5. **In replay mode:** the model's turns are pre-written. The tools, checks and budgets are real, but the
   "decisions" are scripted.

## 6. What makes the live workflow agentic
* The **model chooses actions**: which tool, with what arguments, and when to stop. What it learns from those
  results shapes its next step.
* The **application keeps control**:
  * Only four read-only tools exist, always for the bound case.
  * Arguments are validated.
  * Budgets are fixed: 3 rounds, 5 tool executions, 6 model requests and 90 seconds.
  * The output is checked.
* There is **reflection**: a reviewer pass and one bounded revision.

It is the loop of choosing actions, observing the results and revising that makes it agentic, not a particular
framework.

## 7. How retrieval grounds explanations (RAG)
The investigator can call `retrieve_playbook(query)`. Matching sections of the example playbooks (with ID, version
and source path) come back as tool results, and the model may cite them. The application then checks that any
cited playbook was **really retrieved** in this run, with the same version.

Recommended actions are not written by the model. Each playbook lists numbered next steps (for example `PB-01.S1`),
and the model can only pick step IDs from playbooks it retrieved in this run. The application checks the ID and the
version, then shows the playbook's own wording. The model's short rationale is shown separately and rejected if it
adds steps (such as "delete" or "block") or certainty (such as "malicious"). A valid ID proves the step exists in
that playbook, not that the playbook fits this email, so the reviewer judges fit and a human decides. If no step
fits, the report says so. The system never carries out any action.

The retrieval score is cosine similarity between texts. It says "this playbook's wording matches the query", **not**
"this email is phishing".

## 8. How the reviewer works
The reviewer gets a packet: the draft, the evidence list with statuses, the retrieved playbooks and the
deterministic issues. It gets no tools. It answers `approve` or `revise` with typed objections, such as
`unsupported_claim`, `overconfident` or `followed_email_instructions`.

Approval also requires **no deterministic errors**. The reviewer is the same model in a different role, so it is a
second check, **not an independent guarantee**. A user-reported live run showed a reviewer approving an unsupported
"no attachments" claim; that pattern is now caught deterministically.

## 9. What the system cannot establish
* **Real-world accuracy.** All phishing comes from one corpus and all legitimate mail from another, so the 0.99
  scores cannot be attributed to generalizable detection. No external dataset was tested.
* **Calibrated probabilities.** Scores are uncalibrated.
* **Safety.** `no_strong_indicators` is not proof of safety.
* **Facts it cannot see.** It cannot know where links really go (nothing is fetched), what attachments contain
  (they are never opened), or whether `Authentication-Results` headers are genuine (they are unverified claims).
* **Immunity to prompt injection,** or guaranteed correctness of explanations.

## 10. Illustrative walkthrough (SCRIPTED REPLAY of a SYNTHETIC email, not a live trace)
**Source:** the `credential_link` replay in notebook section 24, local run at code `f6642c9`
([`reports/phase4_summary.json`](../reports/phase4_summary.json)). The model turns are **pre-written** in
`phishtriage/agent_replays.py`.

| Step | What happens |
|---|---|
| Input | A synthetic `.eml` "Urgent: verify your account…". Its link text shows `accounts.example.com`, but the link targets `198.51.100.23` |
| Evidence | Credential-request wording, a link text/target mismatch, a Reply-To on a different domain, Authentication-Results absent (`observed_absent`) |
| Trusted classifier | `phishing`, uncalibrated score shown in the report |
| Investigate | One round with three calls: `inspect_email`, `get_prediction`, `retrieve_playbook` → PB-01 and PB-04 |
| Draft | `suspicious`, with findings citing the evidence IDs, and one overconfident sentence ("definitely a phishing attack") |
| Review | `revise`: objection `overconfident` |
| Revision | The overconfident sentence is replaced by a hedged classifier statement |
| Final review | Approved; 6 model requests and 3 tool executions in total |

## 11. Glossary (tied to this project)
* **TF-IDF.** Each word or word pair gets a weight `tf × idf`. `tf` is how often it appears in this email
  (sublinear: 1 + log(count)); `idf = log((1+N)/(1+df)) + 1` grows when few emails contain it.
  For example, "verify password" is frequent in phishing and rare overall, so it gets a high weight.
* **Sparse features.** Each email is a vector with up to 50,000 dimensions, almost all zero; only non-zeros are
  stored.
* **Logistic regression.** A weighted sum of features passed through the sigmoid `1/(1+e^-z)`. The weights are
  learned on train. Positive weights push towards phishing, which is how section 12 lists influential terms.
* **Naive Bayes (multinomial).** Uses word-frequency distributions per class, assuming words are independent given
  the class; α smooths unseen words.
* **Threshold.** A score ≥ threshold is labelled phishing. It was chosen on dev (0.261 for the primary model in the
  canonical run).
* **Precision.** Of the emails flagged phishing, the share that really are: TP / (TP + FP).
* **Recall.** Of the real phishing emails, the share flagged: TP / (TP + FN).
* **F1.** The harmonic mean 2PR / (P + R).
* **False positive (rate).** A legitimate email flagged as phishing; FPR = FP / (FP + TN).
* **Average precision (AP).** The area under the precision–recall curve across all thresholds.
* **Calibration.** Whether a score of 0.8 means "80% of such emails are phishing". These scores were **not**
  calibrated, because no separate calibration partition exists.
* **RAG (retrieval-augmented generation).** Giving a language model retrieved documents (here, playbook sections)
  to ground what it writes.
* **Tool calling.** The model returns a structured request such as `retrieve_playbook(query="…")`; the
  application runs it and returns the result.
* **Agent state.** Where the loop is (investigate, finalize, review, revise, done), plus the counters for requests,
  tool executions, retries and time.
* **Provenance.** A record of where a result came from: code commit, environment, versions, data fingerprints.
