"""Reusable inference over trusted, project-generated model artifacts.

Artifacts are joblib (pickle) files, and unpickling runs code. Load only artifacts this project generated:
load_artifact refuses a file whose SHA-256 does not match its manifest.
"""
from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn

from . import __version__
from .data import sha256_of
from .text import ARTIFACT_RULES_VERSION, MAX_INPUT_CHARS, PREPROCESSING_VERSION, combine, prepare

SCORE_TYPE = "model_estimated_probability_uncalibrated"
MODEL_FILE = "model.joblib"
MANIFEST_FILE = "manifest.json"
REQUIRED_MANIFEST_KEYS = {"model_id", "kind", "variant", "params", "threshold", "preprocessing_version",
                          "model_sha256", "versions", "dataset", "results"}
LIMITATIONS = [
    "Trained on a confounded benchmark: all phishing is from the Nazario corpus (2015-2022), all legitimate mail "
    "from SpamAssassin ham (~2002), so the model may rely on corpus style rather than phishing behaviour.",
    "Not validated on any external or unseen-source data; scores do not demonstrate real-world accuracy.",
    "The score is an uncalibrated model estimate, not a validated probability of phishing.",
    "Text only: headers, sender identity, link targets and attachments are not analysed.",
]
OUTPUT_KEYS = ("model_id", "predicted_label", "score", "score_type", "threshold", "warnings", "limitations",
               "input_chars", "truncated", "preprocessing_version")


class ArtifactError(RuntimeError):
    """A model artifact is missing, tampered with, or incompatible with this environment."""


def _minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


def environment_versions() -> dict:
    import pandas, scipy
    return {"python": platform.python_version(), "scikit-learn": sklearn.__version__, "numpy": np.__version__,
            "scipy": scipy.__version__, "pandas": pandas.__version__, "joblib": joblib.__version__,
            "phishtriage": __version__}


def save_artifact(pipe, frozen: dict, directory: Path, *, dataset: dict, results: dict, environment: str) -> Path:
    """Write model.joblib plus a manifest with versions, data checksums, config and actual results."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / MODEL_FILE
    joblib.dump(pipe, model_path)
    manifest = {
        "model_id": frozen["model_id"], "kind": frozen["kind"], "variant": frozen["variant"],
        "params": frozen["params"], "threshold": frozen["threshold"], "threshold_rule": frozen["threshold_rule"],
        "selection_metric": frozen["selection_metric"], "score_type": SCORE_TYPE,
        "preprocessing_version": PREPROCESSING_VERSION, "artifact_rules_version": ARTIFACT_RULES_VERSION,
        "max_input_chars": MAX_INPUT_CHARS, "trained_on": "train split only",
        "model_file": MODEL_FILE, "model_sha256": sha256_of(model_path),
        "versions": environment_versions(), "environment": environment, "dataset": dataset, "results": results,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (directory / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n")
    return directory


def load_artifact(directory: Path, *, allow_version_mismatch: bool = False):
    """Verify, then load. Returns (pipeline, manifest). Raises ArtifactError instead of guessing."""
    directory = Path(directory)
    manifest_path, model_path = directory / MANIFEST_FILE, directory / MODEL_FILE
    if not manifest_path.exists() or not model_path.exists():
        raise ArtifactError(f"No trained model at {directory}. Train it in the notebook (section 10) or point "
                            "to a directory containing manifest.json and model.joblib produced by this project.")
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        raise ArtifactError(f"Unreadable manifest {manifest_path}: {e}") from e
    missing = REQUIRED_MANIFEST_KEYS - set(manifest)
    if missing:
        raise ArtifactError(f"Manifest is missing keys {sorted(missing)}")
    if sha256_of(model_path) != manifest["model_sha256"]:
        raise ArtifactError("Model file SHA-256 does not match its manifest; refusing to unpickle it.")
    if manifest["preprocessing_version"] != PREPROCESSING_VERSION:
        raise ArtifactError(f"Artifact preprocessing v{manifest['preprocessing_version']} != installed "
                            f"v{PREPROCESSING_VERSION}; retrain the model.")
    trained = manifest["versions"].get("scikit-learn", "?")
    if _minor(trained) != _minor(sklearn.__version__) and not allow_version_mismatch:
        raise ArtifactError(f"Artifact was trained with scikit-learn {trained}, this environment has "
                            f"{sklearn.__version__}; retrain the model here.")
    return joblib.load(model_path), manifest


def predict(pipe, manifest: dict, *, subject: str | None = None, body: str | None = None,
            text: str | None = None) -> dict:
    """Score one email. Pass subject/body (combined like the training data) or a pre-combined text."""
    if pipe is None or not manifest:
        raise ArtifactError("predict() needs a loaded model and manifest; no score is produced without one.")
    warnings = []
    if text is None:
        if not (subject or "").strip():
            warnings.append("missing_subject")
        if not (body or "").strip():
            warnings.append("missing_body")
        text = combine(subject, body)
    prepared, info = prepare(text, manifest["variant"])
    if info["truncated"]:
        warnings.append(f"truncated: input has {info['input_chars']:,} characters; only the first "
                        f"{MAX_INPUT_CHARS:,} were scored (same policy as training)")
    result = {"model_id": manifest["model_id"], "predicted_label": None, "score": None, "score_type": SCORE_TYPE,
              "threshold": manifest["threshold"], "warnings": warnings, "limitations": list(LIMITATIONS),
              "input_chars": info["input_chars"], "truncated": info["truncated"],
              "preprocessing_version": PREPROCESSING_VERSION}
    if not text.strip():
        warnings.append("empty_input: no text to score; no prediction made")
        return result
    if not prepared.strip():
        warnings.append("empty_after_normalization: nothing left after artifact normalization; no prediction made")
        return result
    classes = list(pipe.classes_)
    score = float(pipe.predict_proba([text])[0, classes.index(1)])
    result["score"] = score
    result["predicted_label"] = "phishing" if score >= manifest["threshold"] else "legitimate"
    return result
