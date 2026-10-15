"""Phase 1: verified acquisition, validation, normalization, auditing and grouped splitting.

Dataset: Zenodo 8339691 (Champa, CC-BY-4.0). See docs/DATASET_CARD.md for provenance and limitations.
"""
from __future__ import annotations

import hashlib
import re
import time
import zlib
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import requests
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

ZENODO_RECORD = "https://zenodo.org/records/8339691"
ZENODO_DOI = "10.5281/zenodo.8339691"
DATASET_LICENSE = "CC-BY-4.0"
CITATION = ("A. I. Champa, M. F. Rabbi, M. F. Zibran, 'Curated Datasets and Feature Analysis for Phishing Email "
            "Detection with Machine Learning', IEEE ICMI 2024.")

# Pinned from the Zenodo API and a verified download on 2026-10-15.
SOURCES = {
    "nazario": {
        "file": "Nazario.csv",
        "url": "https://zenodo.org/api/records/8339691/files/Nazario.csv/content",
        "size": 7_811_841,
        "md5": "4022d055bb7cf8602f30f768f652e91e",
        "sha256": "b8fbc4158fbdfaff1ed98584c43d72e283c6352d7ade4d457d34c1d79488d184",
    },
    "spamassassin": {
        "file": "SpamAssasin.csv",
        "url": "https://zenodo.org/api/records/8339691/files/SpamAssasin.csv/content",
        "size": 14_879_195,
        "md5": "d921e0b2333bfaa058bd38193e6b3fbd",
        "sha256": "3bfe8f8abff89f69a98456be50413c2fcb20a476141116dd84ee1507b980c00e",
    },
}
# (source, original label) -> mapped label; None means excluded, with the reason in EXCLUSION_REASON.
LABEL_MAP = {("nazario", 1): "phishing", ("spamassassin", 0): "legitimate", ("spamassassin", 1): None}
EXCLUSION_REASON = {("spamassassin", 1): "spam_not_phishing"}
LABELS = {"legitimate": 0, "phishing": 1}
REQUIRED_COLUMNS = {"subject", "body", "label"}
MAX_DOWNLOAD_BYTES = 50_000_000

SEED = 42
NEAR_DUP_JACCARD = 0.8
SHINGLE_WORDS = 5
SPLIT_FRACTIONS = {"train": 0.70, "dev": 0.15, "test": 0.15}
MIN_PER_CLASS_PER_SPLIT = 50
MODEL_INPUT_COLUMNS = ["text"]
NON_FEATURE_COLUMNS = {"record_id", "source", "original_label", "mapped_label", "label", "exclusion_reason",
                       "included", "group_id", "split", "year", "src_url_flag", "text_hash"}


class DownloadError(RuntimeError):
    pass


# --------------------------------------------------------------------------- acquisition

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_verified(name: str, spec: dict, raw_dir: Path, retries: int = 3, timeout=(10, 60),
                      session=requests, sleep: Callable[[float], None] = time.sleep) -> tuple[Path, dict]:
    """Reuse a checksum-verified file or download it with bounded retries, size limits and SHA-256 checks."""
    dest = Path(raw_dir) / spec["file"]
    if dest.exists():
        if sha256_of(dest) == spec["sha256"]:
            return dest, {"status": "reused_verified", "attempts": 0}
        print(f"{dest.name}: existing file failed the checksum; re-downloading.")
        dest.unlink()
    tmp = dest.with_name(dest.name + ".part")
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with session.get(spec["url"], stream=True, timeout=timeout,
                             headers={"Accept-Encoding": "identity"}) as r:
                r.raise_for_status()
                declared = int(r.headers.get("Content-Length", -1))
                if declared > MAX_DOWNLOAD_BYTES:
                    raise ValueError(f"server declares {declared:,} bytes (> {MAX_DOWNLOAD_BYTES:,} limit)")
                if declared not in (-1, spec["size"]):
                    raise ValueError(f"server declares {declared:,} bytes, expected {spec['size']:,}")
                h, n = hashlib.sha256(), 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        n += len(chunk)
                        if n > MAX_DOWNLOAD_BYTES:
                            raise ValueError("download exceeded the size limit")
                        f.write(chunk)
                        h.update(chunk)
            if n != spec["size"]:
                raise ValueError(f"received {n:,} bytes, expected {spec['size']:,}")
            if h.hexdigest() != spec["sha256"]:
                raise ValueError("SHA-256 mismatch")
            tmp.replace(dest)
            return dest, {"status": "downloaded_verified", "attempts": attempt}
        except (requests.RequestException, ValueError) as e:
            last_error = e
            tmp.unlink(missing_ok=True)
            print(f"{name}: attempt {attempt}/{retries} failed: {e}")
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                break  # client errors (e.g. 404) will not fix themselves
            if attempt < retries:
                sleep(2 ** attempt)
    raise DownloadError(f"{name}: download failed after {attempt} attempt(s): {last_error}")


def manual_file(spec: dict, manual_dir: Path) -> Path:
    """Default fallback: a file the user placed in manual_dir."""
    dest = Path(manual_dir) / spec["file"]
    if not dest.exists():
        raise DownloadError(f"Download failed. Place {spec['file']} from {ZENODO_RECORD} at {dest} and re-run.")
    return dest


