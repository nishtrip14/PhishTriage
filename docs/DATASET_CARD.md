# Dataset card: PhishTriage phase 1

All numbers come from `reports/audit_summary.json`, which the notebook generated from the files it loaded.
That run was **local, on 2026-10-15**. It still has to be confirmed in Colab (see `COLAB_STATUS.md`).

## Source
| | |
|---|---|
| Dataset | *Phishing Email Curated Datasets*, A. I. Champa |
| Record / DOI | https://zenodo.org/records/8339691 · 10.5281/zenodo.8339691 (published 2023-09-13; the record has no version string) |
| License | CC-BY-4.0. The underlying corpora (Nazario phishing corpus, SpamAssassin public corpus) keep their original terms. This repository **does not redistribute any message text**. |
| Access | Open. Downloaded anonymously from the Zenodo API; no credentials needed. |
| Citation | Champa, Rabbi, Zibran, "Curated Datasets and Feature Analysis for Phishing Email Detection with Machine Learning", IEEE ICMI 2024 |

| File used | Bytes | MD5 (Zenodo) | SHA-256 (verified) | Rows |
|---|---|---|---|---|
| `Nazario.csv` | 7,811,841 | `4022d055bb7cf8602f30f768f652e91e` | `b8fbc4158fbdfaff1ed98584c43d72e283c6352d7ade4d457d34c1d79488d184` | 1,565 |
| `SpamAssasin.csv` | 14,879,195 | `d921e0b2333bfaa058bd38193e6b3fbd` | `3bfe8f8abff89f69a98456be50413c2fcb20a476141116dd84ee1507b980c00e` | 5,809 |

The total download is 22.7 MB. Both files are plain CSV, so no extraction step is needed.
Both have the columns `sender, receiver, date, subject, body, urls, label`.

