import inspect

import pytest

from phishtriage import text as T


def test_combine_matches_training_format_and_handles_missing():
    assert T.combine(" Hi ", " there ") == "Hi\n\nthere"
    assert T.combine(None, "body") == "body"
    assert T.combine(float("nan"), None) == ""


def test_length_policy_truncates_and_flags():
    long = "a" * (T.MAX_INPUT_CHARS + 10)
    prepared, info = T.prepare(long, "original")
    assert len(prepared) == T.MAX_INPUT_CHARS and info["truncated"] and info["input_chars"] == len(long)
    _, info = T.prepare("short", "original")
    assert not info["truncated"]


def test_normalization_removes_documented_artifacts():
    text = ("[ILUG] Re: meeting\n\nDear jose@monkey.org, see http://www.linux.ie/x or visit example.com in 2002.\n"
            "_______________________________________________\n"
            "ILUG mailing list\nhttp://www.linux.ie/mailman/listinfo/ilug for (un)subscription information.\n"
            "Date: Not Supplied\nRegards, Jose from SpamAssassin")
    out = T.normalize_artifacts(text).lower()
    for gone in ("ilug", "monkey", "jose", "http", "example.com", "2002", "____", "listinfo", "not supplied",
                 "spamassassin", "@"):
        assert gone not in out, gone
    assert "meeting" in out and "regards" in out


def test_normalization_is_label_independent_and_idempotent():
    assert list(inspect.signature(T.normalize_artifacts).parameters) == ["text"]
    sample = "Re: [list] hello jose see www.x.com 2019\n-----\nbody text unsubscribe here"
    once = T.normalize_artifacts(sample)
    assert T.normalize_artifacts(once) == once


def test_preprocessor_step_matches_prepare():
    texts = ["Hello http://x.com 2002", "b" * (T.MAX_INPUT_CHARS + 5), ""]
    for variant in T.VARIANTS:
        step = T.TextPreprocessor(variant).fit(texts)
        assert step.transform(texts) == [T.prepare(t, variant)[0] for t in texts]
    with pytest.raises(ValueError):
        T.prepare("x", "unknown")


def test_sanitize_redacts_identifiers():
    s = T.sanitize('>>>>> "J" == Justin Mason writes: hi. From: Lyu F. Sent: Monday To: Bob Subject: x '
                   'mail a.b@example.com or http://evil.example/x 10.0.0.1 +1 (555) 123-4567. Jane Doe wrote: ok', 400)
    for leaked in ("Justin", "Mason", "Lyu", "Bob", "a.b@", "evil", "10.0.0.1", "555", "Jane"):
        assert leaked not in s, leaked