def acquire(name: str, spec: dict, raw_dir: Path, manual_dir: Path,
            upload_fn: Callable[[dict, Path], Path] | None = None, allow_fallback: bool = True,
            **download_kwargs) -> tuple[Path, dict]:
    """Verified download, falling back to a user-supplied file whose checksum status is recorded, never hidden."""
    try:
        return download_verified(name, spec, raw_dir, **download_kwargs)
    except DownloadError as e:
        if not allow_fallback:
            raise
        print(f"DOWNLOAD FAILED, falling back to manual upload: {e}")
        path = (upload_fn or manual_file)(spec, Path(manual_dir))
        ok = sha256_of(path) == spec["sha256"]
        return path, {"status": "uploaded_verified" if ok else "uploaded_CHECKSUM_MISMATCH", "attempts": None}


def load_and_validate(name: str, path: Path, label_map: dict = LABEL_MAP) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"{name}: missing required columns {sorted(missing)}; found {list(df.columns)}")
    if len(df) == 0:
        raise ValueError(f"{name}: file has no rows")
    if df["label"].isna().any():
        raise ValueError(f"{name}: {int(df['label'].isna().sum())} rows have no label")
    unknown = {(name, int(v)) for v in df["label"].unique()} - set(label_map)
    if unknown:
        raise ValueError(f"{name}: unmapped (source, label) values {sorted(unknown)}")
    return df


# --------------------------------------------------------------------------- normalization & audit

def is_missing(s: pd.Series) -> pd.Series:
    return s.isna() | s.fillna("").astype(str).str.strip().eq("")


def combine_subject_body(subject: pd.Series, body: pd.Series) -> pd.Series:
    return (subject.str.strip() + "\n\n" + body.str.strip()).str.strip()


def normalize_sources(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One documented dataframe; missing headers are flagged, never invented."""
    frames = []
    for name, df in raw.items():
        d = pd.DataFrame({
            "record_id": [f"{name}:{i:05d}" for i in range(len(df))],
            "source": name,
            "subject": df["subject"].fillna("").astype(str),
            "body": df["body"].fillna("").astype(str),
            "original_label": df["label"].astype(int),
        })
        for col in ("sender", "receiver", "date", "subject", "body"):
            d[f"missing_{col}"] = is_missing(df[col]) if col in df else True
        d["src_url_flag"] = df["urls"].astype("Int64") if "urls" in df else pd.NA
        d["year"] = (pd.to_datetime(df["date"], errors="coerce", utc=True, format="mixed").dt.year.astype("Int64")
                     if "date" in df else pd.NA)
        frames.append(d)
    data = pd.concat(frames, ignore_index=True)
    data["text"] = combine_subject_body(data["subject"], data["body"])
    keys = list(zip(data["source"], data["original_label"]))
    data["mapped_label"] = [LABEL_MAP[k] for k in keys]
    data["exclusion_reason"] = [EXCLUSION_REASON.get(k, "") for k in keys]
    data.loc[data["exclusion_reason"].eq("") & data["text"].eq(""), "exclusion_reason"] = "empty_text"
    assert data["record_id"].is_unique
    return data


def normalize_for_dup(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower()).strip()


def audit_and_exclude(data: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Duplicate/conflict audit; excludes conflicting labels and extra exact copies. Returns (data, audit)."""
    data = data.copy()
    data["text_hash"] = [hashlib.sha1(normalize_for_dup(t).encode("utf-8")).hexdigest() for t in data["text"]]

    audit = {"rows_loaded": int(len(data)), "rows_per_source": data["source"].value_counts().sort_index().to_dict()}
    audit["original_label_by_source"] = {
        s: {str(k): int(v) for k, v in g.value_counts().sort_index().items()}
        for s, g in data.groupby("source")["original_label"]}
    audit["missing_fields_by_source"] = {
        s: {c.removeprefix("missing_"): int(g[c].sum()) for c in data.columns if c.startswith("missing_")}
        for s, g in data.groupby("source")}
    audit["empty_combined_text"] = int(data["text"].eq("").sum())

    dup_all = data.duplicated("text_hash", keep=False)
    audit["exact_duplicates_all_rows"] = {
        "rows_in_duplicate_groups": int(dup_all.sum()),
        "duplicate_groups": int(data.loc[dup_all, "text_hash"].nunique()),
        "redundant_copies": int(data.duplicated("text_hash").sum())}

    # Identical text with more than one (source, original label) pair is ambiguous: all copies are excluded.
    src_label = data["source"] + ":" + data["original_label"].astype(str)
    conflict_hashes = set(src_label.groupby(data["text_hash"]).nunique().loc[lambda s: s > 1].index)
    audit["conflicting_duplicate_groups_all_rows"] = len(conflict_hashes)

    cand = data["exclusion_reason"].eq("")
    data.loc[cand & data["text_hash"].isin(conflict_hashes), "exclusion_reason"] = "conflicting_duplicate_labels"
    cand = data["exclusion_reason"].eq("")
    extra = data[cand].sort_values("record_id").duplicated("text_hash").reindex(data.index, fill_value=False)
    data.loc[extra, "exclusion_reason"] = "exact_duplicate_extra_copy"

    data["included"] = data["exclusion_reason"].eq("")
    data["label"] = data["mapped_label"].map(LABELS).where(data["included"]).astype("Int64")
    audit["exclusions"] = data.loc[~data["included"], "exclusion_reason"].value_counts().to_dict()
    audit["included_by_class"] = data.loc[data["included"], "mapped_label"].value_counts().to_dict()
    audit["source_by_class_included"] = pd.crosstab(
        data.loc[data["included"], "source"], data.loc[data["included"], "mapped_label"]).to_dict()
    return data, audit


# --------------------------------------------------------------------------- grouping & splitting

def shingle_ids(t: str, words: int = SHINGLE_WORDS) -> set[int]:
    toks = re.findall(r"[a-z0-9]+", t.lower())
    if len(toks) < words:
        return {zlib.crc32(" ".join(toks).encode())}
    return {zlib.crc32(" ".join(toks[i:i + words]).encode()) for i in range(len(toks) - words + 1)}


def near_duplicate_groups(texts: list[str], threshold: float = NEAR_DUP_JACCARD,
                          block: int = 500) -> tuple[np.ndarray, int]:
    """Connected components of pairs with exact shingle-set Jaccard >= threshold. Returns (component ids, pairs)."""
    sets = [shingle_ids(t) for t in texts]
    vocab = {h: j for j, h in enumerate(sorted(set().union(*sets)))}
    indptr = np.cumsum([0] + [len(s) for s in sets])
    indices = np.fromiter((vocab[h] for s in sets for h in sorted(s)), dtype=np.int64, count=indptr[-1])
    X = csr_matrix((np.ones(len(indices), dtype=np.int32), indices, indptr), shape=(len(sets), len(vocab)))
    sizes = np.asarray(X.sum(axis=1)).ravel()
    rows, cols = [np.empty(0, dtype=np.int64)], [np.empty(0, dtype=np.int64)]
    for start in range(0, X.shape[0], block):
        inter = (X[start:start + block] @ X.T).tocoo()
        i, j, v = inter.row + start, inter.col, inter.data
        keep = i < j
        i, j, v = i[keep], j[keep], v[keep]
        jac = v / (sizes[i] + sizes[j] - v)
        hit = jac >= threshold
        rows.append(i[hit]); cols.append(j[hit])
    rows, cols = np.concatenate(rows), np.concatenate(cols)
    graph = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(sets), len(sets)))
    _, comp = connected_components(graph, directed=False)
    return comp, len(rows)