## Why not MeAJOR?
The prompt suggested the MeAJOR v2.0 record (https://zenodo.org/records/18471483, CC-BY-4.0, 2026-02).
It was inspected on 2026-10-15. The record **description** lists TREC-05/06/07, the Nazario corpus and Nigerian
fraud. The **data file** `meajor_cleaned_preprocessed.parquet.gzip` (86 MB; its MD5 matched) has 108,685 rows,
and every row with a source has `source ∈ {trec5, trec6, trec7}`. One row has no source or label.

Its `label=1` (48,034 rows) is therefore the TREC **spam** label. Training on it would conflate generic spam with
phishing, so it was rejected.

## Label mapping
| Source | Original label | Rows | Mapped label |
|---|---|---|---|
| Nazario | 1 | 1,565 | phishing |
| SpamAssassin | 0 (ham) | 4,091 | legitimate |
| SpamAssassin | 1 (spam) | 1,718 | **excluded**: generic spam, not phishing |

Nigerian-fraud (419) files exist in the same record. They were **not used**: advance-fee fraud is a different
social-engineering category from credential or payment phishing, and mixing it in would blur the task.

## Exclusions and final counts
| Step | Rows |
|---|---|
| Loaded | 7,374 |
| Excluded: `spam_not_phishing` | 1,718 |
| Excluded: `exact_duplicate_extra_copy` (one copy kept, the lowest `record_id`) | 14 |
| Excluded: `conflicting_duplicate_labels` | 0 (no identical text appeared with different source/label pairs) |
| Excluded: `empty_text` | 0 |
| **Included** | **5,642** (legitimate 4,090 · phishing 1,552; 27.5% phishing) |

Across all loaded rows, 20 duplicate groups covered 40 rows. Duplicates are matched on lower-cased text with
whitespace collapsed. Six of the 20 redundant copies were spam rows, already excluded for being spam.

Missing or blank fields (Nazario / SpamAssassin):

| Field | Nazario | SpamAssassin |
|---|---|---|
| receiver | 96 | 210 |
| date | 1 | 0 |
| subject | 4 | 16 |
| body | 2 | 2 |
| sender | 0 | 0 |

Every combined `subject + body` text is non-empty. Missing fields are flagged, never filled in.

## Normalized schema
`record_id` (`<source>:<row index>`), `source`, `subject`, `body`, `text` (subject + body: the **only** model
input), `original_label`, `mapped_label`, `exclusion_reason`, `missing_{sender,receiver,date,subject,body}`,
`src_url_flag` (the curator's 0/1 flag), `year` (audit only), `text_hash`, `group_id`, `split`.

## Known confounds and limitations
These were measured on the included rows. Treat them as threats to validity in the evaluation phase.

1. **Source = label.** Every phishing record is from Nazario and every legitimate record from SpamAssassin, so a
   classifier can learn corpus style instead of phishing behaviour.
2. **Collection artifacts in the text:**

   | Artifact | Legitimate | Phishing |
   |---|---|---|
   | Collector mailbox `monkey.org` | 0.3% | 39.6% |
   | Collector name "jose" | 0.3% | 40.7% |
   | Mailing-list footer (`listinfo` / `unsubscribe`) | 61.2% | 3.9% |
   | SpamAssassin / SourceForge mention | 15.4% | 0.1% |
   | Bracketed list tag in subject | 38.1% | 2.8% |
   | Literal `http(s)://` link | 86.7% | 12.4% |
3. **Temporal gap.** Phishing dates span 2015–2022 (median 2018; 10 dates unparseable). Legitimate mail is from
   2002 at the 5th–95th percentiles, with an implausible maximum of 2028 and 48 unparseable dates.
4. **URLs.** The curated `urls` column is a 0/1 flag (legitimate 88.1%, phishing 90.9%). Phishing bodies were
   converted from HTML with their link targets removed, which is why few contain literal links. URL-based features
   cannot be derived from this data.
5. **Small and imbalanced.** There are 1,552 phishing records. One phishing text is about 4.6 M characters long.
6. **Grouping is not de-confounding.** Grouped splitting keeps duplicate and near-duplicate messages within one
   split. It does not remove the source–label confound, because every split has Nazario-only phishing and
   SpamAssassin-only legitimate mail. Leave-one-source-out evaluation is meaningless here, since each source has
   one class. In phase 2, removing the known artifacts barely changed the scores, and residual cues remained
   (`utf`, `url`, mailing-list topics). See `docs/MODEL_EVALUATION.md`.
7. **Label noise.** At least one Nazario "phishing" record is a mailbox-format pseudo-message ("DON'T DELETE THIS
   MESSAGE -- FOLDER INTERNAL DATA"), not a phishing email.
8. **Identifying information.** The text contains real names and addresses from public corpora. Displayed examples
   are redacted (emails, URLs, IP addresses, numbers, reply attributions, and From/To/Cc headers), but the
   redaction is heuristic. The executed report must be checked by a person before it is published.

## Partitions
- **Grouping.** Exact duplicates are collapsed first. Near-duplicates are then linked when the **exact Jaccard
  similarity ≥ 0.8** on CRC32-hashed word 5-gram shingle sets. Connected components become groups.
  This found 274 linked pairs, giving 141 multi-record groups that cover 330 records. The largest group has 9
  records, and no group mixes labels.
  **Limitation:** this does not detect paraphrases or heavily edited templates.
- **Split.** Whole groups are assigned with a seeded shuffle (seed 42), stratified by each group's majority label,
  with cumulative record shares of 70/15/15.

| Split | Records | Share | Groups | Legitimate | Phishing |
|---|---|---|---|---|---|
| train | 3,949 | 70.0% | 3,818 | 2,863 | 1,086 |
| dev | 846 | 15.0% | 821 | 613 | 233 |
| test | 847 | 15.0% | 814 | 614 | 233 |

- **Assertions in the notebook (all passed):** every record assigned; no record overlap; no group spans splits;
  no identical text spans splits; ≥ 50 records per class per split; regenerating the split gives the same result;
  shares within ±3 points of the target; model input is `text` only (no source, label, ID, date or URL flag).
- **Not done yet:** no TF-IDF or other learned preprocessing has been fitted.

## Published evidence (`reports/`)
- `dataset_provenance.json`: URLs, checksums, retrieval status, label mapping, rejected candidate, versions.
- `audit_summary.json`: aggregate counts only.
- `split_manifest.csv` (5,642 rows): `record_id, group_id, split, mapped_label`. Its IDs are row indices
  into the checksum-pinned public files. It contains no text, addresses or text hashes.
- `figures/class_balance.png`, `figures/text_length.png`.
