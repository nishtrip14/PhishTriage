"""Downloader, schema validation and split integrity.

Downloader cases are ported from the phase 1 scratch harness (which hit Zenodo live); here a fake HTTP session
makes them offline and deterministic.
"""
import hashlib
from pathlib import Path

import pandas as pd
import pytest
import requests

from phishtriage import data as D

REPO = Path(__file__).resolve().parents[1]
PAYLOAD = b"subject,body,label\nhello,world,1\n"
SPEC = {"file": "x.csv", "url": "https://example.invalid/x.csv", "size": len(PAYLOAD),
        "sha256": hashlib.sha256(PAYLOAD).hexdigest()}


class FakeResponse:
    def __init__(self, status=200, body=PAYLOAD, length=None):
        self.status_code, self.body = status, body
        self.headers = {"Content-Length": str(len(body) if length is None else length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def iter_content(self, n):
        yield self.body


class FakeSession:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0

    def get(self, url, **kwargs):
        assert kwargs.get("timeout"), "downloads must use a timeout"
        self.calls += 1
        return self.responses.pop(0)


def download(tmp_path, *responses, spec=SPEC):
    session = FakeSession(*responses)
    path, info = D.download_verified("x", spec, tmp_path, session=session, sleep=lambda s: None)
    return path, info, session


def test_download_verifies_and_reuses_cache(tmp_path):
    path, info, _ = download(tmp_path, FakeResponse())
    assert info["status"] == "downloaded_verified" and path.read_bytes() == PAYLOAD
    _, info, session = download(tmp_path)          # no responses queued: must not hit the network
    assert info["status"] == "reused_verified" and session.calls == 0


def test_corrupted_cache_is_replaced(tmp_path):
    (tmp_path / "x.csv").write_bytes(b"corrupted")
    path, info, _ = download(tmp_path, FakeResponse())
    assert info["status"] == "downloaded_verified" and D.sha256_of(path) == SPEC["sha256"]


def test_client_error_is_not_retried_and_leaves_no_partial_file(tmp_path):
    with pytest.raises(D.DownloadError, match=r"after 1 attempt"):
        download(tmp_path, FakeResponse(status=404))
    assert not list(tmp_path.iterdir())


def test_server_errors_are_retried_a_bounded_number_of_times(tmp_path):
    with pytest.raises(D.DownloadError, match=r"after 3 attempt"):
        download(tmp_path, *[FakeResponse(status=503) for _ in range(3)])


def test_size_and_checksum_mismatches_fail(tmp_path):
    with pytest.raises(D.DownloadError, match="expected"):
        download(tmp_path, *[FakeResponse(length=len(PAYLOAD) + 1) for _ in range(3)])
    tampered = PAYLOAD.replace(b"1", b"0")
    with pytest.raises(D.DownloadError, match="SHA-256"):
        download(tmp_path, *[FakeResponse(body=tampered) for _ in range(3)])
    with pytest.raises(D.DownloadError, match=r"limit\)"):
        download(tmp_path, *[FakeResponse(length=D.MAX_DOWNLOAD_BYTES + 1) for _ in range(3)])


def test_fallback_without_file_fails_clearly_and_mismatch_is_flagged(tmp_path):
    raw, manual = tmp_path / "raw", tmp_path / "manual"
    raw.mkdir(); manual.mkdir()
    kw = dict(session=FakeSession(FakeResponse(status=404), FakeResponse(status=404)), sleep=lambda s: None)
    with pytest.raises(D.DownloadError, match="Place x.csv"):
        D.acquire("x", SPEC, raw, manual, **kw)
    (manual / "x.csv").write_bytes(b"subject,body,label\nother,file,1\n")
    path, info = D.acquire("x", SPEC, raw, manual, **kw)
    assert info["status"] == "uploaded_CHECKSUM_MISMATCH" and path.parent == manual


@pytest.mark.parametrize("frame, message", [
    (pd.DataFrame({"subject": ["s"], "label": [1]}), "missing required columns"),
    (pd.DataFrame({"subject": ["s"], "body": ["b"], "label": [None]}), "no label"),
    (pd.DataFrame({"subject": ["s"], "body": ["b"], "label": [2]}), "unmapped"),
    (pd.DataFrame({"subject": [], "body": [], "label": []}), "no rows"),
])
def test_schema_validation_rejects_bad_files(tmp_path, frame, message):
    p = tmp_path / "bad.csv"
    frame.to_csv(p, index=False)
    with pytest.raises(ValueError, match=message):
        D.load_and_validate("nazario", p)


def synthetic_corpus(n=200):
    base = "please review the attached quarterly report and send comments before friday thanks"
    rows = []
    for i in range(n):
        label = int(i % 3 == 0)
        text = f"message number {i} " + " ".join(f"w{i}x{j}" for j in range(12))
        if i < 10:   # ten near-identical template variants share one group
            text = base + f" ref {i}"
        rows.append({"record_id": f"s:{i:05d}", "text": text, "label": label,
                     "mapped_label": "phishing" if label else "legitimate"})
    return pd.DataFrame(rows)


def test_near_duplicates_are_grouped_and_kept_in_one_split():
    df = synthetic_corpus()
    comp, pairs = D.near_duplicate_groups(df["text"].tolist())
    assert pairs > 0 and len(set(comp[:10])) == 1 and len(set(comp)) == len(df) - 9
    df["group_id"] = [f"g{c}" for c in comp]
    df["split"] = D.grouped_stratified_split(df, seed=7)
    assert df.loc[:9, "split"].nunique() == 1
    assert D.grouped_stratified_split(df, seed=7).equals(df["split"])


def test_check_partitions_detects_group_leakage():
    df = synthetic_corpus(400)
    df["group_id"] = [f"g{i}" for i in range(len(df))]
    df["split"] = D.grouped_stratified_split(df)
    D.check_partitions(df, min_per_class=5)
    leaked = df.copy()
    leaked.loc[1, "group_id"] = leaked.loc[0, "group_id"]
    leaked.loc[1, "split"] = "test" if leaked.loc[0, "split"] != "test" else "train"
    with pytest.raises(AssertionError, match="spans more than one split"):
        D.check_partitions(leaked, min_per_class=5)


def test_committed_split_manifest_integrity():
    m = pd.read_csv(REPO / "reports" / "split_manifest.csv", dtype=str)
    assert list(m.columns) == ["record_id", "group_id", "split", "mapped_label"]
    D.check_partitions(m)   # unique records, groups in one split, class coverage, shares
    assert set(m["mapped_label"]) == {"legitimate", "phishing"}
    assert m["record_id"].str.fullmatch(r"(nazario|spamassassin):\d{5}").all()
    assert not ({"text", "subject", "body", "sender"} & set(m.columns)), "manifest must stay text-free"