def grouped_stratified_split(df: pd.DataFrame, fractions: dict = SPLIT_FRACTIONS, seed: int = SEED) -> pd.Series:
    """Assign whole groups to splits, stratified by group majority label, with a seeded shuffle."""
    rng = np.random.default_rng(seed)
    groups = df.groupby("group_id").agg(n=("record_id", "size"), y=("label", lambda s: int(s.mean() >= 0.5)))
    names = list(fractions)
    edges = np.cumsum([fractions[k] for k in names])
    assignment = {}
    for _, g in groups.groupby("y"):
        order = np.array(sorted(g.index))
        rng.shuffle(order)
        cum = np.cumsum(g.loc[order, "n"].to_numpy()) / g["n"].sum()
        idx = np.minimum(np.searchsorted(edges, cum, side="left"), len(names) - 1)
        assignment.update(zip(order, (names[i] for i in idx)))
    return df["group_id"].map(assignment)


def check_partitions(df: pd.DataFrame, fractions: dict = SPLIT_FRACTIONS,
                     min_per_class: int = MIN_PER_CLASS_PER_SPLIT, tolerance: float = 0.03) -> pd.DataFrame:
    """Raise AssertionError on any leakage/coverage problem; return the split x class table.

    Needs columns record_id, group_id, split, mapped_label; text_hash is checked when present."""
    assert df["split"].notna().all(), "every record must be assigned"
    assert set(df["split"]) <= set(fractions), f"unknown split names {set(df['split']) - set(fractions)}"
    assert df["record_id"].is_unique, "record overlap"
    assert (df.groupby("group_id")["split"].nunique() == 1).all(), "a duplicate group spans more than one split"
    if "text_hash" in df:
        assert df.groupby("text_hash")["split"].nunique().max() == 1, "identical text in more than one split"
    per_class = pd.crosstab(df["split"], df["mapped_label"]).reindex(list(fractions), fill_value=0)
    assert (per_class >= min_per_class).all().all(), f"class coverage too low:\n{per_class}"
    shares = df["split"].value_counts(normalize=True)
    for s, f in fractions.items():
        assert abs(shares.get(s, 0) - f) < tolerance, f"{s} share {shares.get(s, 0):.3f} is far from {f}"
    assert not set(MODEL_INPUT_COLUMNS) & NON_FEATURE_COLUMNS, "source/label/ID columns must not be model inputs"
    return per_class
