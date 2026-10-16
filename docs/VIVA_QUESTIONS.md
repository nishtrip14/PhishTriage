# Viva questions and answers

The answers describe **this implementation**. File and section references let you show the evidence.

**1. Why this project?**
Phishing is a common way into accounts and payments, and people triaging email need reasons and next steps, not just
a label. The project explores how a classifier, evidence extraction, retrieval and a bounded agent can together
produce a **checkable** explanation, and how to be honest about what such a system can and cannot establish.

**2. Why not only a classifier?**
A classifier gives a score but no account of *which* evidence matters, what is unknown, or what to do. Its score is
also unreliable outside the training distribution (see Q9). PhishTriage keeps the classifier as one evidence tool.
It adds observations with explicit statuses, example playbooks, and a report whose citations are validated.

**3. Why TF-IDF and linear models instead of a transformer classifier?**
* They run in seconds on a Colab CPU, and the influential terms are inspectable (section 12), which made the
  confound visible: `jose`, `monkey`, `http` and `2002` were top terms before normalization.
* They are a standard, strong text baseline.
* A transformer would not fix the core problem: with source and label confounded, any model can learn corpus style.

**4. Where is RAG used?**
* The investigator can call `retrieve_playbook(query)` (`tools.py` / `retrieval.py`). It searches a separate
  TF-IDF index over 8 example playbooks, split into 40 sections.
* Hits come back with `doc_id`, `version`, excerpt and source reference, and the model may cite them.
* `validate_draft` rejects playbook citations that weren't retrieved in that run, or have the wrong version.
* The reviewer receives the retrieved excerpts.

**5. Where is the agent's decision-making?**
In live mode, the model decides which of the four tools to call, with which arguments, and when it has enough to
stop (`run_triage`, investigate rounds). Its draft is then reviewed, with at most one revision. The application
decides permissions, the case, budgets and acceptance.

**6. Why two roles (investigator and reviewer)?**
* **Separation of concerns:** the investigator gathers and drafts; the reviewer only checks support,
  contradictions, overconfidence, playbook consistency and injected instructions.
* **Same model:** both use the **same provider and model**, so the reviewer is not an independent judge. Approval
  also requires that the deterministic checks pass.
* **Not a guarantee:** a user-reported live run showed a reviewer approving an unsupported "no attachments" claim.
  That is now caught deterministically.

**7. Why not CrewAI or another framework?**
It isn't required by the title. The workflow is agentic because the model chooses actions within a feedback loop.
When checked, `crewai[google-genai]` 1.15.28 pinned `google-genai~=1.65`, which cannot be installed together with
the SDK in use, and it pulled in about 141 packages. The direct SDK loop keeps budgets, retries and validation
explicit and testable.

**8. Does the LLM change the classifier score?**
No. The application calls the classifier itself before the agent runs. The model's draft schema has no classifier
fields, and an extra field is rejected as invalid output. A finding that contradicts the classifier's label or score
is flagged as `classifier_value_mismatch`.

**9. Why are the benchmark scores so high (F1 ≈ 0.99)?**
Because phishing (Nazario, 2015–2022) and legitimate mail (SpamAssassin, about 2002) come from different
collections. The models can use style, topic, encoding and date cues. Even after the known artifacts were removed,
the scores stayed at about 0.98–0.99, and terms like `utf` and `url` remained influential. So the scores **cannot
be attributed to generalizable phishing detection**.

**10. What is source confounding?**
A variable other than the label (here the corpus) predicts the label perfectly. Grouped splitting prevents
duplicate leakage, but every split still has Nazario-only phishing and SpamAssassin-only legitimate mail. For the
same reason, leave-one-source-out evaluation is meaningless here.

**11. How was leakage reduced?**
* Spam was excluded, and conflicting duplicates were excluded.
* Exact duplicates were collapsed, and near-duplicates (Jaccard ≥ 0.8 on 5-word shingles) were grouped.
* Whole groups were split 70/15/15.
* All learned transforms were fit on train; parameters and thresholds were chosen on dev; configurations were
  frozen before a single test run.
* Tests check that no record, group or identical text crosses splits.

**12. What does the score mean?**
It is `model_estimated_probability_uncalibrated`: the logistic-regression output for the prepared text. It is not
calibrated (there was no calibration partition), and it is not a real-world probability. The threshold (0.261 for
the primary model in run A) is a decision cut-off chosen on dev.

**13. What if the classifier and the agent disagree?**
Both are shown unchanged, with a **disagreement warning** (`assessment_classifier_disagreement`). For example, the
classifier labels the synthetic benign notification *phishing* (≈ 0.90), while the replayed agent assessment is
*no_strong_indicators*. A human decides.

**14. What happens without an API key?**
*Run all* still works: data, training, evaluation, evidence, retrieval, tools, scripted replay (labelled NOT live),
evidence-only reports, the interface and export. Live mode stays blocked until the section 21 preflight passes.

**15. What happens during quota or server errors?**
* **Server errors** (5xx, timeout, network) are retried with jittered backoff, or after the provider's delay waited
  in full if it fits the 90 s deadline. There are at most 2 retries per run, and each counts as a request.
* **Rate-limit 429s** (classified from the error body) are retried in the same way.
* **Daily or unclassified quota** is not retried: the case ends with `provider_quota`, and `run_batch_triage` skips
  the remaining cases.
* Nothing is fabricated. The report states the termination, and the trace shows the errors.

**16. How are malicious instructions inside emails handled?**
* The email is wrapped in untrusted markers, and marker strings inside the email are removed.
* Instruction-like phrases become `instruction_like_text` evidence.
* The tools are read-only and bound to one case, so text can't widen access.
* The reviewer checks for `followed_email_instructions`, and output is escaped.
* This **reduces** risk. It does not make the system immune.

**17. How are attachments and authentication treated?**
* **Attachments:** only metadata is recorded (name, declared type, size, SHA-256); they are never opened or
  extracted.
* **Authentication:** `Authentication-Results` headers are `unverified_claim` (they can be forged), and nothing is
  re-checked against DNS.
* **Pasted text:** headers and attachments are `unavailable`, meaning unknown, and the system may not claim "no
  attachments".

**18. What was actually tested?**
* **Offline:** 127 tests (data integrity, splits, train-only fitting, parsing limits, evidence statuses, retrieval,
  tools, the agent loop with scripted and fake-Gemini adapters, retries, budgets, quota, configuration, interface
  logic, export privacy).
* **Notebook:** full local runs at the current code, and a Colab run at code `9acefcb`.
* Details: [VERIFICATION.md](VERIFICATION.md).

**19. What remains unverified?**
* Colab evidence for the **current** code: the owner reports a successful run, but the executed notebook hasn't
  been supplied.
* Widget interaction confirmed by a person.
* A completed live case at the current code: the local preflight passed, but the one live case ended with
  HTTP 503 after 2 bounded retries. Earlier live results are user-reported only, at an unrecorded revision.
* Any real-world accuracy.

**20. What would be needed before real deployment?**
* An independent, multi-source labelled evaluation, and probably a model that generalizes across sources.
* Calibration and threshold policies agreed with the people who would use it.
* Human evaluation of explanation quality.
* Security review: authentication, data handling, retention.
* Monitoring.
* Real organizational policies in place of the example playbooks.
* None of these exist in this project.
