"""Local .env loading: python-dotenv, never overwrites, never returns values, skipped in Colab."""
import sys
import types

import pytest

from phishtriage import llm_preflight as LP

pytest.importorskip("dotenv")
if LP._in_colab():
    pytest.skip("local-only behaviour", allow_module_level=True)
FAKE = "fake-test-key-not-real-0123456789"


@pytest.fixture
def env_file(tmp_path):
    p = tmp_path / ".env"
    p.write_text(f"GEMINI_API_KEY={FAKE}\nOTHER_SECRET=ignored\n")
    return p


def test_loads_key_names_only(env_file, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OTHER_SECRET", raising=False)
    result = LP.load_local_env(env_file)
    assert result["status"] == "ok" and result["loaded"] == ["GEMINI_API_KEY"]
    assert FAKE not in repr(result)                                   # names only, never values
    assert LP.get_api_key() == FAKE
    import os
    assert "OTHER_SECRET" not in os.environ                           # only the allow-listed names are copied


def test_never_overwrites_existing(env_file, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "already-set")
    result = LP.load_local_env(env_file)
    assert result["kept_existing"] == ["GEMINI_API_KEY"] and result["loaded"] == []
    assert LP.get_api_key() == "already-set"


def test_missing_file(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert LP.load_local_env(tmp_path / "absent.env")["status"] == "no_env_file"
    assert LP.get_api_key() is None


def test_skipped_in_colab(env_file, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    google = types.ModuleType("google")
    colab = types.ModuleType("google.colab")
    monkeypatch.setitem(sys.modules, "google.colab", colab)
    monkeypatch.setattr(google, "colab", colab, raising=False)
    if "google" not in sys.modules:
        monkeypatch.setitem(sys.modules, "google", google)
    else:
        monkeypatch.setattr(sys.modules["google"], "colab", colab, raising=False)
    assert LP.load_local_env(env_file)["status"] == "skipped_colab"
    import os
    assert "GEMINI_API_KEY" not in os.environ


def test_not_loaded_implicitly(monkeypatch):
    """Importing the package or resolving the key never reads .env by itself."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert LP.get_api_key() is None
