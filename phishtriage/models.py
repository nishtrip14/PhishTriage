"""Phase 2: CPU-friendly TF-IDF baselines, dev-only selection, and held-out evaluation."""
from __future__ import annotations

import re
import time

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score, precision_recall_curve,
                             precision_score, recall_score)
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from .data import SEED
from .text import TextPreprocessor

MODEL_KINDS = ("tfidf_logreg", "tfidf_mnb")

# Shared by every configuration so the variants differ only in their text preparation.
TFIDF_PARAMS = dict(lowercase=True, ngram_range=(1, 2), min_df=2, max_df=0.95, max_features=50_000,
                    sublinear_tf=True, dtype=np.float32)

# Small, predeclared grids. Imbalance handling: class_weight="balanced" for LR; NB tries learned vs uniform priors.
PARAM_GRIDS = {
    "tfidf_logreg": [{"C": c} for c in (0.1, 1.0, 10.0)],
    "tfidf_mnb": [{"alpha": a, "fit_prior": fp} for a in (0.01, 0.1, 1.0) for fp in (True, False)],
}
SELECTION_METRIC = "dev average precision (phishing)"
THRESHOLD_RULE = "threshold maximizing phishing F1 on dev"


def build_pipeline(kind: str, variant: str, params: dict) -> Pipeline:
    if kind == "tfidf_logreg":
        clf = LogisticRegression(C=params["C"], class_weight="balanced", solver="liblinear", max_iter=2000,
                                 random_state=SEED)
    elif kind == "tfidf_mnb":
        clf = MultinomialNB(alpha=params["alpha"], fit_prior=params["fit_prior"])
    else:
        raise ValueError(f"unknown model kind {kind!r}")
    return Pipeline([("prep", TextPreprocessor(variant)), ("tfidf", TfidfVectorizer(**TFIDF_PARAMS)), ("clf", clf)])


def model_id(kind: str, variant: str) -> str:
    return f"{kind}__{variant}"


def phishing_scores(pipe: Pipeline, texts) -> np.ndarray:
    classes = list(pipe.classes_)
    return pipe.predict_proba(texts)[:, classes.index(1)]


def f1_threshold(y_true, scores) -> tuple[float, float]:
    """Threshold maximizing phishing F1 (first maximum). Returns (threshold, f1)."""
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros_like(precision),
                   where=(precision + recall) > 0)[:-1]
    best = int(np.argmax(f1))
    return float(thresholds[best]), float(f1[best])


def tune_on_dev(kind: str, variant: str, train_texts, y_train, dev_texts, y_dev) -> dict:
    """Fit each grid point on train only, score on dev, then freeze params and a dev-chosen threshold."""
    rows = []
    for params in PARAM_GRIDS[kind]:
        pipe = build_pipeline(kind, variant, params)
        t0 = time.perf_counter()
        pipe.fit(train_texts, y_train)
        fit_s = time.perf_counter() - t0
        scores = phishing_scores(pipe, dev_texts)
        rows.append({"params": params, "dev_average_precision": float(average_precision_score(y_dev, scores)),
                     "fit_seconds": round(fit_s, 3), "_scores": scores})
    best = max(rows, key=lambda r: r["dev_average_precision"])  # first maximum wins ties
    threshold, dev_f1 = f1_threshold(y_dev, best["_scores"])
    return {
        "model_id": model_id(kind, variant), "kind": kind, "variant": variant,
        "params": best["params"], "threshold": threshold, "dev_f1_at_threshold": dev_f1,
        "dev_average_precision": best["dev_average_precision"],
        "selection_metric": SELECTION_METRIC, "threshold_rule": THRESHOLD_RULE,
        "grid": [{k: v for k, v in r.items() if k != "_scores"} for r in rows],
    }


def evaluate(pipe: Pipeline, threshold: float, texts, y_true) -> dict:
    y_true = np.asarray(y_true, dtype=int)
    t0 = time.perf_counter()
    scores = phishing_scores(pipe, texts)
    infer_s = time.perf_counter() - t0
    y_pred = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "support": {"legitimate": int((y_true == 0).sum()), "phishing": int((y_true == 1).sum())},
        "phishing_share": round(float(y_true.mean()), 4),
        "threshold": threshold,
        "precision_phishing": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall_phishing": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1_phishing": float(f1_score(y_true, y_pred, zero_division=0)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "false_positive_rate": float(fp / (fp + tn)) if (fp + tn) else 0.0,
        "average_precision": float(average_precision_score(y_true, scores)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "inference_seconds": round(infer_s, 4),
        "inference_ms_per_email": round(1000 * infer_s / len(y_true), 4),
        "_scores": scores, "_y_pred": y_pred,
    }


# --------------------------------------------------------------------------- interpretability

# Fixed before any test evaluation, from the documented artifacts and the train/dev footer inspection.
ARTIFACT_TERMS = {
    "jose", "monkey", "org", "com", "net", "http", "https", "www", "listinfo", "mailman", "unsubscribe",
    "subscription", "sourceforge", "spamassassin", "sf", "ilug", "ie", "linux", "xent", "fork", "yahoo", "egroups",
    "mailing", "list", "lists", "maintainer", "sponsored", "thinkgeek", "supplied", "geek", "osdn", "perl",
    "exmh", "razor", "redhat",
}
_YEAR_TOKEN = re.compile(r"^(?:19[89]\d|20[0-2]\d)$")


def is_artifact_term(term: str) -> bool:
    return any(tok in ARTIFACT_TERMS or _YEAR_TOKEN.match(tok) for tok in term.split())


def top_terms(pipe: Pipeline, k: int = 25) -> dict:
    """Most influential logistic-regression n-grams (training-derived coefficients) in each direction."""
    clf = pipe.named_steps["clf"]
    if not isinstance(clf, LogisticRegression):
        raise TypeError("top_terms needs a logistic-regression pipeline")
    names = pipe.named_steps["tfidf"].get_feature_names_out()
    coef = clf.coef_[0] if list(clf.classes_) == [0, 1] else -clf.coef_[0]
    order = np.argsort(coef)
    out = {}
    for direction, idx in (("phishing", order[::-1][:k]), ("legitimate", order[:k])):
        terms = [{"term": str(names[i]), "coef": round(float(coef[i]), 4), "artifact": is_artifact_term(names[i])}
                 for i in idx]
        out[direction] = {"terms": terms, "artifact_share": sum(t["artifact"] for t in terms) / k}
    return out
