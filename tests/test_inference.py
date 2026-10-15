"""Artifact handling and the predict() contract. Uses a tiny synthetic workflow corpus, not an accuracy test."""
import json

import numpy as np
import pytest

from phishtriage import inference as I, models as M, text as T

PHISH = ["verify your account password now or it will be suspended", "urgent: confirm billing details today",
         "your mailbox is full click to upgrade account", "security alert verify your login information"] * 5
LEGIT = ["minutes from the weekly team meeting attached", "the patch fixes the build on linux",
         "lunch on friday? let me know", "draft report comments are in the shared folder"] * 5
DATASET = {"file_sha256": {}, "split_manifest_sha256": "synthetic"}


@pytest.fixture(scope="module", params=T.VARIANTS)
def trained(request, tmp_path_factory):
    variant = request.param
    X, y = PHISH + LEGIT, np.array([1] * len(PHISH) + [0] * len(LEGIT))
    frozen = {"model_id": M.model_id("tfidf_logreg", variant), "kind": "tfidf_logreg", "variant": variant,
              "params": {"C": 1.0}, "threshold": 0.5, "threshold_rule": "test", "selection_metric": "test"}
    pipe = M.build_pipeline("tfidf_logreg", variant, frozen["params"])
    # min_df=2 needs repeated n-grams; the synthetic corpus repeats each sentence five times.
    pipe.fit(X, y)
    path = I.save_artifact(pipe, frozen, tmp_path_factory.mktemp(variant), dataset=DATASET,
                           results={"note": "synthetic workflow test"}, environment="test")
    return pipe, path


def test_round_trip_and_training_inference_consistency(trained):
    pipe, path = trained
    model, manifest = I.load_artifact(path)
    email = "Please verify your account password http://bad.example 2021"
    out = I.predict(model, manifest, text=email)
    assert out["score"] == pytest.approx(M.phishing_scores(pipe, [email])[0])
    assert out["score"] == pytest.approx(M.phishing_scores(model, [email])[0])
    # subject/body input is combined exactly like the training data
    via_parts = I.predict(model, manifest, subject="Security alert", body="verify your login")
    assert via_parts["score"] == pytest.approx(M.phishing_scores(pipe, ["Security alert\n\nverify your login"])[0])


def test_output_schema(trained):
    model, manifest = I.load_artifact(trained[1])
    out = I.predict(model, manifest, subject="Lunch", body="lunch on friday?")
    assert tuple(out) == I.OUTPUT_KEYS
    assert out["predicted_label"] in {"phishing", "legitimate"}
    assert 0.0 <= out["score"] <= 1.0 and out["score_type"] == I.SCORE_TYPE
    assert out["threshold"] == manifest["threshold"] and out["limitations"] == I.LIMITATIONS
    assert isinstance(out["warnings"], list) and out["truncated"] is False
    json.dumps(out)   # must be JSON-serialisable for later agent tools


def test_empty_input_abstains(trained):
    model, manifest = I.load_artifact(trained[1])
    out = I.predict(model, manifest, subject="", body="  ")
    assert out["predicted_label"] is None and out["score"] is None
    assert any(w.startswith("empty_input") for w in out["warnings"])
    assert "missing_subject" in out["warnings"] and "missing_body" in out["warnings"]


def test_oversized_input_is_truncated_with_warning(trained):
    model, manifest = I.load_artifact(trained[1])
    body = "verify your account " * 2000
    out = I.predict(model, manifest, body=body)
    assert out["truncated"] and out["input_chars"] > T.MAX_INPUT_CHARS
    assert any(w.startswith("truncated") for w in out["warnings"])
    assert out["score"] == pytest.approx(I.predict(model, manifest, text=body[:T.MAX_INPUT_CHARS])["score"])


def test_normalized_model_abstains_when_nothing_is_left(trained):
    model, manifest = I.load_artifact(trained[1])
    out = I.predict(model, manifest, text="http://example.com jose@monkey.org 2002")
    if manifest["variant"] == "artifact_normalized":
        assert out["score"] is None and any("empty_after_normalization" in w for w in out["warnings"])
    else:
        assert out["score"] is not None


def test_missing_artifact_raises(tmp_path):
    with pytest.raises(I.ArtifactError, match="No trained model"):
        I.load_artifact(tmp_path / "nothing-here")
    with pytest.raises(I.ArtifactError):
        I.predict(None, {}, text="hello")


def test_tampered_or_incompatible_artifacts_are_rejected(trained, tmp_path):
    import shutil
    path = tmp_path / "copy"
    shutil.copytree(trained[1], path)
    manifest = json.loads((path / I.MANIFEST_FILE).read_text())

    def write(**changes):
        (path / I.MANIFEST_FILE).write_text(json.dumps({**manifest, **changes}))

    write(model_sha256="0" * 64)
    with pytest.raises(I.ArtifactError, match="SHA-256"):
        I.load_artifact(path)
    write(preprocessing_version="0.0")
    with pytest.raises(I.ArtifactError, match="preprocessing"):
        I.load_artifact(path)
    write(versions={**manifest["versions"], "scikit-learn": "0.1.0"})
    with pytest.raises(I.ArtifactError, match="scikit-learn"):
        I.load_artifact(path)
    I.load_artifact(path, allow_version_mismatch=True)
    (path / I.MANIFEST_FILE).write_text("{not json")
    with pytest.raises(I.ArtifactError, match="Unreadable"):
        I.load_artifact(path)
    write()
    manifest_without = {k: v for k, v in manifest.items() if k != "threshold"}
    (path / I.MANIFEST_FILE).write_text(json.dumps(manifest_without))
    with pytest.raises(I.ArtifactError, match="missing keys"):
        I.load_artifact(path)


def test_threshold_selection_and_evaluation_shapes():
    y = np.array([0, 0, 0, 1, 1, 1])
    s = np.array([0.1, 0.2, 0.6, 0.55, 0.8, 0.9])
    thr, f1 = M.f1_threshold(y, s)
    assert 0.0 < f1 <= 1.0 and s.min() <= thr <= s.max()
    assert M.is_artifact_term("monkey org") and M.is_artifact_term("in 2002") and not M.is_artifact_term("verify account")
