"""Focused checks for gaps found in the final audit: label/exclusion rules, train-only fitting with dev-only
selection, and the .eml part/attachment limits. All data here is synthetic."""
from email.message import EmailMessage

import numpy as np
import pandas as pd

from phishtriage import data as D, email_input as E, models as M


def raw_frames():
    naz = pd.DataFrame({"sender": ["a@example.com"] * 3, "subject": ["Verify", "Verify", "Shared"],
                        "body": ["verify your account now", "verify your account now", "identical text"],
                        "label": [1, 1, 1]})
    sa = pd.DataFrame({"sender": ["b@example.org"] * 4, "subject": ["Lunch", "Cheap pills", "Shared", ""],
                       "body": ["lunch on friday", "buy cheap pills", "identical text", "  "],
                       "label": [0, 1, 0, 0]})
    return {"nazario": naz, "spamassassin": sa}


def test_label_mapping_and_exclusion_rules():
    data, audit = D.audit_and_exclude(D.normalize_sources(raw_frames()))
    reason = dict(zip(data["record_id"], data["exclusion_reason"]))
    assert reason["spamassassin:00001"] == "spam_not_phishing"              # generic spam is never "phishing"
    assert reason["spamassassin:00003"] == "empty_text"
    # identical text under two (source, label) pairs is ambiguous: every copy is excluded
    assert reason["nazario:00002"] == reason["spamassassin:00002"] == "conflicting_duplicate_labels"
    # exact duplicate with the same label: the lowest record_id is kept, the extra copy dropped
    assert reason["nazario:00000"] == "" and reason["nazario:00001"] == "exact_duplicate_extra_copy"
    kept = data[data["included"]]
    assert dict(zip(kept["record_id"], kept["label"])) == {"nazario:00000": 1, "spamassassin:00000": 0}
    assert audit["conflicting_duplicate_groups_all_rows"] == 1


def test_learned_transforms_fit_on_train_and_selection_uses_dev_only():
    train = ["verify your password now", "confirm billing details", "team meeting notes", "lunch friday plans"] * 3
    y_train = np.array([1, 1, 0, 0] * 3)
    dev = ["verify password zzdevonly", "meeting notes zzdevonly", "confirm billing zzdevonly", "lunch zzdevonly"]
    y_dev = np.array([1, 0, 1, 0])
    cfg = M.tune_on_dev("tfidf_logreg", "original", train, y_train, dev, y_dev)
    pipe = M.build_pipeline("tfidf_logreg", "original", cfg["params"]).fit(train, y_train)
    vocab = pipe.named_steps["tfidf"].vocabulary_
    assert "zzdevonly" not in vocab and "verify" in vocab                   # vocabulary/IDF learned from train only
    dev_scores = M.phishing_scores(pipe, dev)
    assert cfg["threshold"] in set(np.round(dev_scores, 12)) or np.isclose(dev_scores, cfg["threshold"]).any()
    assert {"params", "threshold", "dev_average_precision", "grid"} <= set(cfg)   # chosen from dev scores only


def test_eml_part_and_attachment_limits():
    m = EmailMessage()
    m["From"], m["Subject"] = "x@example.com", "many parts"
    m.set_content("body")
    for i in range(E.MAX_MIME_PARTS + 5):
        m.add_attachment(b"x", maintype="application", subtype="octet-stream", filename=f"f{i}.bin")
    case = E.parse_eml(bytes(m))
    assert len(case.attachments) == E.MAX_ATTACHMENTS
    assert any("attachments recorded" in w for w in case.parse_warnings)
    assert any(f"{E.MAX_MIME_PARTS} MIME parts" in w for w in case.parse_warnings)
